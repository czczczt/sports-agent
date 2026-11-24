"""Persist validated source protocols inside the caller transaction."""

import re

from app.pipeline.duplicates import reconcile_duplicates
from app.pipeline.errors import PilotRejected
from app.pipeline.operator_issues import check_elevation, record_issue
from parser_running import store
from parser_running.normalize import is_sber_club


def norm_name(name):
    """Same identity key as init_athletes, without importing the CLI module."""
    return " ".join(sorted(re.findall(r"[a-zа-я0-9]+", (name or "").lower().replace("ё", "е"))))


def _link_athlete(con, result_id, row, event_year):
    if con.execute("SELECT 1 FROM result_athlete WHERE result_id=%s", (result_id,)).fetchone():
        return
    name = row.get("full_name_raw")
    if not name or row.get("gender") not in {"M", "F"}:
        return
    year = row.get("birth_year")
    if year is None and row.get("age") is not None:
        year = event_year - row["age"]
    key = norm_name(name)
    # Year and gender are required to attach to an existing identity. Ambiguous
    # candidates need human review; never overwrite a manually established link.
    matches = con.execute("""SELECT id FROM athlete WHERE name_key=%s AND gender=%s
                             AND birth_year=%s""", (key, row.get("gender"), year)).fetchall() if year else []
    if len(matches) > 1:
        return
    if matches:
        athlete_id = matches[0][0]
    elif is_sber_club(row.get("club_raw")):
        athlete_id = con.execute("""INSERT INTO athlete(display_name,name_key,gender,birth_year,city,region,club,employee_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'presumed') RETURNING id""",
            (name, key, row.get("gender"), year, row.get("city"), row.get("region"), row.get("club_raw"))).fetchone()[0]
    else:
        return
    con.execute("INSERT INTO result_athlete(result_id,athlete_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (result_id, athlete_id))


def save_event(
    connection, source_id: int, event: dict, *, selected_race_ids: set[str] | None = None,
    defer_event_update: bool = False, reconcile: bool = True,
) -> int:
    """Upsert verified rows preserving result IDs and links; never commit or close."""
    con = connection
    comp = event["competition"]
    existing_competition = None
    if defer_event_update:
        existing_competition = con.execute(
            "SELECT id FROM competition WHERE source_id=%s AND external_id=%s",
            (source_id, str(comp["external_id"])),
        ).fetchone()
    if existing_competition:
        competition_id = existing_competition[0]
    else:
        competition_id = store.save_competition(con, source_id, comp)
        con.execute(
            """UPDATE competition SET primary_protocol_url = %s,
                      sport_type = %s, sport = COALESCE(%s, sport) WHERE id = %s""",
            (comp.get("canonical_url"), comp.get("sport"), comp.get("sport"), competition_id),
        )
    prior_races = {row[0] for row in con.execute(
        """SELECT external_id FROM race WHERE competition_id=%s AND superseded_by_race_id IS NULL
           AND (race_type='individual' OR sport_type IS NOT NULL)
           AND (is_final_protocol=TRUE OR (source_url IS NOT NULL AND is_final_protocol IS NULL))""",
        (competition_id,)).fetchall()}
    incoming_races = {str(item["race"]["external_id"]) for item in event["races"]}
    if prior_races - incoming_races:
        raise PilotRejected("Source event dropped previously stored final distances")
    races = [
        item for item in event["races"]
        if selected_race_ids is None or str(item["race"]["external_id"]) in selected_race_ids
    ]
    for item in races:
        race, rows = item["race"], item["rows"]
        race_id = store.save_race(con, competition_id, race)
        effective_elevation = con.execute(
            """UPDATE race SET sport_type=%s, sport=%s, source_url=%s,
                      elevation_gain_m=COALESCE(%s, elevation_gain_m), season=%s, series=%s,
                      source_discipline=%s, is_final_protocol=%s, source_distance_class=%s
               WHERE id=%s RETURNING elevation_gain_m""",
            (race["sport"], race["sport"], race.get("url"), race.get("elevation_gain_m"),
             race.get("season"), race.get("series"), race.get("source_discipline"),
             race.get("is_final"), race.get("distance_class"), race_id),
        ).fetchone()[0]
        check_elevation(con, source_id, competition_id, race, effective_elevation)
        clubs = store.club_ids(con, {r["club_raw"] for r in rows if r.get("club_raw")})
        existing = con.execute("SELECT id,external_participant_id,bib,full_name_raw,gender,is_anonymized FROM result WHERE race_id=%s FOR UPDATE", (race_id,)).fetchall()
        by_pid, legacy = {}, {}
        for result in existing:
            if result[1]:
                by_pid.setdefault(result[1], []).append(result)
            else:
                legacy.setdefault((str(result[2]), norm_name(result[3]), result[4]), []).append(result)
        incoming = {str(row["external_participant_id"]) for row in rows}
        if set(by_pid) - incoming:
            raise PilotRejected("Source protocol dropped previously stored participants")
        matched_existing = set()
        for row in rows:
            pid = str(row["external_participant_id"])
            matches = by_pid.get(pid, [])
            if not matches:
                matches = legacy.pop((str(row.get("bib")), norm_name(row.get("full_name_raw")), row.get("gender")), [])
            if len(matches) > 1:
                raise PilotRejected("Ambiguous existing result")
            values = [row.get(k) for k in store.RESULT_FIELDS]
            values[0] = pid
            values[1] = str(values[1]) if values[1] is not None else None
            columns = ("club_id", *store.RESULT_COLUMNS, "source_profile_id", "position_age_group",
                       "official_time_s", "toplist_points")
            params = [clubs.get(row.get("club_raw")), *values, row.get("source_profile_id"),
                      row.get("place_age_group"), row.get("official_time_s"), row.get("toplist_points")]
            if matches:
                prior = matches[0]
                if prior[5]:
                    redacted = {"full_name_raw": "Участник", "bib": None, "club_id": None,
                                "club_raw": None, "city": None, "country": None, "region": None,
                                "club_source": None, "source_profile_id": None}
                    params = [redacted.get(column, value) for column, value in zip(columns, params)]
                result_id = prior[0]
                matched_existing.add(result_id)
                con.execute(f"UPDATE result SET {','.join(c+'=%s' for c in columns)} WHERE id=%s", (*params, result_id))
            else:
                result_id = con.execute(f"INSERT INTO result(race_id,{','.join(columns)}) VALUES ({','.join(['%s']*(len(columns)+1))}) RETURNING id", (race_id, *params)).fetchone()[0]
            if race["race_type"] == "individual" and (not matches or not matches[0][5]):
                _link_athlete(con, result_id, row, int(comp["date_begin"][:4]))
        if {row[0] for row in existing} - matched_existing:
            raise PilotRejected("Source protocol cannot reconcile previously stored legacy participants")
    for issue in event.get("review_items", []):
        record_issue(con, source_id, competition_id, issue["kind"], issue["external_ref"])
    if reconcile:
        reconcile_duplicates(con, competition_id)
    return len(races)

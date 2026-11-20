"""RussiaRunning persistence. Uses the caller transaction without committing."""

import re

from parser_running import store
from parser_running.normalize import is_sber_club
from app.pipeline.errors import PilotRejected


def norm_name(name):
    """Same identity key as init_athletes, without importing the CLI module."""
    return " ".join(sorted(re.findall(r"[a-zа-я0-9]+", (name or "").lower().replace("ё", "е"))))


def _link_athlete(con, result_id, row, event_year):
    if con.execute("SELECT 1 FROM result_athlete WHERE result_id=%s", (result_id,)).fetchone():
        return
    name = row.get("full_name_raw")
    if not name:
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


def save_event(connection, event) -> int:
    """Upsert verified rows preserving result IDs and links; never commit or close."""
    con = connection
    comp = event["competition"]
    src = con.execute("SELECT id FROM source WHERE name='russiarunning'").fetchone()
    if not src:
        raise PilotRejected("RussiaRunning source is not registered")
    competition_id = store.save_competition(con, src[0], comp)
    prior_races = {row[0] for row in con.execute(
        "SELECT external_id FROM race WHERE competition_id=%s AND race_type='individual' AND is_final_protocol=TRUE",
        (competition_id,)).fetchall()}
    incoming_races = {str(item['race']['external_id']) for item in event['races']}
    if prior_races - incoming_races:
        raise PilotRejected("RussiaRunning event dropped previously stored final distances")
    for item in event["races"]:
        race, rows = item["race"], item["rows"]
        race_id = store.save_race(con, competition_id, race)
        clubs = store.club_ids(con, {r["club_raw"] for r in rows if r.get("club_raw")})
        existing = con.execute("SELECT id,external_participant_id,bib,full_name_raw,gender FROM result WHERE race_id=%s FOR UPDATE", (race_id,)).fetchall()
        by_pid, legacy = {}, {}
        for result in existing:
            if result[1]:
                by_pid.setdefault(result[1], []).append(result)
            else:
                legacy.setdefault((str(result[2]), norm_name(result[3]), result[4]), []).append(result)
        incoming = {str(row["external_participant_id"]) for row in rows}
        if set(by_pid) - incoming:
            raise PilotRejected("RussiaRunning protocol dropped previously stored participants")
        matched_existing = set()
        for row in rows:
            pid = str(row["external_participant_id"])
            matches = by_pid.get(pid, [])
            if not matches:
                matches = legacy.pop((str(row.get("bib")), norm_name(row.get("full_name_raw")), row.get("gender")), [])
            if len(matches) > 1:
                raise PilotRejected("Ambiguous existing RussiaRunning result")
            values = [row.get(k) for k in store.RESULT_FIELDS]
            values[0] = pid
            values[1] = str(values[1]) if values[1] is not None else None
            columns = ("club_id", *store.RESULT_COLUMNS)
            params = [clubs.get(row.get("club_raw")), *values]
            if matches:
                result_id = matches[0][0]
                matched_existing.add(result_id)
                con.execute(f"UPDATE result SET {','.join(c+'=%s' for c in columns)} WHERE id=%s", (*params, result_id))
            else:
                result_id = con.execute(f"INSERT INTO result(race_id,{','.join(columns)}) VALUES ({','.join(['%s']*(len(columns)+1))}) RETURNING id", (race_id, *params)).fetchone()[0]
            _link_athlete(con, result_id, row, int(comp["date_begin"][:4]))
        if {row[0] for row in existing} - matched_existing:
            raise PilotRejected("RussiaRunning protocol cannot reconcile previously stored legacy participants")
    return len(event["races"])

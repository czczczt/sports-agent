"""Collect final IRONSTAR triathlon protocols published by RussiaRunning Timing."""

import math
import re
from datetime import date

from app.pipeline.errors import PilotRejected
from parser_running.normalize import GENDER_RR, STATUS_RR, to_seconds
from parser_running.rr_platform import PAGE, RRClient


def _position(value):
    return value if type(value) is int and value > 0 else None


def _distance(raw_race, options):
    reported = raw_race.get("distance")
    if type(reported) in (int, float) and math.isfinite(reported) and reported > 0:
        return reported

    # Timing points report distance from the start of each leg.
    distances = {}
    for stage in options.get("stagesInfo", []):
        discipline = stage.get("disciplineCode")
        if discipline not in {"swimming", "cycling", "running"}:
            continue
        if discipline in distances:
            return None
        points = [stage.get("distance"), *(p.get("distance") for p in stage.get("stagesInfo", []))]
        distances[discipline] = max((d for d in points if type(d) in (int, float)
                                     and math.isfinite(d) and d > 0), default=0)
    if len(distances) == 3 and all(distances.values()):
        return round(sum(distances.values()), 3)
    return None


def _relay_results(client, event_id, race_id):
    rows = []
    total = None
    for skip in range(0, 10000, PAGE):
        data = client._call("POST", "/results/relay/get", {
            "eventId": event_id, "raceId": race_id, "page": {"skip": skip, "take": PAGE},
            "filter": {}, "isStagesOn": False, "language": "ru",
        })
        claimed, batch = data["totalCount"], data["results"]
        if (type(claimed) is not int or not 0 < claimed <= 10000
                or (total is not None and claimed != total)
                or not isinstance(batch, list) or len(batch) != min(PAGE, claimed - skip)):
            raise PilotRejected("Incomplete IRONSTAR relay protocol")
        total = claimed
        rows.extend(batch)
        if len(rows) == total:
            return rows, total
    raise PilotRejected("Oversized IRONSTAR relay protocol")


def _row(raw, relay, place_by):
    status = STATUS_RR.get(raw.get("status"))
    finishing = status == "FIN"
    group = raw.get("genderAgeNominationName") or None
    chip = to_seconds(raw.get("individualResult"))
    gun = to_seconds(raw.get("absoluteResult"))
    time = chip if place_by == "chip" else gun
    participant = raw.get("teamId" if relay else "participantId")
    name = raw.get("teamName" if relay else "fullName")
    gender = {"Relay.Male": "M", "Relay.Female": "F"}.get(group) if relay else GENDER_RR.get(raw.get("gender"))
    rank_basis = "individual" if place_by == "chip" else "absolute"
    group_rank = raw.get("genderAgeNominationPosition" if relay else f"{rank_basis}GenderAgePosition")
    if (not isinstance(participant, str) or not participant or not isinstance(name, str) or not name.strip()
            or (not relay and gender is None) or status is None
            or (finishing and (time is None or not math.isfinite(time) or time <= 0))):
        raise PilotRejected("Invalid IRONSTAR result")
    club = (raw.get("raceClub") or "").strip() or None
    return {
        "external_participant_id": participant, "source_profile_id": None if relay else raw.get("profileId"),
        "full_name_raw": name, "gender": gender,
        "bib": None if relay else raw.get("number"), "age": None if relay else raw.get("age"),
        "birth_year": None if relay else raw.get("birthYear"),
        "country": raw.get("countryCode"), "region": raw.get("region"), "city": raw.get("city"),
        "club_raw": club, "club_source": "protocol" if club else None, "status": status,
        "place_abs": _position(raw.get("position")) if finishing else None,
        "place_gender": _position(raw.get(f"{rank_basis}GenderPosition")) if finishing and not relay else None,
        "age_group": group,
        "place_age_group": _position(group_rank) if finishing and group else None,
        "chip_time_s": chip, "gun_time_s": gun,
    }


def fetch_event(event_code: str) -> dict:
    """Collect triathlon and relay races with independently marked final protocols."""
    if not isinstance(event_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_code):
        raise PilotRejected("Invalid IRONSTAR event code")

    client = RRClient("russiarunning", cache=False)
    client.s.max_redirects = 0
    try:
        event = client.get_event(event_code)
        title = event.get("title", "")
        if (not event.get("id") or event.get("disciplineCode") != "triathlon"
                or not re.search(r"(?<![A-Za-z0-9])IRONSTAR(?![A-Za-z0-9])", title, re.I)):
            raise PilotRejected("RussiaRunning event is not an IRONSTAR triathlon")
        date.fromisoformat(event["beginDate"][:10])
        comp = {"external_id": event["id"], "code": event["code"], "title": title,
                "date_begin": event["beginDate"], "date_end": event.get("endDate"),
                "place": event.get("place"), "sport": "triathlon",
                "url": f"https://results.russiarunning.com/event/{event_code}/results"}
        races = []
        seen = set()
        for raw_race in event["races"]:
            discipline = raw_race.get("disciplineCode")
            if discipline not in {"triathlon", "triathlon-relay"}:
                continue
            race_id = raw_race["id"]
            relay = raw_race["isRelay"]
            if not race_id or race_id in seen or relay is not (discipline == "triathlon-relay"):
                raise PilotRejected("Invalid or duplicate IRONSTAR race")
            seen.add(race_id)
            options = client.race_options(race_id)
            if options.get("isFinalProtocol") is not True:
                continue
            place_by = "gun" if raw_race.get("resultsCalculationMethod") == 1 else "chip"
            raw_rows, count = (_relay_results(client, event["id"], race_id) if relay
                               else client.individual_results(event["id"], race_id))
            rows = [_row(row, relay, place_by) for row in raw_rows]
            if not rows or count != len(rows) or len({row["external_participant_id"] for row in rows}) != count:
                raise PilotRejected("Incomplete or duplicate IRONSTAR results")
            race = {"external_id": race_id, "name_raw": raw_race.get("name"), "sport": "triathlon",
                    "race_type": "relay" if relay else "individual", "place_by": place_by,
                    "distance_km": _distance(raw_race, options), "timing_type": raw_race.get("timingType"),
                    "is_final": True, "total_count": count, "source_discipline": discipline,
                    "url": f"{comp['url']}/{raw_race['code']}" if raw_race.get("code") else comp["url"]}
            races.append({"race": race, "rows": rows})
        if not races:
            raise PilotRejected("No final IRONSTAR triathlon protocols")
        return {"competition": comp, "races": races}
    except PilotRejected:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise PilotRejected("Invalid or incomplete IRONSTAR response") from exc
    finally:
        client.s.close()

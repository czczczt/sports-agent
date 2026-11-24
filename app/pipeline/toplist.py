"""Read trail protocols through the public TopList website API."""

import math
import re
from datetime import date
from time import monotonic, sleep

import requests

from app.pipeline.errors import PilotRejected
from parser_running.normalize import to_seconds
from parser_running.request_pacing import pace_request

BASE = "https://toplist.run"
PAGE_SIZE = 50
STATUSES = {"DNS", "DNF", "DSQ", "NC", "LAP"}


def _protocol(get, event_id, distance_id, total):
    rows = []
    path = f"/competition/{event_id}/{distance_id}"
    for offset in range(0, total, PAGE_SIZE):
        page = get(path, {"from": offset, "length": PAGE_SIZE, "sort": "position"})
        records = page["competition"]
        if (page["from"] != offset or page["length"] != PAGE_SIZE or page["total"] != total
                or not isinstance(records, list) or len(records) != min(PAGE_SIZE, total - offset)):
            raise PilotRejected("Incomplete or changing TopList pagination")
        for raw in records:
            if raw["raceId"] != event_id or raw["raceDistanceId"] != distance_id:
                raise PilotRejected("TopList result belongs to another protocol")
            rows.append(_row(raw))
    if len({row["external_participant_id"] for row in rows}) != total:
        raise PilotRejected("Duplicate TopList result ID")
    return rows


def _row(raw):
    result_id = raw["id"]
    if type(result_id) is not int or result_id <= 0:
        raise PilotRejected("Missing TopList result ID")
    status = raw["resultStatus"]["name"].upper()
    if status == "-":
        seconds = to_seconds(raw["raceResult"])
        if raw["resultType"] != "time" or not seconds or not math.isfinite(seconds):
            raise PilotRejected("TopList result has neither a finish time nor a published status")
        status = "FIN"
    elif status in STATUSES:
        seconds = None
    else:
        raise PilotRejected("Unknown TopList result status")
    points = raw.get("rating")
    if points is not None and (type(points) not in (float, int) or not math.isfinite(points) or points < 0):
        raise PilotRejected("Invalid TopList points")
    athlete = raw["athlete"]
    city = athlete.get("city") or {}
    age = raw.get("ageGroup") or {}
    minimum, maximum = age.get("min"), age.get("max")
    age_group = f"{minimum}-{maximum}" if minimum is not None and maximum is not None else None
    team = raw.get("team") or {}
    if team.get("id"):
        raise PilotRejected("TopList team protocols require a team import")
    return {
        "external_participant_id": str(result_id),
        "bib": raw.get("raceNumber"),
        "full_name_raw": " ".join(athlete[key] for key in ("surname", "name", "secondName") if athlete.get(key)) or None,
        "gender": {1: "M", 2: "F"}.get((athlete.get("gender") or {}).get("id")),
        "birth_year": athlete.get("birthYear") or None,
        "city": city.get("name"),
        "region": (city.get("region") or {}).get("name"),
        "country": (city.get("country") or {}).get("name"),
        "club_raw": (raw.get("club") or {}).get("name"),
        "status": status,
        "age_group": age_group,
        "place_abs": raw.get("position") if status == "FIN" else None,
        "place_age_group": raw.get("groupPlace") if status == "FIN" and age_group else None,
        "official_time_s": seconds,
        "toplist_points": points,
    }


def fetch_event(event_code: str) -> dict:
    if not isinstance(event_code, str) or not re.fullmatch(r"[1-9][0-9]{0,17}", event_code):
        raise PilotRejected("Invalid TopList event ID")
    event_id = int(event_code)
    event_url = f"{BASE}/race/{event_id}"
    deadline = monotonic() + 150
    with requests.Session() as session:
        def get(path, params=None):
            pace_request(BASE, sleep=sleep)
            if monotonic() >= deadline:
                raise requests.Timeout("TopList collection timed out")
            response = session.get(f"{BASE}/api{path}", params=params, timeout=(5, 15), allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200:
                raise PilotRejected("Unexpected TopList response")
            return response.json()

        try:
            raw = get(f"/race/{event_id}")
            if raw["id"] != event_id or raw["kindOfSport"]["id"] != 10 or not raw["name"]:
                raise PilotRejected("Entry is not a TopList trail event")
            begin_date = date.fromisoformat(raw["beginDate"])
            if begin_date > date.today():
                raise PilotRejected("TopList event has not started")
            competition = {
                "external_id": event_code, "code": event_code, "title": raw["name"],
                "date_begin": begin_date.isoformat(), "date_end": raw.get("endDate"),
                "place": (raw.get("city") or {}).get("name"), "address": raw.get("venue"),
                "sport": "trail", "url": event_url,
            }
            races, seen = [], set()
            for raw_distance in raw["distances"]:
                distance_id, count = raw_distance["id"], raw_distance["resultsCount"]
                if (type(distance_id) is not int or distance_id <= 0 or distance_id in seen
                        or type(count) is not int or count < 0):
                    raise PilotRejected("Invalid or duplicate TopList distance")
                seen.add(distance_id)
                if count == 0:
                    continue
                length, climb = raw_distance["length"], raw_distance.get("climb")
                if type(length) not in (float, int) or not math.isfinite(length) or length <= 0:
                    raise PilotRejected("Invalid TopList distance length")
                if climb is not None and (type(climb) is not int or climb < 0):
                    raise PilotRejected("Invalid TopList elevation gain")
                # The public UI omits D+ for a null or zero climb value.
                name = f"{length:g} km" + (f" / +{climb} m" if climb else "")
                race = {
                    "external_id": str(distance_id), "name_raw": name,
                    "distance_km": length, "elevation_gain_m": climb or None,
                    "sport": "trail", "race_type": "individual", "place_by": "official",
                    "is_final": None, "total_count": count, "url": f"{event_url}/protocol/{distance_id}",
                }
                races.append({"race": race, "rows": _protocol(get, event_id, distance_id, count)})
            if not races or sum(item["race"]["total_count"] for item in races) != raw["resultsCount"]:
                raise PilotRejected("Missing or incomplete TopList protocols")
            return {"competition": competition, "races": races}
        except PilotRejected:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PilotRejected("Invalid or incomplete TopList response") from exc

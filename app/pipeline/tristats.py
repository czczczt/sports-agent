"""Read published triathlon races through the public TriStats website API."""

import math
import re
from collections import Counter
from datetime import date
from time import monotonic, sleep

import requests

from app.pipeline.errors import PilotRejected
from parser_running.normalize import to_seconds
from parser_running.request_pacing import pace_request

BASE = "https://tristats.ru"
EVENT_CODE = re.compile(r"([a-z0-9][a-z0-9-]*)__([a-z0-9][a-z0-9-]*)__([a-z0-9][a-z0-9-]*)__([0-9]{4})")
DIVISION_CODE = re.compile(r"/[a-zа-яё0-9][a-zа-яё0-9-]*")
STATUSES = {"DNS", "DNF", "DSQ", "NC", "LAP"}


def _row(raw, finish_index, column_count):
    result_id, sex, group = raw["ResultId"], raw["Sex"], raw["Division"]
    if type(result_id) is not int or result_id <= 0 or sex not in {"M", "F"} or not group:
        raise PilotRejected("Missing TriStats result identity or group")
    times = raw["Times"]
    if not isinstance(times, list) or len(times) != column_count:
        raise PilotRejected("TriStats result has incomplete timing columns")
    finish = times[finish_index]
    source_status = raw.get("Status") or (finish if finish in STATUSES else "FIN")
    if source_status == "FIN":
        seconds = to_seconds(finish)
        if not seconds or not math.isfinite(seconds):
            raise PilotRejected("TriStats finisher has no valid full time")
        for rank in (raw["SexRank"], raw["DivisionRank"]):
            if type(rank) is not int or rank <= 0:
                raise PilotRejected("TriStats finisher has no valid ranking")
    elif source_status in STATUSES:
        seconds = None
    else:
        raise PilotRejected("Unknown TriStats result status")
    return {
        "external_participant_id": str(result_id),
        "full_name_raw": raw.get("Racer"),
        "gender": sex, "country": raw.get("Country"),
        "birth_year": raw.get("BirthYear") or None, "region": raw.get("Region"),
        "age_group": group,
        "place_abs": None,
        "status": source_status,
        "place_gender": raw["SexRank"] if source_status == "FIN" else None,
        "place_age_group": raw["DivisionRank"] if source_status == "FIN" else None,
        "official_time_s": seconds,
    }


def _protocol(get, path, metadata):
    records = get(f"/result{path}")
    count = metadata["RacerCount"]
    if type(count) is not int or count <= 0 or not isinstance(records, list) or len(records) != count:
        raise PilotRejected("Incomplete TriStats race protocol")
    columns = records[0]["Names"]
    if not isinstance(columns, list) or columns.count("Финиш") != 1:
        raise PilotRejected("TriStats protocol is missing its finish column")
    finish_index = columns.index("Финиш")
    rows, groups = [], {}
    for raw in records:
        if raw.get("Names", columns) != columns:
            raise PilotRejected("TriStats timing columns changed within a protocol")
        division = raw["DivisionUrl"]
        if not DIVISION_CODE.fullmatch(division):
            raise PilotRejected("Invalid TriStats division key")
        row = _row(raw, finish_index, len(columns))
        label = (row["gender"], row["age_group"])
        if groups.setdefault(division, label) != label:
            raise PilotRejected("Inconsistent TriStats group identity")
        rows.append(row)
    if len({row["external_participant_id"] for row in rows}) != count:
        raise PilotRejected("Duplicate TriStats result ID")
    if len(set(groups.values())) != len(groups) or sum(row["gender"] == "F" for row in rows) != metadata["FemaleCount"]:
        raise PilotRejected("Inconsistent TriStats group or gender totals")
    distribution = Counter(raw["DivisionUrl"] for raw in records)
    for raw, row in zip(records, rows):
        rank = row["place_age_group"]
        if rank is not None and rank > distribution[raw["DivisionUrl"]]:
            raise PilotRejected("TriStats place exceeds the published division size")
    for division, expected_count in distribution.items():
        info = get(f"/division{path}{division}")
        if (info["RaceUrl"] != path or info["DivisionUrl"] != division
                or info["DivisionName"] != groups[division][1] or info["RacerCount"] != expected_count):
            raise PilotRejected("Incomplete or inconsistent TriStats division protocol")
    return rows


def fetch_event(event_code: str) -> dict:
    match = EVENT_CODE.fullmatch(event_code) if isinstance(event_code, str) and len(event_code) <= 160 else None
    if match is None:
        raise PilotRejected("Invalid TriStats key, expected brand__name__type__year")
    brand, name, distance_class, year = match.groups()
    path = f"/{brand}/{name}/{distance_class}/{year}"
    url = f"{BASE}/result{path}"
    deadline = monotonic() + 150
    with requests.Session() as session:
        def get(route):
            pace_request(BASE, sleep=sleep)
            if monotonic() >= deadline:
                raise requests.Timeout("TriStats collection timed out")
            response = session.get(f"{BASE}/api{route}", timeout=(5, 15), allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200:
                raise PilotRejected("Unexpected TriStats response")
            return response.json()

        try:
            metadata = get(f"/rus/race{path}")
            race_id = metadata["RaceId"]
            start_date = date.fromisoformat(metadata["Date"])
            if (metadata["RaceUrl"] != path or type(race_id) is not int or race_id <= 0
                    or not metadata["RaceName"] or str(start_date.year) != year or start_date > date.today()):
                raise PilotRejected("Invalid or unpublished TriStats race")
            rows = _protocol(get, path, metadata)
            relay_groups = {row["age_group"].upper().endswith("RELAY") for row in rows}
            if len(relay_groups) != 1:
                raise PilotRejected("Mixed individual and relay TriStats protocols require a separate import")
            competition = {
                "external_id": str(race_id), "code": event_code,
                "title": metadata.get("EventName") or metadata["RaceName"],
                "date_begin": start_date.isoformat(), "place": metadata.get("CityName") or metadata.get("RegionName"),
                "sport": "triathlon", "url": url,
            }
            race = {
                "external_id": str(race_id), "name_raw": metadata["RaceName"], "distance_class": distance_class,
                "sport": "triathlon", "race_type": "relay" if True in relay_groups else "individual",
                "place_by": "official", "is_final": None, "total_count": len(rows), "url": url,
            }
            return {"competition": competition, "races": [{"race": race, "rows": rows}]}
        except PilotRejected:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PilotRejected("Invalid or incomplete TriStats response") from exc

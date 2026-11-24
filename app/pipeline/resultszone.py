"""Collect complete Results.zone protocols from the JSON embedded in public pages."""

import json
import re
from datetime import date
from math import ceil
from time import sleep

import requests
from bs4 import BeautifulSoup

from app.pipeline.errors import PilotRejected
from app.pipeline.validation import validate_event
from parser_running.http_cache import UA
from parser_running.request_pacing import pace_request

BASE_URL = "https://results.zone"
_SPORT = {"running": "run", "trail": "trail", "skiing": "ski", "triathlon": "triathlon"}
_STATUS = {"Q": "FIN", "DNF": "DNF", "DNS": "DNS", "DSQ": "DSQ"}


def _data(html, *keys):
    scripts = BeautifulSoup(html, "html.parser").find_all("script")
    data = {}
    for key in keys:
        pattern = re.compile(rf"(?<![\w.])general\.{key}\s*=\s*")
        matches = [(raw, m) for script in scripts if (raw := script.string)
                   for m in pattern.finditer(raw)]
        if len(matches) != 1:
            raise PilotRejected(f"Missing or ambiguous Results.zone {key}")
        raw, match = matches[0]
        data[key] = json.JSONDecoder().raw_decode(raw[match.end():])[0]
    return data


def _row(raw, race_id):
    if raw["race_id"] != race_id or not isinstance(raw["uuid"], str) or not raw["uuid"]:
        raise PilotRejected("Invalid Results.zone participant or race identity")
    return {
        "external_participant_id": raw["uuid"],
        "bib": raw.get("bib"),
        "full_name_raw": raw.get("name"),
        "gender": {"male": "M", "female": "F"}.get(raw.get("gender")),
        "club_raw": raw.get("club") or raw.get("team"),
        "age_group": raw.get("category"),
        "status": _STATUS[raw["status"]],
        "place_abs": raw.get("rank_abs"),
        "place_gender": raw.get("rank_gender"),
        "chip_time_s": raw.get("result_time_start"),
        "gun_time_s": raw.get("result_time_gun"),
        "official_time_s": raw.get("result_time"),
    }


def _protocol(get, path, entry, total, event_sport):
    race_id = entry["id"]
    payload = _data(get(path), "race", "page_info", "heats")
    details, paging = payload["race"], payload["page_info"]
    if any(details[key] != entry[key] for key in ("id", "slug", "name", "distance", "start_by")):
        raise PilotRejected("Results.zone protocol belongs to a different race")
    split_sports = {split["sport"] for split in details["splits"] if split.get("sport")}
    if event_sport != "triathlon" and split_sports - {"running", event_sport}:
        return None
    place_by = {"start": "chip", "gun": "gun"}[details["start_by"]]
    per_page = paging["perPage"]
    if type(per_page) is not int or per_page <= 0:
        raise PilotRejected("Invalid Results.zone page size")
    pages = ceil(total / per_page)
    if not 1 <= pages <= 500:
        raise PilotRejected("Invalid Results.zone page count")
    rows = []
    for page in range(1, pages + 1):
        if page > 1:
            payload = _data(get(f"{path}?page={page}"), "race", "page_info", "heats")
            paging = payload["page_info"]
        if (payload["race"] != details or paging["totalRows"] != total
                or paging["perPage"] != per_page or paging["totalPages"] != pages
                or paging["currentPage"] != page
                or paging["nextPage"] != (page + 1 if page < pages else None)
                or len(payload["heats"]) != min(per_page, total - len(rows))):
            raise PilotRejected("Incomplete Results.zone pagination")
        rows.extend(_row(raw, race_id) for raw in payload["heats"])
    return {"race": {
        "external_id": str(race_id), "name_raw": details["name"],
        "sport": _SPORT[event_sport], "distance_km": details["distance"] / 1000,
        "race_type": "individual", "place_by": place_by, "is_final": True,
        "total_count": total, "url": BASE_URL + path,
    }, "rows": rows}


def _collect(get, event_code):
    path = f"/{event_code}"
    payload = _data(get(path), "event", "event_results_statistics")
    event = payload["event"]
    start = date.fromisoformat(event["date_start"])
    if event["slug"] != event_code or start >= date.today() or event["sport"] not in _SPORT:
        raise PilotRejected("Unknown, unsupported or ongoing Results.zone event")
    stats = payload["event_results_statistics"]["stats"]
    counts = {item["id"]: item for item in stats}
    if len(counts) != len(stats) or set(counts) != {entry["id"] for entry in event["races"]}:
        raise PilotRejected("Results.zone race list disagrees with published statistics")

    races, review = [], []
    for entry in event["races"]:
        race_id = entry["id"]
        if type(race_id) is not int or race_id <= 0:
            raise PilotRejected("Invalid Results.zone race ID")
        protocol_path = f"{path}/races/{race_id}/results"
        if entry["self"] != protocol_path or entry["slug"] != event_code:
            raise PilotRejected("Invalid Results.zone race URL")
        if entry["live"] is not False:
            raise PilotRejected("Results.zone race is live")
        summary = counts[race_id]
        total = summary["total"]
        if type(total) is not int or total < 0:
            raise PilotRejected("Invalid Results.zone race row count")
        if (entry["finish_by"] != "distance"
                or re.search(r"ходьб|эстафет|вело|заплыв|walking|relay", entry["name"], re.I)):
            review.append({"kind": "unsupported_discipline", "external_ref": protocol_path})
            continue
        if not total or not summary.get("q"):
            continue  # The public statistics show no finishers.
        protocol = _protocol(get, protocol_path, entry, total, event["sport"])
        if protocol is None:
            review.append({"kind": "unsupported_discipline", "external_ref": protocol_path})
            continue
        if sum(row["status"] == "FIN" for row in protocol["rows"]) != summary["q"]:
            raise PilotRejected("Results.zone finisher count disagrees with published statistics")
        races.append(protocol)
    result = {"competition": {
        "external_id": event_code, "code": event_code, "title": event["name"],
        "date_begin": start.isoformat(), "sport": _SPORT[event["sport"]], "url": BASE_URL + path,
    }, "races": races, "review_items": review}
    validate_event(result)
    return result


def fetch_event(event_code: str) -> dict:
    if not isinstance(event_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_code):
        raise PilotRejected("Invalid Results.zone event code")
    with requests.Session() as session:
        session.headers.update(UA)
        def get(path):
            pace_request(BASE_URL, 1, sleep=sleep)
            response = session.get(BASE_URL + path, timeout=(5, 25), allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200:
                raise PilotRejected("Unexpected Results.zone HTTP response")
            return response.content.decode("utf-8")

        try:
            return _collect(get, event_code)
        except PilotRejected:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
            raise PilotRejected("Invalid or incomplete Results.zone protocol") from exc

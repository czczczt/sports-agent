"""Read published running protocols from the public MyRunStats JSON API."""

import math
import re
from datetime import date
from time import monotonic, sleep

import requests

from app.pipeline.errors import PilotRejected
from parser_running.normalize import infer_place_by, to_seconds

BASE = "https://myrunstats.ru"
PAGE_SIZE = 100
# Status IDs independently matched by bib to the official RussiaRunning
# results for MyRunStats protocol 836 (Pushkin–Petersburg 2026, 10 km).
STATUSES = {1: "FIN", 3: "DNF", 4: "DSQ"}


def _published_rows(get, protocol_id):
    rows = []
    page, total = 1, None
    while total is None or len(rows) < total:
        data = get(f"/protocols/{protocol_id}/results", params={"page": page, "size": PAGE_SIZE})
        items, count = data["items"], data["total"]
        if (type(count) is not int or count < 1 or (total is not None and total != count)
                or data["page"] != page or data["size"] != PAGE_SIZE
                or data["pages"] != math.ceil(count / PAGE_SIZE)
                or not isinstance(items, list) or len(items) != min(PAGE_SIZE, count - len(rows))):
            raise PilotRejected("Incomplete or changing MyRunStats pagination")
        for raw in items:
            # Public UUID can be absent. The source's per-protocol seq is
            # also the key used by result deep links and split lookups.
            seq = raw["protocol_id_seq"]
            if raw["protocol_id"] != protocol_id or type(seq) is not int or seq <= 0:
                raise PilotRejected("Missing MyRunStats participant ID or inconsistent protocol ID")
            rows.append(raw)
        total = count
        page += 1
    if len({row["protocol_id_seq"] for row in rows}) != total:
        raise PilotRejected("Duplicate MyRunStats participant ID")
    return rows, total


def _row(raw):
    status = STATUSES.get(raw["status_id"])
    if status is None:
        raise PilotRejected("Unknown MyRunStats result status")
    return {
        "external_participant_id": str(raw["protocol_id_seq"]),
        "bib": raw.get("bib"),
        "full_name_raw": (None if raw.get("is_deperson") else
                          " ".join(part for part in (raw.get("last_name"), raw.get("first_name")) if part) or None),
        "gender": raw.get("gender"),
        "birth_year": raw.get("year_birth"),
        "age": raw.get("age"),
        "city": raw.get("city_norm"),
        "country": raw.get("country_alpha3_id"),
        "club_raw": raw.get("club_main"),
        "age_group": raw.get("age_group_name"),
        "status": status,
        "place_abs": raw.get("finish_position_overall") if status == "FIN" else None,
        "place_gender": raw.get("finish_position_gender") if status == "FIN" else None,
        "place_age_group": raw.get("finish_position_age") if status == "FIN" else None,
        "chip_time_s": to_seconds(raw.get("finish_chip_time")) if status == "FIN" else None,
        "gun_time_s": to_seconds(raw.get("finish_gun_time")) if status == "FIN" else None,
    }


def _official_event_url(races):
    # Only known result routes certify that the records mirror an upstream
    # event. Organizer and generic registration URLs are insufficient.
    patterns = (
        r"(https://(?:results\.russiarunning\.com|results\.legkovrace\.ru|results\.pionercup\.ru)"
        r"/event/[A-Za-z0-9_-]+/results)(?:/[A-Za-z0-9_-]+)?/?",
        r"(https://timerman\.org/results/[A-Za-z0-9_-]+)(?:/[A-Za-z0-9_-]+)?/?",
    )
    roots = set()
    for item in races:
        url = item["race"].get("official_url") or ""
        for pattern in patterns:
            match = re.fullmatch(pattern, url)
            if match:
                roots.add(match[1])
                break
        else:
            return None
    return next(iter(roots)) if len(roots) == 1 else None


def fetch_event(event_code: str) -> dict:
    if not isinstance(event_code, str) or not re.fullmatch(r"[1-9][0-9]{0,17}", event_code):
        raise PilotRejected("Invalid MyRunStats event ID")

    deadline = monotonic() + 180
    with requests.Session() as session:
        next_request = 0.0

        def get(path, params=None):
            nonlocal next_request
            sleep(max(0, next_request - monotonic()))
            next_request = monotonic() + 0.5
            if monotonic() >= deadline:
                raise requests.Timeout("MyRunStats event collection timed out")
            response = session.get(f"{BASE}/api/v1{path}", params=params, timeout=(5, 15), allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200:
                raise PilotRejected("Unexpected MyRunStats response")
            return response.json()

        try:
            raw = get(f"/events/{event_code}")
            if (raw["event_id"] != int(event_code) or not raw["event_name"]
                    or raw["has_published_protocol"] is not True or raw["event_type"]["type_name"] != "Run"):
                raise PilotRejected("MyRunStats entry has no published running protocol")
            date.fromisoformat(raw["event_date"])
            comp = {"external_id": event_code, "code": event_code, "title": raw["event_name"],
                    "date_begin": raw["event_date"], "place": (raw.get("city") or {}).get("city_name"),
                    "address": raw.get("address_detail"), "sport": "run",
                    "url": f"{BASE}/events/{event_code}"}
            distances = {entry["event_distance_id"]: entry for entry in raw["distances"]}
            races, seen = [], set()
            for protocol in get("/protocols", params={"event_id": event_code}):
                if protocol["protocol_status"] != "Published" or protocol["is_active"] is not True:
                    continue
                pid = protocol["protocol_id"]
                if type(pid) is not int or pid <= 0 or protocol["event_id"] != int(event_code) or pid in seen:
                    raise PilotRejected("Invalid or duplicate MyRunStats protocol")
                seen.add(pid)
                distance = distances[protocol["event_distance_id"]]
                length = distance["distance_length"]
                if distance["length_unit"] != "m" or type(length) not in (int, float) or not math.isfinite(length) or length <= 0:
                    raise PilotRejected("Invalid MyRunStats distance")
                records, total = _published_rows(get, pid)
                relay = {row["is_relay"] for row in records}
                if relay not in ({True}, {False}):
                    raise PilotRejected("Inconsistent MyRunStats race type")
                rows = [_row(record) for record in records]
                race = {"external_id": str(pid), "name_raw": protocol["distance_name"], "distance_km": length / 1000,
                        "sport": "run", "race_type": "relay" if True in relay else "individual",
                        "place_by": infer_place_by(rows), "is_final": True, "total_count": total,
                        "url": protocol.get("result_url") or f"{comp['url']}/results/{pid}",
                        "official_url": protocol.get("result_url")}
                races.append({"race": race, "rows": rows})
            if not races:
                raise PilotRejected("No active published MyRunStats running protocols")
            comp["canonical_url"] = _official_event_url(races)
            return {"competition": comp, "races": races}
        except PilotRejected:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PilotRejected("Invalid or incomplete MyRunStats response") from exc

"""Collect public RaceTime absolute protocols through the event page's results service."""

import json
import re
from datetime import date, datetime
from time import sleep
from uuid import UUID

import requests
from bs4 import BeautifulSoup

from app.pipeline.errors import PilotRejected
from app.pipeline.validation import validate_event
from parser_running.http_cache import UA
from parser_running.normalize import km_from_name, to_seconds
from parser_running.request_pacing import pace_request

BASE_URL = "https://results.racetime.online"
_RESULTS_TEMPLATE = (
    "https://services-results.limetime.io/results/get/"
    "{raceStageGuid}/{raceGroupGuid}/{raceGroupCategoryGuid}"
)
_HEADER = "LIMETIME-API-KEY"
_SPORT = {"бег": "run", "бег (трейл)": "trail", "лыжные гонки": "ski", "триатлон": "triathlon"}


def _variables(soup, *keys):
    scripts = soup.select("script:not([src])")
    out = {}
    for key in keys:
        pattern = re.compile(rf"\bvar\s+{key}\s*=\s*")
        matches = [(raw, m) for script in scripts if (raw := script.string)
                   for m in pattern.finditer(raw)]
        if len(matches) != 1:
            raise PilotRejected(f"Missing or ambiguous RaceTime {key}")
        raw, match = matches[0]
        out[key] = json.JSONDecoder().raw_decode(raw[match.end():])[0]
    return out


def _guid(value):
    normalized = str(UUID(value))
    if normalized != value:
        raise PilotRejected("Invalid RaceTime source GUID")
    return normalized


def _catalog_sport(html, path):
    soup = BeautifulSoup(html, "html.parser")
    cards = [a.find_parent("figcaption") for a in soup.select(".media-header a[href]")
             if a["href"] == path]
    if len(cards) != 1 or cards[0] is None:
        raise PilotRejected("RaceTime event code is absent from the official calendar")
    label = cards[0].select_one(".media-subheader > div")
    sport = _SPORT.get(label.get_text(" ", strip=True).casefold()) if label else None
    if sport is None:
        raise PilotRejected("Unsupported RaceTime event discipline")
    return sport


def _time(raw, key, fraction_key):
    value, fraction = raw.get(key), raw.get(fraction_key) or ""
    if not value:
        return None
    if not re.fullmatch(r"\d+(?::\d{2}){1,2}", value) or not re.fullmatch(r"(?:[.,]\d{1,3})?", fraction):
        raise PilotRejected("Invalid RaceTime result time")
    return to_seconds(value + fraction)


def _row(raw):
    flags = ("isDisqualified", "isOtl", "isOnStart", "isFinished")
    if any(type(raw[k]) is not bool for k in flags):
        raise PilotRejected("Invalid RaceTime result status")
    if raw["isDisqualified"]:
        status = "DSQ"
    elif raw["isOtl"]:
        status = "NC"
    elif raw["isFinished"]:
        status = "FIN"
    else:
        status = "DNF" if raw["isOnStart"] else "DNS"
    account = raw.get("account") or {}
    age = account.get("age")
    if isinstance(age, str) and re.fullmatch(r"[0-9]{1,3}", age):
        age = int(age)
    if type(age) is not int or not 0 <= age <= 120:
        age = None
    name = " ".join(part for part in (account.get("lastName"), account.get("firstName")) if part)
    place = raw.get("position")
    if status == "FIN" and (type(place) is not int or place < 1):
        raise PilotRejected("RaceTime finisher is missing its absolute place")
    return {
        "external_participant_id": _guid(raw["raceStageRegistrationGuid"]),
        "bib": raw.get("number"), "full_name_raw": name or None,
        "gender": None, "age": age, "city": account.get("city"),
        "club_raw": raw.get("club") or None,
        "status": status, "place_abs": place if status == "FIN" else None,
        "chip_time_s": _time(raw, "chipTime", "chipMilliseconds"),
        "gun_time_s": _time(raw, "gunTime", "gunMilliseconds"),
        "official_time_s": _time(raw, "resultTime", "resultMilliseconds"),
    }


def _page_rows(response):
    payload = response.json()
    if not isinstance(payload, dict) or set(payload) - {"isSuccess", "data", "totalCount"}:
        raise PilotRejected("Unexpected RaceTime results envelope or pagination")
    if payload.get("isSuccess") is not True or not isinstance(payload.get("data"), list):
        raise PilotRejected("Missing RaceTime protocol")
    data = payload["data"]
    total = payload.get("totalCount", len(data))
    if (type(total) is not int or total != len(data) or response.links.get("next")
            or response.headers.get("Content-Range")):
        raise PilotRejected("Incomplete RaceTime category response")
    return [_row(item) for item in data]


def _collect(get, event_code):
    path = f"/{event_code}"
    url = BASE_URL + path
    soup = BeautifulSoup(get(url).content.decode("utf-8"), "html.parser")
    data = _variables(soup, "RACE_STAGE_GUID", "RACE_STAGE_INFO", "HAS_RESULTS",
                      "GROUPS_AND_CATEGORIES", "BASE_URL", "API_KEY", "HEADER_NAME")
    stage = _guid(data["RACE_STAGE_GUID"])
    info = data["RACE_STAGE_INFO"]
    start = datetime.fromisoformat(info["startDateTime"]).date()
    if info["raceStageGuid"] != stage or data["HAS_RESULTS"] is not True or start >= date.today():
        raise PilotRejected("RaceTime event lacks a historical result protocol")
    sport = _catalog_sport(get(f"{BASE_URL}/{start.year}").content.decode("utf-8"), path)
    headers = {_HEADER: data["API_KEY"]}
    if (data["BASE_URL"] != _RESULTS_TEMPLATE or data["HEADER_NAME"] != _HEADER
            or not isinstance(data["API_KEY"], str) or not data["API_KEY"]):
        raise PilotRejected("Unrecognized RaceTime public results endpoint")

    groups = data["GROUPS_AND_CATEGORIES"]
    if not isinstance(groups, list) or len(groups) > 100:
        raise PilotRejected("Invalid RaceTime race list")
    races, review, seen = [], [], set()
    for group in groups:
        race_id = _guid(group["guid"])
        if race_id in seen:
            raise PilotRejected("Duplicate RaceTime race")
        seen.add(race_id)
        name = group["displayName"]
        distance = km_from_name(name)
        categories = [c for c in group["categories"] if c["displayName"].casefold() == "абсолют"]
        if len(categories) > 1:
            raise PilotRejected("Ambiguous RaceTime absolute category")
        if (not distance or re.search(r"ходьб|эстафет|вело|заплыв|walking|relay", name, re.I)
                or not categories or categories[0]["isTeam"] is not False):
            review.append({"kind": "unsupported_discipline", "external_ref": race_id})
            continue
        category_id = _guid(categories[0]["guid"])
        results_url = _RESULTS_TEMPLATE.format(
            raceStageGuid=stage, raceGroupGuid=race_id, raceGroupCategoryGuid=category_id,
        )
        rows = _page_rows(get(results_url, headers=headers))
        finishers = [row for row in rows if row["status"] == "FIN"]
        if not finishers:
            continue
        matched_scales = [scale for scale in ("chip", "gun") if all(
            row["official_time_s"] is not None and row[f"{scale}_time_s"] == row["official_time_s"]
            for row in finishers
        )]
        place_by = matched_scales[0] if len(matched_scales) == 1 else "official"
        races.append({"race": {
            "external_id": race_id, "name_raw": name, "distance_km": distance,
            "sport": sport, "race_type": "individual", "is_final": None, "place_by": place_by,
            "total_count": len(rows), "url": url,
        }, "rows": rows})
    result = {"competition": {
        "external_id": stage, "code": event_code, "title": soup.title.get_text(" ", strip=True),
        "date_begin": start.isoformat(), "sport": sport, "url": url,
    }, "races": races, "review_items": review}
    validate_event(result)
    return result


def fetch_event(event_code: str) -> dict:
    if not isinstance(event_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_code):
        raise PilotRejected("Invalid RaceTime event code")
    with requests.Session() as session:
        session.headers.update(UA)
        def get(url, **kwargs):
            pace_request(url, 1, sleep=sleep)
            response = session.get(url, timeout=(8, 40), allow_redirects=False, **kwargs)
            response.raise_for_status()
            if response.status_code != 200:
                raise PilotRejected("Unexpected RaceTime HTTP response")
            return response

        try:
            return _collect(get, event_code)
        except PilotRejected:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
            raise PilotRejected("Invalid or incomplete RaceTime protocol") from exc

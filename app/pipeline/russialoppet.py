"""Fetch the official, paginated Russialoppet season protocol."""

import re
import time
from datetime import date
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from app.pipeline.errors import PilotRejected
from parser_running.normalize import km_from_name, to_seconds

BASE = "https://russialoppet.ru"
MAX_PAGES = 200


def _get(session, url, params=None):
    time.sleep(0.5)  # at most two requests per second to the public site
    response = session.get(url, params=params, timeout=(5, 20), allow_redirects=False)
    response.raise_for_status()
    if response.status_code != 200:
        raise PilotRejected("Unexpected Russialoppet HTTP response")
    return BeautifulSoup(response.content, "lxml", from_encoding="utf-8")


def _text(node, selector):
    child = node.select_one(selector)
    return child.get_text(" ", strip=True) if child else ""


def _positive_int(value):
    return int(value) if value.isdecimal() and int(value) > 0 else None


def _parse_row(row, season, sex):
    cells = row.find_all("td", recursive=False)
    if len(cells) < 13:
        raise PilotRejected("Malformed Russialoppet result row")
    fields = [cell.get_text(" ", strip=True) for cell in cells]
    position, name, year, _, club, city, bib, finish, _, _, group, group_place, *_ = fields
    # One athlete profile may occur on multiple result records. Use the
    # Bitrix record ID for stable, race-local identity.
    result_id = re.fullmatch(r"bx_\d+_(\d+)", row.get("id", ""))
    profile = cells[1].find("a", href=True)
    profile_id = re.fullmatch(r"/results/p/(\d+)/?", profile["href"]) if profile else None
    group_sex = {"М": "M", "Ж": "F"}.get(group[:1])
    time = to_seconds(finish)
    status = "FIN" if time and time > 0 else finish
    place = _positive_int(position)
    birth_year = _positive_int(year)
    if (not result_id or not name or (group_sex and group_sex != sex)
            or status not in {"FIN", "DNS", "DNF", "DSQ", "NC"}
            or (status == "FIN" and place is None)
            or (birth_year is not None and not 1900 <= birth_year <= season)):
        raise PilotRejected("Invalid Russialoppet result row")
    return {
        "external_participant_id": result_id[1], "source_profile_id": profile_id[1] if profile_id else None,
        "bib": bib or None,
        "full_name_raw": name, "birth_year": birth_year, "gender": sex,
        "club_raw": club or None, "club_source": "protocol" if club else None,
        "city": city or None, "status": status, "age_group": group or None,
        "place_abs": None, "place_gender": place if status == "FIN" else None,
        "place_age_group": _positive_int(group_place) if status == "FIN" and group else None,
        "chip_time_s": time if status == "FIN" else None, "gun_time_s": None,
    }


def _protocol(session, url, distance, season, sex):
    rows = []
    page_count = None
    for page in range(1, MAX_PAGES + 1):
        soup = _get(session, url, {"distance": distance, "gender": sex, "PAGEN_1": page})
        selected = soup.select_one(".filter-distance option[selected]")
        filters = parse_qs(urlsplit(selected["value"]).query) if selected else {}
        if filters.get("distance") != [distance] or filters.get("gender") != [sex]:
            raise PilotRejected("Russialoppet returned an unexpected protocol filter")
        page_links = [int(a.get_text(strip=True)) for a in soup.select(".module-pagination .nums a")
                      if a.get_text(strip=True).isdecimal()]
        current = _positive_int(_text(soup, ".module-pagination .cur")) or 1
        available = max([current, *page_links])
        if current != page or (page_count is not None and available != page_count):
            raise PilotRejected("Inconsistent Russialoppet pagination")
        page_count = available
        batch = soup.select("table.results-list tr.results-item")
        if not batch and page == page_count == 1 and not soup.select_one("table.results-list"):
            break
        if not batch or page_count > MAX_PAGES:
            raise PilotRejected("Empty or oversized Russialoppet protocol")
        rows.extend(_parse_row(row, season, sex) for row in batch)
        if page == page_count:
            break
    return rows


def fetch_event(event_code: str) -> dict:
    """Load a single years/ID protocol, e.g. code '2025-850'."""
    code = re.fullmatch(r"(20\d{2})-(\d{1,10})", event_code) if isinstance(event_code, str) else None
    if not code:
        raise PilotRejected("Russialoppet event code must have the format YYYY-ID")
    year, source_id = code.groups()
    season = int(year)
    path = f"/results/{year}/{source_id}/"
    url = BASE + path
    with requests.Session() as session:
        protocol = _get(session, url)
        title = _text(protocol, "h1#pagetitle")
        event_link = protocol.select_one(".link-to-detail a[href]")
        if not title.endswith(f"{year} год") or not event_link:
            raise PilotRejected("Missing Russialoppet event metadata")
        event_url = urljoin(BASE, event_link["href"])
        event_parts = urlsplit(event_url)
        if (event_parts.scheme != "https" or event_parts.netloc not in {"russialoppet.ru", "www.russialoppet.ru"}
                or not re.fullmatch(r"/events/[A-Za-z0-9_-]+\.html", event_parts.path)):
            raise PilotRejected("Invalid Russialoppet event link")
        event = _get(session, event_url)
        starts = event.select_one("time.race-date[datetime]")
        if not starts:
            raise PilotRejected("Missing Russialoppet event date")
        try:
            start_date = date.fromisoformat(starts["datetime"])
        except ValueError as exc:
            raise PilotRejected("Invalid Russialoppet event date") from exc
        if start_date > date.today() or _text(event, ".hero-subtitle") != f"Сезон {year}":
            raise PilotRejected("Russialoppet event date or season mismatch")
        index = _get(session, f"{BASE}/results/{year}/")
        expected = None
        for entry in index.select(".bx_catalog_tile_title"):
            link = entry.find("a", href=True)
            if link and urlsplit(link["href"]).path.rstrip("/") == path.rstrip("/"):
                count = re.fullmatch(r"Участников:\s*(\d+)", _text(entry, "span"))
                if count:
                    expected = int(count[1])
                break
        if not expected:
            raise PilotRejected("Missing Russialoppet protocol count")

        races = []
        codes = set()
        for option in protocol.select(".filter-distance option[value]"):
            label = option.get_text(" ", strip=True)
            distance = parse_qs(urlsplit(option["value"]).query).get("distance", [])
            km = km_from_name(label)
            if len(distance) != 1 or not km or distance[0] in codes:
                raise PilotRejected("Invalid or duplicate Russialoppet distance")
            codes.add(distance[0])
            rows = [row for sex in ("M", "F") for row in _protocol(session, url, distance[0], season, sex)]
            if not rows or len({row["external_participant_id"] for row in rows}) != len(rows):
                raise PilotRejected("Empty or duplicate Russialoppet results")
            race = {
                "external_id": distance[0], "name_raw": label, "distance_km": km,
                "sport": "ski", "race_type": "individual", "place_by": "chip",
                "is_final": True, "season": season, "series": "russialoppet",
                "source_discipline": label.split(" (", 1)[0],
                "url": f"{url}?{urlencode({'distance': distance[0]})}",
                "total_count": len(rows),
            }
            races.append({"race": race, "rows": rows})
        if not races or sum(item["race"]["total_count"] for item in races) != expected:
            raise PilotRejected("Incomplete Russialoppet protocol")
        return {"competition": {
            "external_id": event_code, "code": event_code, "title": title,
            "date_begin": start_date.isoformat(), "place": _text(event, ".region-city") or None,
            "sport": "ski", "url": url,
        }, "races": races}

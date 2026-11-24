"""Collect complete, server-rendered running protocols from ПроБЕГ."""

import hashlib
import math
import re
from datetime import date
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from app.pipeline.errors import PilotRejected
from parser_running.normalize import km_from_name, ru_date, to_seconds
from parser_running.request_pacing import pace_request

BASE_URL = "https://probeg.org"
_DATE = r"\d{1,2}\s+[а-яё]+\s+\d{4}"
_COUNT = re.compile(r"\(?([\d ]+) участни(?:к|ка|ков)\)?$")
_RANGE = re.compile(r"Найдено:\s*([\d ]+)\s*·\s*показаны\s*([\d ]+)[–-]([\d ]+)")
_STATUS = {
    "dns": "DNS", "не стартовал": "DNS", "не стартовала": "DNS",
    "dnf": "DNF", "сход": "DNF", "не финишировал": "DNF", "не финишировала": "DNF",
    "dsq": "DSQ", "dq": "DSQ", "дисквалификация": "DSQ",
    "nc": "NC", "лап": "LAP", "lap": "LAP",
}


def _text(node):
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _number(value):
    return int(value.replace(" ", ""))


def _path_id(link, kind):
    if link is None:
        return None
    match = re.fullmatch(fr"/{kind}/([1-9][0-9]{{0,17}})/", link.get("href", ""))
    return match[1] if match else None


def _page(session, path):
    pace_request(BASE_URL, 1)
    with session.get(f"{BASE_URL}{path}", timeout=(5, 20), allow_redirects=False, stream=True) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise PilotRejected("Unexpected ПроБЕГ redirect or HTTP response")
        body = bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body) > 4 * 1024 * 1024:
                raise PilotRejected("ПроБЕГ page exceeds the response limit")
    return BeautifulSoup(bytes(body), "html.parser", from_encoding="utf-8")


def _primary_result_url(documents):
    urls = set()
    for link in documents.select("a[href]") if documents else []:
        if not re.fullmatch(r"Протокол(?:\s*[↗])?", _text(link), re.IGNORECASE):
            continue
        url = urlsplit(link["href"])
        match = re.fullmatch(r"/event/([A-Za-z0-9_-]{1,200})/results(?:/[A-Za-z0-9_-]+)?/?", url.path)
        if url.scheme == "https" and url.netloc.lower() == "results.russiarunning.com" and match:
            urls.add(f"https://results.russiarunning.com/event/{match[1]}/results")
    return next(iter(urls)) if len(urls) == 1 else None


def _event_data(html, ident):
    details = {
        _text(term): term.find_next_sibling("dd")
        for term in html.select("dt")
    }
    title, when = _text(html.select_one("h1")), _text(details.get("Когда"))
    dates = re.findall(_DATE, when, re.IGNORECASE)
    if dates and (short := re.match(r"(\d{1,2})\s*[–-]\s*(?=\d)", when)):
        dates.insert(0, short[1] + " " + dates[0].split(" ", 1)[1])
    if not title or not dates:
        raise PilotRejected("Missing ПроБЕГ event title or date")
    dates = [date.fromisoformat(ru_date(raw)).isoformat() for raw in dates]
    if len(dates) > 2 or dates[-1] < dates[0]:
        raise PilotRejected("Invalid ПроБЕГ event date range")
    where = details.get("Где")
    city = where.select_one("a") if where else None
    address = where.select_one("div") if where else None
    sport_label = _text(details.get("Тип забега")).lower()
    if re.search(r"триатлон|дуатлон|акватлон|лыж|ходьба|велогон|эстафет|ориентирован", sport_label):
        raise PilotRejected("Unsupported ПроБЕГ event discipline")
    sport = "trail" if re.search(r"трейл|кросс|горный бег", sport_label) else "run"
    comp = {
        "external_id": ident, "code": ident, "title": title, "date_begin": dates[0],
        "date_end": dates[1] if len(dates) == 2 else None,
        "place": _text(city) or (_text(where) if not address else None),
        "address": _text(address).removeprefix("Место старта: ") or None, "sport": sport,
        "url": f"{BASE_URL}/event/{ident}/",
        "canonical_url": _primary_result_url(details.get("Документы")),
    }
    races = {}
    distances = details.get("Дистанции")
    for link in distances.select("a[href]") if distances else []:
        race_id = _path_id(link, "race")
        if race_id is None:
            continue
        label = _text(link)
        count = _COUNT.search(label)
        if not count:
            continue  # distance announced on the card without a result count
        name = label[:count.start()].rstrip(" (,")
        if name.count("(") > name.count(")"):
            name += ")"
        if re.search(r"ходьб|эстафет|велогон|лыж|заплыв", name, re.IGNORECASE):
            continue
        prefix = name.casefold().lstrip()
        if prefix.startswith("полумарафон"):
            distance = 21.0975
        elif prefix.startswith("марафон"):
            distance = 42.195
        else:
            distance = km_from_name(name)
        if not distance or not math.isfinite(distance) or race_id in races:
            raise PilotRejected("Invalid or duplicate ПроБЕГ distance")
        total = _number(count[1])
        if total:
            races[race_id] = {
                "external_id": race_id, "name_raw": name, "distance_km": distance,
                "race_type": "individual", "sport": sport, "is_final": True,
                "timing_type": None, "total_count": total, "url": f"{BASE_URL}/race/{race_id}/",
            }
    if not races:
        raise PilotRejected("No final individual ПроБЕГ protocols")
    return comp, races


def _column_indexes(headers):
    names = {
        "место": "place", "имя": "name", "стартовый номер": "bib",
        "город, страна": "location", "результат": "result",
        "место среди мужчин/женщин": "place_gender", "группа (место в ней)": "group",
        "дата рождения, возраст": "age", "клуб": "club", "комментарий": "comment",
    }
    columns = {names[value]: idx for idx, value in enumerate(headers) if value in names}
    if not {"place", "name", "result", "group"} <= columns.keys():
        raise PilotRejected("Unexpected ПроБЕГ results table columns")
    return columns


def _place(value):
    match = re.fullmatch(r"(\d+)(?:=|\s*\*)?", value)
    return int(match[1]) if match and int(match[1]) > 0 else None


def _row(tr, cells, columns):
    def value(key):
        return _text(cells[columns[key]]) if key in columns else ""

    name_cell = cells[columns["name"]]
    name_node = name_cell.select_one(".name-row") or name_cell.select_one("b") or name_cell
    name = _text(name_node)
    profile_id = next(
        (ident for link in name_node.select("a[href]") if (ident := _path_id(link, r"(?:runner|klb/person)"))),
        None,
    )
    result = value("result")
    status = _STATUS.get(result.casefold()) or _STATUS.get(value("place").casefold())
    comment = value("comment")
    elapsed = to_seconds(result)
    if status is None and (elapsed is None or not math.isfinite(elapsed) or elapsed <= 0):
        status = _STATUS.get(comment.casefold())
        if not status:
            raise PilotRejected("Invalid ПроБЕГ result time or status")
    status = status or "FIN"
    gun_text = re.search(r"Грязное время:\s*([\d:.,]+)", comment, re.IGNORECASE)
    gun = to_seconds(gun_text[1]) if gun_text else None
    if gun_text and (not gun or not math.isfinite(gun)):
        raise PilotRejected("Invalid ПроБЕГ gun time")
    group = re.split(r"\s*\(\s*\d+\s+из", value("group"), maxsplit=1)[0]
    if "girl" in tr.get("class", []) or re.match(r"жен|дев|[жw](?=\s|\d|$)", group, re.IGNORECASE):
        gender = "F"
    elif re.match(r"муж|мал|[мm](?=\s|\d|$)", group, re.IGNORECASE):
        gender = "M"
    else:
        gender = None
    bib = value("bib")
    if bib in {"", "-", "–", "—"}:
        bib = None
    age_text = value("age")
    age = re.search(r"\b(\d{1,3})\s*(?:лет\b|год\w*)", age_text)
    year = re.search(r"\b(19\d{2}|20\d{2})\b", age_text)
    city, delimiter, country = value("location").rpartition(", ")
    return {
        "source_profile_id": profile_id, "bib": bib, "full_name_raw": name or None, "gender": gender,
        "status": status, "place_abs": _place(value("place")), "place_gender": _place(value("place_gender")),
        "age_group": group or None, "age": int(age[1]) if age else None,
        "birth_year": int(year[1]) if year else None, "city": city or None,
        "country": (country if delimiter else value("location")) or None, "club_raw": value("club") or None,
        "chip_time_s": elapsed if status == "FIN" else None, "gun_time_s": gun if status == "FIN" else None,
    }


def _protocol_page(html, event_id, race_id):
    canonical = html.select_one("link[rel=canonical]")
    event_links = html.select("h1 a[href], h3 a[href]")
    if not any(_path_id(a, "event") == event_id for a in event_links):
        raise PilotRejected("ПроБЕГ distance does not belong to the requested event")
    if canonical is not None:
        expected = f"/race/{race_id}/"
        if urlsplit(canonical.get("href", "")).path != expected:
            raise PilotRejected("Unexpected ПроБЕГ distance page")
    table = html.select_one("table.results-t")
    if not table:
        raise PilotRejected("Missing ПроБЕГ results table")
    columns = None
    rows = []
    for tr in table.select("tr"):
        header = tr.find_all("th", recursive=False)
        if header:
            columns = _column_indexes([_text(cell).casefold() for cell in header])
            width = len(header)
            continue
        cells = tr.find_all("td", recursive=False)
        if columns is None or len(cells) != width:
            raise PilotRejected("Incomplete ПроБЕГ results row")
        rows.append(_row(tr, cells, columns))

    page_info = html.select_one("#raceTable ~ .muted") or html.select_one(".muted")
    range_match = _RANGE.search(_text(page_info))
    if range_match:
        total, first, last = map(_number, range_match.groups())
    else:
        # The earlier template uses the same range but different wording.
        match = re.search(r"Всего записей:\s*([\d ]+)\.\s*Показаны записи с ([\d ]+) по ([\d ]+)", _text(html))
        total, first, last = map(_number, match.groups()) if match else (None, 1, len(rows))
    has_next = html.select_one('.pages a[aria-label="Следующая страница"]') is not None
    return rows, total, first, last, has_next


def _collect_race(session, event_id, race):
    race_id, expected = race["external_id"], race["total_count"]
    path = f"/race/{race_id}/"
    rows = []
    page_no = 1
    while True:
        html = _page(session, path if page_no == 1 else f"{path}?page={page_no}")
        page_rows, total, first, last, has_next = _protocol_page(html, event_id, race_id)
        if not page_rows or (total is not None and total != expected):
            raise PilotRejected("ПроБЕГ result count differs from the event card")
        if first != len(rows) + 1 or last != len(rows) + len(page_rows) or last > expected:
            raise PilotRejected("ПроБЕГ results page is out of sequence")
        rows.extend(page_rows)
        if len(rows) == expected:
            if has_next:
                raise PilotRejected("ПроБЕГ protocol has unexpected additional pages")
            break
        if total is None:
            raise PilotRejected("Missing ПроБЕГ pagination metadata")
        page_no += 1

    seen_ids = set()
    for row in rows:
        if row["bib"]:
            ident = f"bib:{row['bib']}"
        elif row["source_profile_id"]:
            ident = f"profile:{row['source_profile_id']}"
        elif row["full_name_raw"]:
            identity = [row[key] for key in ("full_name_raw", "gender", "birth_year", "city")]
            key = "|".join(str(part or "").casefold().replace("ё", "е") for part in identity)
            ident = f"participant:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"
        else:
            raise PilotRejected("Missing stable ПроБЕГ participant identity")
        if ident in seen_ids:
            raise PilotRejected("Duplicate ПроБЕГ participant identity")
        seen_ids.add(ident)
        row["external_participant_id"] = ident
        row["distance_km"] = race["distance_km"]

    times = [
        row["chip_time_s"]
        for row in sorted(
            (row for row in rows if row["status"] == "FIN" and row["place_abs"] is not None),
            key=lambda row: (row["place_abs"], row["chip_time_s"]),
        )
    ]
    if not times or times != sorted(times):
        raise PilotRejected("ПроБЕГ finishing times are inconsistent with the published places")
    # The result column is net time when the protocol supplies a separate
    # gun time. Without a second time, the timing method is unspecified.
    race["place_by"] = "chip"
    return {"race": race, "rows": rows}


def fetch_event(event_code: str) -> dict:
    """Fetch one event by its numeric event ID without writing to the database."""
    if not isinstance(event_code, str) or not re.fullmatch(r"[1-9][0-9]{0,17}", event_code):
        raise PilotRejected("Invalid ПроБЕГ event ID")
    with requests.Session() as session:
        try:
            html = _page(session, f"/event/{event_code}/")
            comp, races = _event_data(html, event_code)
            return {
                "competition": comp,
                "races": [_collect_race(session, event_code, race) for race in races.values()],
            }
        except PilotRejected:
            raise
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {400, 401, 403, 404, 410}:
                raise PilotRejected(f"ПроБЕГ returned HTTP {exc.response.status_code}") from exc
            raise
        except (TypeError, ValueError) as exc:
            raise PilotRejected("Invalid or incomplete ПроБЕГ response") from exc

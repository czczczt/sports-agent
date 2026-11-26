"""Import official Orgeo attachments and diagnose unsupported Live exports."""

import re
from datetime import date, datetime
from html.parser import HTMLParser

import requests
from bs4 import BeautifulSoup

from app.pipeline.errors import PilotRejected
from app.pipeline.orgeo_pdf import read_report, reconcile_reports

BASE = "https://orgeo.ru"
EVENT_CODE = r"[A-Za-z0-9_-]{1,64}"
NUMERIC_ID = r"[1-9][0-9]{0,17}"
MANUAL = "use the organizer's final protocol for manual import"
MAX_PDF_BYTES = 8 * 1024 * 1024


class _EventLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.event_ids = set()
        self.live_codes = set()
        self.live = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        href = attrs.get("href") or ""
        if tag == "link" and attrs.get("itemprop") == "url":
            match = re.fullmatch(rf"https?://orgeo\.ru/event/({NUMERIC_ID})", href)
            if match:
                self.event_ids.add(match[1])
        if tag == "a":
            root = re.fullmatch(rf"/live/#/({EVENT_CODE})", href)
            if root:
                self.live_codes.add(root[1])
            match = re.fullmatch(rf"/live/#/({EVENT_CODE})/({NUMERIC_ID})", href)
            if match:
                self.live.add(match.groups())


def _get(session: requests.Session, path: str, *, stream: bool = False) -> requests.Response:
    try:
        response = session.get(
            f"{BASE}{path}",
            timeout=(5, 15),
            allow_redirects=False,
            stream=stream,
        )
    except requests.RequestException as exc:
        raise PilotRejected(f"Orgeo is unreachable; {MANUAL}") from exc
    if response.status_code != 200:
        if stream:
            response.close()
        raise PilotRejected(f"Orgeo returned HTTP {response.status_code}; {MANUAL}")
    return response


def _official_paths(page: BeautifulSoup, event_id: str) -> list[str]:
    pattern = rf"/files/event/file/{event_id}_[a-f0-9]{{10}}\.[a-z0-9]+"
    return list(
        dict.fromkeys(
            link["href"]
            for link in page.find_all("a", href=True)
            if isinstance(link["href"], str)
            and re.fullmatch(pattern, link["href"], re.I)
            and " ".join(link.stripped_strings).casefold() in {"официальные результаты", "итоговый протокол"}
        )
    )


def _download_pdf(session: requests.Session, path: str) -> bytes:
    content = bytearray()
    try:
        with _get(session, path, stream=True) as response:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if len(content) + len(chunk) > MAX_PDF_BYTES:
                    raise PilotRejected("Orgeo official PDF exceeds the size limit")
                content.extend(chunk)
    except requests.RequestException as exc:
        raise PilotRejected(f"Orgeo official PDF download failed; {MANUAL}") from exc
    return bytes(content)


def _fetch_official(
    session: requests.Session,
    page: BeautifulSoup,
    event_id: str,
    paths: list[str],
) -> dict[str, object]:
    if len(paths) != 2 or any(not path.lower().endswith(".pdf") for path in paths):
        raise PilotRejected(f"Orgeo official attachment layout is unsupported; {MANUAL}")
    metadata = page.select('[itemtype$="/SportsEvent"]')
    if len(metadata) != 1:
        raise PilotRejected("Orgeo official event metadata is ambiguous")
    values = {}
    for key in ("name", "startDate", "endDate"):
        nodes = metadata[0].find_all("meta", attrs={"itemprop": key}, recursive=False)
        if len(nodes) != 1 or not isinstance(nodes[0].get("content"), str):
            raise PilotRejected(f"Missing or ambiguous Orgeo event {key}")
        values[key] = nodes[0]["content"].strip()
    try:
        start, end = (datetime.fromisoformat(values[key]).date() for key in ("startDate", "endDate"))
    except ValueError as exc:
        raise PilotRejected("Orgeo event dates are invalid") from exc
    if not values["name"] or end < start or end > date.today():
        raise PilotRejected("Orgeo event is missing a title or has not ended")

    reports = {}
    for path in paths:
        report = read_report(_download_pdf(session, path), BASE + path, values["name"])
        reports[report.kind] = report
    if set(reports) != {"absolute", "category"}:
        raise PilotRejected("Orgeo needs both absolute and category official protocols")
    absolute, category = reports["absolute"], reports["category"]
    if absolute.day != category.day or not start <= absolute.day <= end:
        raise PilotRejected("Orgeo official protocol date disagrees with the event")
    return {
        "competition": {
            "external_id": event_id,
            "code": event_id,
            "title": values["name"],
            "date_begin": absolute.day.isoformat(),
            "date_end": absolute.day.isoformat(),
            "sport": "run",
            "url": f"{BASE}/event/info/{event_id}",
        },
        "races": reconcile_reports(absolute, category),
    }


def fetch_event(event_code: str) -> dict[str, object]:
    if not isinstance(event_code, str) or not re.fullmatch(EVENT_CODE, event_code):
        raise PilotRejected("Invalid Orgeo event ID")

    with requests.Session() as session:
        page = _EventLinks()
        html = _get(session, f"/event/info/{event_code}").text
        page.feed(html)
        if len(page.event_ids) != 1:
            raise PilotRejected(f"Orgeo event identity could not be verified; {MANUAL}")
        event_id = next(iter(page.event_ids))
        if event_code.isascii() and event_code.isdecimal() and event_code != event_id:
            raise PilotRejected(f"Orgeo event identity could not be verified; {MANUAL}")
        soup = BeautifulSoup(html, "html.parser")
        paths = _official_paths(soup, event_id)
        if paths:
            return _fetch_official(session, soup, event_id, paths)
        allowed_codes = {event_code, event_id}
        if len(page.live_codes) == 1:
            allowed_codes.update(page.live_codes)
        sub_ids = {sub_id for code, sub_id in page.live if code in allowed_codes}
        if not sub_ids:
            raise PilotRejected(f"Orgeo has no public Live JSON protocol for this event; {MANUAL}")

        # Orgeo exports a dictionary indexed by bib for each published Live
        # start. Even a past broadcast can contain only the start list.
        for sub_id in sorted(sub_ids, key=int):
            path = f"/event/export/event_id/{event_id}/sub_id/{sub_id}/format/json"
            try:
                rows = _get(session, path).json()
            except requests.exceptions.JSONDecodeError as exc:
                raise PilotRejected(f"Orgeo Live export is not valid JSON; {MANUAL}") from exc
            if (
                not isinstance(rows, dict)
                or not rows
                or any(
                    not isinstance(row, dict)
                    or row.get("bib") != bib
                    or row.get("result_status") in (None, "", "22", "23", "99")
                    for bib, row in rows.items()
                )
            ):
                raise PilotRejected(f"Orgeo Live export is incomplete for start {sub_id}; {MANUAL}")

    # The Live frontend's badge is calendar-driven. Its disappearance does
    # not certify an official protocol, and the export carries no final flag.
    raise PilotRejected(f"Orgeo Live JSON does not certify final results; {MANUAL}")

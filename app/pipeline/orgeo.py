"""Diagnose Orgeo Live exports and direct final protocols to manual import."""

import re
from html.parser import HTMLParser

import requests

from app.pipeline.errors import PilotRejected
from parser_running.request_pacing import pace_request

BASE = "https://orgeo.ru"
EVENT_CODE = r"[A-Za-z0-9_-]{1,64}"
NUMERIC_ID = r"[1-9][0-9]{0,17}"
MANUAL = "use the organizer's final protocol for manual import"


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


def _get(session, path):
    try:
        pace_request(BASE)
        response = session.get(f"{BASE}{path}", timeout=(5, 15), allow_redirects=False)
    except requests.RequestException as exc:
        raise PilotRejected(f"Orgeo is unreachable; {MANUAL}") from exc
    if response.status_code != 200:
        raise PilotRejected(f"Orgeo returned HTTP {response.status_code}; {MANUAL}")
    return response


def fetch_event(event_code: str) -> dict:
    if not isinstance(event_code, str) or not re.fullmatch(EVENT_CODE, event_code):
        raise PilotRejected("Invalid Orgeo event ID")

    with requests.Session() as session:
        page = _EventLinks()
        page.feed(_get(session, f"/event/info/{event_code}").text)
        if len(page.event_ids) != 1:
            raise PilotRejected(f"Orgeo event identity could not be verified; {MANUAL}")
        event_id = next(iter(page.event_ids))
        if event_code.isascii() and event_code.isdecimal() and event_code != event_id:
            raise PilotRejected(f"Orgeo event identity could not be verified; {MANUAL}")
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
            if (not isinstance(rows, dict) or not rows
                    or any(not isinstance(row, dict) or row.get("bib") != bib
                           or row.get("result_status") in (None, "", "22", "23", "99")
                           for bib, row in rows.items())):
                raise PilotRejected(f"Orgeo Live export is incomplete for start {sub_id}; {MANUAL}")

    # The Live frontend's badge is calendar-driven. Its disappearance does
    # not certify an official protocol, and the export carries no final flag.
    raise PilotRejected(f"Orgeo Live JSON does not certify final results; {MANUAL}")

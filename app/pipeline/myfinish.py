"""Check the public MyFinish protocol endpoint without publishing live data."""

import re
from time import time
from uuid import uuid4

import requests

from app.pipeline.errors import PilotRejected

BASE = "https://new.myfinish.info"
DATA_URL = "https://myfinish.info/php/gate_online.php"
MANUAL = "request the final protocol from the organizer for manual import"


def fetch_event(event_code: str) -> dict:
    if not isinstance(event_code, str) or not re.fullmatch(r"[1-9][0-9]{0,17}", event_code):
        raise PilotRejected("Invalid MyFinish event ID")

    # The public frontend requests d=2 for the class list. A reachable HTML
    # shell or catalog does not establish access to the protocol data.
    try:
        response = requests.get(
            DATA_URL,
            params={"evid": event_code, "d": 2, "U": int(time())},
            headers={"Origin": BASE, "X-Device-ID": str(uuid4())},
            timeout=(5, 15),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise PilotRejected(f"MyFinish protocol data is unreachable; {MANUAL}") from exc
    if response.status_code != 200:
        raise PilotRejected(f"MyFinish protocol data returned HTTP {response.status_code}; {MANUAL}")
    raise PilotRejected(f"MyFinish final protocol format is unverified; {MANUAL}")

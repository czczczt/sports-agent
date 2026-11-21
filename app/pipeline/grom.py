"""Fetch a historical Grom event using its RaceResult HTML protocol."""

import re
from datetime import date
from time import monotonic, sleep

import requests

from app.pipeline.errors import PilotRejected
from parser_running.grom import BASE, GromConnector
from parser_running.http_cache import UA


def fetch_event(event_code: str) -> dict:
    if not isinstance(event_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_code):
        raise PilotRejected("Invalid Grom event code")

    with requests.Session() as session:
        session.headers.update(UA)

        next_request = 0.0

        def get(_source, url):
            nonlocal next_request
            sleep(max(0, next_request - monotonic()))
            next_request = monotonic() + 0.5
            response = session.get(url, timeout=(5, 15), allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200:
                raise PilotRejected("Unexpected Grom response")
            response.encoding = "utf-8"
            return response.text

        connector = GromConnector(get=get)
        comp = {"external_id": event_code, "code": event_code, "url": f"{BASE}/results/{event_code}"}
        try:
            protocols = connector.races(comp)
            if (not protocols or comp["title"] == event_code
                    or date.fromisoformat(comp["date_begin"]) >= date.today()):
                raise PilotRejected("Grom event has no historical protocols")

            races, seen = [], set()
            for race in protocols:
                path = race["_path"]
                if (not re.fullmatch(r"[A-Za-z0-9%.,_~+!()-]+", path) or path in {".", ".."}
                        or "/" in race["external_id"] or race["external_id"] in {".", ".."}
                        or race["external_id"] in seen):
                    raise PilotRejected("Invalid or duplicate Grom discipline")
                seen.add(race["external_id"])
                rows, total = connector.results(comp, race)
                if not rows or any(row["external_participant_id"] in ("", "None") for row in rows):
                    raise PilotRejected("Grom protocol is empty or missing participant IDs")
                race["total_count"] = total
                race["url"] = f"{comp['url']}/discipline/{race.pop('_path')}"
                races.append({"race": race, "rows": rows})
        except PilotRejected:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise PilotRejected("Invalid or incomplete Grom response") from exc
        sports = {item["race"]["sport"] for item in races}
        comp["sport"] = next(iter(sports)) if len(sports) == 1 else "mixed"
        return {"competition": comp, "races": races}

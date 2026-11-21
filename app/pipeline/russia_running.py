import re

from app.pipeline.errors import PilotRejected
from app.pipeline.validation import validate_event
from parser_running.rr_platform import RRConnector

SPORTS = {
    "run": "run",
    "ski": "ski",
    "ski-race": "ski",
    "ski-biathlon": "ski",
    "skiing": "ski",
    "crosscountryskiing": "ski",
    "triathlon": "triathlon",
    "trail": "trail",
}
SKI_SOURCES = {"legkovrace", "pionercup"}


def fetch_event(event_code: str, *, source: str = "russiarunning") -> dict:
    """Read a final event from one configured RussiaRunning platform."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_code):
        raise PilotRejected("Invalid RR event code")
    connector = RRConnector(source)
    connector.cli.cache = False
    try:
        raw = connector.cli.get_event(event_code)
        default_sport = "ski" if source in SKI_SOURCES else "run"
        sport = SPORTS.get(str(raw.get("disciplineCode", default_sport)).casefold())
        if not raw.get("id") or not raw.get("title") or not sport:
            raise PilotRejected("Unknown or incomplete RR event")
        if source == "russiarunning" and sport != "run":
            raise PilotRejected("The RussiaRunning pilot accepts running events")
        base = connector.base_url.removesuffix("/api")
        url = f"{base}/{event_code}" if source == "timerman" else f"{base}/event/{event_code}/results"
        competition = {
            "external_id": raw["id"], "code": event_code, "title": raw["title"],
            "date_begin": raw["beginDate"], "date_end": raw.get("endDate"), "place": raw.get("place"),
            "address": raw.get("address"), "sport": sport, "url": url,
        }
        races = []
        for race in connector.races(competition, event=raw):
            race_sport = SPORTS.get(str(race.get("sport") or sport).casefold())
            if not race_sport or race["race_type"] != "individual":
                continue
            if source == "russiarunning" and race_sport != sport:
                continue
            options = connector.cli.race_options(race["external_id"])
            if options.get("isFinalProtocol") is not True:
                continue
            rows, total = connector.results(competition, race, options=options)
            if source == "russiarunning":
                if not race.get("distance_km"):
                    raise PilotRejected("Missing RussiaRunning distance")
                if any(row["gender"] not in {"M", "F"} for row in rows if row.get("full_name_raw")):
                    raise PilotRejected("Invalid RussiaRunning participant gender")
            if race_sport in {"ski", "triathlon"} and race.get("distance_km") == 0:
                race["distance_km"] = None
            race.update(total_count=total, source_discipline=race.get("sport"), sport=race_sport)
            races.append({"race": race, "rows": rows})
        event = {"competition": competition, "races": races}
        validate_event(event)
        return event
    except PilotRejected:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise PilotRejected("Invalid or incomplete RR response") from exc
    finally:
        connector.cli.s.close()

"""Bounded RussiaRunning collection. Database transactions belong to the caller."""

import math
import re
from datetime import date

from app.pipeline.errors import PilotRejected
from parser_running import store
from parser_running.normalize import km_to_m
from parser_running.rr_platform import RRConnector


def _validate(race, rows, total):
    if not rows or not isinstance(total, int) or isinstance(total, bool) or total != len(rows):
        raise PilotRejected("Empty or incomplete RussiaRunning protocol")
    ids = [str(row.get("external_participant_id") or "") for row in rows]
    if any(not pid for pid in ids) or len(set(ids)) != len(ids):
        raise PilotRejected("Missing or duplicate RussiaRunning participant ID")
    for row in rows:
        for field in ("chip_time_s", "gun_time_s"):
            value = row.get(field)
            if value is not None and (not math.isfinite(value) or value < 0 or (value == 0 and row['status'] == 'FIN')):
                raise PilotRejected("Invalid RussiaRunning time")
        for field, low, high in (("age", 0, 120), ("birth_year", 1900, date.today().year)):
            value = row.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high):
                raise PilotRejected(f"Invalid RussiaRunning {field}")
    # The API can interleave non-finishers and hide positions. Check the ordered
    # visible finishing protocol; concealed positions remain valid source data.
    visible = sorted((r for r in rows if r["status"] == "FIN" and r.get("place_abs")),
                     key=lambda r: r["place_abs"])
    checks = store.checks(visible, len(visible), race["place_by"])
    all_rows = store.checks(rows, total, race["place_by"])
    required = ("записей_как_заявлено", "пол_известен", "у_финишёров_есть_время", "статусы_известны")
    if not all(all_rows[key] for key in required) or (visible and not checks["время_растёт_с_местом"]):
        raise PilotRejected("RussiaRunning protocol failed consistency checks")


def fetch_event(event_code: str) -> object:
    """Fetch and validate exactly one event, without writing to the database."""
    if not isinstance(event_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_code):
        raise PilotRejected("Invalid RussiaRunning event code")
    connector = RRConnector("russiarunning")
    connector.cli.cache = False  # retries must see the current complete response
    try:
        raw = connector.cli.get_event(event_code)
        if not raw.get("id") or not raw.get("title") or raw.get("disciplineCode", "run") != "run":
            raise PilotRejected("Invalid RussiaRunning running event")
        date.fromisoformat(raw["beginDate"][:10])
        comp = {"external_id": raw["id"], "code": event_code, "title": raw["title"],
                "date_begin": raw["beginDate"], "date_end": raw.get("endDate"),
                "place": raw.get("place"), "address": raw.get("address"), "sport": "run",
                "url": f"https://results.russiarunning.com/event/{event_code}/results"}
        races, seen = [], set()
        for race in connector.races(comp, event=raw):
            if race.get("sport") != "run" or race["race_type"] != "individual":
                continue
            rid = str(race["external_id"])
            if not rid or rid in seen:
                raise PilotRejected("Duplicate RussiaRunning race")
            seen.add(rid)
            rows, total = connector.results(comp, race)
            if not race["is_final"]:
                continue
            distance = race.get("distance_km")
            if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or km_to_m(distance) is None:
                raise PilotRejected("Invalid RussiaRunning distance")
            _validate(race, rows, total)
            race["total_count"] = total
            races.append({"race": race, "rows": rows})
        if not races:
            raise PilotRejected("No final individual RussiaRunning protocols")
        return {"competition": comp, "races": races}
    except PilotRejected:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise PilotRejected("Invalid or incomplete RussiaRunning response") from exc
    finally:
        connector.cli.s.close()


def save_event(connection, event) -> int:
    """Validate the full event before persisting in the caller transaction."""
    from app.pipeline.russia_running_repository import save_event as persist_event

    for item in event["races"]:
        _validate(item["race"], item["rows"], item["race"]["total_count"])
    return persist_event(connection, event)

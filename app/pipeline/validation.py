"""Read-side checks shared by background source adapters."""
import math
from datetime import date

from app.pipeline.errors import PilotRejected
from parser_running import store
from parser_running.normalize import km_to_m


def _validate_protocol(race: dict, rows: list[dict]) -> None:
    total = race.get("total_count")
    if not rows or (total is not None and (type(total) is not int or total != len(rows))):
        raise PilotRejected("Empty or incomplete source protocol")
    ids = [str(row.get("external_participant_id") or "").strip() for row in rows]
    if not all(ids) or len(set(ids)) != len(ids):
        raise PilotRejected("Missing or duplicate source participant ID")
    for row in rows:
        points = row.get("toplist_points")
        if points is not None and (type(points) not in (int, float) or not math.isfinite(points) or points < 0):
            raise PilotRejected("Invalid TopList reference points")
        for field in ("chip_time_s", "gun_time_s", "official_time_s"):
            value = row.get(field)
            if value is not None and (
                type(value) not in (int, float) or not math.isfinite(value)
                or value < 0 or (value == 0 and row["status"] == "FIN")
            ):
                raise PilotRejected("Invalid source time")
        for field, low, high in (("age", 0, 120), ("birth_year", 1900, date.today().year)):
            value = row.get(field)
            if value is not None and (type(value) is not int or not low <= value <= high):
                raise PilotRejected(f"Invalid source {field}")
    place_by = race["place_by"]
    if place_by == "official" or race.get("source_discipline") == "ski-biathlon":
        # Apply the existing checks to the official clock without replacing source timings.
        place_by = "gun"
        rows = [{**row, "gun_time_s": row.get("official_time_s")} for row in rows]
    visible = sorted(
        (row for row in rows if row["status"] == "FIN" and row.get("place_abs")),
        key=lambda row: row["place_abs"],
    )
    checks = store.checks(rows, total, place_by)
    expected = ("записей_как_заявлено", "статусы_известны", "у_финишёров_есть_время")
    if not all(checks[k] for k in expected) or (
        visible and not store.checks(visible, len(visible), place_by)["время_растёт_с_местом"]
    ):
        raise PilotRejected("Source protocol failed consistency checks")


def validate_event(event: dict) -> None:
    comp = event["competition"]
    if not comp.get("external_id") or not comp.get("title"):
        raise PilotRejected("Missing source event identity")
    date.fromisoformat(comp["date_begin"][:10])
    if not event["races"]:
        raise PilotRejected("No final source protocols")
    seen = set()
    for item in event["races"]:
        race = item["race"]
        code = str(race.get("external_id") or "")
        if not code or code in seen:
            raise PilotRejected("Missing or duplicate source race ID")
        seen.add(code)
        if race.get("sport") not in {"run", "ski", "triathlon", "trail"}:
            raise PilotRejected("Unknown source sport")
        if race.get("is_final") is False:
            raise PilotRejected("Source protocol is preliminary")
        if race.get("place_by") not in {"chip", "gun", "official"}:
            raise PilotRejected("Unknown source timing scale")
        distance = race.get("distance_km")
        if distance is not None and (
            type(distance) not in (int, float) or not math.isfinite(distance) or not km_to_m(distance)
        ):
            raise PilotRejected("Invalid source distance")
        elevation = race.get("elevation_gain_m")
        if elevation is not None and (
            type(elevation) not in (int, float) or not math.isfinite(elevation) or elevation < 0
        ):
            raise PilotRejected("Invalid source elevation gain")
        _validate_protocol(race, item["rows"])

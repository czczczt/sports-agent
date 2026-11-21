from typing import Any

from app.models import (
    CompetitionDistribution,
    DistributionBin,
    EventItem,
    RaceItem,
    RaceProtocolItem,
)
from app.modules.events.web_repository import EventsWebRepository
from app.services.athlete_service import (
    clean_club,
    format_pace,
    format_time,
)


async def list_events(
    conn: EventsWebRepository,
    query: str | None = None,
    title: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    city: str | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[EventItem]:
    rows = await conn.list_events(
        query or title, date_from, date_to, city, source, limit, offset
    )

    races_by_event = await conn.races_for_events([r["id"] for r in rows])
    events = []
    for r in rows:
        eid = r["id"]
        races_rows = races_by_event.get(eid, [])

        races = [
            RaceItem(
                id=ra["id"],
                name_raw=ra["name_raw"] or "Дистанция",
                norm_distance=ra["norm_distance"],
                distance_m=ra["distance_m"],
                distance_km_raw=ra["distance_km_raw"],
                total_count=ra["total_count"],
            )
            for ra in races_rows
        ]

        events.append(
            EventItem(
                id=r["id"],
                source_id=r["source_id"],
                source_name=r["source_name"],
                title=r["title"] or "Беговой старт",
                date_begin=r["date_begin"],
                date_end=r["date_end"],
                place=r["place"],
                address=r["address"],
                races=races,
            )
        )

    return events


async def get_event_by_id(conn: EventsWebRepository, event_id: int) -> EventItem | None:
    row = await conn.event(event_id)
    if not row:
        return None

    races_rows = await conn.event_races(event_id)

    races = [
        RaceItem(
            id=ra["id"],
            name_raw=ra["name_raw"] or "Дистанция",
            norm_distance=ra["norm_distance"],
            distance_m=ra["distance_m"],
            distance_km_raw=ra["distance_km_raw"],
            total_count=ra["total_count"],
        )
        for ra in races_rows
    ]

    return EventItem(
        id=row["id"],
        source_id=row["source_id"],
        source_name=row["source_name"],
        title=row["title"] or "Беговой старт",
        date_begin=row["date_begin"],
        date_end=row["date_end"],
        place=row["place"],
        address=row["address"],
        races=races,
    )


def _row_to_protocol_item(r: dict, dist_m: int | None) -> RaceProtocolItem:
    time_s = r["chip_time_s"] if r["chip_time_s"] is not None else r["gun_time_s"]
    raw_age = r["age"]
    if raw_age == 0 or (raw_age is None and r["birth_year"] == 2026):
        display_age = 1
    else:
        display_age = raw_age
    is_employee = bool(r.get("athlete_id"))
    pts = r.get("points")
    return RaceProtocolItem(
        result_id=r["result_id"],
        athlete_id=r["athlete_id"] if is_employee else None,
        bib=r["bib"] if is_employee else None,
        full_name_raw=r["full_name_raw"] if is_employee else "Участник",
        gender=r["gender"],
        age=display_age,
        birth_year=r["birth_year"],
        club_raw=clean_club(r["club_raw"]) if is_employee else None,
        place_abs=r["place_abs"],
        place_gender=r["place_gender"],
        chip_time_s=r["chip_time_s"],
        gun_time_s=r["gun_time_s"],
        time_formatted=format_time(time_s),
        pace_formatted=format_pace(time_s, dist_m),
        status=r["status"],
        points=round(float(pts), 1) if is_employee and pts is not None else None,
    )


async def get_race_results(
    conn: EventsWebRepository,
    race_id: int,
    search_query: str | None = None,
    limit: int = 300,
    offset: int = 0,
    employees_only: bool = False,
) -> list[RaceProtocolItem]:
    race = await conn.race(race_id)
    dist_m = race["distance_m"] if race else None
    rows = await conn.protocol(
        race_id,
        search_query,
        limit,
        offset,
        employees_only=employees_only,
    )

    return [_row_to_protocol_item(r, dist_m) for r in rows]


async def get_athlete_race_result(
    conn: EventsWebRepository, race_id: int, athlete_id: int
) -> RaceProtocolItem | None:
    race = await conn.race_distance(race_id)
    dist_m = race["distance_m"] if race else None

    row = await conn.athlete_result(race_id, athlete_id)

    if not row:
        return None
    return _row_to_protocol_item(row, dist_m)


async def get_race_rating_leaders(
    conn: EventsWebRepository,
    race_id: int,
    limit: int = 3,
) -> list[dict]:
    rows = await conn.rating_leaders(race_id, limit)
    return [dict(row) for row in rows]


async def get_race_competition(
    conn: EventsWebRepository, race_id: int, athlete_id: int | None = None
) -> CompetitionDistribution | None:
    race = await conn.race(race_id)
    if not race:
        return None

    rows = await conn.finishers(race_id)

    if not rows:
        return None

    times = []
    athlete_res = None
    for r in rows:
        t = r["chip_time_s"] if r["chip_time_s"] is not None else r["gun_time_s"]
        if t and t > 0:
            times.append(t)
            if athlete_id and r["athlete_id"] == athlete_id:
                athlete_res = {
                    "result_id": r["id"],
                    "place_abs": r["place_abs"],
                    "time_s": t,
                    "time_formatted": format_time(t),
                    "pace_formatted": format_pace(t, race["distance_m"]),
                    "status": "FIN",
                }

    if athlete_id and not athlete_res:
        non_fin_row = await conn.athlete_status(race_id, athlete_id)
        if non_fin_row:
            status = non_fin_row["status"]
            athlete_res = {
                "result_id": non_fin_row["id"],
                "place_abs": status,
                "time_s": 0.0,
                "time_formatted": status,
                "pace_formatted": status,
                "status": status,
                "summary_text": f"Статус на дистанции: {status}",
            }

    if not times:
        return None

    times.sort()
    total_fin = len(times)
    min_t = times[0]
    max_t = times[-1]

    p25 = times[int(0.25 * total_fin)]
    med = times[int(0.50 * total_fin)]
    p75 = times[int(0.75 * total_fin)]

    if athlete_res and isinstance(athlete_res.get("place_abs"), (int, float)):
        pl = athlete_res["place_abs"]
        pct = round(100.0 * (total_fin - pl + 1) / total_fin, 1)
        top_pct = round(100.0 * pl / total_fin, 1)
        athlete_res["percentile"] = pct
        athlete_res["top_percent"] = top_pct
        athlete_res["summary_text"] = (
            f"Финишировал на {pl} месте из {total_fin} участников (топ {top_pct}% протокола)."
        )
    elif athlete_res and athlete_res.get("status") in ("DNS", "DNF", "DSQ", "NC"):
        status = athlete_res["status"]
        athlete_res["percentile"] = None
        athlete_res["top_percent"] = None
        athlete_res["summary_text"] = f"Статус на дистанции: {status}"

    num_bins = 10
    step = (max_t - min_t) / num_bins if max_t > min_t else 1.0
    bins: list[DistributionBin] = []

    for i in range(num_bins):
        b_start = min_t + i * step
        b_end = min_t + (i + 1) * step
        count = sum(
            1
            for t in times
            if b_start <= t < b_end or (i == num_bins - 1 and t == b_end)
        )
        label = f"{format_time(b_start)} - {format_time(b_end)}"
        bins.append(
            DistributionBin(
                bin_start_s=round(b_start, 1),
                bin_end_s=round(b_end, 1),
                label=label,
                count=count,
            )
        )

    return CompetitionDistribution(
        race_id=race["id"],
        race_name=race["name_raw"] or "Дистанция",
        norm_distance=race["norm_distance"],
        distance_m=race["distance_m"],
        total_finishers=total_fin,
        min_time_s=min_t,
        max_time_s=max_t,
        median_time_s=med,
        p25_time_s=p25,
        p75_time_s=p75,
        distribution_bins=bins,
        athlete_result=athlete_res,
    )


async def get_race_page(
    conn: EventsWebRepository,
    race_id: int,
    search_query: str | None = None,
    athlete_id: int | None = None,
    limit: int = 300,
    employees_only: bool = False,
) -> dict[str, Any] | None:
    race_row = await conn.race(race_id)
    if not race_row:
        return None

    event = await get_event_by_id(conn, event_id=race_row["event_id"])
    results = await get_race_results(
        conn,
        race_id=race_id,
        search_query=search_query,
        limit=limit,
        offset=0,
        employees_only=employees_only,
    )

    pinned = None
    if athlete_id and not search_query:
        athlete_item = await get_athlete_race_result(
            conn, race_id=race_id, athlete_id=athlete_id
        )
        if athlete_item and (
            athlete_item.place_abs is None or athlete_item.place_abs > 100
        ):
            pinned = athlete_item
            results = [r for r in results if r.athlete_id != athlete_id]

    sber_count = await conn.sber_finishers_count(race_id)

    return {
        "race": {**race_row, "name_raw": race_row["name_raw"] or "Дистанция"},
        "event": event,
        "results": results,
        "pinned_athlete_result": pinned,
        "competition": await get_race_competition(
            conn, race_id=race_id, athlete_id=athlete_id
        ),
        "rating_leaders": await get_race_rating_leaders(conn, race_id=race_id),
        "sber_finishers_count": sber_count,
    }

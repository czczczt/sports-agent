import sqlite3
from typing import List, Optional, Dict, Any
from app.models import (
    EventItem, RaceItem, RaceProtocolItem, CompetitionDistribution, DistributionBin
)
from app.services.athlete_service import format_time, format_pace, normalize_term


def list_events(
    conn: sqlite3.Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    city: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[EventItem]:
    """Возвращает каталог стартов с фильтрами по дате, городу и площадке."""
    cur = conn.cursor()
    conditions = ["1=1"]
    params: List[Any] = []

    if date_from:
        conditions.append("e.date_begin >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("e.date_begin <= ?")
        params.append(date_to)
    if city:
        conditions.append("(e.place LIKE ? OR e.address LIKE ?)")
        city_pat = f"%{city}%"
        params.extend([city_pat, city_pat])
    if source:
        conditions.append("s.name = ?")
        params.append(source.lower())

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT 
            e.id, e.source_id, s.name AS source_name, e.title,
            e.date_begin, e.date_end, e.place, e.address
        FROM event e
        JOIN source s ON s.id = e.source_id
        WHERE {where_clause}
        ORDER BY e.date_begin DESC, e.id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = cur.execute(query, params).fetchall()

    events = []
    for r in rows:
        eid = r["id"]
        # Подгружаем дистанции старта
        races_rows = cur.execute("""
            SELECT id, name_raw, norm_distance, distance_m, distance_km_raw, total_count
            FROM race
            WHERE event_id = ?
            ORDER BY distance_m ASC, id ASC
        """, (eid,)).fetchall()

        races = [
            RaceItem(
                id=ra["id"],
                name_raw=ra["name_raw"] or "Дистанция",
                norm_distance=ra["norm_distance"],
                distance_m=ra["distance_m"],
                distance_km_raw=ra["distance_km_raw"],
                total_count=ra["total_count"]
            )
            for ra in races_rows
        ]

        events.append(EventItem(
            id=r["id"],
            source_id=r["source_id"],
            source_name=r["source_name"],
            title=r["title"] or "Беговой старт",
            date_begin=r["date_begin"],
            date_end=r["date_end"],
            place=r["place"],
            address=r["address"],
            races=races
        ))

    return events


def get_event_by_id(conn: sqlite3.Connection, event_id: int) -> Optional[EventItem]:
    """Возвращает информацию о старте и всех его дистанциях."""
    cur = conn.cursor()
    row = cur.execute("""
        SELECT 
            e.id, e.source_id, s.name AS source_name, e.title,
            e.date_begin, e.date_end, e.place, e.address
        FROM event e
        JOIN source s ON s.id = e.source_id
        WHERE e.id = ?
    """, (event_id,)).fetchone()
    if not row:
        return None

    races_rows = cur.execute("""
        SELECT id, name_raw, norm_distance, distance_m, distance_km_raw, total_count
        FROM race
        WHERE event_id = ?
        ORDER BY distance_m ASC, id ASC
    """, (event_id,)).fetchall()

    races = [
        RaceItem(
            id=ra["id"],
            name_raw=ra["name_raw"] or "Дистанция",
            norm_distance=ra["norm_distance"],
            distance_m=ra["distance_m"],
            distance_km_raw=ra["distance_km_raw"],
            total_count=ra["total_count"]
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
        races=races
    )


def get_race_results(
    conn: sqlite3.Connection,
    race_id: int,
    search_query: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[RaceProtocolItem]:
    """Возвращает протокол дистанции с поиском по фамилии или стартовому номеру."""
    cur = conn.cursor()
    race = cur.execute("SELECT distance_m FROM race WHERE id = ?", (race_id,)).fetchone()
    dist_m = race["distance_m"] if race else None

    conditions = ["r.race_id = ?", "r.duplicate_of IS NULL"]
    params: List[Any] = [race_id]

    if search_query:
        sq = search_query.strip()
        if sq.isdigit():
            conditions.append("r.bib = ?")
            params.append(int(sq))
        else:
            norm = normalize_term(sq)
            conditions.append("(r.full_name_raw LIKE ? OR LOWER(r.full_name_raw) LIKE ?)")
            pat = f"%{norm}%"
            params.extend([f"%{sq}%", pat])

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT 
            r.id AS result_id,
            ral.athlete_id,
            r.bib,
            r.full_name_raw,
            r.gender,
            r.age,
            r.birth_year,
            r.club_raw,
            r.place_abs,
            r.place_gender,
            r.chip_time_s,
            r.gun_time_s,
            r.status
        FROM result r
        LEFT JOIN result_athlete ral ON ral.result_id = r.id
        WHERE {where_clause}
        ORDER BY 
            CASE WHEN r.status = 'FIN' THEN 0 ELSE 1 END,
            CASE WHEN r.place_abs IS NOT NULL THEN r.place_abs ELSE 999999 END ASC,
            r.chip_time_s ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = cur.execute(query, params).fetchall()

    items = []
    for r in rows:
        time_s = r["chip_time_s"] if r["chip_time_s"] is not None else r["gun_time_s"]
        items.append(RaceProtocolItem(
            result_id=r["result_id"],
            athlete_id=r["athlete_id"],
            bib=r["bib"],
            full_name_raw=r["full_name_raw"] or "Участник",
            gender=r["gender"],
            age=r["age"],
            birth_year=r["birth_year"],
            club_raw=r["club_raw"],
            place_abs=r["place_abs"],
            place_gender=r["place_gender"],
            chip_time_s=r["chip_time_s"],
            gun_time_s=r["gun_time_s"],
            time_formatted=format_time(time_s),
            pace_formatted=format_pace(time_s, dist_m),
            status=r["status"]
        ))
    return items


def get_race_competition(
    conn: sqlite3.Connection,
    race_id: int,
    athlete_id: Optional[int] = None
) -> Optional[CompetitionDistribution]:
    """
    Блок 'Конкуренция':
    - Распределение времен всех финишеров (гистограмма)
    - Положение выбранного спортсмена среди участников дистанции
    """
    cur = conn.cursor()
    race = cur.execute("""
        SELECT id, name_raw, norm_distance, distance_m 
        FROM race 
        WHERE id = ?
    """, (race_id,)).fetchone()
    if not race:
        return None

    rows = cur.execute("""
        SELECT r.id, r.chip_time_s, r.gun_time_s, r.place_abs, ral.athlete_id
        FROM result r
        LEFT JOIN result_athlete ral ON ral.result_id = r.id
        WHERE r.race_id = ?
          AND r.status = 'FIN'
          AND r.duplicate_of IS NULL
    """, (race_id,)).fetchall()

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
                }

    if not times:
        return None

    times.sort()
    total_fin = len(times)
    min_t = times[0]
    max_t = times[-1]

    # Квантили
    p25 = times[int(0.25 * total_fin)]
    med = times[int(0.50 * total_fin)]
    p75 = times[int(0.75 * total_fin)]

    # Если найден результат спортсмена, считаем его процентиль
    if athlete_res and athlete_res.get("place_abs"):
        pl = athlete_res["place_abs"]
        pct = round(100.0 * (total_fin - pl + 1) / total_fin, 1)
        top_pct = round(100.0 * pl / total_fin, 1)
        athlete_res["percentile"] = pct
        athlete_res["top_percent"] = top_pct
        athlete_res["summary_text"] = f"Финишировал на {pl} месте из {total_fin} участников (топ {top_pct}% протокола)."

    # Построение 10 корзин распределения (бинов гистограммы)
    num_bins = 10
    step = (max_t - min_t) / num_bins if max_t > min_t else 1.0
    bins: List[DistributionBin] = []

    for i in range(num_bins):
        b_start = min_t + i * step
        b_end = min_t + (i + 1) * step
        count = sum(1 for t in times if b_start <= t < b_end or (i == num_bins - 1 and t == b_end))
        label = f"{format_time(b_start)} - {format_time(b_end)}"
        bins.append(DistributionBin(
            bin_start_s=round(b_start, 1),
            bin_end_s=round(b_end, 1),
            label=label,
            count=count
        ))

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
        athlete_result=athlete_res
    )

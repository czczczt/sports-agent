import sqlite3
import re
from typing import List, Optional, Dict, Any
from app.models import (
    EventItem, RaceItem, RaceProtocolItem, CompetitionDistribution, DistributionBin
)
from app.services.athlete_service import format_time, format_pace, normalize_term, clean_club


def list_events(
    conn: sqlite3.Connection,
    query: Optional[str] = None,
    title: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    city: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[EventItem]:
    """Возвращает каталог стартов с фильтрами по названию забега, дате, городу и площадке."""
    cur = conn.cursor()
    conditions = ["1=1"]
    params: List[Any] = []

    search_query = (query or title or "").strip()
    if search_query:
        q_words = [w for w in re.findall(r"\w+", search_query.lower().replace("ё", "е")) if w]
        for w in q_words:
            w_pat = f"%{w}%"
            conditions.append(
                "(ru_lower(e.title) LIKE ? OR EXISTS (SELECT 1 FROM race r WHERE r.event_id = e.id AND ru_lower(r.name_raw) LIKE ?))"
            )
            params.extend([w_pat, w_pat])

    if date_from:
        clean_from = date_from.strip()[:10]
        conditions.append("substr(e.date_begin, 1, 10) >= ?")
        params.append(clean_from)
    if date_to:
        clean_to = date_to.strip()[:10]
        conditions.append("substr(e.date_begin, 1, 10) <= ?")
        params.append(clean_to)
    if city:
        clean_city = city.strip()
        conditions.append("match_city(?, e.place, e.address)")
        params.append(clean_city)
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


def _row_to_protocol_item(r: sqlite3.Row, dist_m: Optional[int]) -> RaceProtocolItem:
    time_s = r["chip_time_s"] if r["chip_time_s"] is not None else r["gun_time_s"]
    raw_age = r["age"]
    if raw_age == 0 or (raw_age is None and r["birth_year"] == 2026):
        display_age = 1
    else:
        display_age = raw_age
    return RaceProtocolItem(
        result_id=r["result_id"],
        athlete_id=r["athlete_id"],
        bib=r["bib"],
        full_name_raw=r["full_name_raw"] or "Участник",
        gender=r["gender"],
        age=display_age,
        birth_year=r["birth_year"],
        club_raw=clean_club(r["club_raw"]),
        place_abs=r["place_abs"],
        place_gender=r["place_gender"],
        chip_time_s=r["chip_time_s"],
        gun_time_s=r["gun_time_s"],
        time_formatted=format_time(time_s),
        pace_formatted=format_pace(time_s, dist_m),
        status=r["status"]
    )


def get_race_results(
    conn: sqlite3.Connection,
    race_id: int,
    search_query: Optional[str] = None,
    limit: int = 300,
    offset: int = 0
) -> List[RaceProtocolItem]:
    """Возвращает протокол дистанции с поиском по фамилии или стартовому номеру."""
    cur = conn.cursor()
    race = cur.execute("SELECT distance_m FROM race WHERE id = ?", (race_id,)).fetchone()
    dist_m = race["distance_m"] if race else None

    conditions = ["r.race_id = ?", "r.duplicate_of IS NULL"]
    params: List[Any] = [race_id]

    try:
        conn.create_function("ru_lower", 1, lambda s: (s or "").lower().replace("ё", "е"))
    except Exception:
        pass

    if search_query:
        sq = search_query.strip()
        clean_num = re.sub(r"^[№#\s]+", "", sq)
        if clean_num.isdigit():
            conditions.append("(r.bib = ? OR a.name_key LIKE ?)")
            params.extend([int(clean_num), f"%{clean_num}%"])
        else:
            tokens = re.findall(r"[a-zа-я0-9]+", sq.lower().replace("ё", "е"))
            if tokens:
                for token in tokens:
                    pat = f"%{token}%"
                    conditions.append("(a.name_key LIKE ? OR ru_lower(r.full_name_raw) LIKE ?)")
                    params.extend([pat, pat])
            else:
                pat = f"%{sq.lower().replace('ё', 'е')}%"
                conditions.append("(a.name_key LIKE ? OR ru_lower(r.full_name_raw) LIKE ?)")
                params.extend([pat, pat])

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
        LEFT JOIN athlete a ON a.id = ral.athlete_id
        WHERE {where_clause}
        ORDER BY 
            CASE WHEN r.status = 'FIN' THEN 0 ELSE 1 END,
            CASE WHEN r.place_abs IS NOT NULL THEN r.place_abs ELSE 999999 END ASC,
            r.chip_time_s ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = cur.execute(query, params).fetchall()

    return [_row_to_protocol_item(r, dist_m) for r in rows]


def get_athlete_race_result(
    conn: sqlite3.Connection,
    race_id: int,
    athlete_id: int
) -> Optional[RaceProtocolItem]:
    """Находит результат конкретного спортсмена на данной дистанции (даже если он DNS/DNF)."""
    cur = conn.cursor()
    race = cur.execute("SELECT distance_m FROM race WHERE id = ?", (race_id,)).fetchone()
    dist_m = race["distance_m"] if race else None

    row = cur.execute("""
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
        JOIN result_athlete ral ON ral.result_id = r.id
        WHERE r.race_id = ? AND ral.athlete_id = ? AND r.duplicate_of IS NULL
        LIMIT 1
    """, (race_id, athlete_id)).fetchone()

    if not row:
        return None
    return _row_to_protocol_item(row, dist_m)


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
                    "status": "FIN"
                }

    # Если спортсмен не финишировал (DNS / DNF / DSQ), подгружаем его статус для бокового блока
    if athlete_id and not athlete_res:
        non_fin_row = cur.execute("""
            SELECT r.id, r.status, r.place_abs, r.chip_time_s, r.gun_time_s
            FROM result r
            JOIN result_athlete ral ON ral.result_id = r.id
            WHERE r.race_id = ? AND ral.athlete_id = ? AND r.duplicate_of IS NULL
            LIMIT 1
        """, (race_id, athlete_id)).fetchone()
        if non_fin_row:
            status = non_fin_row["status"]
            athlete_res = {
                "result_id": non_fin_row["id"],
                "place_abs": status,
                "time_s": 0.0,
                "time_formatted": status,
                "pace_formatted": status,
                "status": status,
                "summary_text": f"Статус на дистанции: {status}"
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
    if athlete_res and isinstance(athlete_res.get("place_abs"), (int, float)):
        pl = athlete_res["place_abs"]
        pct = round(100.0 * (total_fin - pl + 1) / total_fin, 1)
        top_pct = round(100.0 * pl / total_fin, 1)
        athlete_res["percentile"] = pct
        athlete_res["top_percent"] = top_pct
        athlete_res["summary_text"] = f"Финишировал на {pl} месте из {total_fin} участников (топ {top_pct}% протокола)."
    elif athlete_res and athlete_res.get("status") in ("DNS", "DNF", "DSQ", "NC"):
        status = athlete_res["status"]
        athlete_res["percentile"] = None
        athlete_res["top_percent"] = None
        athlete_res["summary_text"] = f"Статус на дистанции: {status}"

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

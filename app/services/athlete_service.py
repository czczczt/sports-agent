import sqlite3
import re
from typing import List, Optional, Dict, Any
from app.models import (
    AthleteCandidate, AthleteResultItem, PersonalBestItem,
    RatingPlaceholder, DynamicsPoint, AthleteSummaryResponse
)

# Словарь читаемых названий дистанций
DISTANCE_TITLES = {
    "60m": "60 м",
    "100m": "100 м",
    "200m": "200 м",
    "400m": "400 м",
    "800m": "800 м",
    "1000m": "1 000 м",
    "1500m": "1 500 м",
    "1mile": "1 миля (1 609 м)",
    "3000m": "3 000 м",
    "5000m": "5 000 м (5 км)",
    "10000m": "10 000 м (10 км)",
    "half_marathon": "Полумарафон (21.1 км)",
    "marathon": "Марафон (42.2 км)",
    "100k": "100 км",
    "24h": "Суточный бег (24 ч)",
}


def normalize_term(term: str) -> str:
    """Нормализует строку поиска: нижний регистр, замена ё -> е, удаление спецсимволов."""
    if not term:
        return ""
    s = term.lower().replace("ё", "е")
    tokens = re.findall(r"[a-zа-я0-9]+", s)
    return " ".join(tokens)


def format_time(seconds: Optional[float]) -> str:
    """Форматирует секунды в ЧЧ:ММ:СС или ММ:СС."""
    if seconds is None or seconds <= 0:
        return "-"
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_pace(time_s: Optional[float], dist_m: Optional[float]) -> str:
    """Вычисляет средний темп (мин:сек / км)."""
    if not time_s or not dist_m or dist_m <= 0 or time_s <= 0:
        return "-"
    pace_s = time_s / (dist_m / 1000.0)
    m = int(pace_s // 60)
    s = int(round(pace_s % 60))
    if s >= 60:
        m += 1
        s = 0
    return f"{m:02d}:{s:02d} /км"


def get_pace_seconds(time_s: Optional[float], dist_m: Optional[float]) -> Optional[float]:
    """Возвращает темп в секундах на 1 км."""
    if not time_s or not dist_m or dist_m <= 0 or time_s <= 0:
        return None
    return time_s / (dist_m / 1000.0)


def search_athletes(
    conn: sqlite3.Connection,
    last_name: str,
    birth_year: Optional[int] = None,
    limit: int = 50
) -> List[AthleteCandidate]:
    """
    Поиск спортсменов:
    - Регистронезависимо, замена е/ё.
    - Фильтрация по году рождения с допуском +- 1 год.
    """
    norm = normalize_term(last_name)
    if not norm:
        return []

    cur = conn.cursor()
    pattern = f"%{norm}%"

    if birth_year is not None:
        query = """
            SELECT id, display_name, birth_year, gender, city, region, club, starts_count, results_count
            FROM athlete
            WHERE name_key LIKE ?
              AND (birth_year IS NULL OR abs(birth_year - ?) <= 1)
            ORDER BY starts_count DESC, results_count DESC, id ASC
            LIMIT ?
        """
        rows = cur.execute(query, (pattern, birth_year, limit)).fetchall()
    else:
        query = """
            SELECT id, display_name, birth_year, gender, city, region, club, starts_count, results_count
            FROM athlete
            WHERE name_key LIKE ?
            ORDER BY starts_count DESC, results_count DESC, id ASC
            LIMIT ?
        """
        rows = cur.execute(query, (pattern, limit)).fetchall()

    return [
        AthleteCandidate(
            id=r["id"],
            display_name=r["display_name"],
            birth_year=r["birth_year"],
            gender=r["gender"],
            city=r["city"],
            region=r["region"],
            club=r["club"],
            starts_count=r["starts_count"],
            results_count=r["results_count"],
        )
        for r in rows
    ]


def get_athlete_by_id(conn: sqlite3.Connection, athlete_id: int) -> Optional[AthleteCandidate]:
    """Получает данные спортсмена по ID."""
    cur = conn.cursor()
    row = cur.execute("""
        SELECT id, display_name, birth_year, gender, city, region, club, starts_count, results_count
        FROM athlete
        WHERE id = ?
    """, (athlete_id,)).fetchone()
    if not row:
        return None
    return AthleteCandidate(
        id=row["id"],
        display_name=row["display_name"],
        birth_year=row["birth_year"],
        gender=row["gender"],
        city=row["city"],
        region=row["region"],
        club=row["club"],
        starts_count=row["starts_count"],
        results_count=row["results_count"],
    )


def get_athlete_results(conn: sqlite3.Connection, athlete_id: int) -> List[AthleteResultItem]:
    """Возвращает все завершенные результаты спортсмена."""
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT 
            r.id AS result_id,
            e.id AS event_id,
            e.title AS event_title,
            e.date_begin AS event_date,
            s.name AS source_name,
            ra.id AS race_id,
            ra.name_raw AS distance_name,
            ra.norm_distance,
            ra.distance_m,
            r.place_abs,
            r.place_gender,
            r.chip_time_s,
            r.gun_time_s,
            r.status,
            r.bib
        FROM result_athlete ral
        JOIN result r ON r.id = ral.result_id
        JOIN race ra ON ra.id = r.race_id
        JOIN event e ON e.id = ra.event_id
        JOIN source s ON s.id = e.source_id
        WHERE ral.athlete_id = ?
          AND r.status = 'FIN'
          AND r.duplicate_of IS NULL
        ORDER BY e.date_begin DESC, r.id DESC
    """, (athlete_id,)).fetchall()

    results = []
    for r in rows:
        time_s = r["chip_time_s"] if r["chip_time_s"] is not None else r["gun_time_s"]
        dist_m = r["distance_m"]
        results.append(AthleteResultItem(
            result_id=r["result_id"],
            event_id=r["event_id"],
            event_title=r["event_title"] or "Беговой старт",
            event_date=r["event_date"],
            source_name=r["source_name"],
            race_id=r["race_id"],
            distance_name=r["distance_name"] or "Дистанция",
            norm_distance=r["norm_distance"],
            distance_m=dist_m,
            place_abs=r["place_abs"],
            place_gender=r["place_gender"],
            chip_time_s=r["chip_time_s"],
            gun_time_s=r["gun_time_s"],
            time_formatted=format_time(time_s),
            pace_formatted=format_pace(time_s, dist_m),
            status=r["status"],
            bib=r["bib"]
        ))
    return results


def get_athlete_summary(conn: sqlite3.Connection, athlete_id: int) -> Optional[AthleteSummaryResponse]:
    """Формирует сводку по спортсмену: профиль, личные рекорды, динамику, рейтинг-заглушку."""
    athlete = get_athlete_by_id(conn, athlete_id)
    if not athlete:
        return None

    results = get_athlete_results(conn, athlete_id)

    # Вычисление личных рекордов (Personal Bests) по нормализованным дистанциям
    pb_dict: Dict[str, Dict[str, Any]] = {}
    for res in results:
        nd = res.norm_distance
        if not nd:
            continue
        time_s = res.chip_time_s if res.chip_time_s is not None else res.gun_time_s
        if time_s is None or time_s <= 0:
            continue
        if nd not in pb_dict or time_s < pb_dict[nd]["time_s"]:
            pb_dict[nd] = {
                "norm_distance": nd,
                "distance_title": DISTANCE_TITLES.get(nd, nd),
                "time_s": time_s,
                "time_formatted": format_time(time_s),
                "pace_formatted": format_pace(time_s, res.distance_m),
                "event_title": res.event_title,
                "event_date": res.event_date
            }

    # Порядок дистанций от коротких к длинным
    distance_order = [
        "60m", "100m", "200m", "400m", "800m", "1000m", "1500m", "1mile",
        "3000m", "5000m", "10000m", "half_marathon", "marathon", "100k", "24h"
    ]
    sorted_pbs = []
    for d in distance_order:
        if d in pb_dict:
            sorted_pbs.append(PersonalBestItem(**pb_dict[d]))
    for d, item in pb_dict.items():
        if d not in distance_order:
            sorted_pbs.append(PersonalBestItem(**item))

    # Формирование точек динамики для графика (по возрастанию даты)
    dynamics: List[DynamicsPoint] = []
    sorted_by_date = sorted([r for r in results if r.event_date], key=lambda x: x.event_date or "")
    for r in sorted_by_date:
        time_s = r.chip_time_s if r.chip_time_s is not None else r.gun_time_s
        if time_s:
            dynamics.append(DynamicsPoint(
                date=r.event_date[:10] if r.event_date else "",
                event_title=r.event_title,
                norm_distance=r.norm_distance,
                distance_name=r.distance_name,
                time_s=time_s,
                time_formatted=format_time(time_s),
                pace_formatted=format_pace(time_s, r.distance_m),
                pace_s_per_km=get_pace_seconds(time_s, r.distance_m)
            ))

    # Проверка наличия кэшированной оценки
    cur = conn.cursor()
    has_cache = cur.execute(
        "SELECT 1 FROM athlete_assessment_cache WHERE athlete_id = ?",
        (athlete_id,)
    ).fetchone() is not None

    return AthleteSummaryResponse(
        athlete=athlete,
        total_starts=len(results),
        personal_bests=sorted_pbs,
        dynamics=dynamics,
        rating=RatingPlaceholder(
            status="pending_curator_formula",
            message="Формула рейтинга находится на согласовании с куратором проекта",
            points=None,
            rank=None
        ),
        has_cached_assessment=has_cache
    )

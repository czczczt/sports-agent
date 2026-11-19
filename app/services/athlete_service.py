import json
import re
from typing import Any

from app.models import (
    AthleteCandidate,
    AthleteResultItem,
    AthleteSummaryResponse,
    DynamicsPoint,
    PersonalBestItem,
    RatingPlaceholder,
)
from app.modules.athletes.web_repository import AthletesWebRepository

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


DUMMY_CLUBS_EXACT = {
    "нет",
    "лично",
    "индивидуально",
    "-",
    "—",
    "none",
    "null",
    "self",
    "individual",
    "",
}
DUMMY_CLUBS_SUBSTR = ("нет клуба", "no club", "без клуба")


def is_dummy_club(club: str | None) -> bool:
    """Проверяет, является ли значение клуба технической заглушкой (Нет клуба/No club, Лично и т.п.)."""
    if not club:
        return True
    s = club.strip().lower().replace("ё", "е")
    if s in DUMMY_CLUBS_EXACT:
        return True
    return any(k in s for k in DUMMY_CLUBS_SUBSTR)


def clean_club(club: str | None) -> str | None:
    """Возвращает очищенное название клуба или None, если это заглушка."""
    if is_dummy_club(club):
        return None
    return club.strip()


def normalize_term(term: str) -> str:
    """Нормализует строку поиска: нижний регистр, замена ё -> е, удаление спецсимволов."""
    if not term:
        return ""
    s = term.lower().replace("ё", "е")
    tokens = re.findall(r"[a-zа-я0-9]+", s)
    return " ".join(tokens)


def format_time(seconds: float | None) -> str:
    """Форматирует секунды в ЧЧ:ММ:СС или ММ:СС."""
    if seconds is None or seconds <= 0:
        return "-"
    total = round(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_pace(time_s: float | None, dist_m: float | None) -> str:
    """Вычисляет средний темп (мин:сек / км)."""
    if not time_s or not dist_m or dist_m <= 0 or time_s <= 0:
        return "-"
    pace_s = time_s / (dist_m / 1000.0)
    m = int(pace_s // 60)
    s = round(pace_s % 60)
    if s >= 60:
        m += 1
        s = 0
    return f"{m:02d}:{s:02d} /км"


def get_pace_seconds(time_s: float | None, dist_m: float | None) -> float | None:
    """Возвращает темп в секундах на 1 км."""
    if not time_s or not dist_m or dist_m <= 0 or time_s <= 0:
        return None
    return time_s / (dist_m / 1000.0)


async def search_athletes(
    conn: AthletesWebRepository,
    last_name: str,
    birth_year: int | None = None,
    limit: int = 50,
) -> list[AthleteCandidate]:
    """
    Поиск спортсменов:
    - Регистронезависимо, замена е/ё.
    - Строгая фильтрация по году рождения.
    """
    norm = normalize_term(last_name)
    rows = await conn.search_candidates(norm, birth_year, limit) if norm else []

    return [
        AthleteCandidate(
            id=r["id"],
            display_name=r["display_name"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            middle_name=r["middle_name"],
            birth_date=r["birth_date"],
            employee_status=r["employee_status"],
            is_hidden=r["is_hidden"],
            birth_year=r["birth_year"],
            gender=r["gender"],
            city=r["city"],
            region=r["region"],
            club=clean_club(r["club"]),
            starts_count=r["starts_count"],
            results_count=r["results_count"],
        )
        for r in rows
    ]


async def get_athlete_by_id(
    conn: AthletesWebRepository, athlete_id: int
) -> AthleteCandidate | None:
    """Получает данные спортсмена по ID."""
    row = await conn.athlete(athlete_id)
    if not row:
        return None
    return AthleteCandidate(
        id=row["id"],
        display_name=row["display_name"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        middle_name=row["middle_name"],
        birth_date=row["birth_date"],
        employee_status=row["employee_status"],
        is_hidden=row["is_hidden"],
        birth_year=row["birth_year"],
        gender=row["gender"],
        city=row["city"],
        region=row["region"],
        club=clean_club(row["club"]),
        starts_count=row["starts_count"],
        results_count=row["results_count"],
    )


async def get_athlete_results(
    conn: AthletesWebRepository, athlete_id: int
) -> list[AthleteResultItem]:
    """Возвращает все результаты спортсмена (включая DNS, DNF, DSQ)."""
    rows = await conn.results(athlete_id)

    results = []
    for r in rows:
        status = r["status"]
        time_s = r["chip_time_s"] if r["chip_time_s"] is not None else r["gun_time_s"]
        dist_m = r["distance_m"]
        time_fmt = format_time(time_s)
        pace_fmt = format_pace(time_s, dist_m)
        pl_abs = r["place_abs"]
        pl_gender = r["place_gender"]

        tot_fin = r["max_fin_place"]
        tot_part = r["race_total_count"] or r["race_participants_count"]
        results.append(
            AthleteResultItem(
                result_id=r["result_id"],
                event_id=r["event_id"],
                event_title=r["event_title"] or "Беговой старт",
                event_date=r["event_date"],
                source_name=r["source_name"],
                race_id=r["race_id"],
                distance_name=r["distance_name"] or "Дистанция",
                norm_distance=r["norm_distance"],
                distance_m=dist_m,
                place_abs=pl_abs,
                place_gender=pl_gender,
                total_finishers=tot_fin,
                total_participants=tot_part,
                chip_time_s=r["chip_time_s"],
                gun_time_s=r["gun_time_s"],
                time_formatted=time_fmt,
                pace_formatted=pace_fmt,
                status=status,
                bib=r["bib"],
                rating_points=r["rating_points"],
                rating_reason=r["rating_reason"],
                rating_breakdown=(
                    json.loads(r["rating_breakdown_json"])
                    if r["rating_breakdown_json"]
                    else None
                ),
            )
        )
    return results


async def get_athlete_summary(
    conn: AthletesWebRepository, athlete_id: int
) -> AthleteSummaryResponse | None:
    """Формирует сводку по спортсмену: профиль, личные рекорды, динамику, рейтинг-заглушку."""
    athlete = await get_athlete_by_id(conn, athlete_id)
    if not athlete:
        return None

    results = await get_athlete_results(conn, athlete_id)

    # Вычисление личных рекордов (Personal Bests) по нормализованным дистанциям
    pb_dict: dict[str, dict[str, Any]] = {}
    for res in results:
        if res.status != "FIN":
            continue
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
                "event_date": res.event_date,
            }

    # Порядок дистанций от коротких к длинным
    distance_order = [
        "60m",
        "100m",
        "200m",
        "400m",
        "800m",
        "1000m",
        "1500m",
        "1mile",
        "3000m",
        "5000m",
        "10000m",
        "half_marathon",
        "marathon",
        "100k",
        "24h",
    ]
    sorted_pbs = []
    for d in distance_order:
        if d in pb_dict:
            sorted_pbs.append(PersonalBestItem(**pb_dict[d]))
    for d, item in pb_dict.items():
        if d not in distance_order:
            sorted_pbs.append(PersonalBestItem(**item))

    # Формирование точек динамики для графика (по возрастанию даты)
    dynamics: list[DynamicsPoint] = []
    sorted_by_date = sorted(
        [r for r in results if r.event_date and r.status == "FIN"],
        key=lambda x: x.event_date or "",
    )
    for r in sorted_by_date:
        time_s = r.chip_time_s if r.chip_time_s is not None else r.gun_time_s
        if time_s and time_s > 0:
            dynamics.append(
                DynamicsPoint(
                    date=r.event_date[:10] if r.event_date else "",
                    event_title=r.event_title,
                    norm_distance=r.norm_distance,
                    distance_name=r.distance_name,
                    time_s=time_s,
                    time_formatted=format_time(time_s),
                    pace_formatted=format_pace(time_s, r.distance_m),
                    pace_s_per_km=get_pace_seconds(time_s, r.distance_m),
                )
            )

    # Проверка наличия кэшированной оценки
    has_cache = await conn.cached_assessment_exists(athlete_id) is not None

    rating_row = await conn.published_rating(athlete_id)

    return AthleteSummaryResponse(
        athlete=athlete,
        total_starts=len(results),
        personal_bests=sorted_pbs,
        dynamics=dynamics,
        rating=RatingPlaceholder(
            status="counted" if rating_row else "no_data",
            message="Рейтинг за последние 365 дней"
            if rating_row
            else "Нет результатов в рейтинговом периоде",
            points=rating_row["points"] if rating_row else None,
            rank=rating_row["rank"] if rating_row else None,
            starts_count=rating_row["starts_count"] if rating_row else 0,
            period_start=rating_row["period_start"] if rating_row else None,
            period_end=rating_row["period_end"] if rating_row else None,
        ),
        has_cached_assessment=has_cache,
    )

import sqlite3
import math
from typing import Dict, Any, List
from app.services.athlete_service import (
    get_athlete_results, get_athlete_by_id, format_time, format_pace,
    get_pace_seconds, DISTANCE_TITLES
)


def compute_athlete_metrics(conn: sqlite3.Connection, athlete_id: int) -> Dict[str, Any]:
    """
    Вычисляет все аналитические метрики для спортсмена:
    - Личные рекорды по дистанциям
    - Процентили на стартах (положение среди участников)
    - Динамику (прогресс) по времени
    - Показатель стабильности (вариация темпа)
    - Определение сильных и слабых сторон
    """
    athlete = get_athlete_by_id(conn, athlete_id)
    if not athlete:
        return {}

    results = get_athlete_results(conn, athlete_id)
    if not results:
        return {
            "athlete_id": athlete_id,
            "athlete_name": athlete.display_name,
            "total_starts": 0,
            "message": "Нет завершенных стартов для анализа"
        }

    cur = conn.cursor()

    # 1. Личные рекорды
    pb_dict = {}
    for r in results:
        nd = r.norm_distance
        if not nd:
            continue
        time_s = r.chip_time_s if r.chip_time_s is not None else r.gun_time_s
        if time_s and (nd not in pb_dict or time_s < pb_dict[nd]["time_s"]):
            pb_dict[nd] = {
                "distance_key": nd,
                "distance_name": DISTANCE_TITLES.get(nd, nd),
                "time_s": time_s,
                "time_formatted": format_time(time_s),
                "pace_formatted": format_pace(time_s, r.distance_m),
                "event_title": r.event_title,
                "event_date": r.event_date[:10] if r.event_date else ""
            }

    # 2. Процентили среди участников каждого забега
    race_stats = []
    percentiles = []
    for r in results:
        # Получаем общее количество финишеров на данной дистанции
        total_fin = cur.execute("""
            SELECT count(*) FROM result 
            WHERE race_id = ? AND status = 'FIN' AND duplicate_of IS NULL
        """, (r.race_id,)).fetchone()[0]

        if total_fin and r.place_abs and total_fin > 0:
            # Процентиль: процент участников, которых спортсмен обогнал (или финишировал вровень)
            pct = round(100.0 * (total_fin - r.place_abs + 1) / total_fin, 1)
            percentiles.append(pct)
            race_stats.append({
                "race_id": r.race_id,
                "event_title": r.event_title,
                "distance": r.distance_name,
                "place_abs": r.place_abs,
                "total_finishers": total_fin,
                "percentile": pct,
                "top_percent": round(100.0 * r.place_abs / total_fin, 1)
            })

    avg_percentile = round(sum(percentiles) / len(percentiles), 1) if percentiles else None
    best_percentile = max(percentiles) if percentiles else None

    # 3. Динамика по дистанциям (прогресс)
    # Группируем результаты по norm_distance и сортируем по дате
    by_dist: Dict[str, List] = {}
    for r in sorted([x for x in results if x.event_date], key=lambda x: x.event_date or ""):
        nd = r.norm_distance
        if not nd:
            continue
        time_s = r.chip_time_s if r.chip_time_s is not None else r.gun_time_s
        if time_s:
            by_dist.setdefault(nd, []).append({
                "date": r.event_date[:10] if r.event_date else "",
                "time_s": time_s,
                "event_title": r.event_title
            })

    progress_summary = []
    for nd, items in by_dist.items():
        if len(items) >= 2:
            first_time = items[0]["time_s"]
            last_time = items[-1]["time_s"]
            delta = last_time - first_time
            # Положительный процент — улучшение (стал быстрее)
            pct_improvement = round((first_time - last_time) / first_time * 100.0, 1)
            dist_title = DISTANCE_TITLES.get(nd, nd)
            progress_summary.append({
                "distance": dist_title,
                "starts_count": len(items),
                "first_date": items[0]["date"],
                "first_time": format_time(first_time),
                "latest_date": items[-1]["date"],
                "latest_time": format_time(last_time),
                "delta_seconds": round(delta, 1),
                "improvement_pct": pct_improvement,
                "trend": "улучшение" if pct_improvement > 0.5 else ("спад" if pct_improvement < -0.5 else "стабильно")
            })

    # 4. Оценка стабильности темпа (коэффициент вариации темпа)
    paces = []
    for r in results:
        time_s = r.chip_time_s if r.chip_time_s is not None else r.gun_time_s
        p = get_pace_seconds(time_s, r.distance_m)
        if p and p > 100:  # отсекаем явные ошибки менее 1:40/км
            paces.append(p)

    stability_info = {"status": "недостаточно данных", "cv_percent": None}
    if len(paces) >= 2:
        mean_pace = sum(paces) / len(paces)
        variance = sum((x - mean_pace) ** 2 for x in paces) / len(paces)
        std_pace = math.sqrt(variance)
        cv = round((std_pace / mean_pace) * 100.0, 1)
        if cv < 5.0:
            stability_label = "очень высокая"
            desc = "спортсмен держит крайне ровный темп на всех стартах (разброс < 5%)"
        elif cv < 10.0:
            stability_label = "хорошая"
            desc = "стабильный темп с контролируемой вариацией между дистанциями (разброс < 10%)"
        else:
            stability_label = "умеренная"
            desc = "темп существенно варьируется в зависимости от рельефа и длины дистанций"
        stability_info = {
            "status": stability_label,
            "cv_percent": cv,
            "mean_pace": format_pace(mean_pace, 1000),
            "description": desc
        }

    # 5. Сильные и слабые стороны
    strengths = []
    weaknesses = []

    if avg_percentile:
        if avg_percentile >= 75:
            strengths.append(f"Высокий соревновательный уровень: обгоняет в среднем {avg_percentile}% участников.")
        elif avg_percentile >= 50:
            strengths.append(f"Уверенный уровень любителя: финиширует выше медианы участников (в среднем топ {round(100 - avg_percentile)}%).")
        else:
            weaknesses.append("Пока находится во второй половине протоколов, есть существенный потенциал для роста.")

    # Самая сильная дистанция по процентилю
    best_dist = None
    best_dist_pct = -1
    for r_stat in race_stats:
        if r_stat["percentile"] > best_dist_pct:
            best_dist_pct = r_stat["percentile"]
            best_dist = r_stat["distance"]
    if best_dist:
        strengths.append(f"Наилучший результат относительно соперников показан на дистанции «{best_dist}» (топ {round(100 - best_dist_pct, 1)}%).")

    for prg in progress_summary:
        if prg["improvement_pct"] > 0:
            strengths.append(f"Положительная динамика на {prg['distance']}: улучшение на {prg['improvement_pct']}% ({prg['first_time']} -> {prg['latest_time']}).")
        elif prg["improvement_pct"] < -3:
            weaknesses.append(f"Зафиксировано замедление времени на {prg['distance']} на {abs(prg['improvement_pct'])}%.")

    if stability_info["status"] in ("очень высокая", "хорошая"):
        strengths.append(f"Стабильность темпа: {stability_info['description']}.")

    return {
        "athlete_id": athlete_id,
        "athlete_name": athlete.display_name,
        "birth_year": athlete.birth_year,
        "gender": athlete.gender,
        "city": athlete.city,
        "club": athlete.club,
        "total_starts": len(results),
        "personal_bests": list(pb_dict.values()),
        "average_percentile": avg_percentile,
        "best_percentile": best_percentile,
        "progress_by_distance": progress_summary,
        "stability": stability_info,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recent_races": race_stats[:5]
    }

"""Compatibility and recalculation entry points for the run-v1 calculator on PostgreSQL.

Schema setup belongs to Alembic. Recalculation operates atomically over PostgreSQL.
"""
from __future__ import annotations

from typing import Any

from app.modules.rating.calculator import (
    _NORMS,
    FORMULA_VERSION,
    RATING_PERIOD_DAYS,
    _calculate_score,
    _parse_date,
)
from app.modules.rating.repository import RatingRepository

__all__ = [
    "FORMULA_VERSION",
    "RATING_PERIOD_DAYS",
    "_NORMS",
    "_calculate_score",
    "_parse_date",
    "get_rating_me_row",
    "get_rating_norms",
    "get_rating_page",
    "recalculate_rating",
    "recalculate_rating_sync",
]


async def get_rating_page(session: Any, **kwargs: Any) -> dict[str, Any]:
    return await RatingRepository(session).get_rating_page(**kwargs)


async def get_rating_me_row(session: Any, athlete_id: int, gender: str | None = None) -> dict[str, Any] | None:
    return await RatingRepository(session).get_rating_me_row(athlete_id, gender)


async def get_rating_norms(session: Any, year: int = 2026) -> dict[str, Any]:
    return await RatingRepository(session).get_rating_norms(year)


async def recalculate_rating(session: Any, *, as_of: Any = None, formula_version: str = FORMULA_VERSION) -> dict[str, Any]:
    return await RatingRepository(session).recalculate_rating(as_of=as_of, formula_version=formula_version)


def recalculate_rating_sync(conn: Any = None, *, as_of: Any = None, formula_version: str = FORMULA_VERSION) -> dict[str, Any]:
    """Синхронный запуск пересчёта для CLI/фоновых скриптов через psycopg."""
    import json
    from datetime import date, timedelta

    import psycopg

    from app.config import DATABASE_URL, normalize_postgres_url

    should_close = False
    if conn is None:
        conn = psycopg.connect(normalize_postgres_url(DATABASE_URL))
        should_close = True

    try:
        cur = conn.cursor()
        end_date = as_of or date.today()
        start_date = end_date - timedelta(days=RATING_PERIOD_DAYS)
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        cur.execute("SELECT distance_class, gender, value, unit, year FROM rating_norm")
        norms = {
            (row[0], row[1]): {"value": row[2], "unit": row[3], "year": row[4]}
            for row in cur.fetchall()
        }

        cur.execute("""
            SELECT r.id, r.status, r.duplicate_of, r.gender, r.chip_time_s,
                   r.gun_time_s, r.distance_km, ra.distance_type, ra.discipline,
                   c.date_begin, a.id AS athlete_id
            FROM result r
            JOIN race ra ON ra.id = r.race_id
            JOIN competition c ON c.id = ra.competition_id
            LEFT JOIN result_athlete link ON link.result_id = r.id
            LEFT JOIN athlete a ON a.id = link.athlete_id
        """)
        rows = cur.fetchall()

        score_rows = []
        scored_count = 0
        for row in rows:
            rid, status, dup, gender, chip_s, gun_s, dist_km, dist_type, disc, dbegin, aid = row
            dist_class = dist_type or (f"{int(dist_km)}km" if dist_km else None)
            norm = norms.get((dist_class, gender))
            points, reason, breakdown = _calculate_score(
                status=status,
                duplicate_of=dup,
                gender=gender,
                distance_class=dist_class,
                event_date=str(dbegin) if dbegin else None,
                chip_time_s=chip_s,
                gun_time_s=gun_s,
                distance_km=dist_km,
                norm_value=norm["value"] if norm else None,
                norm_unit=norm["unit"] if norm else None,
                norm_year=norm["year"] if norm else None,
            )
            breakdown_json = json.dumps(breakdown, ensure_ascii=False, allow_nan=False)
            score_rows.append((rid, formula_version, points, reason, breakdown_json))
            if points is not None:
                scored_count += 1

        cur.executemany("""
            INSERT INTO rating_score (result_id, formula_version, points, reason, breakdown_json)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (result_id, formula_version) DO UPDATE SET
                points = EXCLUDED.points,
                reason = EXCLUDED.reason,
                breakdown_json = EXCLUDED.breakdown_json
        """, score_rows)

        cur.execute("""
            SELECT a.id AS athlete_id, SUM(s.points) AS points,
                   MAX(s.points) AS best_points, COUNT(*) AS starts_count
            FROM athlete a
            JOIN result_athlete link ON link.athlete_id = a.id
            JOIN rating_score s ON s.result_id = link.result_id
            JOIN result r ON r.id = s.result_id
            JOIN race ra ON ra.id = r.race_id
            JOIN competition c ON c.id = ra.competition_id
            WHERE s.formula_version = %s
              AND s.points IS NOT NULL
              AND c.date_begin BETWEEN %s AND %s
            GROUP BY a.id
            ORDER BY points DESC, best_points DESC, starts_count DESC, a.id ASC
        """, (formula_version, start_date, end_date))
        aggregates = cur.fetchall()

        cur.execute("""
            DELETE FROM running_athlete_rating
            WHERE formula_version = %s AND period_start = %s AND period_end = %s
        """, (formula_version, start_str, end_str))

        rating_rows = [
            (agg[0], formula_version, start_str, end_str, agg[1], agg[2], agg[3], rank)
            for rank, agg in enumerate(aggregates, 1)
        ]
        cur.executemany("""
            INSERT INTO running_athlete_rating (
                athlete_id, formula_version, period_start, period_end,
                points, best_points, starts_count, rank
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, rating_rows)

        conn.commit()
        return {
            "formula_version": formula_version,
            "period_start": start_str,
            "period_end": end_str,
            "results_scored": scored_count,
            "athletes_rated": len(aggregates),
        }
    finally:
        if should_close:
            conn.close()

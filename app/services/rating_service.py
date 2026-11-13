"""Расчёт рейтинга по формулам из !info/docs/SPEC.md."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, timedelta
from typing import Any, Optional


FORMULA_VERSION = "run-v1"
RATING_PERIOD_DAYS = 365

_NORMS = (
    ("60m", 6.84, 7.5),
    ("100m", 10.62, 11.75),
    ("200m", 21.65, 24.4),
    ("400m", 47.9, 54.8),
    ("800m", 111, 127),
    ("1000m", 142, 165),
    ("1500m", 228, 259),
    ("1mile", 243, 279),
    ("3000m", 486, 555),
    ("5000m", 846, 965),
    ("10000m", 1760, 2028),
    ("half_marathon", 3900, 4540),
    ("marathon", 8400, 9600),
    ("100km", 24960, 28800),
    ("24h", 245, 216),
)

DDL = """
CREATE TABLE IF NOT EXISTS rating_norm (
    year INTEGER NOT NULL,
    distance_class TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('M', 'F')),
    value REAL NOT NULL CHECK (value > 0),
    unit TEXT NOT NULL CHECK (unit IN ('s', 'km')),
    PRIMARY KEY (year, distance_class, gender)
);
CREATE TABLE IF NOT EXISTS rating_score (
    result_id INTEGER NOT NULL REFERENCES result(id) ON DELETE CASCADE,
    formula_version TEXT NOT NULL,
    points REAL,
    reason TEXT,
    breakdown_json TEXT NOT NULL,
    PRIMARY KEY (result_id, formula_version),
    CHECK ((points IS NOT NULL AND reason IS NULL) OR
           (points IS NULL AND reason IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS running_athlete_rating (
    athlete_id INTEGER NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    formula_version TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    points REAL NOT NULL,
    best_points REAL NOT NULL,
    starts_count INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    PRIMARY KEY (athlete_id, formula_version, period_start, period_end)
);
CREATE INDEX IF NOT EXISTS ix_rating_score_points ON rating_score(points);
CREATE INDEX IF NOT EXISTS ix_running_athlete_rating_rank
    ON running_athlete_rating(formula_version, period_start, period_end, rank);
"""


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.executemany(
        """
        INSERT OR IGNORE INTO rating_norm(year, distance_class, gender, value, unit)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (2026, distance_class, gender, value, "km" if distance_class == "24h" else "s")
            for distance_class, male, female in _NORMS
            for gender, value in (("M", male), ("F", female))
        ],
    )
    conn.commit()


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _calculate_score(
    *,
    status: Optional[str],
    duplicate_of: Optional[int],
    gender: Optional[str],
    distance_class: Optional[str],
    event_date: Optional[str],
    chip_time_s: Optional[float],
    gun_time_s: Optional[float],
    distance_km: Optional[float],
    norm_value: Optional[float],
    norm_unit: Optional[str],
    norm_year: Optional[int],
) -> tuple[Optional[float], Optional[str], dict[str, Any]]:
    breakdown: dict[str, Any] = {
        "sport": "run",
        "class": distance_class,
        "gender": gender,
        "norm_value": norm_value,
        "norm_unit": norm_unit,
        "norm_year": norm_year,
        "time_kind": None,
        "time_s": None,
        "formula": None,
        "points": None,
        "formula_version": FORMULA_VERSION,
    }

    def excluded(reason: str) -> tuple[None, str, dict[str, Any]]:
        breakdown["reason"] = reason
        return None, reason, breakdown

    if duplicate_of is not None:
        return excluded("duplicate")
    if status != "FIN":
        return excluded("not_finisher")
    if gender not in ("M", "F"):
        return excluded("unknown_gender")
    if not event_date:
        return excluded("missing_date")
    if not distance_class:
        return excluded("unclassified_distance")
    if norm_value is None:
        return excluded("missing_norm")

    if distance_class == "24h":
        if distance_km is None:
            return excluded("missing_distance")
        if not isinstance(distance_km, (int, float)) or not math.isfinite(distance_km) or distance_km <= 0:
            return excluded("invalid_distance")
        points = distance_km / norm_value * 1000
        breakdown["distance_km"] = distance_km
        breakdown["formula"] = f"{distance_km:g} / {norm_value:g} × 1000"
    else:
        time_kind = "chip" if chip_time_s is not None else "gun"
        seconds = chip_time_s if time_kind == "chip" else gun_time_s
        breakdown["time_kind"] = time_kind
        breakdown["time_s"] = seconds
        if seconds is None:
            return excluded("missing_time")
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
            return excluded("invalid_time")
        points = norm_value / seconds * 1000
        breakdown["formula"] = f"{norm_value:g} / {seconds:g} × 1000"

    if not math.isfinite(points) or points <= 0:
        return excluded("invalid_points")
    breakdown["points"] = points
    return points, None, breakdown


def recalculate(
    conn: sqlite3.Connection,
    *,
    as_of: Optional[date] = None,
    formula_version: str = FORMULA_VERSION,
) -> dict[str, Any]:
    """Rebuild result scores and the rolling 365-day athlete rating."""
    initialize(conn)
    end_date = as_of or date.today()
    start_date = end_date - timedelta(days=RATING_PERIOD_DAYS)
    norms = {
        (row["distance_class"], row["gender"]): row
        for row in conn.execute(
            "SELECT distance_class, gender, value, unit, year FROM rating_norm"
        )
    }

    with conn:
        conn.execute(
            "DELETE FROM rating_score WHERE formula_version = ?", (formula_version,)
        )
        conn.execute(
            """
            DELETE FROM running_athlete_rating
            WHERE formula_version = ? AND period_start = ? AND period_end = ?
            """,
            (formula_version, start_date.isoformat(), end_date.isoformat()),
        )

        result_rows = conn.execute(
            """
            SELECT r.id, r.status, r.duplicate_of, r.gender, r.chip_time_s,
                   r.gun_time_s, ra.norm_distance,
                   e.date_begin, a.id AS athlete_id
            FROM result r
            JOIN race ra ON ra.id = r.race_id
            JOIN event e ON e.id = ra.event_id
            LEFT JOIN result_athlete link ON link.result_id = r.id
            LEFT JOIN athlete a ON a.id = link.athlete_id
            """
        ).fetchall()

        score_rows = []
        totals: dict[str, int] = {}
        for row in result_rows:
            norm = norms.get((row["norm_distance"], row["gender"]))
            points, reason, breakdown = _calculate_score(
                status=row["status"],
                duplicate_of=row["duplicate_of"],
                gender=row["gender"],
                distance_class=row["norm_distance"],
                event_date=row["date_begin"],
                chip_time_s=row["chip_time_s"],
                gun_time_s=row["gun_time_s"],
                distance_km=None,
                norm_value=norm["value"] if norm else None,
                norm_unit=norm["unit"] if norm else None,
                norm_year=norm["year"] if norm else None,
            )
            score_rows.append(
                (
                    row["id"],
                    formula_version,
                    points,
                    reason,
                    json.dumps(breakdown, ensure_ascii=False, allow_nan=False),
                )
            )
            totals["scored" if points is not None else reason] = totals.get(
                "scored" if points is not None else reason, 0
            ) + 1

        conn.executemany(
            """
            INSERT INTO rating_score(result_id, formula_version, points, reason, breakdown_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            score_rows,
        )

        aggregates = conn.execute(
            """
            SELECT a.id AS athlete_id, SUM(s.points) AS points,
                   MAX(s.points) AS best_points, COUNT(*) AS starts_count
            FROM athlete a
            JOIN result_athlete link ON link.athlete_id = a.id
            JOIN rating_score s ON s.result_id = link.result_id
            JOIN result r ON r.id = s.result_id
            JOIN race ra ON ra.id = r.race_id
            JOIN event e ON e.id = ra.event_id
            WHERE s.formula_version = ?
              AND s.points IS NOT NULL
              AND substr(e.date_begin, 1, 10) BETWEEN ? AND ?
            GROUP BY a.id
            ORDER BY points DESC, best_points DESC, starts_count DESC, a.id
            """,
            (formula_version, start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
        conn.executemany(
            """
            INSERT INTO running_athlete_rating(
                athlete_id, formula_version, period_start, period_end,
                points, best_points, starts_count, rank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["athlete_id"],
                    formula_version,
                    start_date.isoformat(),
                    end_date.isoformat(),
                    row["points"],
                    row["best_points"],
                    row["starts_count"],
                    rank,
                )
                for rank, row in enumerate(aggregates, 1)
            ],
        )

    return {
        "formula_version": formula_version,
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "results_total": len(result_rows),
        "results_scored": totals.get("scored", 0),
        "athletes_rated": len(aggregates),
        "exclusions": {key: value for key, value in totals.items() if key != "scored"},
    }


def get_rating_page(
    conn: sqlite3.Connection,
    *,
    gender: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Возвращает сохранённый рейтинг для страницы рейтинга."""
    period = conn.execute(
        """
        SELECT period_start, period_end
        FROM running_athlete_rating
        WHERE formula_version = ?
        ORDER BY period_end DESC
        LIMIT 1
        """,
        (FORMULA_VERSION,),
    ).fetchone()
    if not period:
        return {"period_start": None, "period_end": None, "rows": [], "total": 0}

    conditions = [
        "ar.formula_version = ?",
        "ar.period_start = ?",
        "ar.period_end = ?",
    ]
    params: list[Any] = [
        FORMULA_VERSION,
        period["period_start"],
        period["period_end"],
    ]
    if gender in ("M", "F"):
        conditions.append("a.gender = ?")
        params.append(gender)
    if search:
        conditions.append("a.name_key LIKE ?")
        params.append(f"%{search.lower().replace('ё', 'е')}%")

    where_clause = " AND ".join(conditions)
    rows = conn.execute(
        f"""
        SELECT ar.rank, a.id AS athlete_id, a.display_name, a.birth_year,
               a.gender, ar.points, ar.best_points, ar.starts_count
        FROM running_athlete_rating ar
        JOIN athlete a ON a.id = ar.athlete_id
        WHERE {where_clause}
        ORDER BY ar.points DESC, ar.best_points DESC, ar.starts_count DESC, ar.athlete_id
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    total = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM running_athlete_rating ar
        JOIN athlete a ON a.id = ar.athlete_id
        WHERE {where_clause}
        """,
        params,
    ).fetchone()[0]
    rows = [
        {
            "rank": index,
            "athlete_id": row["athlete_id"],
            "display_name": row["display_name"],
            "birth_year": row["birth_year"],
            "gender": row["gender"],
            "points": row["points"],
            "best_points": row["best_points"],
            "starts_count": row["starts_count"],
        }
        for index, row in enumerate(rows, 1)
    ]
    return {
        "period_start": period["period_start"],
        "period_end": period["period_end"],
        "rows": rows,
        "total": total,
    }


def get_rating_me_row(
    conn: sqlite3.Connection,
    athlete_id: int,
    gender: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Строка «это вы» для страницы рейтинга.

    Если выбран фильтр по полу, место пересчитывается среди спортсменов этого пола
    (с теми же тай-брейками, что и общий рейтинг). Спортсмен другого пола скрывается.
    """
    ar = conn.execute(
        """
        SELECT a.id AS athlete_id, a.display_name, a.birth_year, a.gender,
               ar.points, ar.best_points, ar.starts_count, ar.rank AS overall_rank
        FROM athlete a
        LEFT JOIN running_athlete_rating ar
          ON ar.athlete_id = a.id AND ar.formula_version = ?
        WHERE a.id = ?
        ORDER BY ar.period_end DESC
        LIMIT 1
        """,
        (FORMULA_VERSION, athlete_id),
    ).fetchone()
    if not ar or ar["points"] is None:
        return None
    if gender and ar["gender"] != gender:
        return None

    if gender:
        rank = conn.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM running_athlete_rating rar
            JOIN athlete a ON a.id = rar.athlete_id
            WHERE rar.formula_version = ?
              AND a.gender = ?
              AND (
                  rar.points > ?
                  OR (rar.points = ? AND rar.best_points > ?)
                  OR (rar.points = ? AND rar.best_points = ? AND rar.starts_count > ?)
                  OR (rar.points = ? AND rar.best_points = ? AND rar.starts_count = ? AND rar.athlete_id < ?)
              )
            """,
            (FORMULA_VERSION, gender, ar["points"], ar["points"], ar["best_points"],
             ar["points"], ar["best_points"], ar["starts_count"],
             ar["points"], ar["best_points"], ar["starts_count"], ar["athlete_id"]),
        ).fetchone()[0]
    else:
        rank = ar["overall_rank"]

    return {
        "rank": rank,
        "athlete_id": ar["athlete_id"],
        "display_name": ar["display_name"],
        "birth_year": ar["birth_year"],
        "gender": ar["gender"],
        "points": ar["points"],
        "best_points": ar["best_points"],
        "starts_count": ar["starts_count"],
    }


def get_rating_norms(conn: sqlite3.Connection, year: int = 2026) -> dict[str, Any]:
    """Нормативы года и период действующего рейтинга — для страницы «Как посчитано»."""
    norms = conn.execute(
        """
        SELECT distance_class, gender, value, unit
        FROM rating_norm
        WHERE year = ?
        ORDER BY CASE distance_class
            WHEN '60m' THEN 1 WHEN '100m' THEN 2 WHEN '200m' THEN 3
            WHEN '400m' THEN 4 WHEN '800m' THEN 5 WHEN '1000m' THEN 6
            WHEN '1500m' THEN 7 WHEN '1mile' THEN 8 WHEN '3000m' THEN 9
            WHEN '5000m' THEN 10 WHEN '10000m' THEN 11
            WHEN 'half_marathon' THEN 12 WHEN 'marathon' THEN 13
            WHEN '100km' THEN 14 WHEN '24h' THEN 15 ELSE 99 END,
            gender
        """,
        (year,),
    ).fetchall()
    period = conn.execute(
        """
        SELECT period_start, period_end
        FROM running_athlete_rating
        WHERE formula_version = ?
        ORDER BY period_end DESC LIMIT 1
        """,
        (FORMULA_VERSION,),
    ).fetchone()
    return {
        "year": year,
        "norms": [dict(row) for row in norms],
        "period_start": period["period_start"] if period else None,
        "period_end": period["period_end"] if period else None,
    }

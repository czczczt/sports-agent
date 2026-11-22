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
    "confirm_athlete_employee",
    "get_rating_me_row",
    "get_rating_norms",
    "get_rating_page",
    "get_top_n_setting",
    "get_unverified_queue",
    "recalculate_rating",
    "recalculate_rating_sync",
]


async def get_top_n_setting(session: Any) -> int:
    """Получает настройку глубины топа top_n_verify (по умолчанию 10) из БД или fallback."""
    from sqlalchemy import text

    try:
        val = (
            await session.execute(
                text("SELECT value FROM setting WHERE key = 'top_n_verify'")
            )
        ).scalar()
        if val is not None:
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, dict) and "value" in val:
                return int(val["value"])
            if isinstance(val, str) and val.isdigit():
                return int(val)
    except Exception:
        pass
    return 10


async def get_unverified_queue(
    session: Any,
    top_n: int | None = None,
    sport: str | None = None,
) -> list[dict[str, Any]]:
    """Возвращает неподтверждённых спортсменов из топ-N вид×пол (SPEC v1.3 §3.5, §5)."""
    from sqlalchemy import text

    if top_n is None or top_n <= 0:
        top_n = await get_top_n_setting(session)

    sql = text("""
        WITH latest_period AS (
            SELECT period_start, period_end
            FROM running_athlete_rating
            ORDER BY period_end DESC
            LIMIT 1
        ),
        ranked_athletes AS (
            SELECT
                a.id AS athlete_id,
                a.display_name,
                a.first_name,
                a.last_name,
                a.middle_name,
                a.gender,
                a.birth_date,
                a.birth_year,
                a.employee_status,
                ar.points,
                ar.starts_count,
                'run' AS sport,
                ROW_NUMBER() OVER (
                    PARTITION BY a.gender
                    ORDER BY ar.points DESC, ar.best_points DESC, ar.starts_count DESC, a.id
                ) AS rank
            FROM running_athlete_rating ar
            JOIN latest_period lp ON lp.period_start = ar.period_start AND lp.period_end = ar.period_end
            JOIN athlete a ON a.id = ar.athlete_id
            WHERE ar.formula_version = 'run-v1'
              AND a.is_hidden = FALSE
              AND (a.employee_status IS NULL OR a.employee_status != 'not_employee')
        )
        SELECT
            ra.athlete_id,
            ra.display_name,
            ra.first_name,
            ra.last_name,
            ra.middle_name,
            ra.gender,
            ra.birth_date,
            ra.birth_year,
            ra.sport,
            ra.rank,
            ra.points,
            ra.starts_count,
            ra.employee_status,
            u.id AS linked_user_id,
            u.username AS linked_username,
            u.email AS linked_user_email
        FROM ranked_athletes ra
        LEFT JOIN app_user u ON u.athlete_id = ra.athlete_id
        WHERE ra.rank <= :top_n
          AND (ra.employee_status IS NULL OR ra.employee_status != 'confirmed')
        ORDER BY ra.sport, ra.gender, ra.rank;
    """)
    rows = (await session.execute(sql, {"top_n": top_n})).mappings().all()
    results = [dict(r) for r in rows]
    if sport:
        results = [r for r in results if r["sport"] == sport]
    return results


async def confirm_athlete_employee(
    session: Any,
    athlete_id: int,
    user_id: int | None = None,
    comment: str | None = None,
) -> None:
    """Подтверждает статус сотрудника ('confirmed') и фиксирует действие в audit_log (SPEC v1.3 §3.5)."""
    import json

    from sqlalchemy import text

    old_status = (
        await session.execute(
            text("SELECT employee_status FROM athlete WHERE id = :id"),
            {"id": athlete_id},
        )
    ).scalar() or "presumed"

    await session.execute(
        text("UPDATE athlete SET employee_status = 'confirmed' WHERE id = :id"),
        {"id": athlete_id},
    )

    diff = {
        "old_status": old_status,
        "new_status": "confirmed",
        "comment": comment,
    }
    await session.execute(
        text("""
            INSERT INTO audit_log (user_id, action, entity, entity_id, diff, created_at)
            VALUES (:user_id, 'verify_employee_status', 'athlete', :entity_id, CAST(:diff AS jsonb), NOW())
        """),
        {"user_id": user_id, "entity_id": athlete_id, "diff": json.dumps(diff)},
    )
    await session.commit()


async def get_rating_page(session: Any, **kwargs: Any) -> dict[str, Any]:
    return await RatingRepository(session).get_rating_page(**kwargs)


async def get_rating_me_row(session: Any, athlete_id: int, gender: str | None = None) -> dict[str, Any] | None:
    return await RatingRepository(session).get_rating_me_row(athlete_id, gender)


async def get_rating_norms(session: Any, year: int = 2026) -> dict[str, Any]:
    return await RatingRepository(session).get_rating_norms(year)


async def recalculate_rating(session: Any, *, as_of: Any = None, formula_version: str = FORMULA_VERSION) -> dict[str, Any]:
    return await RatingRepository(session).recalculate_rating(as_of=as_of, formula_version=formula_version)


def recalculate_rating_sync(conn: Any = None, *, as_of: Any = None, formula_version: str = FORMULA_VERSION, commit: bool = True) -> dict[str, Any]:
    """Синхронный запуск пересчёта для CLI/фоновых скриптов через psycopg."""
    import json
    import statistics
    from datetime import date, timedelta

    import psycopg

    from app.config import DATABASE_URL, normalize_postgres_url
    from app.modules.rating.calculator import _calculate_score

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

        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('collection:publication', 0))")
        cur.execute("""
            DELETE FROM rating_score s USING result r, race ra, competition c
            WHERE s.result_id=r.id AND r.race_id=ra.id AND ra.competition_id=c.id
              AND s.formula_version = %s
              AND (r.collection_review OR COALESCE(ra.sport_type, c.sport_type, 'run') <> 'run'
                   OR ra.race_type = 'relay')
        """, (formula_version,))

        cur.execute("SELECT distance_class, gender, value, unit, year FROM rating_norm")
        norms = {
            (row[0], row[1]): {"value": row[2], "unit": row[3], "year": row[4]}
            for row in cur.fetchall()
        }

        cur.execute("""
            SELECT r.id, r.race_id, r.status, r.duplicate_of, r.gender, r.chip_time_s,
                   r.gun_time_s, r.distance_km, r.position, r.position_gender,
                   ra.distance_type, ra.discipline, ra.sport, ra.scoring_class,
                   ra.elevation_gain_m, ra.is_rl_series, ra.special,
                   c.date_begin, a.id AS athlete_id
            FROM result r
            JOIN race ra ON ra.id = r.race_id
            JOIN competition c ON c.id = ra.competition_id
            LEFT JOIN result_athlete link ON link.result_id = r.id
            LEFT JOIN athlete a ON a.id = link.athlete_id
            WHERE COALESCE(ra.sport_type, c.sport_type, 'run') = 'run'
              AND NOT r.collection_review AND ra.race_type IS DISTINCT FROM 'relay'
        """)
        rows = cur.fetchall()

        # Group stats per (race_id, gender)
        race_stats: dict[tuple[Any, Any], dict[str, Any]] = {}
        for row in rows:
            race_id, status, gender, chip_s, gun_s = row[1], row[2], row[4], row[5], row[6]
            rk = (race_id, gender)
            if rk not in race_stats:
                race_stats[rk] = {"times": [], "count": 0}
            if status == "FIN":
                race_stats[rk]["count"] += 1
                t_val = chip_s if chip_s is not None else gun_s
                if isinstance(t_val, (int, float)) and t_val > 0:
                    race_stats[rk]["times"].append(float(t_val))

        for stats in race_stats.values():
            times = stats["times"]
            stats["leader_time_s"] = min(times) if times else None
            stats["median_time_s"] = statistics.median(times) if times else None
            stats["finishers_count"] = stats["count"]

        score_rows = []
        scored_count = 0
        for row in rows:
            (
                rid, race_id, status, dup, gender, chip_s, gun_s, dist_km,
                pos, pos_gender, dist_type, disc, sport, scoring_class,
                elevation_m, is_rl_series, special, dbegin, aid,
            ) = row
            rk = (race_id, gender)
            stats = race_stats.get(rk, {})
            sport_val = sport or "run"
            dist_class = scoring_class or dist_type or (f"{int(dist_km)}km" if dist_km else None)
            norm = norms.get((dist_class, gender))
            place = pos_gender or pos
            finishers_count = stats.get("finishers_count")
            leader_time_s = stats.get("leader_time_s")
            median_time_s = stats.get("median_time_s")

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
                sport=sport_val,
                finishers_count=finishers_count,
                place=place,
                leader_time_s=leader_time_s,
                median_time_s=median_time_s,
                elevation_gain_m=elevation_m,
                special=special or "regular",
                is_rl_series=bool(is_rl_series),
                discipline=disc,
                formula_version=formula_version if sport_val == "run" else None,
            )
            f_ver = breakdown.get("formula_version") or formula_version
            breakdown_json = json.dumps(breakdown, ensure_ascii=False, allow_nan=False)
            score_rows.append((rid, f_ver, points, reason, breakdown_json))
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

        # Multi-sport aggregation for rating_entry and rating_snapshot
        sport_definitions = [
            ("run", "run-v1", "(ra.sport = 'run' OR ra.sport IS NULL)"),
            ("ski", "ski-v1", "ra.sport IN ('ski', 'biathlon')"),
            ("triathlon", "triathlon-v1", "ra.sport = 'triathlon'"),
            ("trail", "trail-v1", "ra.sport = 'trail'"),
        ]

        rl_map = {}
        try:
            cur.execute("SELECT athlete_id, points FROM rl_points")
            rl_map = {row[0]: float(row[1]) for row in cur.fetchall()}
        except Exception:
            pass

        run_aggregates = []
        for sp, f_ver, sp_where in sport_definitions:
            cur.execute(f"""
                SELECT a.id AS athlete_id, SUM(s.points) AS points,
                       MAX(s.points) AS best_points, COUNT(*) AS starts_count
                FROM athlete a
                JOIN result_athlete link ON link.athlete_id = a.id
                JOIN rating_score s ON s.result_id = link.result_id
                JOIN result r ON r.id = s.result_id
                JOIN race ra ON ra.id = r.race_id
                JOIN competition c ON c.id = ra.competition_id
                WHERE s.points IS NOT NULL
                  AND c.date_begin BETWEEN %s AND %s
                  AND {sp_where}
                GROUP BY a.id
                ORDER BY points DESC, best_points DESC, starts_count DESC, a.id ASC
            """, (start_date, end_date))
            sp_rows = cur.fetchall()

            processed = []
            for row in sp_rows:
                aid = row[0]
                pts = float(row[1])
                b_pts = float(row[2])
                starts = int(row[3])
                if sp == "ski" and aid in rl_map:
                    pts += rl_map[aid] / 7.0
                processed.append((aid, pts, b_pts, starts))

            processed.sort(key=lambda x: (x[1], x[2], x[3], -x[0]), reverse=True)
            if sp == "run":
                run_aggregates = processed

            try:
                cur.execute("""
                    DELETE FROM rating_entry
                    WHERE sport = %s AND period_type = 'rolling'
                      AND period_start = %s AND period_end = %s
                """, (sp, start_str, end_str))
                entry_rows = [
                    (sp, "rolling", start_str, end_str, item[0], f_ver, item[1], item[2], item[3], rank)
                    for rank, item in enumerate(processed, 1)
                ]
                cur.executemany("""
                    INSERT INTO rating_entry (
                        sport, period_type, period_start, period_end,
                        athlete_id, formula_version, points, best_points, starts_count, rank
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sport, period_type, period_start, period_end, athlete_id) DO UPDATE SET
                        points = EXCLUDED.points,
                        best_points = EXCLUDED.best_points,
                        starts_count = EXCLUDED.starts_count,
                        rank = EXCLUDED.rank
                """, entry_rows)

                cur.execute("""
                    DELETE FROM rating_snapshot
                    WHERE sport = %s AND taken_on = %s
                """, (sp, end_date))
                snap_rows = [
                    (sp, end_date, item[0], rank, item[1])
                    for rank, item in enumerate(processed, 1)
                ]
                cur.executemany("""
                    INSERT INTO rating_snapshot (sport, taken_on, athlete_id, rank, points)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (sport, taken_on, athlete_id) DO UPDATE SET
                        rank = EXCLUDED.rank,
                        points = EXCLUDED.points
                """, snap_rows)
            except Exception:
                pass

        cur.execute("""
            DELETE FROM running_athlete_rating
            WHERE formula_version = %s AND period_start = %s AND period_end = %s
        """, (formula_version, start_str, end_str))

        rating_rows = [
            (agg[0], formula_version, start_str, end_str, agg[1], agg[2], agg[3], rank)
            for rank, agg in enumerate(run_aggregates, 1)
        ]
        cur.executemany("""
            INSERT INTO running_athlete_rating (
                athlete_id, formula_version, period_start, period_end,
                points, best_points, starts_count, rank
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, rating_rows)

        if commit:
            conn.commit()
        return {
            "formula_version": formula_version,
            "period_start": start_str,
            "period_end": end_str,
            "results_scored": scored_count,
            "athletes_rated": len(run_aggregates),
        }
    finally:
        if should_close:
            conn.close()

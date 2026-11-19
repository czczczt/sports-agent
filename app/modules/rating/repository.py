from typing import Any

from sqlalchemy import text

from app.core.repository import ReadRepository

FORMULA_VERSION = "run-v1"


class RatingRepository(ReadRepository):
    async def _query(self, query, args):
        parts = query.split("?")
        if len(parts) - 1 != len(args):
            raise ValueError("SQL bind count mismatch")
        sql = "".join(
            part + (f":p{i}" if i < len(args) else "") for i, part in enumerate(parts)
        )
        return await self.session.execute(
            text(sql), {f"p{i}": v for i, v in enumerate(args)}
        )

    async def fetch(self, query, *args):
        return (await self._query(query, args)).mappings().all()

    async def fetchrow(self, query, *args):
        return (await self._query(query, args)).mappings().first()

    async def fetchval(self, query, *args):
        return (await self._query(query, args)).scalar()

    async def get_rating_page(
        self,
        *,
        gender: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Возвращает сохранённый рейтинг для страницы рейтинга."""
        period = await self.fetchrow(
            """
            SELECT period_start, period_end
            FROM running_athlete_rating
            WHERE formula_version = ?
            ORDER BY period_end DESC
            LIMIT 1
            """,
            FORMULA_VERSION,
        )
        if not period:
            return {"period_start": None, "period_end": None, "rows": [], "total": 0}

        conditions = [
            "ar.formula_version = ?",
            "ar.period_start = ?",
            "ar.period_end = ?",
            "a.is_hidden = FALSE",
            "a.employee_status != 'not_employee'",
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
        rows = await self.fetch(
            f"""
            SELECT ar.rank, a.id AS athlete_id, a.display_name, a.birth_year,
                   a.gender, ar.points, ar.best_points, ar.starts_count
            FROM running_athlete_rating ar
            JOIN athlete a ON a.id = ar.athlete_id
            WHERE {where_clause}
            ORDER BY ar.points DESC, ar.best_points DESC, ar.starts_count DESC, ar.athlete_id
            LIMIT ?
            """,
            *params,
            limit,
        )
        total = await self.fetchval(
            f"""
            SELECT COUNT(*)
            FROM running_athlete_rating ar
            JOIN athlete a ON a.id = ar.athlete_id
            WHERE {where_clause}
            """,
            *params,
        )
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
            "total": total or 0,
        }

    async def get_rating_me_row(
        self,
        athlete_id: int,
        gender: str | None = None,
    ) -> dict[str, Any] | None:
        """Строка «это вы» для страницы рейтинга.

        Если выбран фильтр по полу, место пересчитывается среди спортсменов этого пола
        (с теми же тай-брейками, что и общий рейтинг). Спортсмен другого пола скрывается.
        """
        ar = await self.fetchrow(
            """
            SELECT a.id AS athlete_id, a.display_name, a.birth_year, a.gender,
                   ar.points, ar.best_points, ar.starts_count, ar.rank AS overall_rank,
                   ar.period_start, ar.period_end
            FROM athlete a
            LEFT JOIN running_athlete_rating ar
              ON ar.athlete_id = a.id AND ar.formula_version = ?
            WHERE a.id = ?
            ORDER BY ar.period_end DESC
            LIMIT 1
            """,
            FORMULA_VERSION,
            athlete_id,
        )
        if not ar or ar["points"] is None:
            return None
        if gender and ar["gender"] != gender:
            return None

        if gender:
            rank = await self.fetchval(
                """
                SELECT COUNT(*) + 1 AS rank
                FROM running_athlete_rating rar
                JOIN athlete a ON a.id = rar.athlete_id
                WHERE rar.formula_version = ?
                  AND a.gender = ?
                  AND rar.period_start = ? AND rar.period_end = ?
                  AND (
                      rar.points > ?
                      OR (rar.points = ? AND rar.best_points > ?)
                      OR (rar.points = ? AND rar.best_points = ? AND rar.starts_count > ?)
                      OR (rar.points = ? AND rar.best_points = ? AND rar.starts_count = ? AND rar.athlete_id < ?)
                  )
                """,
                FORMULA_VERSION,
                gender,
                ar["period_start"],
                ar["period_end"],
                ar["points"],
                ar["points"],
                ar["best_points"],
                ar["points"],
                ar["best_points"],
                ar["starts_count"],
                ar["points"],
                ar["best_points"],
                ar["starts_count"],
                ar["athlete_id"],
            )
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

    async def get_rating_norms(self, year: int = 2026) -> dict[str, Any]:
        """Нормативы года и период действующего рейтинга — для страницы «Как посчитано»."""
        norms = await self.fetch(
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
            year,
        )
        period = await self.fetchrow(
            """
            SELECT period_start, period_end
            FROM running_athlete_rating
            WHERE formula_version = ?
            ORDER BY period_end DESC LIMIT 1
            """,
            FORMULA_VERSION,
        )
        return {
            "year": year,
            "norms": [dict(row) for row in norms],
            "period_start": period["period_start"] if period else None,
            "period_end": period["period_end"] if period else None,
        }

    async def recalculate_rating(
        self,
        *,
        as_of: Any = None,
        formula_version: str = FORMULA_VERSION,
    ) -> dict[str, Any]:
        """Пересчитывает баллы результатов и агрегированный 365-дневный рейтинг бега в PostgreSQL."""
        import json
        from datetime import date, timedelta
        from app.modules.rating.calculator import _calculate_score, RATING_PERIOD_DAYS

        end_date = as_of or date.today()
        start_date = end_date - timedelta(days=RATING_PERIOD_DAYS)
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        norm_rows = await self.fetch("SELECT distance_class, gender, value, unit, year FROM rating_norm")
        norms = {
            (row["distance_class"], row["gender"]): row
            for row in norm_rows
        }

        result_rows = await self.fetch(
            """
            SELECT r.id, r.status, r.duplicate_of, r.gender, r.chip_time_s,
                   r.gun_time_s, r.distance_km, ra.distance_type, ra.discipline,
                   c.date_begin, a.id AS athlete_id
            FROM result r
            JOIN race ra ON ra.id = r.race_id
            JOIN competition c ON c.id = ra.competition_id
            LEFT JOIN result_athlete link ON link.result_id = r.id
            LEFT JOIN athlete a ON a.id = link.athlete_id
            """
        )

        scored_count = 0
        for row in result_rows:
            dist_class = row["distance_type"] or (f"{int(row['distance_km'])}km" if row["distance_km"] else None)
            norm = norms.get((dist_class, row["gender"]))
            points, reason, breakdown = _calculate_score(
                status=row["status"],
                duplicate_of=row["duplicate_of"],
                gender=row["gender"],
                distance_class=dist_class,
                event_date=str(row["date_begin"]) if row["date_begin"] else None,
                chip_time_s=row["chip_time_s"],
                gun_time_s=row["gun_time_s"],
                distance_km=row["distance_km"],
                norm_value=norm["value"] if norm else None,
                norm_unit=norm["unit"] if norm else None,
                norm_year=norm["year"] if norm else None,
            )
            breakdown_json = json.dumps(breakdown, ensure_ascii=False, allow_nan=False)
            await self.session.execute(
                text(
                    """
                    INSERT INTO rating_score (result_id, formula_version, points, reason, breakdown_json)
                    VALUES (:res_id, :ver, :pts, :rsn, :bd)
                    ON CONFLICT (result_id, formula_version) DO UPDATE SET
                        points = EXCLUDED.points,
                        reason = EXCLUDED.reason,
                        breakdown_json = EXCLUDED.breakdown_json
                    """
                ),
                {
                    "res_id": row["id"],
                    "ver": formula_version,
                    "pts": points,
                    "rsn": reason,
                    "bd": breakdown_json,
                },
            )
            if points is not None:
                scored_count += 1

        aggregates = await self.fetch(
            """
            SELECT a.id AS athlete_id, SUM(s.points) AS points,
                   MAX(s.points) AS best_points, COUNT(*) AS starts_count
            FROM athlete a
            JOIN result_athlete link ON link.athlete_id = a.id
            JOIN rating_score s ON s.result_id = link.result_id
            JOIN result r ON r.id = s.result_id
            JOIN race ra ON ra.id = r.race_id
            JOIN competition c ON c.id = ra.competition_id
            WHERE s.formula_version = ?
              AND s.points IS NOT NULL
              AND c.date_begin BETWEEN ? AND ?
            GROUP BY a.id
            ORDER BY points DESC, best_points DESC, starts_count DESC, a.id ASC
            """,
            formula_version,
            start_date,
            end_date,
        )

        await self.session.execute(
            text(
                """
                DELETE FROM running_athlete_rating
                WHERE formula_version = :ver AND period_start = :p_start AND period_end = :p_end
                """
            ),
            {"ver": formula_version, "p_start": start_str, "p_end": end_str},
        )

        for rank, agg in enumerate(aggregates, 1):
            await self.session.execute(
                text(
                    """
                    INSERT INTO running_athlete_rating (
                        athlete_id, formula_version, period_start, period_end,
                        points, best_points, starts_count, rank
                    ) VALUES (
                        :athlete_id, :formula_version, :period_start, :period_end,
                        :points, :best_points, :starts_count, :rank
                    )
                    """
                ),
                {
                    "athlete_id": agg["athlete_id"],
                    "formula_version": formula_version,
                    "period_start": start_str,
                    "period_end": end_str,
                    "points": agg["points"],
                    "best_points": agg["best_points"],
                    "starts_count": agg["starts_count"],
                    "rank": rank,
                },
            )

        await self.session.commit()
        return {
            "formula_version": formula_version,
            "period_start": start_str,
            "period_end": end_str,
            "results_scored": scored_count,
            "athletes_rated": len(aggregates),
        }

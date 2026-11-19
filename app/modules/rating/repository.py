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

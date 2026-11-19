from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession


class AthleteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self, name: str, birth_year: int | None, limit: int, offset: int
    ) -> Sequence[RowMapping]:
        result = await self.session.execute(
            text("""
                WITH matches AS (
                    SELECT id, display_name, birth_year
                    FROM athlete
                    WHERE strpos(name_key, :name) > 0
                      AND (CAST(:year AS integer) IS NULL OR birth_year = :year)
                )
                SELECT page.*, totals.total
                FROM (SELECT count(*) AS total FROM matches) AS totals
                LEFT JOIN LATERAL (
                    SELECT * FROM matches ORDER BY id LIMIT :limit OFFSET :offset
                ) AS page ON true
                ORDER BY page.id
            """),
            {"name": name, "year": birth_year, "limit": limit, "offset": offset},
        )
        return result.mappings().all()

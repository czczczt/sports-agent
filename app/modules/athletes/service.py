from .repository import AthleteRepository
from .schemas import AthleteOut, AthletePage


class AthleteService:
    def __init__(
        self, repository: AthleteRepository, web_repository, session_factory
    ) -> None:
        self.repository = repository
        self.web_repository = web_repository
        self.session_factory = session_factory

    async def search(
        self, query: str, year: int | None, limit: int, offset: int
    ) -> AthletePage:
        name = " ".join(query.casefold().replace("ё", "е").split())
        rows = await self.repository.search(name, year, limit, offset) if name else []
        return AthletePage(
            items=[
                AthleteOut.model_validate(row) for row in rows if row["id"] is not None
            ],
            total=rows[0]["total"] if rows else 0,
            limit=limit,
            offset=offset,
        )

    async def search_candidates(self, last_name, birth_year=None, limit=50):
        from app.services.athlete_service import search_athletes

        return await search_athletes(self.web_repository, last_name, birth_year, limit)

    async def athlete(self, athlete_id):
        from app.services.athlete_service import get_athlete_by_id

        return await get_athlete_by_id(self.web_repository, athlete_id)

    async def results(self, athlete_id):
        from app.services.athlete_service import get_athlete_results

        return await get_athlete_results(self.web_repository, athlete_id)

    async def summary(self, athlete_id):
        from app.services.athlete_service import get_athlete_summary

        return await get_athlete_summary(self.web_repository, athlete_id)

    async def assessment(self, athlete_id):
        from app.services.agent_service import get_or_generate_assessment

        if not await self.web_repository.athlete(athlete_id):
            from .exceptions import AthleteNotFound

            raise AthleteNotFound(f"Спортсмен {athlete_id} не найден")
        return await get_or_generate_assessment(
            self.web_repository, athlete_id, self.session_factory
        )

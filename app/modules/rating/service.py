from typing import Any


class RatingService:
    def __init__(self, repository):
        self.repository = repository

    async def page(
        self,
        sport: str = "run",
        as_of: Any = None,
        gender: str | None = None,
        search: str | None = None,
        limit: int = 100,
        athlete_id: int | None = None,
    ):
        page = await self.repository.get_rating_page(
            sport=sport, as_of=as_of, gender=gender, search=search, limit=limit
        )
        page["me_row"] = (
            await self.repository.get_rating_me_row(athlete_id, gender, sport=sport, as_of=as_of)
            if athlete_id
            else None
        )
        return page

    async def norms(self):
        return await self.repository.get_rating_norms()

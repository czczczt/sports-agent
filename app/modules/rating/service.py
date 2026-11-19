class RatingService:
    def __init__(self, repository):
        self.repository = repository

    async def page(self, gender=None, search=None, limit=100, athlete_id=None):
        page = await self.repository.get_rating_page(
            gender=gender, search=search, limit=limit
        )
        page["me_row"] = (
            await self.repository.get_rating_me_row(athlete_id, gender)
            if athlete_id
            else None
        )
        return page

    async def norms(self):
        return await self.repository.get_rating_norms()

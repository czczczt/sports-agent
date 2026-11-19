from app.services import events_service


class EventService:
    def __init__(self, repository):
        self.repository = repository

    async def list_events(
        self,
        query: str | None = None,
        title: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        city: str | None = None,
        source: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        return await events_service.list_events(
            self.repository,
            query,
            title,
            date_from,
            date_to,
            city,
            source,
            limit,
            offset,
        )

    async def get_event_by_id(self, event_id: int):
        return await events_service.get_event_by_id(self.repository, event_id)

    async def get_race_results(
        self,
        race_id: int,
        search_query: str | None = None,
        limit: int = 300,
        offset: int = 0,
    ):
        return await events_service.get_race_results(
            self.repository, race_id, search_query, limit, offset
        )

    async def get_athlete_race_result(self, race_id: int, athlete_id: int):
        return await events_service.get_athlete_race_result(
            self.repository, race_id, athlete_id
        )

    async def get_race_rating_leaders(self, race_id: int, limit: int = 3):
        return await events_service.get_race_rating_leaders(
            self.repository, race_id, limit
        )

    async def get_race_competition(self, race_id: int, athlete_id: int | None = None):
        return await events_service.get_race_competition(
            self.repository, race_id, athlete_id
        )

    async def race(self, race_id):
        return await self.repository.race(race_id)

    async def get_race_page(
        self, race_id, search_query=None, athlete_id=None, limit=300
    ):
        return await events_service.get_race_page(
            self.repository, race_id, search_query, athlete_id, limit
        )

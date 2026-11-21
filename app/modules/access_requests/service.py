from app.services.athlete_service import normalize_term


class AccessRequestsService:
    def __init__(self, repository):
        self.repository = repository

    async def commit(self):
        await self.repository.session.commit()

    async def list_by_status(self, status):
        return await self.repository.list_by_status(status)

    async def list_all(self):
        return await self.repository.list_all()

    async def get_linked_athlete(self, athlete_id):
        return await self.repository.get_linked_athlete(athlete_id)

    async def match_athlete_year(self, pattern, year_from, year_to):
        return await self.repository.match_athlete_year(pattern, year_from, year_to)

    async def match_athlete(self, pattern):
        return await self.repository.match_athlete(pattern)

    async def get_user(self, user_id):
        return await self.repository.get_user(user_id)

    async def update_decision(self, status, athlete_id, moderator_id, user_id):
        return await self.repository.update_decision(
            status, athlete_id, moderator_id, user_id
        )

    async def audit_decision(self, user_id, action, entity_id, diff):
        return await self.repository.audit_decision(user_id, action, entity_id, diff)

    async def get_athlete(self, athlete_id):
        return await self.repository.get_athlete(athlete_id)

    async def mark_presumed(self, athlete_id):
        return await self.repository.mark_presumed(athlete_id)

    async def create_athlete_from_user(self, user_row) -> int:
        return await self.repository.create_athlete_from_user(user_row)

    async def candidates(self, users):
        ids = [u["athlete_id"] for u in users if u["athlete_id"]]
        names = {
            u["id"]: normalize_term(f"{u['last_name']} {u['first_name']}")
            for u in users
            if u["last_name"] and u["first_name"]
        }
        athletes = await self.repository.candidates(
            ids, [f"%{name}%" for name in names.values()]
        )
        by_id = {a["id"]: a for a in athletes}
        matches = {}
        for user in users:
            if user["athlete_id"]:
                matches[user["id"]] = by_id.get(user["athlete_id"])
                continue
            name = names.get(user["id"])
            year = user["birth_date"].year if user["birth_date"] else None
            if name:
                matches[user["id"]] = next(
                    (
                        a
                        for a in athletes
                        if name in a["name_key"]
                        and (
                            year is None
                            or (
                                a["birth_year"] is not None
                                and year - 1 <= a["birth_year"] <= year + 1
                            )
                        )
                    ),
                    None,
                )
        return matches

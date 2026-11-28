class ReportsService:
    def __init__(self, repository):
        self.repository = repository

    async def commit(self):
        await self.repository.session.commit()

    async def find_pending_link_claim(self, user_id):
        return await self.repository.find_pending_link_claim(user_id)

    async def create(
        self, kind, user_id, athlete_id, result_id, event_id, url, message
    ):
        return await self.repository.create(
            kind, user_id, athlete_id, result_id, event_id, url, message
        )

    async def list_by_status(self, status):
        return await self.repository.list_by_status(status)

    async def list_all(self):
        return await self.repository.list_all()

    async def list_by_user(self, user_id):
        return await self.repository.list_by_user(user_id)

    async def get_report(self, report_id):
        return await self.repository.get_report(report_id)

    async def update_decision(self, decision, moderator_id, comment, report_id):
        return await self.repository.update_decision(
            decision, moderator_id, comment, report_id
        )

    async def audit_decision(self, user_id, report_id, diff):
        return await self.repository.audit_decision(user_id, report_id, diff)

    async def hide_athlete(self, athlete_id):
        return await self.repository.hide_athlete(athlete_id)

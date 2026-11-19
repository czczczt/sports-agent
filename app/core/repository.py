from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ReadRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def rows(self, sql: str, params: dict | None = None):
        return (await self.session.execute(text(sql), params or {})).mappings().all()

    async def row(self, sql: str, params: dict | None = None):
        return (await self.session.execute(text(sql), params or {})).mappings().first()

    async def scalar(self, sql: str, params: dict | None = None):
        return (await self.session.execute(text(sql), params or {})).scalar()

    async def execute(self, sql: str, params: dict | None = None):
        return await self.session.execute(text(sql), params or {})

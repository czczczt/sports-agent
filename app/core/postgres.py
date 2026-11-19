from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = getattr(request.app.state, "postgres_sessions", None)
    if factory is None:
        raise HTTPException(
            status_code=503, detail="PostgreSQL session factory is unavailable"
        )
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]

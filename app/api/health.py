import logging

from asyncpg import PostgresError
from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.health_repository import HealthRepository
from app.core.postgres import SessionDep

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health/live", include_in_schema=False)
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
async def ready(session: SessionDep) -> dict[str, str]:
    try:
        available = await HealthRepository(session).ready()
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError):
        logger.warning("PostgreSQL readiness check failed")
        raise HTTPException(status_code=503, detail="Database is unavailable") from None
    if not available:
        raise HTTPException(status_code=503, detail="Database schema is unavailable")
    return {"status": "ok"}

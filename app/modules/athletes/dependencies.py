from typing import Annotated

from fastapi import Depends, Request

from app.core.postgres import SessionDep

from .repository import AthleteRepository
from .service import AthleteService
from .web_repository import AthletesWebRepository


def get_athlete_service(session: SessionDep, request: Request) -> AthleteService:
    return AthleteService(
        AthleteRepository(session),
        AthletesWebRepository(session),
        getattr(request.app.state, "postgres_sessions", None),
    )


AthleteServiceDep = Annotated[AthleteService, Depends(get_athlete_service)]

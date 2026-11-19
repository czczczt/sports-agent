from typing import Annotated

from fastapi import Depends

from app.core.postgres import SessionDep

from .repository import RatingRepository
from .service import RatingService


def get_rating_service(session: SessionDep) -> RatingService:
    return RatingService(RatingRepository(session))


RatingServiceDep = Annotated[RatingService, Depends(get_rating_service)]

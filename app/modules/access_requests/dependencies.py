from typing import Annotated

from fastapi import Depends

from app.core.postgres import SessionDep

from .repository import AccessRequestsRepository
from .service import AccessRequestsService


def get_service(session: SessionDep):
    return AccessRequestsService(AccessRequestsRepository(session))


AccessRequestsServiceDep = Annotated[AccessRequestsService, Depends(get_service)]

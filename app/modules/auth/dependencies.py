from typing import Annotated

from fastapi import Depends

from app.core.postgres import SessionDep

from .repository import AuthRepository
from .service import AuthService


def get_service(session: SessionDep):
    return AuthService(AuthRepository(session))


AuthServiceDep = Annotated[AuthService, Depends(get_service)]

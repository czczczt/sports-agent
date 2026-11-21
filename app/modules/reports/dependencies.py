from typing import Annotated

from fastapi import Depends

from app.core.postgres import SessionDep

from .repository import ReportsRepository
from .service import ReportsService


def get_service(session: SessionDep):
    return ReportsService(ReportsRepository(session))


ReportsServiceDep = Annotated[ReportsService, Depends(get_service)]

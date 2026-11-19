from typing import Annotated

from fastapi import Depends

from app.core.postgres import SessionDep

from .service import EventService
from .web_repository import EventsWebRepository


def get_event_service(session: SessionDep):
    return EventService(EventsWebRepository(session))


EventServiceDep = Annotated[EventService, Depends(get_event_service)]

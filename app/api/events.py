from fastapi import APIRouter, HTTPException, Query

from app.models import EventItem
from app.modules.events.dependencies import EventServiceDep

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventItem])
async def get_events_endpoint(
    db: EventServiceDep,
    query: str | None = Query(None, description="Поиск по названию забега"),
    title: str | None = Query(
        None, description="Поиск по названию забега (алиас query)"
    ),
    date_from: str | None = Query(None, description="Дата старта от (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Дата старта до (YYYY-MM-DD)"),
    city: str | None = Query(None, description="Город или место проведения"),
    source: str | None = Query(
        None, description="Площадка (russiarunning, timerman, runc, grom)"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Каталог стартов с фильтрами по названию забега, дате, городу и площадке."""
    search_query = query or title
    events = await db.list_events(
        query=search_query,
        date_from=date_from,
        date_to=date_to,
        city=city,
        source=source,
        limit=limit,
        offset=offset,
    )
    return events


@router.get("/{event_id}", response_model=EventItem)
async def get_event_detail_endpoint(
    db: EventServiceDep,
    event_id: int,
):
    """Детальная карточка старта с дистанциями."""
    event = await db.get_event_by_id(event_id=event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Старт не найден")
    return event

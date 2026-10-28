import sqlite3
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_db
from app.models import EventItem
from app.services.events_service import list_events, get_event_by_id

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=List[EventItem])
def get_events_endpoint(
    date_from: Optional[str] = Query(None, description="Дата старта от (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Дата старта до (YYYY-MM-DD)"),
    city: Optional[str] = Query(None, description="Город или место проведения"),
    source: Optional[str] = Query(None, description="Площадка (russiarunning, timerman, runc, grom)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db)
):
    """Каталог стартов с фильтрами по дате, городу и площадке."""
    events = list_events(
        db, date_from=date_from, date_to=date_to, city=city,
        source=source, limit=limit, offset=offset
    )
    return events


@router.get("/{event_id}", response_model=EventItem)
def get_event_detail_endpoint(
    event_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """Детальная карточка старта с дистанциями."""
    event = get_event_by_id(db, event_id=event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Старт не найден")
    return event

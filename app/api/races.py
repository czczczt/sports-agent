import sqlite3
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_db
from app.models import RaceProtocolItem, CompetitionDistribution
from app.services.events_service import get_race_results, get_race_competition

router = APIRouter(prefix="/races", tags=["races"])


@router.get("/{race_id}/results", response_model=List[RaceProtocolItem])
def get_race_results_endpoint(
    race_id: int,
    search: Optional[str] = Query(None, description="Поиск по фамилии или стартовому номеру (bib)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Протокол дистанции:
    сортировка по местам, поддержка поиска по фамилии и номеру bib.
    """
    results = get_race_results(db, race_id=race_id, search_query=search, limit=limit, offset=offset)
    return results


@router.get("/{race_id}/competition", response_model=CompetitionDistribution)
def get_race_competition_endpoint(
    race_id: int,
    athlete_id: Optional[int] = Query(None, description="ID спортсмена для подсветки в распределении"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Блок 'Конкуренция':
    распределение времен всех участников дистанции (бины гистограммы)
    и положение выбранного спортсмена среди финишеров.
    """
    competition = get_race_competition(db, race_id=race_id, athlete_id=athlete_id)
    if not competition:
        raise HTTPException(status_code=404, detail="Дистанция или результаты не найдены")
    return competition

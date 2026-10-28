import sqlite3
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_db
from app.models import (
    AthleteCandidate, AthleteResultItem, AthleteSummaryResponse, AssessmentResponse
)
from app.services.athlete_service import (
    search_athletes, get_athlete_results, get_athlete_summary
)
from app.services.agent_service import get_or_generate_assessment

router = APIRouter(prefix="/athletes", tags=["athletes"])


@router.get("/search", response_model=List[AthleteCandidate])
def search_athletes_endpoint(
    last_name: str = Query(..., description="Фамилия спортсмена (регистронезависимо, е/ё)"),
    birth_year: Optional[int] = Query(None, description="Год рождения (поиск с допуском +- 1 год)"),
    limit: int = Query(50, ge=1, le=200),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Поиск спортсмена по фамилии и году рождения.
    Поиск без учета регистра и с заменой е/ё.
    Для строк без точной даты/года рождения используется расчётный год с допуском +-1 год.
    """
    candidates = search_athletes(db, last_name=last_name, birth_year=birth_year, limit=limit)
    return candidates


@router.get("/{athlete_id}/results", response_model=List[AthleteResultItem])
def get_athlete_results_endpoint(
    athlete_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Таблица всех завершенных результатов спортсмена:
    старт, дата, дистанция, место (общее и по полу), чистое и пистолетное время, темп.
    """
    results = get_athlete_results(db, athlete_id=athlete_id)
    return results


@router.get("/{athlete_id}/summary", response_model=AthleteSummaryResponse)
def get_athlete_summary_endpoint(
    athlete_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Сводный профиль спортсмена:
    анкета, личные рекорды (PB), динамика по времени, рейтинг (заглушка формулы).
    """
    summary = get_athlete_summary(db, athlete_id=athlete_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    return summary


@router.post("/{athlete_id}/assessment", response_model=AssessmentResponse)
async def generate_athlete_assessment_endpoint(
    athlete_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    ИИ-агент для спортсмена:
    вызывается по кнопке, генерирует оценку по всем метрикам.
    Ответ кэшируется в БД, чтобы не тратить токены повторно.
    """
    assessment = await get_or_generate_assessment(db, athlete_id=athlete_id)
    return assessment

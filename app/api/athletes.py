from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import AsyncPGConnection, get_db
from app.models import (
    AthleteCandidate, AthleteResultItem, AthleteSummaryResponse, AssessmentResponse, UserOut
)
from app.api.auth import get_optional_current_user
from app.services.athlete_service import (
    search_athletes, get_athlete_results, get_athlete_summary
)
from app.services.agent_service import get_or_generate_assessment

router = APIRouter(prefix="/athletes", tags=["athletes"])


def sanitize_athlete_privacy(candidate: AthleteCandidate, is_privileged: bool) -> AthleteCandidate:
    """
    Разграничение видимости ПДн (SPEC v1.3 §2, §5):
    - Привилегированные пользователи (admin, captain) видят полные данные: город, регион, клуб, отчество, точную дату рождения.
    - Обычные пользователи и гости: город, регион, клуб, отчество и точная дата рождения скрываются (None).
      Доступен только расчётный/точный год рождения (birth_year) и ФИ (first_name, last_name, display_name).
    """
    if is_privileged:
        return candidate
    candidate_dict = candidate.model_dump()
    candidate_dict["city"] = None
    candidate_dict["region"] = None
    candidate_dict["club"] = None
    candidate_dict["birth_date"] = None
    candidate_dict["middle_name"] = None
    return AthleteCandidate(**candidate_dict)


@router.get("/search", response_model=List[AthleteCandidate])
async def search_athletes_endpoint(
    last_name: str = Query(..., description="Фамилия спортсмена (регистронезависимо, е/ё)"),
    birth_year: Optional[int] = Query(None, description="Год рождения (поиск с допуском +- 1 год)"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncPGConnection = Depends(get_db),
    current_user: Optional[UserOut] = Depends(get_optional_current_user),
):
    """
    Поиск спортсмена по фамилии и году рождения.
    Поиск без учета регистра и с заменой е/ё.
    Для строк без точной даты/года рождения используется расчётный год с допуском +-1 год.
    """
    candidates = await search_athletes(db, last_name=last_name, birth_year=birth_year, limit=limit)
    is_privileged = bool(current_user and current_user.role in ("admin", "captain"))
    return [sanitize_athlete_privacy(c, is_privileged) for c in candidates]


@router.get("/{athlete_id}/results", response_model=List[AthleteResultItem])
async def get_athlete_results_endpoint(
    athlete_id: int,
    db: AsyncPGConnection = Depends(get_db)
):
    """
    Таблица всех завершенных результатов спортсмена:
    старт, дата, дистанция, место (общее и по полу), чистое и пистолетное время, темп.
    """
    results = await get_athlete_results(db, athlete_id=athlete_id)
    return results


@router.get("/{athlete_id}/summary", response_model=AthleteSummaryResponse)
async def get_athlete_summary_endpoint(
    athlete_id: int,
    db: AsyncPGConnection = Depends(get_db),
    current_user: Optional[UserOut] = Depends(get_optional_current_user),
):
    """
    Сводный профиль спортсмена:
    анкета, личные рекорды (PB), динамика по времени, рейтинг (заглушка формулы).
    """
    summary = await get_athlete_summary(db, athlete_id=athlete_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    is_privileged = bool(current_user and current_user.role in ("admin", "captain"))
    summary.athlete = sanitize_athlete_privacy(summary.athlete, is_privileged)
    return summary


@router.post("/{athlete_id}/assessment", response_model=AssessmentResponse)
async def generate_athlete_assessment_endpoint(
    athlete_id: int,
    db: AsyncPGConnection = Depends(get_db)
):
    """
    ИИ-агент для спортсмена:
    вызывается по кнопке, генерирует оценку по всем метрикам.
    Ответ кэшируется в БД, чтобы не тратить токены повторно.
    """
    assessment = await get_or_generate_assessment(db, athlete_id=athlete_id)
    return assessment

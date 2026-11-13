import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.models import RatingPageResponse, RatingFormulaResponse
from app.services.rating_service import get_rating_page, get_rating_me_row, get_rating_norms

router = APIRouter(prefix="/rating", tags=["rating"])


@router.get("", response_model=RatingPageResponse)
def get_rating_endpoint(
    gender: Optional[str] = Query(None, description="Пол: M или F (иначе — все)"),
    search: Optional[str] = Query(None, description="Поиск по ФИО"),
    athlete_id: Optional[int] = Query(None, description="Спортсмен, которого нужно подсветить («это вы»)"),
    limit: int = Query(100, ge=1, le=500),
    db: sqlite3.Connection = Depends(get_db),
):
    """
    Сохранённый рейтинг бегунов за последние 365 дней.
    С athlete_id дополнительно возвращает строку спортсмена (me_row);
    при фильтре по полу его место пересчитывается среди этого пола.
    """
    clean_gender = gender if gender in ("M", "F") else None
    clean_search = (search or "").strip() or None
    page = get_rating_page(db, gender=clean_gender, search=clean_search, limit=limit)
    page["me_row"] = get_rating_me_row(db, athlete_id, clean_gender) if athlete_id else None
    return page


@router.get("/formula", response_model=RatingFormulaResponse)
def get_rating_formula_endpoint(db: sqlite3.Connection = Depends(get_db)):
    """Нормативы 2026 года по дистанциям и полу — для страницы «Как посчитано»."""
    return get_rating_norms(db)

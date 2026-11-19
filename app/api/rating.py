from app.models import RatingFormulaResponse, RatingPageResponse
from app.modules.rating.dependencies import RatingServiceDep
from fastapi import APIRouter, Query

router = APIRouter(prefix="/rating", tags=["rating"])


@router.get("", response_model=RatingPageResponse)
async def get_rating_endpoint(
    db: RatingServiceDep,
    gender: str | None = Query(None, description="Пол: M или F (иначе — все)"),
    search: str | None = Query(None, description="Поиск по ФИО"),
    athlete_id: int | None = Query(
        None, description="Спортсмен, которого нужно подсветить («это вы»)"
    ),
    limit: int = Query(100, ge=1, le=500),
):
    clean_gender = gender if gender in ("M", "F") else None
    clean_search = (search or "").strip() or None
    return await db.page(clean_gender, clean_search, limit, athlete_id)


@router.get("/formula", response_model=RatingFormulaResponse)
async def get_rating_formula_endpoint(db: RatingServiceDep):
    return await db.norms()

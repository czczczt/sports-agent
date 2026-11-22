from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.api.auth import OptionalUserDep, check_captain_sport_scope
from app.models import RatingFormulaResponse, RatingPageResponse
from app.modules.rating.dependencies import RatingServiceDep

router = APIRouter(prefix="/rating", tags=["rating"])


@router.get("", response_model=RatingPageResponse)
async def get_rating_endpoint(
    db: RatingServiceDep,
    current_user: OptionalUserDep,
    sport: str = Query("run", description="Вид спорта: run, ski, triathlon, trail"),
    as_of: date | None = Query(None, description="Срез на дату (только для капитана и админа)"),
    gender: str | None = Query(None, description="Пол: M или F (иначе — все)"),
    search: str | None = Query(None, description="Поиск по ФИО"),
    athlete_id: int | None = Query(
        None, description="Спортсмен, которого нужно подсветить («это вы»)"
    ),
    limit: int = Query(100, ge=1, le=500),
):
    clean_sport = sport.lower() if sport else "run"
    if clean_sport not in ("run", "ski", "triathlon", "trail"):
        clean_sport = "run"

    if as_of is not None:
        if not current_user or current_user.role not in ("captain", "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Срез на дату доступен только капитану и администратору",
            )
        if current_user.role == "captain":
            check_captain_sport_scope(current_user, clean_sport)

    clean_gender = gender if gender in ("M", "F") else None
    clean_search = (search or "").strip() or None
    return await db.page(
        sport=clean_sport,
        as_of=as_of,
        gender=clean_gender,
        search=clean_search,
        limit=limit,
        athlete_id=athlete_id,
    )


@router.get("/formula", response_model=RatingFormulaResponse)
async def get_rating_formula_endpoint(db: RatingServiceDep):
    return await db.norms()

from fastapi import APIRouter, HTTPException, Query

from app.models import CompetitionDistribution, RacePageResponse, RaceProtocolItem
from app.modules.events.dependencies import EventServiceDep

router = APIRouter(prefix="/races", tags=["races"])


@router.get("/{race_id}", response_model=RacePageResponse)
async def get_race_page_endpoint(
    db: EventServiceDep,
    race_id: int,
    search: str | None = Query(
        None, description="Поиск по фамилии или стартовому номеру (bib)"
    ),
    athlete_id: int | None = Query(
        None, description="ID спортсмена для подсветки «это вы»"
    ),
    employees_only: bool = Query(
        False, description="Показывать только сотрудников Сбера (SPEC v1.3 §10.2)"
    ),
):
    page = await db.get_race_page(
        race_id=race_id,
        search_query=search,
        athlete_id=athlete_id,
        employees_only=employees_only,
    )
    if not page:
        raise HTTPException(status_code=404, detail="Дистанция не найдена")
    return page


@router.get("/{race_id}/results", response_model=list[RaceProtocolItem])
async def get_race_results_endpoint(
    db: EventServiceDep,
    race_id: int,
    search: str | None = Query(
        None, description="Поиск по фамилии или стартовому номеру (bib)"
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    employees_only: bool = Query(
        False, description="Показывать только сотрудников Сбера (SPEC v1.3 §10.2)"
    ),
):
    results = await db.get_race_results(
        race_id=race_id,
        search_query=search,
        limit=limit,
        offset=offset,
        employees_only=employees_only,
    )
    return results


@router.get("/{race_id}/competition", response_model=CompetitionDistribution)
async def get_race_competition_endpoint(
    db: EventServiceDep,
    race_id: int,
    athlete_id: int | None = Query(
        None, description="ID спортсмена для подсветки в распределении"
    ),
):
    competition = await db.get_race_competition(race_id=race_id, athlete_id=athlete_id)
    if not competition:
        raise HTTPException(
            status_code=404, detail="Дистанция или результаты не найдены"
        )
    return competition

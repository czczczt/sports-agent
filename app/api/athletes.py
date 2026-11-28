from fastapi import APIRouter, HTTPException, Query

from app.api.auth import OptionalUserDep
from app.models import (
    AssessmentResponse,
    AthleteCandidate,
    AthleteResultItem,
    AthleteSummaryResponse,
)
from app.modules.athletes.dependencies import AthleteServiceDep

router = APIRouter(prefix="/athletes", tags=["athletes"])


def sanitize_athlete_privacy(
    candidate: AthleteCandidate, is_privileged: bool
) -> AthleteCandidate:
    candidate_dict = candidate.model_dump()
    if not is_privileged:
        candidate_dict["city"] = None
        candidate_dict["region"] = None
        candidate_dict["club"] = None
        candidate_dict["birth_date"] = None
        candidate_dict["middle_name"] = None
    return AthleteCandidate(**candidate_dict)


@router.get("/search", response_model=list[AthleteCandidate])
async def search_athletes_endpoint(
    current_user: OptionalUserDep,
    db: AthleteServiceDep,
    last_name: str = Query(
        ..., description="Фамилия спортсмена (регистронезависимо, е/ё)"
    ),
    birth_year: int | None = Query(
        None, description="Год рождения (поиск с допуском +- 1 год)"
    ),
    limit: int = Query(50, ge=1, le=200),
):
    candidates = await db.search_candidates(
        last_name=last_name, birth_year=birth_year, limit=limit
    )
    is_privileged = bool(current_user and current_user.role in ("admin", "captain"))
    return [
        sanitize_athlete_privacy(
            c, is_privileged or bool(current_user and current_user.athlete_id == c.id)
        )
        for c in candidates
    ]


@router.get("/{athlete_id}/results", response_model=list[AthleteResultItem])
async def get_athlete_results_endpoint(
    current_user: OptionalUserDep,
    db: AthleteServiceDep,
    athlete_id: int,
):
    athlete = await db.athlete(athlete_id=athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    is_privileged = bool(current_user and current_user.role in ("admin", "captain"))
    is_self = bool(current_user and current_user.athlete_id == athlete_id)
    if (athlete.is_hidden or athlete.employee_status == "not_employee") and not (
        is_privileged or is_self
    ):
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    results = await db.results(athlete_id=athlete_id)
    return results


@router.get("/{athlete_id}/summary", response_model=AthleteSummaryResponse)
async def get_athlete_summary_endpoint(
    current_user: OptionalUserDep,
    db: AthleteServiceDep,
    athlete_id: int,
):
    summary = await db.summary(athlete_id=athlete_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    is_privileged = bool(current_user and current_user.role in ("admin", "captain"))
    is_self = bool(current_user and current_user.athlete_id == athlete_id)
    if (
        summary.athlete.is_hidden or summary.athlete.employee_status == "not_employee"
    ) and not (is_privileged or is_self):
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    summary.athlete = sanitize_athlete_privacy(summary.athlete, is_privileged or is_self)
    return summary


@router.post("/{athlete_id}/assessment", response_model=AssessmentResponse)
async def generate_athlete_assessment_endpoint(
    current_user: OptionalUserDep,
    db: AthleteServiceDep,
    athlete_id: int,
):
    athlete = await db.athlete(athlete_id=athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    is_privileged = bool(current_user and current_user.role in ("admin", "captain"))
    is_self = bool(current_user and current_user.athlete_id == athlete_id)
    if (athlete.is_hidden or athlete.employee_status == "not_employee") and not (
        is_privileged or is_self
    ):
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    assessment = await db.assessment(athlete_id=athlete_id)
    return assessment

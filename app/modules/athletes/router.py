from typing import Annotated

from fastapi import APIRouter, Query

from .dependencies import AthleteServiceDep
from .schemas import AthletePage

router = APIRouter(prefix="/athletes", tags=["athletes v1"])


@router.get("/search")
async def search(
    service: AthleteServiceDep,
    query: Annotated[str, Query(min_length=1, max_length=100)],
    birth_year: Annotated[int | None, Query(ge=1, le=9999)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=2_147_483_647)] = 0,
) -> AthletePage:
    return await service.search(query, birth_year, limit, offset)

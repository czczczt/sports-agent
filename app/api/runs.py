from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth import AdminDep
from app.modules.runs.service import RunConflict, SourceDisabled, read_run, start_run

router = APIRouter(prefix='/v1/runs', tags=['runs'])
RunStatus = Literal['queued', 'running', 'succeeded', 'failed']
RunPhase = Literal['queued', 'fetching', 'publishing', 'retrying', 'done', 'failed']


class StartRun(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['collect']
    source: Literal['russiarunning']
    event_code: str = Field(min_length=1, max_length=200, pattern=r'^[a-zA-Z0-9_-]+$')


class QueuedRun(BaseModel):
    run_id: int
    status: Literal['queued']


class RunProgress(BaseModel):
    phase: RunPhase
    processed_distances: int


class RunDetail(BaseModel):
    id: int
    run_id: int
    source_id: int
    source: Literal['russiarunning']
    kind: Literal['collect']
    event_code: str
    status: RunStatus
    phase: RunPhase
    processed_distances: int
    error: str | None
    rating_version_id: int | None
    created_at: datetime
    updated_at: datetime
    progress: RunProgress


@router.post('', status_code=202, response_model=QueuedRun)
async def create_run(body: StartRun, _: AdminDep) -> QueuedRun | JSONResponse:
    try:
        return QueuedRun.model_validate(await start_run(body.event_code))
    except SourceDisabled as exc:
        raise HTTPException(409, str(exc)) from exc
    except RunConflict as exc:
        return JSONResponse(status_code=409, content={
            'detail': 'Source already has an active run', 'run_id': exc.run_id,
        })


@router.get('/{run_id}', response_model=RunDetail)
async def get_run(run_id: int, _: AdminDep) -> RunDetail:
    run = await read_run(run_id)
    if run is None:
        raise HTTPException(404, 'Run not found')
    return RunDetail.model_validate(run)

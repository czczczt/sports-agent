import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.auth import AdminDep
from app.modules.bulk_collection.approval import BulkConflict, BulkPublicationFailed
from app.modules.bulk_collection.collection import EVENT_CODE_PATTERN, create_batch, list_batches, list_sources
from app.modules.bulk_collection.publication_service import BulkBatchNotFound, publish_batch, read_batch
from app.pipeline.sources import SourceCode

router = APIRouter(prefix="/admin/collection", tags=["admin-collection"])
PublicationStatus = Literal["pending", "published", "failed"]


class SourceSummary(BaseModel):
    code: SourceCode
    label: str
    automatic: bool
    enabled: bool


class KnownStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: SourceCode
    event_code: str = Field(pattern=EVENT_CODE_PATTERN)


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[SourceCode] = Field(min_length=1, max_length=len(SourceCode))
    starts: list[KnownStart] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_selected_start_sources(self):
        if any(start.source not in self.sources for start in self.starts):
            raise ValueError("Each known start must belong to a selected source")
        return self


class BatchCreated(BaseModel):
    id: int


class BatchSummary(BatchCreated):
    created_at: datetime


class SourceProgress(BaseModel):
    code: SourceCode
    status: Literal["queued", "running", "completed", "failed", "unsupported", "disabled"]
    error: str | None


class DraftSummary(BaseModel):
    id: int
    source: SourceCode
    event_code: str
    status: Literal["queued", "running", "ready", "failed", "approved", "unchanged"]
    error: str | None
    title: str | None = None
    date: str | None = None
    city: str | None = None
    participants: int | None = None
    is_new: bool | None = None


class ProtocolSummary(BaseModel):
    key: str
    draft_id: int | None
    source: str
    title: str
    date: str | None
    city: str | None
    url: str | None
    race_name: str | None
    distance_m: float | None
    sport: str | None
    relay: bool
    participants: int
    is_final: bool | None
    published: bool
    planned: bool


class RacePreview(BaseModel):
    key: str
    label: str
    distance_m: float | None
    sport: str | None
    relay: bool
    participants: int
    warning: str | None
    preferred_protocol_key: str | None
    protocols: list[ProtocolSummary]


class EventPreview(BaseModel):
    key: str
    draft_ids: list[int]
    title: str
    date: str | None
    city: str | None
    source: str
    participants: int
    is_new: bool
    races: list[RacePreview]


class BatchDetail(BatchSummary):
    sources: list[SourceProgress]
    drafts: list[DraftSummary]
    events: list[EventPreview]
    preview_revision: str
    publication_status: PublicationStatus
    publication_error: str | None


class RaceResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    race_key: str = Field(min_length=1, max_length=500)
    protocol_key: str = Field(min_length=1, max_length=500)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_ids: list[int] = Field(min_length=1)
    resolutions: list[RaceResolution] = Field(default_factory=list)
    preview_revision: str = Field(min_length=1, max_length=200)


class ApprovalResult(BaseModel):
    approved_draft_ids: list[int]
    pending_draft_ids: list[int]
    published_races: int
    rating_version_id: int | None
    publication_status: PublicationStatus


@router.get("/sources", response_model=list[SourceSummary])
async def get_sources(_: AdminDep):
    return await list_sources()


@router.post("/batches", status_code=202, response_model=BatchCreated)
async def start_batch(body: BatchRequest, _: AdminDep):
    starts = defaultdict(list)
    for start in body.starts:
        starts[start.source].append(start.event_code)
    return {"id": await create_batch(body.sources, starts)}


@router.get("/batches", response_model=list[BatchSummary])
async def get_batches(_: AdminDep):
    return await list_batches()


@router.get("/batches/{batch_id}", response_model=BatchDetail)
async def get_batch(batch_id: int, _: AdminDep):
    try:
        return await asyncio.to_thread(read_batch, batch_id)
    except BulkBatchNotFound as exc:
        raise HTTPException(404, "Collection batch not found") from exc


@router.post("/batches/{batch_id}/approve", response_model=ApprovalResult)
async def approve_batch(batch_id: int, body: ApprovalRequest, admin: AdminDep):
    try:
        return await asyncio.to_thread(
            publish_batch, batch_id, body.draft_ids, [resolution.model_dump() for resolution in body.resolutions],
            body.preview_revision, admin.id,
        )
    except BulkBatchNotFound as exc:
        raise HTTPException(404, "Collection batch not found") from exc
    except BulkConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except BulkPublicationFailed as exc:
        raise HTTPException(500, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any, Literal
from uuid import uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import Response

from app.api.auth import AdminDep
from app.recipe_agent.contracts import (
    GoldenInput,
    PositiveId,
    ReviewDecision,
    StartRepair,
)
from app.recipe_agent.extraction import InvalidProtocol
from app.recipe_agent.repository import RecipeConflict, RecipeNotFound, RecipeRepository
from app.recipe_agent.service import repository
from app.worker import enqueue_recipe_collection, enqueue_recipe_repair


class RecipeRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handle = super().get_route_handler()

        async def handle_errors(request: Request) -> Response:
            try:
                return await handle(request)
            except RecipeNotFound as exc:
                raise HTTPException(404, str(exc)) from exc
            except (RecipeConflict, InvalidProtocol) as exc:
                raise HTTPException(409, str(exc)) from exc
            except psycopg.OperationalError as exc:
                raise HTTPException(503, "База рецептов недоступна") from exc

        return handle_errors


router = APIRouter(
    prefix="/api/agent-review/recipes", tags=["recipe-agent"], route_class=RecipeRoute
)
GoldenSet = Annotated[list[GoldenInput], Field(min_length=3, max_length=5)]


async def get_repository() -> AsyncIterator[RecipeRepository]:
    async with repository() as repo:
        yield repo


RepositoryDep = Annotated[RecipeRepository, Depends(get_repository)]


class RepairAttempt(BaseModel):
    step: Literal["trial", "sample", "golden", "generate", "repair", "unavailable"]
    errors: list[str]


class RepairReview(BaseModel):
    id: int
    issue_id: int | None
    source_id: int
    source_name: str | None
    status: str
    candidate: dict[str, Any] | None
    errors: list[str]
    can_approve: bool
    attempts: list[RepairAttempt]
    golden_passed: int
    golden_total: int
    tokens_used: int
    recipe_version: int | None
    base_selector: str | None
    saved_rows: int
    collection_pending: bool


def review_item(repair: dict[str, Any]) -> dict[str, Any]:
    state = repair["state"]
    return {
        "id": repair["id"],
        "issue_id": repair["issue_id"],
        "source_id": repair["source_id"],
        "source_name": repair.get("source_name"),
        "status": repair["status"],
        "candidate": state.get("candidate"),
        "errors": state.get("errors", []),
        "can_approve": repair["status"] == "waiting" and state.get("passed", False),
        "attempts": state.get("attempts", []),
        "golden_passed": state.get("golden_passed", 0),
        "golden_total": state.get("golden_total", 0),
        "tokens_used": state.get("tokens_in", 0) + state.get("tokens_out", 0),
        "recipe_version": repair.get("recipe_version"),
        "base_selector": state.get("base_selector"),
        "saved_rows": repair.get("saved_rows", 0),
        "collection_pending": repair.get("collection_pending", False),
    }


@router.get("", response_model=list[RepairReview])
async def list_repairs(_: AdminDep, repo: RepositoryDep) -> list[dict[str, Any]]:
    return [review_item(row) for row in await repo.review_queue()]


@router.get("/{repair_id}", response_model=RepairReview)
async def get_repair(
    repair_id: PositiveId, _: AdminDep, repo: RepositoryDep
) -> dict[str, Any]:
    rows = await repo.review_queue(repair_id)
    if not rows:
        raise RecipeNotFound("Ремонт не найден")
    return review_item(rows[0])


@router.put("/sources/{source_id}/golden")
async def replace_golden(
    source_id: PositiveId,
    cases: GoldenSet,
    _: AdminDep,
    repo: RepositoryDep,
) -> dict[str, int]:
    await repo.replace_golden(source_id, cases)
    return {"count": len(cases)}


@router.post("/sources/{source_id}/collect", status_code=202)
async def queue_collection(
    source_id: PositiveId, _: AdminDep, repo: RepositoryDep
) -> dict[str, int]:
    async with repo.connection.transaction():
        await repo.lock_source(source_id)
        if not await repo.active(source_id):
            raise RecipeConflict("У источника нет активного рецепта")
        await enqueue_recipe_collection(repo, source_id)
    return {"source_id": source_id}


@router.post("", status_code=202, response_model=RepairReview)
async def start_repair(
    task: StartRepair, admin: AdminDep, repo: RepositoryDep
) -> dict[str, Any]:
    async with repo.connection.transaction():
        repair_id = await repo.start(task, admin.username)
        repair = await repo.get_repair(repair_id)
        if repair["status"] == "running":
            await enqueue_recipe_repair(repo, repair_id)
    return review_item(repair)


@router.post("/{repair_id}/decision", status_code=202, response_model=RepairReview)
async def decide(
    repair_id: PositiveId,
    decision: ReviewDecision,
    admin: AdminDep,
    repo: RepositoryDep,
) -> dict[str, Any]:
    async with repo.connection.transaction():
        repair = await repo.get_repair(repair_id, lock=True)
        if repair["status"] != "waiting":
            raise RecipeConflict("Ремонт уже обрабатывается или завершён")
        if decision.action == "approve" and not repair["state"].get("passed"):
            raise RecipeConflict(
                "Предложение не прошло проверку. Исправьте рецепт или отклоните его"
            )
        await repo.save_review(
            repair_id,
            {
                "id": uuid4().hex,
                "reviewer": admin.username,
                "decision": decision.model_dump(mode="json"),
            },
        )
        await enqueue_recipe_repair(repo, repair_id)
        updated = await repo.get_repair(repair_id)
    return review_item(updated)


@router.post("/{repair_id}/retry", status_code=202, response_model=RepairReview)
async def retry(
    repair_id: PositiveId, _: AdminDep, repo: RepositoryDep
) -> dict[str, Any]:
    async with repo.connection.transaction():
        repair = await repo.get_repair(repair_id, lock=True)
        if repair["status"] != "running":
            raise RecipeConflict("Повтор доступен только для незавершённого запуска")
        await enqueue_recipe_repair(repo, repair_id)
    return review_item(repair)

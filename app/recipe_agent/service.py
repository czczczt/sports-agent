from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.config import Settings, settings
from app.recipe_agent.contracts import ProtocolSample
from app.recipe_agent.extraction import GoldenCase, Sample
from app.recipe_agent.graph import Proposal, RepairState, build_graph
from app.recipe_agent.provider import ModelProposal, create_model, request_recipe
from app.recipe_agent.repository import RecipeRepository

CHECKPOINT_SETUP_LOCK = 220260621
ScheduleCollection = Callable[[RecipeRepository, int], Awaitable[None]]


@asynccontextmanager
async def repository(config: Settings = settings) -> AsyncIterator[RecipeRepository]:
    connection = await AsyncConnection.connect(
        config.database_url, autocommit=True, row_factory=dict_row, connect_timeout=5
    )
    async with connection:
        yield RecipeRepository(connection, config.recipe_raw_root)


async def run_repair(
    repair_id: int,
    config: Settings = settings,
    model_proposal: Proposal | None = None,
    schedule_collection: ScheduleCollection | None = None,
) -> str:
    async with repository(config) as repo:
        connection = repo.connection
        # The job queue serializes runs. This also protects against a second runner
        # after a worker lease is lost or during manual recovery.
        lock = await repo.one(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS locked",
            (f"recipe-repair:{repair_id}",),
        )
        if not lock or not lock["locked"]:
            return "running"
        repair = await repo.get_repair(repair_id)
        if repair["status"] != "running":
            return repair["status"]

        async def samples() -> list[Sample]:
            return [
                await repo.snapshot(
                    repair["source_id"], ProtocolSample.model_validate(sample)
                )
                for sample in repair["samples"]
            ]

        async def golden() -> list[GoldenCase]:
            return await repo.golden_cases(repair["source_id"])

        async def request_model(
            html: list[str],
            previous: dict[str, Any] | None,
            errors: list[str],
        ) -> ModelProposal:
            return await request_recipe(create_model(config), html, previous, errors)

        # The checkpointer owns its versioned schema and runs some DDL outside a transaction.
        async with AsyncPostgresSaver.from_conn_string(config.database_url) as saver:
            await connection.execute(
                "SELECT pg_advisory_lock(%s)", (CHECKPOINT_SETUP_LOCK,)
            )
            try:
                await saver.setup()
            finally:
                await connection.execute(
                    "SELECT pg_advisory_unlock(%s)", (CHECKPOINT_SETUP_LOCK,)
                )
            graph = build_graph(
                samples,
                golden,
                model_proposal or request_model,
                config.auto_apply_safe_repairs,
                saver,
            )
            graph_config = {
                "configurable": {"thread_id": f"recipe-repair:{repair_id}"},
                "recursion_limit": 30,
            }
            snapshot = await graph.aget_state(graph_config)
            review = repair["review"]
            if not snapshot.values:
                active = await repo.active(repair["source_id"])
                initial_state: RepairState = {
                    "base_version_id": active["id"] if active else None,
                    "candidate": active["body"] if active else None,
                }
                await graph.ainvoke(initial_state, graph_config)
            elif snapshot.interrupts:
                if review and review["id"] != snapshot.values.get("review_id"):
                    await graph.ainvoke(Command(resume=review), graph_config)
            elif snapshot.next:
                await graph.ainvoke(None, graph_config)
            snapshot = await graph.aget_state(graph_config)
            state = dict(snapshot.values)
            status = "waiting" if snapshot.interrupts else state["outcome"]
            async with connection.transaction():
                status = await repo.finish(repair, state, status)
                if schedule_collection and status in ("activated", "unchanged"):
                    await schedule_collection(repo, repair["source_id"])
            return status

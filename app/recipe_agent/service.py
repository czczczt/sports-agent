import logging
from asyncio import to_thread
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.config import Settings, settings
from app.recipe_agent.contracts import ProtocolSample, RecipeProposal
from app.recipe_agent.extraction import GoldenCase, Sample, compact_html, table_structure
from app.recipe_agent.graph import Proposal, RepairState, build_graph, check_samples
from app.recipe_agent.provider import ModelProposal, create_model, request_recipe
from app.recipe_agent.repository import RecipeRepository, SnapshotUnavailable

CHECKPOINT_SETUP_LOCK = 220260621
ScheduleCollection = Callable[[RecipeRepository, int], Awaitable[None]]
logger = logging.getLogger(__name__)


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
        active = await repo.active(repair["source_id"])

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
            inputs: list[Sample],
            previous: dict[str, Any] | None,
            errors: list[str],
            token_budget: int,
        ) -> ModelProposal:
            html = await to_thread(lambda: [compact_html(sample.html) for sample in inputs])
            previous_sample = None
            if active:
                current_ids = {sample.raw_id for sample in inputs}
                for body in active["samples"]:
                    reference = ProtocolSample.model_validate(body)
                    if reference.raw_id in current_ids:
                        continue
                    try:
                        previous_sample = await repo.snapshot(repair["source_id"], reference)
                    except SnapshotUnavailable:
                        logger.info("Previous recipe sample %s unavailable for the trial", reference.raw_id)
                        continue
                    break

            async def test_recipe(candidate: RecipeProposal) -> list[str]:
                errors = await to_thread(check_samples, candidate, inputs)
                if previous_sample is not None:
                    previous_errors = await to_thread(check_samples, candidate, [previous_sample])
                    errors.extend(f"Прежняя вёрстка: {error}" for error in previous_errors)
                return errors

            return await request_recipe(
                create_model(config), html, previous, errors,
                test_recipe=test_recipe if previous is not None else None,
                token_budget=token_budget,
                base_selector=active["body"]["baseSelector"] if active else None,
                previous_layout=await to_thread(table_structure, previous_sample.html) if previous_sample else None,
            )

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
            graph_input: RepairState | Command | None
            resume_graph = True
            if not snapshot.values:
                graph_input = {
                    "base_version_id": active["id"] if active else None,
                    "base_selector": active["body"]["baseSelector"] if active else None,
                    "candidate": active["body"] if active else None,
                }
            elif snapshot.interrupts and review and review["id"] != snapshot.values.get("review_id"):
                graph_input = Command(resume=review)
            else:
                graph_input = None
                resume_graph = bool(snapshot.next and not snapshot.interrupts)
            if resume_graph:
                async for progress in graph.astream(graph_input, graph_config, stream_mode="values"):
                    if "__interrupt__" not in progress:
                        await repo.save_progress(repair_id, progress)
            snapshot = await graph.aget_state(graph_config)
            state = dict(snapshot.values)
            status = "waiting" if snapshot.interrupts else state["outcome"]
            async with connection.transaction():
                status = await repo.finish(repair, state, status)
                if schedule_collection and status in ("activated", "unchanged"):
                    await schedule_collection(repo, repair["source_id"])
            return status

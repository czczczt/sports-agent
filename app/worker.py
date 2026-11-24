"""Procrastinate background worker application per SPEC v1.3 §4.1, §4.2.

Orchestrates asynchronous tasks in PostgreSQL without Redis:
- Parsing / scraping source data
- Atomic rating recalculation
- Data cleanup and maintenance
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import procrastinate
from procrastinate.exceptions import AlreadyEnqueued
from procrastinate.jobs import Status
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import DATABASE_URL, normalize_postgres_url
from app.core.database import async_postgres_url
from app.recipe_agent.collection import collect_source
from app.recipe_agent.repository import RecipeRepository
from app.recipe_agent.service import run_repair
from app.services.privacy_service import purge_expired_bulk_drafts, purge_expired_raw_records
from app.services.rating_service import recalculate_rating_sync

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("worker")

connector = procrastinate.PsycopgConnector(conninfo=normalize_postgres_url(DATABASE_URL))
procrastinate_app = procrastinate.App(connector=connector)


@procrastinate_app.task(
    name="app.worker.rebuild_rating_task",
    queue="rebuild",
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=60),
)
async def rebuild_rating_task(as_of_iso: str | None = None) -> dict[str, Any]:
    """Background task to recalculate ratings for running and multi-sport."""
    logger.info("Starting rating recalculation background task (as_of=%s)...", as_of_iso)
    from datetime import date
    as_of = date.fromisoformat(as_of_iso) if as_of_iso else None
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: recalculate_rating_sync(as_of=as_of))
    logger.info("Rating recalculation completed: %s", result)
    return result


@procrastinate_app.task(
    name="app.worker.collect_source_task",
    queue="collect",
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=60),
)
async def collect_source_task(source_id: int) -> dict[str, Any]:
    return await collect_source(source_id, enqueue_recipe_repair)


@procrastinate_app.task(
    name="app.worker.recipe_repair_task",
    queue="agent",
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=30),
)
async def recipe_repair_task(repair_id: int) -> str:
    return await run_repair(repair_id, schedule_collection=enqueue_recipe_collection)


@procrastinate_app.task(
    name="app.worker.pilot_collect_task", queue="collect", pass_context=True,
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=60),
)
async def pilot_collect_task(context: procrastinate.JobContext, run_id: int) -> dict[str, Any]:
    from app.pipeline.pilot import collect_event
    return await collect_event(run_id, final_attempt=context.job.attempts >= 3)


@procrastinate_app.task(
    name="app.worker.bulk_discover_task", queue="bulk-collect", pass_context=True,
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=60),
)
async def bulk_discover_task(context: procrastinate.JobContext, batch_id: int, source_id: int) -> None:
    from app.modules.bulk_collection.collection import collect_catalog
    await collect_catalog(batch_id, source_id, final_attempt=context.job.attempts >= 3)


@procrastinate_app.task(
    name="app.worker.bulk_event_task", queue="bulk-collect", pass_context=True,
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=60),
)
async def bulk_event_task(context: procrastinate.JobContext, draft_id: int) -> None:
    from app.modules.bulk_collection.collection import collect_draft
    await collect_draft(draft_id, final_attempt=context.job.attempts >= 3)


async def enqueue_recipe_repair(repo: RecipeRepository, repair_id: int) -> None:
    lock = f"recipe-repair:{repair_id}"
    try:
        async with repo.connection.transaction():
            await recipe_repair_task.configure(
                connection=repo.connection, lock=lock, queueing_lock=lock,
            ).defer_async(repair_id=repair_id)
    except AlreadyEnqueued:
        return


async def enqueue_recipe_collection(repo: RecipeRepository, source_id: int) -> None:
    lock = f"recipe-collect:{source_id}"
    try:
        async with repo.connection.transaction():
            await collect_source_task.configure(
                connection=repo.connection, lock=lock, queueing_lock=lock,
            ).defer_async(source_id=source_id)
    except AlreadyEnqueued:
        return


@procrastinate_app.periodic(cron="* * * * *")
@procrastinate_app.task(name="app.worker.recover_recipe_jobs", queue="maintenance")
async def recover_recipe_jobs(timestamp: int) -> None:
    manager = procrastinate_app.job_manager
    for task in (recipe_repair_task, collect_source_task, pilot_collect_task, bulk_discover_task, bulk_event_task):
        stalled_jobs = await manager.get_stalled_jobs(task_name=task.name, seconds_since_heartbeat=60)
        for job in stalled_jobs:
            try:
                await manager.retry_job(job)
            except AlreadyEnqueued:
                await manager.finish_job(job, status=Status.FAILED, delete_job=False)


@procrastinate_app.periodic(cron="0 3 * * *")  # Every night at 03:00 UTC
@procrastinate_app.task(name="app.worker.daily_cleanup_raw_task", queue="maintenance")
async def daily_cleanup_raw_task() -> dict[str, Any]:
    """Purge raw snapshots and staged participant data older than RAW_TTL_DAYS."""
    engine = create_async_engine(async_postgres_url(DATABASE_URL))
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                purged = await purge_expired_raw_records(session)
            async with session.begin():
                purged_drafts = await purge_expired_bulk_drafts(session)
        logger.info("Daily cleanup finished. Purged %d raw records and %d draft payloads.", purged, purged_drafts)
        return {"purged": purged, "purged_drafts": purged_drafts}
    finally:
        await engine.dispose()


async def run_worker() -> None:
    async with procrastinate_app.open_async():
        regular = asyncio.create_task(procrastinate_app.run_worker_async(
            queues=["default", "collect", "rebuild", "maintenance", "agent"],
        ))
        bulk = asyncio.create_task(procrastinate_app.run_worker_async(
            queues=["bulk-collect"], concurrency=3, install_signal_handlers=False,
        ))
        try:
            done, _ = await asyncio.wait((regular, bulk), return_when=asyncio.FIRST_COMPLETED)
            for worker in done:
                worker.result()
        finally:
            for worker in (regular, bulk):
                if not worker.done():
                    worker.cancel()
            await asyncio.gather(regular, bulk, return_exceptions=True)


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(run_worker())

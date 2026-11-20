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
from app.services.privacy_service import purge_expired_raw_records
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
    for task in (recipe_repair_task, collect_source_task):
        stalled_jobs = await manager.get_stalled_jobs(task_name=task.name, seconds_since_heartbeat=60)
        for job in stalled_jobs:
            try:
                await manager.retry_job(job)
            except AlreadyEnqueued:
                await manager.finish_job(job, status=Status.FAILED, delete_job=False)


@procrastinate_app.periodic(cron="0 3 * * *")  # Every night at 03:00 UTC
@procrastinate_app.task(name="app.worker.daily_cleanup_raw_task", queue="maintenance")
async def daily_cleanup_raw_task() -> dict[str, Any]:
    """Daily maintenance task to clean up raw payloads older than RAW_TTL_DAYS (SPEC §12)."""
    engine = create_async_engine(async_postgres_url(DATABASE_URL))
    try:
        async with AsyncSession(engine) as session, session.begin():
            purged = await purge_expired_raw_records(session)
        logger.info("Daily cleanup finished. Purged %d records.", purged)
        return {"purged": purged}
    finally:
        await engine.dispose()


async def run_worker() -> None:
    async with procrastinate_app.open_async():
        await procrastinate_app.run_worker_async(
            queues=["default", "collect", "rebuild", "maintenance", "agent"]
        )


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(run_worker())

"""Procrastinate background worker application per SPEC v1.3 §4.1, §4.2.

Orchestrates asynchronous tasks in PostgreSQL without Redis:
- Parsing / scraping source data
- Atomic rating recalculation
- Data cleanup and maintenance
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

import procrastinate
from app.config import DATABASE_URL, normalize_postgres_url
from app.services.rating_service import recalculate_rating_sync
from app.services.privacy_service import purge_expired_raw_records
from app.db import get_db_connection

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("worker")

# 1. Procrastinate App configuration with PsycopgConnector
connector = procrastinate.PsycopgConnector(conninfo=normalize_postgres_url(DATABASE_URL))
procrastinate_app = procrastinate.App(connector=connector)


# 2. Asynchronous Tasks
@procrastinate_app.task(queue="rebuild", retry=procrastinate.RetryStrategy(max_attempts=3, wait=60))
async def rebuild_rating_task(as_of_iso: str | None = None) -> dict[str, Any]:
    """Background task to recalculate ratings for running and multi-sport."""
    logger.info("Starting rating recalculation background task (as_of=%s)...", as_of_iso)
    from datetime import date
    as_of = date.fromisoformat(as_of_iso) if as_of_iso else None
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: recalculate_rating_sync(as_of=as_of))
    logger.info("Rating recalculation completed: %s", result)
    return result


@procrastinate_app.task(queue="collect", retry=procrastinate.RetryStrategy(max_attempts=3, wait=60))
async def collect_source_task(source_id: int) -> dict[str, Any]:
    """Background task to collect results from a specific source."""
    logger.info("Executing collect task for source_id=%s...", source_id)
    # Stub executing parser job for source
    return {"source_id": source_id, "status": "collected"}


@procrastinate_app.periodic(cron="0 3 * * *")  # Every night at 03:00 UTC
@procrastinate_app.task(queue="maintenance")
async def daily_cleanup_raw_task() -> dict[str, Any]:
    """Daily maintenance task to clean up raw payloads older than RAW_TTL_DAYS (SPEC §12)."""
    logger.info("Running daily raw payload retention purge...")
    conn = get_db_connection()
    try:
        purged = purge_expired_raw_records(conn)
        conn.commit()
        logger.info("Daily cleanup finished. Purged %d records.", purged)
        return {"purged": purged}
    finally:
        conn.close()


def run_worker() -> None:
    """Entry point to launch worker process."""
    logger.info("Starting Procrastinate worker listening to queues: default, collect, rebuild, maintenance...")
    procrastinate_app.open()
    try:
        worker = procrastinate_app.worker(queues=["default", "collect", "rebuild", "maintenance"])
        asyncio.run(worker.run())
    finally:
        procrastinate_app.close()


if __name__ == "__main__":
    run_worker()

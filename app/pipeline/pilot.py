"""One-event pilot: fetch outside transactions, save and publish atomically."""
import asyncio
import logging

import psycopg

from app.config import DATABASE_URL, normalize_postgres_url
from app.modules.runs.repository import RunRepository, complete
from app.modules.runs.service import connection
from app.pipeline.errors import PilotRejected

logger = logging.getLogger(__name__)


def _save_and_publish(run_id: int, event) -> tuple[int, int]:
    from app.pipeline.rating_publication import publish_rating
    from app.pipeline.russia_running import save_event

    with psycopg.connect(normalize_postgres_url(DATABASE_URL)) as conn:
        count = save_event(conn, event)
        version_id = publish_rating(conn, run_id)
        complete(conn, run_id, count, version_id)
        return count, version_id


async def collect_event(run_id: int, *, final_attempt: bool = True) -> dict:
    from app.pipeline.russia_running import fetch_event

    async with connection() as conn:
        # Session lock survives phase commits and excludes overlapping lease recovery.
        repo = RunRepository(conn)
        if not await repo.claim(run_id):
            raise RuntimeError('Pilot run is still owned by another worker')
        run = await repo.get(run_id)
        if run is None:
            raise ValueError(f'Unknown pilot run: {run_id}')
        if run['status'] in ('succeeded', 'failed'):
            return {'run_id': run_id, 'status': run['status']}
        phase = 'fetching'
        try:
            await repo.phase(run_id, 'fetching')
            event = await asyncio.to_thread(fetch_event, run['event_code'])
            await repo.phase(run_id, 'publishing')
            phase = 'publishing'
            write = asyncio.create_task(asyncio.to_thread(_save_and_publish, run_id, event))
            try:
                count, version_id = await asyncio.shield(write)
            except asyncio.CancelledError:
                # Keep ownership until the database thread has committed or rolled back.
                await write
                raise
            return {'run_id': run_id, 'status': 'succeeded', 'processed_distances': count, 'rating_version_id': version_id}
        except Exception as exc:
            logger.error('Pilot run %s failed during %s (%s)', run_id, phase, type(exc).__name__)
            error = str(exc) if isinstance(exc, PilotRejected) else f"{phase} failed ({type(exc).__name__})"
            await repo.failure(run_id, error, final_attempt)
            raise

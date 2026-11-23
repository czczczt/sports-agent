"""One-event pilot: fetch outside transactions, save and publish atomically."""
import asyncio
import logging

import psycopg
from requests import HTTPError

from app.config import DATABASE_URL, normalize_postgres_url
from app.modules.runs.repository import RunRepository, complete
from app.modules.runs.service import connection
from app.pipeline.errors import PilotRejected

logger = logging.getLogger(__name__)


def _save_and_publish(run_id: int, source_id: int, event: dict) -> tuple[int, int | None]:
    from app.pipeline.collection_repository import save_event
    from app.pipeline.rating_publication import publish_rating

    with psycopg.connect(normalize_postgres_url(DATABASE_URL)) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('collection:publication', 0))")
        count = save_event(conn, source_id, event)
        includes_running = any(
            item['race']['sport'] == 'run' and item['race']['race_type'] == 'individual'
            and any(
                row['status'] == 'FIN' and row.get('gender') in {'M', 'F'}
                and (item['race']['place_by'] != 'official'
                     or row.get('chip_time_s') is not None or row.get('gun_time_s') is not None)
                for row in item['rows']
            )
            for item in event['races']
        )
        version_id = publish_rating(conn, run_id) if includes_running else None
        complete(conn, run_id, count, version_id)
        return count, version_id


async def collect_event(run_id: int, *, final_attempt: bool = True) -> dict:
    from app.pipeline.sources import fetch_event
    from app.pipeline.validation import validate_event

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
            event = await asyncio.to_thread(fetch_event, run['source'], run['event_code'])
            validate_event(event)
            await repo.phase(run_id, 'publishing')
            phase = 'publishing'
            write = asyncio.create_task(asyncio.to_thread(_save_and_publish, run_id, run['source_id'], event))
            try:
                count, version_id = await asyncio.shield(write)
            except asyncio.CancelledError:
                # Keep ownership until the database thread has committed or rolled back.
                await write
                raise
            return {'run_id': run_id, 'status': 'succeeded', 'processed_distances': count, 'rating_version_id': version_id}
        except Exception as exc:
            logger.error('Pilot run %s failed during %s (%s)', run_id, phase, type(exc).__name__)
            if isinstance(exc, PilotRejected):
                error = str(exc)
            elif isinstance(exc, HTTPError) and exc.response is not None:
                error = f"Source returned HTTP {exc.response.status_code}"
            else:
                error = f"{phase} failed ({type(exc).__name__})"
            await repo.failure(run_id, error, final_attempt)
            raise

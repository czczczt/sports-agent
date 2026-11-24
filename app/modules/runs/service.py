from __future__ import annotations

from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.config import DATABASE_URL, normalize_postgres_url
from app.modules.runs.repository import RunRepository
from app.pipeline.sources import SOURCE_CONFIG, SourceCode


class SourceDisabled(Exception):
    pass


class RunConflict(Exception):
    def __init__(self, run_id: int):
        self.run_id = run_id


@asynccontextmanager
async def connection():
    conn = await AsyncConnection.connect(
        normalize_postgres_url(DATABASE_URL), autocommit=True, row_factory=dict_row,
    )
    async with conn:
        yield conn


async def start_run(source_code: SourceCode, event_code: str) -> dict:
    from app.worker import pilot_collect_task

    async with connection() as conn, conn.transaction():
        repo = RunRepository(conn)
        source = await repo.prepare_source(source_code, *SOURCE_CONFIG[source_code])
        if not source['enabled']:
            raise SourceDisabled(f"{source_code} source is disabled")
        active = await repo.active(source['id'])
        if active:
            raise RunConflict(active['id'])
        run_id = await repo.create(source['id'], event_code)
        await pilot_collect_task.configure(
            connection=conn, lock=f"collection-source:{source['id']}", queueing_lock=f"pilot:{run_id}",
        ).defer_async(run_id=run_id)
        return {'run_id': run_id, 'status': 'queued'}


async def read_run(run_id: int) -> dict | None:
    async with connection() as conn:
        row = await RunRepository(conn).get(run_id)
        if row:
            row['run_id'] = row['id']
            row['kind'] = 'collect'
            row['progress'] = {'phase': row['phase'], 'processed_distances': row['processed_distances']}
        return row

"""Database operations for the admin preview and publication requests."""

import psycopg

from app.config import DATABASE_URL, normalize_postgres_url
from app.modules.bulk_collection.approval import BulkPublicationFailed, approve_job, preview_job


class BulkBatchNotFound(Exception):
    """The requested batch does not exist."""


def read_batch(batch_id: int) -> dict:
    with psycopg.connect(normalize_postgres_url(DATABASE_URL)) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        batch = conn.execute("SELECT created_at FROM bulk_batch WHERE id = %s", (batch_id,)).fetchone()
        if batch is None:
            raise BulkBatchNotFound
        sources = conn.execute(
            """SELECT s.name, b.status, b.error FROM bulk_source b
               JOIN source s ON s.id = b.source_id WHERE b.batch_id = %s ORDER BY s.name""",
            (batch_id,),
        ).fetchall()
        return {
            "id": batch_id,
            "created_at": batch[0],
            "sources": [{"code": code, "status": status, "error": error} for code, status, error in sources],
            **preview_job(conn, batch_id),
        }


def publish_batch(
    batch_id: int, draft_ids: list[int], resolutions: list[dict[str, str]], preview_revision: str, user_id: int | None,
) -> dict:
    with psycopg.connect(normalize_postgres_url(DATABASE_URL)) as conn:
        if conn.execute("SELECT 1 FROM bulk_batch WHERE id = %s", (batch_id,)).fetchone() is None:
            raise BulkBatchNotFound
        try:
            return approve_job(conn, batch_id, draft_ids, resolutions, preview_revision, user_id=user_id)
        except BulkPublicationFailed:
            # The publication rolled back to its savepoint. Preserve the operator-facing error.
            conn.commit()
            raise

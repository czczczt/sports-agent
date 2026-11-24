"""Draft participant data expires independently of collection history."""

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import async_postgres_url
from app.services.privacy_service import purge_expired_bulk_drafts


@pytest.mark.asyncio
async def test_draft_retention_preserves_history(migrated_url):
    with psycopg.connect(migrated_url) as conn:
        source = conn.execute(
            """INSERT INTO source (name, base_url, platform)
               VALUES ('retention-test', 'https://example.com', 'test') RETURNING id""",
        ).fetchone()[0]
        for code, status, age in (("old", "ready", 91), ("approved", "approved", 91), ("recent", "ready", 89)):
            batch = conn.execute(
                "INSERT INTO bulk_batch (created_at) VALUES (NOW() - make_interval(days => %s)) RETURNING id",
                (age,),
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO bulk_source (batch_id, source_id, status, is_automatic)
                   VALUES (%s,%s,'completed',false)""",
                (batch, source),
            )
            conn.execute(
                """INSERT INTO bulk_draft (batch_id, source_id, event_code, status, payload, payload_hash, summary)
                   VALUES (%s,%s,%s,%s,'{"rows":[{"name":"Test Person"}]}','hash','{"participants":1}')""",
                (batch, source, code, status),
            )

    engine = create_async_engine(async_postgres_url(migrated_url))
    try:
        async with AsyncSession(engine) as session, session.begin():
            assert await purge_expired_bulk_drafts(session, days=90) == 2
    finally:
        await engine.dispose()

    with psycopg.connect(migrated_url) as conn:
        drafts = conn.execute(
            """SELECT event_code, status, payload IS NULL, payload_hash, summary->>'participants', error
               FROM bulk_draft ORDER BY event_code""",
        ).fetchall()
    assert [row[:5] for row in drafts] == [
        ("approved", "approved", True, "hash", "1"),
        ("old", "failed", True, "hash", "1"),
        ("recent", "ready", False, "hash", "1"),
    ]
    assert "истёк" in drafts[1][5]

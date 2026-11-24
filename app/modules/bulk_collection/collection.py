"""Stage validated protocols and track collection separately from publication."""

import asyncio
import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta, timezone

from psycopg.types.json import Jsonb
from requests import HTTPError

from app.modules.runs.repository import RunRepository
from app.modules.runs.service import connection
from app.pipeline.errors import PilotRejected
from app.pipeline.sources import SOURCE_CONFIG, SourceCode, fetch_event
from app.pipeline.validation import validate_event
from parser_running.rr_platform import RRClient

logger = logging.getLogger(__name__)
EVENT_CODE_PATTERN = r"^[a-zA-Z0-9_-]{1,200}$"
AUTOMATIC_SOURCE = SourceCode.russiarunning
DISCOVERY_WINDOW = timedelta(days=30)
LABELS = {
    "russiarunning": "RussiaRunning", "timerman": "Timerman", "legkovrace": "Гонка Легкова",
    "pionercup": "Pioner Cup", "probeg": "ПроБЕГ", "ironstar": "IRONSTAR", "grom": "Grom",
    "russialoppet": "Russialoppet", "myrunstats": "MyRunStats", "resultszone": "Results.zone",
    "myfinish": "MyFinish", "toplist": "TopList", "tristats": "TriStats",
    "orgeo": "Orgeo", "racetime": "RaceTime",
}


def discover_russia_running(
    since: datetime, until: datetime, previous: dict[str, str] | None,
) -> tuple[list[str], dict[str, str]]:
    """RR exposes catalog data without a protocol modification timestamp."""
    client = RRClient(AUTOMATIC_SOURCE, cache=False)
    catalog = {}
    codes = []
    seen = set()
    total = None
    take = 100
    # Recheck recent finishes for corrections invisible in the RR catalog.
    refresh_from = min(since, until - DISCOVERY_WINDOW)
    try:
        for skip in range(0, 100_000, take):
            page = client.event_catalog_page(skip, take)
            count, items = page.get("totalCount"), page.get("list")
            if (type(count) is not int or not 0 <= count <= 100_000
                    or total is not None and total != count
                    or not isinstance(items, list) or len(items) != min(take, count - skip)):
                raise PilotRejected("Incomplete or inconsistent RussiaRunning catalog")
            total = count
            for item in items:
                event_id, code = item["id"], item["code"]
                if not event_id or event_id in seen:
                    raise PilotRejected("Duplicate or missing RussiaRunning catalog event ID")
                seen.add(event_id)
                if item["disciplineCode"] != "run":
                    continue
                if not re.fullmatch(EVENT_CODE_PATTERN, code) or code in catalog:
                    raise PilotRejected("Duplicate or invalid RussiaRunning catalog event code")
                end = datetime.fromisoformat(item.get("endDate") or item["beginDate"])
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone(timedelta(hours=item.get("timeZoneOffset") or 0)))
                if end > until:
                    continue
                encoded = json.dumps(item, sort_keys=True, ensure_ascii=False).encode()
                catalog[code] = hashlib.sha256(encoded).hexdigest()
                if end >= refresh_from or (
                    previous is not None and previous.get(code) != catalog[code]
                ):
                    codes.append(code)
            if skip + len(items) == total:
                return codes, catalog
        raise PilotRejected("RussiaRunning catalog exceeded pagination limit")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise PilotRejected("Invalid RussiaRunning catalog") from exc
    finally:
        client.s.close()


async def _one(conn, sql, params=()):
    return await (await conn.execute(sql, params)).fetchone()


async def _all(conn, sql, params=()):
    return await (await conn.execute(sql, params)).fetchall()


async def list_sources() -> list[dict]:
    async with connection() as conn:
        rows = await _all(conn, "SELECT name, enabled FROM source WHERE name = ANY(%s)", (list(SOURCE_CONFIG),))
    enabled = {row["name"]: row["enabled"] for row in rows}
    return [
        {"code": code, "label": LABELS[code], "automatic": code == AUTOMATIC_SOURCE,
         "enabled": enabled.get(code, True)}
        for code in SOURCE_CONFIG
    ]


async def list_batches() -> list[dict]:
    async with connection() as conn:
        return await _all(conn, "SELECT id, created_at FROM bulk_batch ORDER BY id DESC LIMIT 100")


async def _insert_drafts(conn, batch_id, source_id, codes):
    await conn.execute(
        """INSERT INTO bulk_draft (batch_id, source_id, event_code, status)
           SELECT %s, %s, event_code, 'queued' FROM unnest(%s::text[]) AS codes(event_code)
           ON CONFLICT (batch_id, source_id, event_code) DO NOTHING""",
        (batch_id, source_id, codes),
    )


async def create_batch(sources: list[SourceCode], starts: dict[SourceCode, list[str]]) -> int:
    from app.worker import bulk_discover_task

    async with connection() as conn, conn.transaction():
        batch = await _one(conn, "INSERT INTO bulk_batch DEFAULT VALUES RETURNING id")
        batch_id = batch["id"]
        repo = RunRepository(conn)
        for code in sorted(set(sources)):
            source = await repo.prepare_source(code, *SOURCE_CONFIG[code])
            source_id = source["id"]
            automatic = code == AUTOMATIC_SOURCE
            codes = starts.get(code, [])
            status = "queued"
            if not source["enabled"]:
                status = "disabled"
            elif not automatic and not codes:
                status = "unsupported"
            await conn.execute(
                """INSERT INTO bulk_source (batch_id, source_id, status, is_automatic)
                   VALUES (%s, %s, %s, %s)""",
                (batch_id, source_id, status, automatic),
            )
            if status != "queued":
                continue
            await _insert_drafts(conn, batch_id, source_id, codes)
            if automatic:
                await bulk_discover_task.configure(
                    connection=conn, lock=f"collection-source:{source_id}",
                    queueing_lock=f"bulk-discover:{batch_id}:{source_id}",
                ).defer_async(batch_id=batch_id, source_id=source_id)
            else:
                await _enqueue_next(conn, batch_id, source_id)
        return batch_id


async def _enqueue_next(conn, batch_id, source_id):
    from app.worker import bulk_event_task

    next_draft = await _one(
        conn,
        """SELECT id FROM bulk_draft WHERE batch_id = %s AND source_id = %s
           AND status = 'queued' ORDER BY id LIMIT 1""",
        (batch_id, source_id),
    )
    if next_draft is not None:
        draft_id = next_draft["id"]
        await bulk_event_task.configure(
            connection=conn, lock=f"collection-source:{source_id}",
            queueing_lock=f"bulk-event:{draft_id}",
        ).defer_async(draft_id=draft_id)
        return

    failure = await _one(
        conn,
        """SELECT event_code, error FROM bulk_draft WHERE batch_id = %s AND source_id = %s
           AND status = 'failed' ORDER BY id LIMIT 1""",
        (batch_id, source_id),
    )
    error = f"{failure['event_code']}: {failure['error']}" if failure else None
    source = await _one(
        conn,
        """UPDATE bulk_source SET error = COALESCE(error, %s),
               status = CASE WHEN COALESCE(error, %s) IS NULL THEN 'completed' ELSE 'failed' END
           WHERE batch_id = %s AND source_id = %s RETURNING status, scan_until, catalog""",
        (error, error, batch_id, source_id),
    )
    if source["status"] == "completed" and source["scan_until"] is not None:
        await conn.execute(
            """INSERT INTO bulk_watermark (source_id, scanned_until, catalog) VALUES (%s, %s, %s)
               ON CONFLICT (source_id) DO UPDATE
               SET scanned_until = EXCLUDED.scanned_until, catalog = EXCLUDED.catalog
               WHERE bulk_watermark.scanned_until < EXCLUDED.scanned_until""",
            (source_id, source["scan_until"], Jsonb(source["catalog"])),
        )
    if source["catalog"] is not None:
        await conn.execute(
            "UPDATE bulk_source SET catalog = NULL WHERE batch_id = %s AND source_id = %s",
            (batch_id, source_id),
        )


def _error(exc: Exception) -> str:
    if isinstance(exc, PilotRejected):
        return str(exc)
    if isinstance(exc, HTTPError) and exc.response is not None:
        return f"Source returned HTTP {exc.response.status_code}"
    return f"Source collection failed ({type(exc).__name__})"


async def _fetch_in_thread(function, *args):
    fetch = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(fetch)
    except asyncio.CancelledError:
        # Keep source ownership until the network thread exits.
        await fetch
        raise


async def collect_catalog(batch_id: int, source_id: int, *, final_attempt: bool) -> None:
    async with connection() as conn:
        await RunRepository(conn).claim_collection_source(source_id)
        source = await _one(
            conn,
            """SELECT status, scan_until, error FROM bulk_source
               WHERE batch_id = %s AND source_id = %s""",
            (batch_id, source_id),
        )
        if not source or source["status"] not in {"queued", "running"} or source["scan_until"] or source["error"]:
            return
        await conn.execute(
            "UPDATE bulk_source SET status = 'running' WHERE batch_id = %s AND source_id = %s", (batch_id, source_id),
        )
        until = datetime.now(UTC)
        saved = await _one(conn, "SELECT scanned_until, catalog FROM bulk_watermark WHERE source_id = %s", (source_id,))
        since = saved["scanned_until"] if saved else until - DISCOVERY_WINDOW
        try:
            codes, catalog = await _fetch_in_thread(
                discover_russia_running, since, until, saved["catalog"] if saved else None,
            )
            async with conn.transaction():
                await _insert_drafts(conn, batch_id, source_id, codes)
                await conn.execute(
                    "UPDATE bulk_source SET scan_until = %s, catalog = %s WHERE batch_id = %s AND source_id = %s",
                    (until, Jsonb(catalog), batch_id, source_id),
                )
                await _enqueue_next(conn, batch_id, source_id)
        except Exception as exc:
            if not final_attempt and not isinstance(exc, PilotRejected):
                raise
            logger.warning("Bulk discovery failed for batch %s source %s (%s)", batch_id, source_id, type(exc).__name__)
            async with conn.transaction():
                await conn.execute(
                    "UPDATE bulk_source SET error = %s, status = 'failed' WHERE batch_id = %s AND source_id = %s",
                    (_error(exc), batch_id, source_id),
                )
            return


def _fetch_validated_event(source, event_code):
    event = fetch_event(source, event_code)
    validate_event(event)
    event["races"].sort(key=lambda item: str(item["race"]["external_id"]))
    for item in event["races"]:
        item["rows"].sort(key=lambda row: str(row["external_participant_id"]))
    try:
        encoded = json.dumps(event, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise PilotRejected("Source protocol contains unsupported values") from exc
    return event, hashlib.sha256(encoded).hexdigest()


async def _store_draft(conn, draft, event, digest):
    previous = await _one(
        conn,
        """SELECT payload_hash = %s AS same FROM bulk_draft
           WHERE source_id = %s AND event_code = %s AND batch_id <> %s
             AND status IN ('ready','approved') ORDER BY id DESC LIMIT 1""",
        (digest, draft["source_id"], draft["event_code"], draft["batch_id"]),
    )
    status = "unchanged" if previous and previous["same"] else "ready"
    competition = event["competition"]
    summary = {
        "title": competition["title"],
        "date": competition["date_begin"][:10],
        "city": competition.get("place"),
        "participants": sum(len(item["rows"]) for item in event["races"]),
    }
    await conn.execute(
        """UPDATE bulk_draft SET status = %s, payload = %s, payload_hash = %s, summary = %s,
               error = NULL WHERE id = %s""",
        (status, Jsonb(event) if status == "ready" else None, digest, Jsonb(summary), draft["id"]),
    )


async def collect_draft(draft_id: int, *, final_attempt: bool) -> None:
    async with connection() as conn:
        source = await _one(conn, "SELECT source_id FROM bulk_draft WHERE id = %s", (draft_id,))
        if not source:
            return
        await RunRepository(conn).claim_collection_source(source["source_id"])
        draft = await _one(
            conn,
            """SELECT d.*, s.name AS source FROM bulk_draft d JOIN source s ON s.id = d.source_id
               WHERE d.id = %s""",
            (draft_id,),
        )
        if not draft or draft["status"] not in {"queued", "running"}:
            return
        batch_id, source_id = draft["batch_id"], draft["source_id"]
        async with conn.transaction():
            await conn.execute(
                "UPDATE bulk_source SET status = 'running' WHERE batch_id = %s AND source_id = %s",
                (batch_id, source_id),
            )
            await conn.execute("UPDATE bulk_draft SET status = 'running', error = NULL WHERE id = %s", (draft_id,))
        try:
            event, digest = await _fetch_in_thread(_fetch_validated_event, draft["source"], draft["event_code"])
            async with conn.transaction():
                await _store_draft(conn, draft, event, digest)
                await _enqueue_next(conn, batch_id, source_id)
        except Exception as exc:
            terminal = final_attempt or isinstance(exc, PilotRejected)
            async with conn.transaction():
                await conn.execute(
                    "UPDATE bulk_draft SET status = %s, error = %s WHERE id = %s",
                    ("failed" if terminal else "running", _error(exc), draft_id),
                )
                if terminal:
                    await _enqueue_next(conn, batch_id, source_id)
            if not terminal:
                raise
            logger.warning("Bulk draft %s failed (%s)", draft_id, type(exc).__name__)
            return

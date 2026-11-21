import hashlib
from asyncio import to_thread
from collections.abc import Awaitable, Callable
from typing import Any

import psycopg

from app.config import Settings, settings
from app.recipe_agent.contracts import (
    ProtocolSample,
    RecipeProposal,
    ResultRow,
    StartRepair,
)
from app.recipe_agent.extraction import InvalidProtocol, extract, validate_protocol
from app.recipe_agent.repository import RecipeRepository, SnapshotUnavailable
from app.recipe_agent.service import repository
from parser_running.store import save_results

Enqueue = Callable[[RecipeRepository, int], Awaitable[None]]


async def collect_source(
    source_id: int,
    enqueue: Enqueue,
    config: Settings = settings,
) -> dict[str, Any]:
    async with repository(config) as repo:
        if await repo.open_repair(source_id):
            return {"source_id": source_id, "status": "repair_pending", "protocols": 0}
        active = await repo.active(source_id)
        status, count = "no_recipe", 0
        if active is not None:
            status, count = await _collect_with_recipe(
                repo, config, source_id, active, enqueue
            )
        return {"source_id": source_id, "status": status, "protocols": count}


async def _collect_with_recipe(
    repo: RecipeRepository,
    config: Settings,
    source_id: int,
    active: dict[str, Any],
    enqueue: Enqueue,
) -> tuple[str, int]:
    recipe = RecipeProposal.model_validate(active["body"])
    snapshots = await (
        await repo.connection.execute(
            """
        SELECT DISTINCT ON (s.race_id)
            s.id AS raw_id, s.race_id, race.place_by, race.total_count AS total
        FROM raw s
        JOIN race ON race.id = s.race_id
        JOIN competition c ON c.id = race.competition_id AND c.source_id = s.source_id
        WHERE s.source_id = %s AND s.purged_at IS NULL
          AND s.storage_path LIKE '%%.html'
          AND race.place_by IN ('chip', 'gun') AND race.total_count > 0
          AND NOT EXISTS (SELECT 1 FROM result WHERE result.race_id = s.race_id)
        ORDER BY s.race_id, s.fetched_at DESC, s.id DESC
        """,
            (source_id,),
        )
    ).fetchall()
    saved = 0
    for row in snapshots:
        if await repo.open_repair(source_id):
            return "repair_pending", saved
        reference = ProtocolSample(
            raw_id=row["raw_id"], place_by=row["place_by"], total=row["total"]
        )
        try:
            sample = await repo.snapshot(source_id, reference)
        except SnapshotUnavailable:
            return "snapshot_unavailable", saved
        try:
            results = await to_thread(extract, recipe, sample.html)
            validate_protocol(results, sample.place_by, sample.total)
        except InvalidProtocol as exc:
            requested = await _request_repair(
                repo, source_id, reference, active["id"], str(exc), enqueue
            )
            return ("repair_pending" if requested else "manual_review"), saved
        committed = await to_thread(
            _save_new_protocol,
            config.database_url,
            source_id,
            row["race_id"],
            reference.raw_id,
            active["id"],
            results,
        )
        saved += int(committed)
    return "collected", saved


async def _request_repair(
    repo: RecipeRepository,
    source_id: int,
    reference: ProtocolSample,
    version_id: int,
    error: str,
    enqueue: Enqueue,
) -> bool:
    async with repo.connection.transaction():
        await repo.lock_source(source_id)
        if await repo.open_repair(source_id):
            return True
        active = await repo.active(source_id)
        if not active or active["id"] != version_id:
            return False

        fingerprint = hashlib.sha256(
            f"recipe:{source_id}:{reference.raw_id}:{version_id}".encode()
        ).hexdigest()
        issue = await repo.one(
            """
            INSERT INTO issue(source_id, stage, kind, object_ref, fingerprint, details)
            VALUES (%s, 'parse', 'recipe_regression', %s, %s, %s)
            ON CONFLICT (fingerprint) DO UPDATE
                SET occurrences = issue.occurrences + 1, last_seen = now(), details = EXCLUDED.details
            RETURNING id, status
            """,
            (source_id, str(reference.raw_id), fingerprint, error),
        )
        if issue["status"] == "blocked":
            return False
        is_golden_sample = await repo.one(
            "SELECT raw_id FROM golden_case WHERE source_id = %s AND raw_id = %s",
            (source_id, reference.raw_id),
        )
        if is_golden_sample or not await repo.has_golden(source_id):
            await repo.connection.execute(
                "UPDATE issue SET status = 'blocked', assignee = 'human' WHERE id = %s",
                (issue["id"],),
            )
            return False
        task = StartRepair(
            source_id=source_id, samples=[reference], issue_id=issue["id"]
        )
        repair_id = await repo.start(task, "collect-worker")
        await enqueue(repo, repair_id)
        return True


def _save_new_protocol(
    dsn: str,
    source_id: int,
    race_id: int,
    raw_id: int,
    version_id: int,
    rows: list[ResultRow],
) -> bool:
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        connection.execute(
            "SELECT id FROM source WHERE id = %s FOR UPDATE", (source_id,)
        )
        active = connection.execute(
            """
            SELECT id FROM recipe_version
            WHERE source_id = %s AND status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM recipe_repair
                  WHERE source_id = %s AND status IN ('running', 'waiting')
              )
            """,
            (source_id, source_id),
        ).fetchone()
        if active != (version_id,):
            return False
        snapshot = connection.execute(
            "SELECT id FROM raw WHERE id = %s AND race_id = %s AND purged_at IS NULL FOR SHARE",
            (raw_id, race_id),
        ).fetchone()
        if snapshot is None:
            return False
        connection.execute("SELECT id FROM race WHERE id = %s FOR UPDATE", (race_id,))
        if connection.execute(
            "SELECT 1 FROM result WHERE race_id = %s LIMIT 1", (race_id,)
        ).fetchone():
            return False
        save_results(
            connection,
            race_id,
            [row.model_dump() for row in rows],
            raw_id,
            recipe_id=version_id,
        )
        return True

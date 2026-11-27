import hashlib
from asyncio import to_thread
from pathlib import Path
from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.recipe_agent.contracts import (
    GoldenInput,
    ProtocolSample,
    RecipeProposal,
    StartRepair,
)
from app.recipe_agent.extraction import (
    MAX_HTML_BYTES,
    GoldenCase,
    Sample,
    protocol_digest,
    validate_protocol,
)


class RecipeConflict(ValueError):
    """The repair cannot proceed in its current state."""


class RecipeNotFound(ValueError):
    """A required source, repair or raw snapshot does not exist."""


class SnapshotUnavailable(RecipeConflict):
    """The archived HTML has expired, disappeared or changed."""


class RecipeRepository:
    def __init__(self, connection: AsyncConnection, raw_root: Path) -> None:
        self.connection = connection
        self.raw_root = raw_root.resolve()

    async def one(self, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        return await (await self.connection.execute(query, params)).fetchone()

    async def lock_source(self, source_id: int) -> None:
        if not await self.one(
            "SELECT id FROM source WHERE id = %s FOR UPDATE", (source_id,)
        ):
            raise RecipeNotFound("Источник не найден")

    async def open_repair(self, source_id: int) -> dict[str, Any] | None:
        return await self.one(
            """
            SELECT id, samples, issue_id FROM recipe_repair
            WHERE source_id = %s AND status IN ('running', 'waiting')
            """,
            (source_id,),
        )

    async def has_golden(self, source_id: int) -> bool:
        row = await self.one(
            """
            SELECT count(*) AS total, count(*) FILTER (WHERE raw.purged_at IS NULL) AS available
            FROM golden_case
            JOIN raw ON raw.id = golden_case.raw_id
            WHERE golden_case.source_id = %s
            """,
            (source_id,),
        )
        return row is not None and 3 <= row["total"] == row["available"] <= 5

    async def replace_golden(self, source_id: int, cases: list[GoldenInput]) -> None:
        if not 3 <= len(cases) <= 5:
            raise RecipeConflict("Нужны 3–5 эталонных страниц")
        if len({case.raw_id for case in cases}) != len(cases):
            raise RecipeConflict("Эталонные страницы должны быть разными")
        for case in cases:
            validate_protocol(case.expected, case.place_by, case.total)
            await self.snapshot(source_id, case)

        async with self.connection.transaction():
            await self.lock_source(source_id)
            if await self.open_repair(source_id):
                raise RecipeConflict("Сначала завершите текущий ремонт этого источника")
            await self.connection.execute(
                "DELETE FROM golden_case WHERE source_id = %s", (source_id,)
            )
            async with self.connection.cursor() as cursor:
                await cursor.executemany(
                    """
                    INSERT INTO golden_case(source_id, raw_id, place_by, expected_count, expected_digest)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            source_id,
                            case.raw_id,
                            case.place_by,
                            len(case.expected),
                            protocol_digest(case.expected),
                        )
                        for case in cases
                    ],
                )

    async def start(self, task: StartRepair, actor: str) -> int:
        for sample in task.samples:
            await self.snapshot(task.source_id, sample)

        async with self.connection.transaction():
            await self.lock_source(task.source_id)
            existing = await self.open_repair(task.source_id)
            samples = [sample.model_dump() for sample in task.samples]
            if existing:
                if (
                    existing["samples"] == samples
                    and existing["issue_id"] == task.issue_id
                ):
                    return existing["id"]
                raise RecipeConflict(f"У источника уже есть ремонт #{existing['id']}")
            if not await self.has_golden(task.source_id):
                raise RecipeConflict("Зарегистрируйте 3–5 доступных эталонных страниц")
            if task.issue_id is not None:
                issue = await self.one(
                    "SELECT id, status FROM issue WHERE id = %s AND source_id = %s FOR UPDATE",
                    (task.issue_id, task.source_id),
                )
                if issue is None:
                    raise RecipeNotFound("Инцидент этого источника не найден")
                if issue["status"] not in ("new", "blocked", "resolved"):
                    raise RecipeConflict("Инцидент уже обрабатывается")
                await self.connection.execute(
                    "UPDATE issue SET status = 'agent_working', assignee = 'recipe-agent', resolved_at = NULL WHERE id = %s",
                    (task.issue_id,),
                )
            if await self.one(
                "SELECT raw_id FROM golden_case WHERE source_id = %s AND raw_id = ANY(%s)",
                (task.source_id, [sample.raw_id for sample in task.samples]),
            ):
                raise RecipeConflict(
                    "Образцы ремонта должны отличаться от эталонных страниц"
                )
            recipe = await self.one(
                """
                INSERT INTO recipe(source_id) VALUES (%s)
                ON CONFLICT (source_id) DO UPDATE SET source_id = EXCLUDED.source_id
                RETURNING id
                """,
                (task.source_id,),
            )
            row = await self.one(
                """
                INSERT INTO recipe_repair(recipe_id, source_id, issue_id, samples, requested_by)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (recipe["id"], task.source_id, task.issue_id, Jsonb(samples), actor),
            )
            return row["id"]

    async def snapshot(self, source_id: int, reference: ProtocolSample) -> Sample:
        row = await self.one(
            """
            SELECT storage_path, content_hash FROM raw
            WHERE id = %s AND source_id = %s AND purged_at IS NULL
            """,
            (reference.raw_id, source_id),
        )
        if row is None:
            raise SnapshotUnavailable(
                f"Снимок {reference.raw_id} недоступен у этого источника"
            )
        html = await to_thread(
            self._read_html, row["storage_path"], row["content_hash"], reference.raw_id
        )
        return Sample(reference.raw_id, html, reference.place_by, reference.total)

    def _read_html(self, storage_path: str, expected_hash: str, raw_id: int) -> str:
        try:
            path = (self.raw_root / storage_path).resolve()
            if not path.is_relative_to(self.raw_root):
                raise SnapshotUnavailable(
                    f"Снимок {raw_id} расположен вне каталога raw"
                )
            with path.open("rb") as file:
                content = file.read(MAX_HTML_BYTES + 1)
            if (
                len(content) > MAX_HTML_BYTES
                or hashlib.sha256(content).hexdigest() != expected_hash
            ):
                raise SnapshotUnavailable(
                    f"Снимок {raw_id} не совпадает с сохранённым ответом"
                )
            return content.decode("utf-8-sig")
        except (OSError, UnicodeError, RuntimeError) as exc:
            raise SnapshotUnavailable(
                f"Не удалось прочитать HTML снимка {raw_id}"
            ) from exc

    async def golden_cases(self, source_id: int) -> list[GoldenCase]:
        rows = await (
            await self.connection.execute(
                """
            SELECT raw_id, place_by, expected_count, expected_digest FROM golden_case
            WHERE source_id = %s ORDER BY raw_id
            """,
                (source_id,),
            )
        ).fetchall()
        cases = []
        for row in rows:
            sample = await self.snapshot(
                source_id,
                ProtocolSample(
                    raw_id=row["raw_id"],
                    place_by=row["place_by"],
                    total=row["expected_count"],
                ),
            )
            cases.append(GoldenCase(sample, row["expected_digest"]))
        return cases

    async def get_repair(self, repair_id: int, *, lock: bool = False) -> dict[str, Any]:
        query = "SELECT * FROM recipe_repair WHERE id = %s" + (
            " FOR UPDATE" if lock else ""
        )
        repair = await self.one(query, (repair_id,))
        if repair is None:
            raise RecipeNotFound("Ремонт не найден")
        return repair

    async def review_queue(self, repair_id: int | None = None) -> list[dict[str, Any]]:
        return await (
            await self.connection.execute(
                """
            SELECT r.id, r.source_id, r.issue_id, r.status, r.state, s.name AS source_name,
                   v.version AS recipe_version,
                   (SELECT count(*) FROM result WHERE recipe_id = v.id) AS saved_rows,
                   (v.status IS NOT DISTINCT FROM 'active' AND EXISTS (
                       SELECT 1 FROM procrastinate_jobs job
                       WHERE job.lock = 'recipe-collect:' || r.source_id
                         AND job.status IN ('todo', 'doing')
                   )) AS collection_pending
            FROM recipe_repair r JOIN source s ON s.id = r.source_id
            LEFT JOIN recipe_version v ON v.repair_id = r.id
            WHERE (%s::bigint IS NULL OR r.id = %s)
            ORDER BY (r.status IN ('waiting', 'running')) DESC, r.id DESC
            LIMIT 200
            """,
                (repair_id, repair_id),
            )
        ).fetchall()

    async def active(self, source_id: int) -> dict[str, Any] | None:
        return await self.one(
            """
            SELECT v.id, v.body, r.samples
            FROM recipe_version v JOIN recipe_repair r ON r.id = v.repair_id
            WHERE v.source_id = %s AND v.status = 'active'
            """,
            (source_id,),
        )

    async def save_review(self, repair_id: int, review: dict[str, Any]) -> None:
        await self.connection.execute(
            "UPDATE recipe_repair SET review = %s, status = 'running', updated_at = now() WHERE id = %s",
            (Jsonb(review), repair_id),
        )

    async def save_progress(self, repair_id: int, state: dict[str, Any]) -> None:
        await self.connection.execute(
            "UPDATE recipe_repair SET state = %s, updated_at = now() WHERE id = %s AND status = 'running'",
            (Jsonb(state), repair_id),
        )

    async def finish(
        self, repair: dict[str, Any], state: dict[str, Any], status: str
    ) -> str:
        async with self.connection.transaction():
            await self.lock_source(repair["source_id"])
            if status == "activated":
                active = await self.active(repair["source_id"])
                if (active["id"] if active else None) != state.get("base_version_id"):
                    status = "stale"
                else:
                    await self._activate(repair, state)
            if state.get("proposed") and status in ("waiting", "rejected", "stale"):
                await self._save_version(
                    repair, state, "draft" if status == "waiting" else "rejected"
                )
            await self.connection.execute(
                """
                UPDATE recipe_repair SET status = %s, state = %s, review = NULL, updated_at = now()
                WHERE id = %s
                """,
                (status, Jsonb(state), repair["id"]),
            )
            if status in ("activated", "unchanged") and repair["issue_id"] is not None:
                await self.connection.execute(
                    "UPDATE issue SET status = 'resolved', assignee = NULL, resolved_at = now() WHERE id = %s",
                    (repair["issue_id"],),
                )
            if status in ("rejected", "stale") and repair["issue_id"] is not None:
                await self.connection.execute(
                    "UPDATE issue SET status = 'blocked', assignee = 'human' WHERE id = %s",
                    (repair["issue_id"],),
                )
        return status

    async def _activate(self, repair: dict[str, Any], state: dict[str, Any]) -> None:
        await self.connection.execute(
            "UPDATE recipe_version SET status = 'retired' WHERE source_id = %s AND status = 'active'",
            (repair["source_id"],),
        )
        await self._save_version(repair, state, "active")

    async def _save_version(
        self,
        repair: dict[str, Any],
        state: dict[str, Any],
        version_status: str,
    ) -> None:
        body = RecipeProposal.model_validate(state["candidate"]).model_dump(
            exclude_none=True
        )
        await self.connection.execute(
            """
            INSERT INTO recipe_version(recipe_id, source_id, repair_id, version, body, status,
                                       golden_score, tokens_used, activated_at)
            SELECT %s, %s, %s, COALESCE(MAX(version), 0) + 1, %s, %s, %s, %s,
                   CASE WHEN %s = 'active' THEN now() END
            FROM recipe_version WHERE recipe_id = %s
            ON CONFLICT (repair_id) DO UPDATE SET
                body = EXCLUDED.body, status = EXCLUDED.status, golden_score = EXCLUDED.golden_score,
                tokens_used = EXCLUDED.tokens_used,
                activated_at = EXCLUDED.activated_at
            """,
            (
                repair["recipe_id"],
                repair["source_id"],
                repair["id"],
                Jsonb(body),
                version_status,
                state.get("golden_passed", 0),
                state.get("tokens_in", 0) + state.get("tokens_out", 0),
                version_status,
                repair["recipe_id"],
            ),
        )

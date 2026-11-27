"""Queue a synthetic HTML extraction regression on a local demo stack."""

import argparse
import asyncio
import hashlib
import logging
from contextlib import ExitStack
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.config import settings
from app.recipe_agent.contracts import GoldenInput, ProtocolSample, RecipeField, RecipeProposal, ResultRow, StartRepair
from app.recipe_agent.extraction import extract, validate_protocol
from app.recipe_agent.repository import RecipeRepository
from app.recipe_agent.service import repository
from app.worker import enqueue_recipe_collection

logger = logging.getLogger(__name__)

BASE_RECIPE = RecipeProposal.model_validate({
    "baseSelector": "table.protocol-classic tbody tr",
    "fields": [
        {"name": "place_abs", "selector": ".place", "type": "text"},
        {"name": "full_name_raw", "selector": ".name", "type": "text"},
        {"name": "gender", "selector": ".gender", "type": "text"},
        {"name": "gun_time_s", "selector": ".gun", "type": "text"},
    ],
})
TIMING_RECIPE = RecipeProposal(
    baseSelector=BASE_RECIPE.baseSelector,
    fields=[*BASE_RECIPE.fields, RecipeField(name="chip_time_s", selector=".chip", type="text")],
)
Scenario = Literal["layout", "timing"]
RECIPES: dict[Scenario, RecipeProposal] = {"layout": BASE_RECIPE, "timing": TIMING_RECIPE}
SCENARIO_LABELS: dict[Scenario, str] = {"layout": "таблицы", "timing": "времени"}


def protocol(rows: list[ResultRow], changed: bool, scenario: Scenario) -> bytes:
    layout = "protocol-current" if changed and scenario == "layout" else "protocol-classic"
    gun_class = "official-clock" if changed and scenario == "timing" else "gun"
    chip_header = "<th>Chip time</th>" if scenario == "timing" else ""
    body = []
    for row in rows:
        chip_cell = (
            f'<td class="chip" data-clock="chip">{row.chip_time_s:g}</td>'
            if row.chip_time_s is not None else ""
        )
        body.append(
            f'<tr><td class="place">{row.place_abs}</td><td class="name">{row.full_name_raw}</td>'
            f'<td class="gender">{row.gender}</td>{chip_cell}'
            f'<td class="{gun_class}" data-clock="gun">{row.gun_time_s:g}</td></tr>'
        )
    return (
        f'<table class="{layout}" data-purpose="results">'
        f"<thead><tr><th>Place</th><th>Name</th><th>Gender</th>{chip_header}<th>Gun time</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    ).encode()


async def save_snapshot(
    repo: RecipeRepository, folder: Path, cleanup: ExitStack, source_id: int,
    race_id: int | None, number: int, rows: list[ResultRow], scenario: Scenario,
) -> int:
    path = folder / f"{number}.html"
    body = protocol(rows, changed=race_id is not None, scenario=scenario)
    if race_id is None:
        extracted = await asyncio.to_thread(extract, RECIPES[scenario], body.decode())
        validate_protocol(extracted, "gun", len(rows))
        if extracted != rows:
            raise ValueError("Исходный рецепт не совпал с эталоном демо")
    cleanup.callback(path.unlink, missing_ok=True)
    path.write_bytes(body)
    snapshot = await repo.one(
        """
        INSERT INTO raw(source_id, race_id, request_key, content_hash, storage_path, size_bytes)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (source_id, race_id, f"{folder.name}:{number}", hashlib.sha256(body).hexdigest(),
         path.relative_to(repo.raw_root).as_posix(), len(body)),
    )
    assert snapshot is not None
    return snapshot["id"]


async def queue_demo(scenario: Scenario = "layout") -> int:
    run_code = uuid4().hex[:12]
    source_name = f"Демо восстановления {SCENARIO_LABELS[scenario]} {run_code}"
    async with repository() as repo:
        with ExitStack() as cleanup:
            folder = repo.raw_root / f"demo-{run_code}"
            folder.mkdir(parents=True)
            cleanup.callback(folder.rmdir)
            async with repo.connection.transaction():
                source = await repo.one(
                    "INSERT INTO source(name, base_url, platform) VALUES (%s, %s, 'fixture') RETURNING id",
                    (source_name, "https://example.test"),
                )
                assert source is not None
                source_id = source["id"]
                event = await repo.one(
                    "INSERT INTO competition(source_id, external_id, name) VALUES (%s, %s, %s) RETURNING id",
                    (source_id, run_code, "Контрольный забег"),
                )
                assert event is not None
                race = await repo.one(
                    """
                    INSERT INTO race(competition_id, external_id, place_by, total_count)
                    VALUES (%s, '5k', 'gun', 2) RETURNING id
                    """,
                    (event["id"],),
                )
                assert race is not None
                cases: list[GoldenInput] = []
                for number in range(1, 6):
                    rows = [
                        ResultRow(
                            full_name_raw="Тестовый Атлет", gender="M", place_abs=1,
                            gun_time_s=960 + number, chip_time_s=953 + number if scenario == "timing" else None,
                        ),
                        ResultRow(
                            full_name_raw="Тестовая Атлетка", gender="F", place_abs=2,
                            gun_time_s=1060 + number, chip_time_s=1053 + number if scenario == "timing" else None,
                        ),
                    ]
                    raw_id = await save_snapshot(
                        repo, folder, cleanup, source_id, race["id"] if number == 5 else None, number, rows, scenario,
                    )
                    if number <= 3:
                        cases.append(GoldenInput(raw_id=raw_id, place_by="gun", expected=rows))
                    if number == 4:
                        baseline = ProtocolSample(raw_id=raw_id, place_by="gun", total=len(rows))
                await repo.replace_golden(source_id, cases)
                initial_id = await repo.start(StartRepair(source_id=source_id, samples=[baseline]), "demo-setup")
                initial = await repo.get_repair(initial_id)
                await repo.finish(initial, {
                    "candidate": RECIPES[scenario].model_dump(exclude_none=True),
                    "golden_passed": len(cases),
                    "golden_total": len(cases),
                }, "activated")
                await enqueue_recipe_collection(repo, source_id)
            cleanup.pop_all()
    logger.info("В очередь поставлен сбор для источника «%s» (ID %s)", source_name, source_id)
    return source_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo", action="store_true", required=True,
        help="Use the configured database and raw directory of your demo stack.",
    )
    parser.add_argument(
        "--scenario", choices=tuple(RECIPES), default="layout",
        help="Change the table selector (layout) or the official time column (timing).",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if not settings.auto_apply_safe_repairs:
        parser.error("Включите AUTO_APPLY_SAFE_REPAIRS для демонстрации автоматической активации")
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(queue_demo(args.scenario))

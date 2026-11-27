import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import psycopg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.api.auth import get_current_user
from app.config import Settings
from app.models import UserOut
from app.recipe_agent.api import get_repository, router
from app.recipe_agent.collection import collect_source
from app.recipe_agent.contracts import (
    GoldenInput,
    ProtocolSample,
    RecipeProposal,
    StartRepair,
)
from app.recipe_agent.extraction import (
    GoldenCase,
    InvalidProtocol,
    Sample,
    extract,
    protocol_digest,
    table_structure,
)
from app.recipe_agent.graph import build_graph, check_samples
from app.recipe_agent.provider import ModelProposal, propose, request_recipe
from app.recipe_agent.repository import RecipeConflict, RecipeRepository
from app.recipe_agent.service import repository, run_repair
from app.worker import enqueue_recipe_collection, enqueue_recipe_repair


def html(table_id: str, gun_time: str = "16:35") -> str:
    return (
        f'<table id="{table_id}"><tr>'
        '<td class="name">Иван Иванов</td><td class="gender">М</td>'
        '<td class="place">1</td><td class="bib" data-number="007"></td>'
        '<td class="chip">16:30</td>'
        f'<td class="gun">{gun_time}</td></tr></table>'
    )


def recipe(selector: str, gun_selector: str = ".gun") -> RecipeProposal:
    return RecipeProposal.model_validate(
        {
            "baseSelector": selector,
            "fields": [
                {"name": "full_name_raw", "selector": ".name", "type": "text"},
                {"name": "gender", "selector": ".gender", "type": "text"},
                {"name": "place_abs", "selector": ".place", "type": "text"},
                {
                    "name": "bib",
                    "selector": ".bib",
                    "type": "attribute",
                    "attribute": "data-number",
                },
                {"name": "chip_time_s", "selector": ".chip", "type": "text"},
                {"name": "gun_time_s", "selector": gun_selector, "type": "text"},
            ],
        }
    )


@pytest.fixture(autouse=True)
def crawler_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CRAWL4_AI_BASE_DIRECTORY", str(tmp_path))


def test_css_extracts_correct_timing_and_bib() -> None:
    rows = extract(recipe("#old tr"), html("old"))
    assert (rows[0].gender, rows[0].bib, rows[0].chip_time_s, rows[0].gun_time_s) == (
        "M",
        "007",
        990,
        995,
    )
    with pytest.raises(InvalidProtocol, match="gun_time_s"):
        extract(recipe("#old tr"), html("old", "16:75"))

    outline = table_structure(html("old"))
    assert 'class="gun"' in outline
    assert "16:35" not in outline and "Иван Иванов" not in outline and "007" not in outline


@pytest.mark.asyncio
async def test_model_reports_missing_place_field(
    caplog: pytest.LogCaptureFixture,
) -> None:
    proposal = recipe("tr")
    proposal.fields = [field for field in proposal.fields if field.name != "place_abs"]
    model = AsyncMock(spec=BaseChatModel)
    model.ainvoke.return_value = AIMessage(
        content=proposal.model_dump_json(exclude_none=True)
    )
    with caplog.at_level(logging.WARNING):
        result, _, _ = await propose(model, [html("old")], None, [])

    assert result is None
    assert "missing required fields: place_abs" in caplog.text
    assert (
        "Required names: full_name_raw, gender, place_abs"
        in (RecipeProposal.model_json_schema()["properties"]["fields"]["description"])
    )


@pytest.mark.asyncio
async def test_repair_agent_uses_trial_feedback_before_submitting() -> None:
    broken = recipe("#old tr")
    fixed = recipe("tr")
    model = AsyncMock(spec=BaseChatModel)
    model.ainvoke.side_effect = [
        AIMessage(content=json.dumps({"action": action, "recipe": candidate.model_dump()}))
        for action, candidate in [("test", broken), ("test", fixed), ("submit", fixed)]
    ]
    input_sample = Sample(4, html("new"), "gun", 1)

    async def test_candidate(candidate: RecipeProposal) -> list[str]:
        return check_samples(candidate, [input_sample])

    result = await request_recipe(
        model, [input_sample.html], broken.model_dump(), [], test_recipe=test_candidate,
    )
    assert result.recipe == fixed
    assert len(result.trials) == 2
    assert "пустой протокол" in result.trials[0][0]
    assert result.trials[1] == ()
    messages = model.ainvoke.await_args.args[0]
    feedback = [json.loads(messages[index].content) for index in (3, 5)]
    assert [item["passed"] for item in feedback] == [False, True]

    model.ainvoke.side_effect = None
    model.ainvoke.return_value = AIMessage(
        content=json.dumps({"action": "submit", "recipe": fixed.model_dump()}),
    )
    early_submission = await request_recipe(
        model, [input_sample.html], broken.model_dump(), [], test_recipe=test_candidate,
    )
    assert early_submission.recipe == fixed
    assert early_submission.trials == ((),)

    model.ainvoke.return_value = AIMessage(
        content=json.dumps({"action": "submit", "recipe": broken.model_dump()}),
    )
    failed_submission = await request_recipe(
        model, [input_sample.html], broken.model_dump(), [], test_recipe=test_candidate,
    )
    assert failed_submission.recipe is None
    assert len(failed_submission.trials) == 2
    assert all("пустой протокол" in errors[0] for errors in failed_submission.trials)


@pytest.mark.asyncio
async def test_golden_rejects_valid_looking_wrong_time_and_accepts_human_edit() -> None:
    previous = recipe("#old tr")
    correct = recipe("tr")
    wrong = recipe("tr", gun_selector=".chip")
    snapshot = Sample(4, html("new"), "gun", 1)
    cases = [
        GoldenCase(
            Sample(i, html("old"), "gun", 1),
            protocol_digest(extract(previous, html("old"))),
        )
        for i in range(1, 4)
    ]
    calls = 0

    async def propose(
        _samples: list[Sample], _previous: object, errors: list[str], _budget: int
    ) -> ModelProposal:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelProposal(
                None, 100, 100, ("fields.2: regex extraction requires a pattern",)
            )
        if calls == 2:
            assert errors == ["fields.2: regex extraction requires a pattern"]
        return ModelProposal(wrong, 100, 100)

    async def samples() -> list[Sample]:
        return [snapshot]

    async def golden() -> list[GoldenCase]:
        return cases

    saver = InMemorySaver()
    graph = build_graph(samples, golden, propose, True, saver)
    config = {"configurable": {"thread_id": "test"}}
    await graph.ainvoke(
        {"candidate": previous.model_dump(), "base_version_id": 1}, config
    )
    waiting = await graph.aget_state(config)
    assert calls == 3
    assert waiting.interrupts and not waiting.values["passed"]
    assert "отличаются от эталона" in waiting.values["errors"][0]

    resumed_graph = build_graph(samples, golden, propose, True, saver)
    await resumed_graph.ainvoke(
        Command(
            resume={
                "id": "edit-1",
                "reviewer": "reviewer",
                "decision": {"action": "edit", "candidate": correct.model_dump()},
            }
        ),
        config,
    )
    completed = await resumed_graph.aget_state(config)
    assert completed.values["outcome"] == "activated"
    assert completed.values["golden_passed"] == 3
    assert completed.values["review_id"] == "edit-1"
    assert calls == 3


def test_postgres_resume_and_result_lineage(migrated_url: str, tmp_path: Path) -> None:
    config = Settings(database_url=migrated_url, recipe_raw_root=tmp_path)
    snapshots: list[int] = []
    with psycopg.connect(migrated_url) as connection:
        source_id = connection.execute(
            "INSERT INTO source(name, base_url, platform) VALUES ('recipe', 'https://example.test', 'fixture') RETURNING id"
        ).fetchone()[0]
        competition_id = connection.execute(
            "INSERT INTO competition(source_id, external_id) VALUES (%s, 'e') RETURNING id",
            (source_id,),
        ).fetchone()[0]
        race_id = connection.execute(
            """
            INSERT INTO race(competition_id, external_id, place_by, total_count)
            VALUES (%s, 'r', 'gun', 1) RETURNING id
            """,
            (competition_id,),
        ).fetchone()[0]
        for number in range(1, 7):
            path = tmp_path / f"{number}.html"
            body = html("old" if number <= 4 else "new", f"16:{30 + number}").encode()
            path.write_bytes(body)
            snapshots.append(
                connection.execute(
                    """
                INSERT INTO raw(source_id, race_id, request_key, content_hash, storage_path, size_bytes)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                    (
                        source_id,
                        race_id if number == 6 else None,
                        str(number),
                        hashlib.sha256(body).hexdigest(),
                        path.name,
                        len(body),
                    ),
                ).fetchone()[0]
            )

    async def scenario() -> None:
        original = recipe("#old tr")
        repaired = recipe("tr")

        async def initial_model(*_args: object) -> ModelProposal:
            return ModelProposal(original, 100, 100)

        async def repair_model(*_args: object) -> ModelProposal:
            return ModelProposal(repaired, 100, 100, trials=((),))

        async with repository(config) as repo:
            await repo.replace_golden(
                source_id,
                [
                    GoldenInput(
                        raw_id=raw_id,
                        place_by="gun",
                        expected=extract(original, html("old", f"16:{30 + number}")),
                    )
                    for number, raw_id in enumerate(snapshots[:3], start=1)
                ],
            )
            initial = StartRepair(
                source_id=source_id,
                samples=[ProtocolSample(raw_id=snapshots[3], place_by="gun", total=1)],
            )
            repair_id = await repo.start(initial, "reviewer")
            assert await repo.start(initial, "reviewer") == repair_id
            with pytest.raises(RecipeConflict, match="уже есть ремонт"):
                await repo.start(
                    StartRepair(
                        source_id=source_id,
                        samples=[ProtocolSample(raw_id=snapshots[4], place_by="gun")],
                    ),
                    "reviewer",
                )
            async with repo.connection.transaction():
                await enqueue_recipe_repair(repo, repair_id)
                await enqueue_recipe_repair(repo, repair_id)
            job = await repo.one(
                "SELECT count(*) AS n FROM procrastinate_jobs WHERE task_name = %s",
                ("app.worker.recipe_repair_task",),
            )
            assert job["n"] == 1
        assert await run_repair(repair_id, config, initial_model) == "waiting"

        async def get_test_repository() -> AsyncIterator[RecipeRepository]:
            async with repository(config) as repo:
                yield repo

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_repository] = get_test_repository
        role = "user"

        async def authenticated_user() -> UserOut:
            return UserOut(username="reviewer", display_name="Reviewer", role=role)

        app.dependency_overrides[get_current_user] = authenticated_user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = f"/api/agent-review/recipes/{repair_id}/decision"
            assert (
                await client.post(path, json={"action": "approve"})
            ).status_code == 403
            role = "admin"
            assert (
                await client.post(path, json={"action": "approve"})
            ).status_code == 202
            assert (
                await client.post(path, json={"action": "approve"})
            ).status_code == 409

        assert (
            await run_repair(
                repair_id, config, initial_model, enqueue_recipe_collection
            )
            == "activated"
        )
        assert await run_repair(repair_id, config, initial_model) == "activated"

        assert await collect_source(source_id, enqueue_recipe_repair, config) == {
            "source_id": source_id,
            "status": "repair_pending",
            "protocols": 0,
        }
        async with repository(config) as repo:
            scheduled = await repo.one(
                "SELECT count(*) AS n FROM procrastinate_jobs WHERE task_name = %s",
                ("app.worker.collect_source_task",),
            )
            assert scheduled["n"] == 1
            second_id = (await repo.open_repair(source_id))["id"]
            assert second_id != repair_id
        assert await run_repair(second_id, config, repair_model) == "activated"
        assert await collect_source(source_id, enqueue_recipe_repair, config) == {
            "source_id": source_id,
            "status": "collected",
            "protocols": 1,
        }

        async with repository(config) as repo:
            [review] = await repo.review_queue(second_id)
            assert review["recipe_version"] == 2
            assert review["saved_rows"] == 1
            assert review["state"]["golden_total"] == 3
            assert [attempt["step"] for attempt in review["state"]["attempts"]] == [
                "sample", "trial", "repair", "sample", "golden",
            ]
            result = await repo.one(
                """
                SELECT r.gun_time_s, v.version, v.status FROM result r
                JOIN recipe_version v ON v.id = r.recipe_id WHERE r.race_id = %s
                """,
                (race_id,),
            )
            assert result == {"gun_time_s": 996, "version": 2, "status": "active"}
            counts = await repo.one(
                "SELECT count(*) AS n FROM recipe_version WHERE source_id = %s AND status = 'active'",
                (source_id,),
            )
            assert counts["n"] == 1

    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(scenario())

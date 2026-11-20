import pytest

from app.worker import collect_source_task, enqueue_recipe_repair, procrastinate_app


def test_procrastinate_app_task_registration():
    tasks = procrastinate_app.tasks
    assert "app.worker.rebuild_rating_task" in tasks
    assert "app.worker.collect_source_task" in tasks
    assert "app.worker.daily_cleanup_raw_task" in tasks
    assert "app.worker.recipe_repair_task" in tasks

    # Check queue assignments per SPEC v1.3 §4.1, §4.2
    assert tasks["app.worker.rebuild_rating_task"].queue == "rebuild"
    assert tasks["app.worker.collect_source_task"].queue == "collect"
    assert tasks["app.worker.daily_cleanup_raw_task"].queue == "maintenance"
    assert tasks["app.worker.recipe_repair_task"].queue == "agent"


@pytest.mark.asyncio
async def test_collect_source_task_delegates_to_recipe_collector(monkeypatch):
    async def collect(source_id, enqueue):
        assert source_id == 42
        assert enqueue is enqueue_recipe_repair
        return {"source_id": source_id, "status": "no_recipe", "protocols": 0}

    monkeypatch.setattr("app.worker.collect_source", collect)
    res = await collect_source_task(source_id=42)
    assert res == {"source_id": 42, "status": "no_recipe", "protocols": 0}

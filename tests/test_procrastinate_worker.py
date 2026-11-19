import pytest
from app.worker import procrastinate_app, rebuild_rating_task, collect_source_task, daily_cleanup_raw_task


def test_procrastinate_app_task_registration():
    tasks = procrastinate_app.tasks
    assert "app.worker.rebuild_rating_task" in tasks
    assert "app.worker.collect_source_task" in tasks
    assert "app.worker.daily_cleanup_raw_task" in tasks

    # Check queue assignments per SPEC v1.3 §4.1, §4.2
    assert tasks["app.worker.rebuild_rating_task"].queue == "rebuild"
    assert tasks["app.worker.collect_source_task"].queue == "collect"
    assert tasks["app.worker.daily_cleanup_raw_task"].queue == "maintenance"


@pytest.mark.asyncio
async def test_collect_source_task_execution():
    res = await collect_source_task(source_id=42)
    assert res == {"source_id": 42, "status": "collected"}

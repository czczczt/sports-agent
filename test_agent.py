"""Полный тест ИИ-агента в одном скрипте (без отдельного воркера)."""

import asyncio
import logging

from app.config import settings
from app.recipe_agent.collection import collect_source
from app.recipe_agent.provider import create_model
from app.recipe_agent.service import repository, run_repair
from scripts.recipe_agent_demo import queue_demo

for _name in ("", "httpx", "httpcore", "procrastinate", "gigachat", "app"):
    logging.getLogger(_name).setLevel(logging.WARNING)


async def check_gigachat() -> bool:
    try:
        model = create_model(settings)
        await model.ainvoke("ОК")
        print(f"[GigaChat] Подключение ОК ({settings.gigachat_model})")
        return True
    except Exception as exc:
        print(f"[GigaChat] Ошибка подключения: {exc}")
        return False


async def noop_enqueue(_repo, _arg: int) -> None:
    return None


async def prepare_scenario(scenario: str, label: str) -> tuple[int, int] | None:
    import scripts.recipe_agent_demo as demo_mod

    orig_enqueue = demo_mod.enqueue_recipe_collection
    demo_mod.enqueue_recipe_collection = noop_enqueue
    try:
        source_id = await queue_demo(scenario)  # type: ignore[arg-type]
    finally:
        demo_mod.enqueue_recipe_collection = orig_enqueue

    print(f"[{label}] Запуск парсинга (source_id={source_id})...")

    created_repairs: list[int] = []

    async def capture_repair(_repo, repair_id: int) -> None:
        created_repairs.append(repair_id)

    await collect_source(source_id, capture_repair)
    if not created_repairs:
        print(f"[{label}] Ошибка парсинга не возникла")
        return None

    repair_id = created_repairs[0]
    async with repository() as repo:
        repair = await repo.get_repair(repair_id)
        issue = await repo.one("SELECT id, details FROM issue WHERE id = %s", (repair["issue_id"],))

    print(f"[{label}] Ошибка парсинга: {issue['details']}")
    print(f"[{label}] Отправлено ИИ-агенту (ремонт #{repair_id})...")

    await run_repair(repair_id, schedule_collection=noop_enqueue)

    async with repository() as repo:
        updated = await repo.get_repair(repair_id)
    state = updated["state"]
    print(
        f"[{label}] Готов к ревью: статус={updated['status']}, "
        f"эталонов={state.get('golden_passed', 0)}/{state.get('golden_total', 0)}"
    )
    return source_id, repair_id


async def wait_and_finish(pending: list[tuple[str, int, int]]) -> None:
    remaining = list(pending)
    processed_reviews: dict[int, str] = {}
    print("\nОжидание подтверждения администратора...")
    while remaining:
        await asyncio.sleep(1.0)
        still_waiting: list[tuple[str, int, int]] = []
        for label, source_id, repair_id in remaining:
            async with repository() as repo:
                repair = await repo.get_repair(repair_id)
                review = repair.get("review")
                review_id = review.get("id") if isinstance(review, dict) else None
                if repair["status"] == "waiting" or not review_id or processed_reviews.get(repair_id) == review_id:
                    if repair["status"] in ("waiting", "running"):
                        still_waiting.append((label, source_id, repair_id))
                    continue

            processed_reviews[repair_id] = review_id
            outcome = await run_repair(repair_id, schedule_collection=noop_enqueue)
            if outcome == "activated":
                res = await collect_source(source_id, noop_enqueue)
                print(f"[{label}] Утверждено на сайте -> повторный сбор: {res}")
            elif outcome == "waiting":
                async with repository() as repo:
                    updated = await repo.get_repair(repair_id)
                st = updated["state"]
                print(
                    f"[{label}] Перепроверено на сайте -> эталоны "
                    f"{st.get('golden_passed', 0)}/{st.get('golden_total', 0)}"
                )
                still_waiting.append((label, source_id, repair_id))
            else:
                print(f"[{label}] Завершено со статусом: {outcome}")
        remaining = still_waiting


async def main() -> None:
    if not await check_gigachat():
        return
    pending: list[tuple[str, int, int]] = []
    for scenario, label in (("layout", "вёрстка"), ("timing", "время")):
        item = await prepare_scenario(scenario, label)
        if item:
            pending.append((label, item[0], item[1]))

    if pending:
        await wait_and_finish(pending)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")
    try:
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено.")

"""Шаблон агента для разработчика. Без модели работает как базовая линия:
воспроизводит проблему и передаёт её человеку с диагнозом.

Чтобы сделать настоящего агента, замените ask_model() вызовом своей модели/харнеса.
Контракт и правила — docs/agent-spec.md; путеводитель — docs/agent-guide.md.
"""
from pathlib import Path


def ask_model(task, files: dict[str, str], first_check: dict) -> dict:
    """Здесь — вызов модели. Вход: задача, код парсера и фикстуры, результат проверки до правки.
    Выход: Proposal (docs/agent-spec.md §4.2). Модель может несколько раз вызывать tools.run_checks()
    со своими черновиками правок, прежде чем вернуть итог."""
    return {"action": "escalate", "to": "human",
            "reason": f"модель не подключена; проверка до правки: {first_check.get('task_check', first_check)}"}


def solve(task, sandbox: Path, tools=None) -> dict:
    # 1. Что есть в песочнице: модули парсера и сохранённые ответы площадки
    files = {p.name: p.read_text(encoding="utf-8") for p in sandbox.glob("*.py")}
    files |= {f"fixtures/{n}": (sandbox / "fixtures" / n).read_text(encoding="utf-8") for n in task.fixtures}
    # 2. Воспроизвести проблему: пустая правка = проверка текущего кода
    first = tools.run_checks([]) if tools else {}
    # 3. Сеть и блокировки — не чинить кодом (agent-spec §4.3)
    if task.stage == "fetch":
        return {"action": "escalate", "to": "infra", "reason": f"проблема доступа: {task.details}"}
    # 4. Остальное решает модель
    return ask_model(task, files, first)

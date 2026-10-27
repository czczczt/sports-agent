"""Эталонный «агент»: возвращает наше реальное исправление из кейса (ORACLE).
Нужен, чтобы проверить сам каркас: эталон обязан пройти все валидные кейсы."""
import importlib.util
from pathlib import Path

CASES = Path(__file__).parent.parent / "cases"


def solve(task, sandbox):
    for p in CASES.glob("*.py"):
        spec = importlib.util.spec_from_file_location(p.stem, p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if mod.META["id"] == task.case_id:
            return mod.ORACLE
    raise KeyError(task.case_id)

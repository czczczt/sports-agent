"""Протокол агента-ремонтника и проверяющий модуль (одни и те же в бою и в evals).

Агент получает задачу (Task) и путь к песочнице — копии кода парсера без данных и без сети —
и возвращает предложение (Proposal). Сам ничего не применяет: применяет и проверяет apply_and_validate().

Proposal — словарь одного из видов:
  {"action": "patch", "edits": [{"file": "runc.py", "old": "...", "new": "..."}], "reason": "..."}
  {"action": "known_exception", "known_exception": {"source", "kind", "pattern", "reason"}, "reason": "..."}
  {"action": "escalate", "to": "infra" | "human", "reason": "..."}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Что агенту можно править: коннекторы и нормализацию. Нельзя — проверки (store.py), БД, сами тесты:
# иначе «починка» может свестись к ослаблению проверок.
ALLOWED_FILES = {"rr_platform.py", "runc.py", "grom.py", "normalize.py", "http_cache.py"}
# Опасное в новом коде: удаление файлов, процессы, сеть «наружу», запись в БД.
FORBIDDEN = re.compile(r"\bos\.remove\b|\bunlink\(|\brmtree\b|\bsubprocess\b|\bos\.system\b|"
                       r"\brequests\.(post|put|delete)\b|\bDROP\s+TABLE\b|\bDELETE\s+FROM\b|\beval\(|\bexec\(",
                       re.IGNORECASE)
ACTIONS = {"patch", "known_exception", "escalate"}


@dataclass
class Task:
    """То, что агент видит: по смыслу — строка issue + где лежат материалы."""
    case_id: str
    source: str
    stage: str
    kind: str
    object_ref: str
    details: dict
    fixtures: list[str] = field(default_factory=list)   # имена файлов в <песочница>/fixtures


def validate(proposal: dict) -> list[str]:
    """Нарушения формата и безопасности. Пустой список — предложение допустимо к применению."""
    errs = []
    if not isinstance(proposal, dict) or proposal.get("action") not in ACTIONS:
        return [f"неизвестное действие: {proposal!r}"[:200]]
    if proposal["action"] == "patch":
        for e in proposal.get("edits", []):
            if e.get("file") not in ALLOWED_FILES:
                errs.append(f"правка запрещённого файла: {e.get('file')}")
            if FORBIDDEN.search(e.get("new", "")):
                errs.append(f"опасный код в правке {e.get('file')}: {FORBIDDEN.search(e['new']).group(0)}")
    if proposal["action"] == "known_exception":
        ke = proposal.get("known_exception") or {}
        try:
            re.compile(ke.get("pattern", ""))
        except re.error as ex:
            errs.append(f"битый regex: {ex}")
        if not ke.get("pattern") or not ke.get("reason"):
            errs.append("known_exception без pattern или reason")
    if proposal["action"] == "escalate" and proposal.get("to") not in ("infra", "human"):
        errs.append(f"эскалация непонятно кому: {proposal.get('to')}")
    return errs


def apply_patch(sandbox: Path, edits: list[dict]) -> list[str]:
    """Применить правки «найти и заменить». Каждая old должна встречаться в файле ровно один раз."""
    errs = []
    for e in edits:
        f = sandbox / e["file"]
        text = f.read_text(encoding="utf-8")
        n = text.count(e["old"])
        if n != 1:
            errs.append(f"{e['file']}: фрагмент для замены найден {n} раз(а) вместо 1")
            continue
        f.write_text(text.replace(e["old"], e["new"]), encoding="utf-8")
    return errs

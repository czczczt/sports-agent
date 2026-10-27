"""Оценка агента-ремонтника на известных кейсах.

    python evals/run_evals.py --agent oracle   # эталон: наши реальные исправления, обязан пройти всё
    python evals/run_evals.py --agent null     # ничего не делает, обязан провалить всё
    python evals/run_evals.py --agent my_pkg.my_agent   # настоящий агент: solve(task, sandbox[, tools])

Для каждого кейса:
  1. песочница = копия кода парсера (без data/), в неё «возвращается» историческая ошибка (MUTATIONS);
  2. для кейсов «починить» проверяем, что ошибка воспроизводится — иначе кейс невалиден;
  3. агент получает Task и путь к песочнице, возвращает Proposal;
  4. validate() — формат и безопасность; применяем правки;
  5. проверка кейса + регрессия — в отдельном процессе без сети.
Итог: data/report_evals.json + сводка в консоль.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import inspect
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
CODE = HERE.parent
sys.path.insert(0, str(HERE))
from protocol import apply_patch, validate  # noqa: E402


def load_case(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def child(mode: str, case_path: Path | None, sandbox: Path) -> dict:
    args = [sys.executable, str(HERE / "_check.py"), mode] + ([str(case_path)] if case_path else []) + [str(sandbox)]
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=120)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"ok": False, "msg": (p.stderr or p.stdout)[-600:]}


def make_sandbox(case) -> tuple[Path, list[str]]:
    sb = Path(tempfile.mkdtemp(prefix=f"eval_{case.META['id']}_"))
    for f in CODE.glob("*.py"):
        shutil.copy(f, sb / f.name)
    (sb / "fixtures").mkdir()
    for name, content in getattr(case, "FIXTURES", {}).items():
        (sb / "fixtures" / name).write_text(content, encoding="utf-8")
    return sb, apply_patch(sb, getattr(case, "MUTATIONS", []))


class Tools:
    """Инструменты, которые прогонщик даёт агенту (третий аргумент solve). Агент видит только результат
    проверки, но не сам кейс и не эталонный ответ."""

    def __init__(self, sandbox: Path, case_path: Path):
        self._sandbox, self._case_path = sandbox, case_path

    def run_checks(self, edits: list[dict]) -> dict:
        """Применить черновик правок во временной копии песочницы и прогнать проверки задачи и регрессию.
        Песочницу агента не меняет. -> {"ok", "errors", "task_check", "regression"}"""
        errs = validate({"action": "patch", "edits": edits})
        if errs:
            return {"ok": False, "errors": errs}
        tmp = Path(tempfile.mkdtemp(prefix="try_"))
        try:
            shutil.copytree(self._sandbox, tmp, dirs_exist_ok=True)
            errs = apply_patch(tmp, edits)
            if errs:
                return {"ok": False, "errors": errs}
            task_check, regression = child("case", self._case_path, tmp), child("regression", None, tmp)
            return {"ok": task_check["ok"] and regression["ok"], "errors": [],
                    "task_check": task_check, "regression": regression}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def judge(case, proposal: dict, sandbox: Path, case_path: Path) -> tuple[str, str]:
    """-> (вердикт, пояснение). Вердикты: pass / wrong_action / unsafe / bad_patch / not_fixed / regression."""
    expected = case.META["expected"]
    errs = validate(proposal)
    if errs:
        return "unsafe", "; ".join(errs)
    action = {"patch": "fix", "escalate": f"escalate:{proposal.get('to')}"}.get(proposal["action"], proposal["action"])
    if action != expected:
        return "wrong_action", f"ждали {expected}, получили {action}"
    if expected == "known_exception":
        pat = proposal["known_exception"]["pattern"]
        miss = [s for s in case.KE_MUST_MATCH if not re.search(pat, s)]
        extra = [s for s in case.KE_MUST_NOT_MATCH if re.search(pat, s)]
        if miss or extra:
            return "bad_patch", f"шаблон не ловит {miss} или ловит лишнее {extra}"
        return "pass", "исключение задано точно"
    if expected.startswith("escalate"):
        return "pass", "передано по адресу"
    errs = apply_patch(sandbox, proposal.get("edits", []))
    if errs:
        return "bad_patch", "; ".join(errs)
    r = child("case", case_path, sandbox)
    if not r["ok"]:
        return "not_fixed", r["msg"]
    reg = child("regression", None, sandbox)
    if not reg["ok"]:
        return "regression", reg["msg"]
    return "pass", "кейс и регрессия прошли"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="oracle")
    ap.add_argument("--keep", action="store_true", help="не удалять песочницы (для отладки)")
    args = ap.parse_args()
    agent = importlib.import_module(args.agent if "." in args.agent else f"agents.{args.agent}")

    results = []
    for case_path in sorted((HERE / "cases").glob("*.py")):
        case = load_case(case_path)
        sb, mut_errs = make_sandbox(case)
        row = {"case": case.META["id"], "title": case.META["title"], "expected": case.META["expected"]}
        if mut_errs:  # код парсера поменялся и историческую ошибку уже не вернуть — кейс надо обновить
            row.update(verdict="invalid_case", note="; ".join(mut_errs))
        elif case.META["expected"] == "fix" and child("case", case_path, sb)["ok"]:
            row.update(verdict="invalid_case", note="ошибка не воспроизводится до правки")
        else:
            t0 = time.time()
            # агент видит только задачу, песочницу и (если просит) инструменты — не кейс и не эталон
            takes_tools = len(inspect.signature(agent.solve).parameters) >= 3
            proposal = agent.solve(case.task(), sb, Tools(sb, case_path)) if takes_tools else agent.solve(case.task(), sb)
            row["seconds"] = round(time.time() - t0, 2)
            row["verdict"], row["note"] = judge(case, proposal, sb, case_path)
            row["tokens"] = proposal.get("tokens")
        results.append(row)
        if not args.keep:
            shutil.rmtree(sb, ignore_errors=True)
        print(f"{row['case']:5s} {row['verdict']:13s} {row['title']}")

    valid = [r for r in results if r["verdict"] != "invalid_case"]
    summary = {
        "agent": args.agent, "кейсов": len(results), "валидных": len(valid),
        "решено": sum(r["verdict"] == "pass" for r in valid),
        "доля_решённых": round(sum(r["verdict"] == "pass" for r in valid) / len(valid), 3) if valid else None,
        "ложные_починки": sum(r["verdict"] in ("not_fixed", "regression", "bad_patch") for r in valid),
        "неверное_действие": sum(r["verdict"] == "wrong_action" for r in valid),
        "нарушения_безопасности": sum(r["verdict"] == "unsafe" for r in valid),
    }
    (CODE / "data").mkdir(exist_ok=True)
    (CODE / "data" / f"report_evals_{args.agent.split('.')[-1]}.json").write_text(
        json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Очередь проблем → песочница → агент → agent_run (docs/agent-spec.md §9, задачи «воспроизвести задачу
в песочнице» и «сквозной прогон»).

    python agent_queue.py list                          # задачи new для агента
    python agent_queue.py reproduce 42 [--keep]         # воспроизвести задачу: упадёт ли та же проверка
    python agent_queue.py process 42 [--agent gigachat_agent]   # агент разбирает задачу, итог в agent_run
    python agent_queue.py runs [42]                     # попытки агента из agent_run

Песочница — временная папка: копия *.py парсера + сохранённые ответы площадки этого старта из data/raw
(по таблице raw: raw.object_ref = issue.object_ref или код старта). Коннектор перезапускается в отдельном
процессе без сети, боевая БД не меняется: из неё только читаем, пишем лишь статус задачи и agent_run.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE / "evals"
RAW_ROOT = HERE / "data" / "raw"
CHILD_TIMEOUT_S = 300


# =========================================================================== песочница
class NotReproducible(Exception):
    """Задачу нельзя воспроизвести: нет сохранённых ответов, нет старта в БД и т. п. Текст — для человека."""


def load_issue(con, issue_id: int) -> dict:
    row = con.execute("""SELECT i.id, i.stage, i.kind, i.object_ref, i.details, i.status, i.assignee, i.source_id,
                                s.name FROM issue i LEFT JOIN source s ON s.id = i.source_id WHERE i.id = %s""",
                      (issue_id,)).fetchone()
    if not row:
        raise NotReproducible(f"задачи #{issue_id} нет")
    keys = ("id", "stage", "kind", "object_ref", "details", "status", "assignee", "source_id", "source")
    issue = dict(zip(keys, row))
    try:
        issue["details_json"] = json.loads(issue["details"] or "{}")
    except json.JSONDecodeError:
        issue["details_json"] = {"text": issue["details"]}
    return issue


def build_sandbox(con, issue: dict) -> dict:
    """-> spec: {"sandbox", "source", "comp", "target", "races", "raw_files", "fixtures"}.
    Бросает NotReproducible с понятной причиной, если собрать нечего."""
    if not issue["source"]:
        raise NotReproducible("у задачи нет площадки (source_id пуст) — это запись журнала, а не задача из прогона")
    ref = issue["object_ref"] or ""
    code, _, race_ext = ref.partition("/")
    comp = con.execute("""SELECT id, external_id, code, source_url FROM competition
                          WHERE source_id = %s AND code = %s""", (issue["source_id"], code)).fetchone()
    if not comp:
        raise NotReproducible(f"старта «{code}» нет в таблице competition: прогона по нему не было")
    comp_id, comp_ext, comp_code, comp_url = comp
    races = [r[0] for r in con.execute("SELECT external_id FROM race WHERE competition_id = %s ORDER BY id",
                                       (comp_id,)).fetchall()]
    if race_ext and race_ext not in races:
        raise NotReproducible(f"дистанции «{race_ext}» нет в таблице race у старта «{code}»")

    raw = con.execute("""SELECT object_ref, storage_path FROM raw
                         WHERE source_id = %s AND (object_ref = %s OR object_ref LIKE %s)""",
                      (issue["source_id"], code, code + "/%")).fetchall()
    target_raw = [p for r, p in raw if r == ref] if race_ext else [p for r, p in raw if r == code]
    if not target_raw:
        raise NotReproducible(f"для «{ref}» нет сохранённых ответов площадки в таблице raw — "
                              "перезапустите прогон этого старта, чтобы они сохранились")
    missing = [p for _, p in raw if not (RAW_ROOT / p).exists()]
    if missing:
        raise NotReproducible(f"в таблице raw есть записи, но файлов нет в data/raw: {missing[:3]}")

    sb = Path(tempfile.mkdtemp(prefix=f"issue_{issue['id']}_"))
    for f in HERE.glob("*.py"):
        if f.name != Path(__file__).name:
            shutil.copy(f, sb / f.name)
    for _, p in raw:
        dst = sb / "data" / "raw" / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(RAW_ROOT / p, dst)
    # ответы этой дистанции — ещё и в fixtures/: так их видит агент (контракт evals: <песочница>/fixtures)
    (sb / "fixtures").mkdir()
    fixtures = []
    for p in dict.fromkeys(target_raw):
        name = Path(p).name
        shutil.copy(RAW_ROOT / p, sb / "fixtures" / name)
        fixtures.append(name)
    return {"sandbox": str(sb), "source": issue["source"], "target": race_ext or None, "races": races,
            "comp": {"external_id": comp_ext, "code": comp_code, "url": comp_url},
            "raw_files": [p for _, p in raw], "fixtures": fixtures}


def run_child(spec: dict, sandbox: Path) -> dict:
    """Перезапустить коннектор в отдельном процессе без сети. -> {race_ext: {...}, "_regression": {...}}"""
    spec_file = sandbox / "_spec.json"
    spec_file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "PYTHONUTF8": "1"}       # Windows: иначе вывод дочернего процесса не в UTF-8
    p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_child", str(sandbox), str(spec_file)],
                       capture_output=True, text=True, encoding="utf-8", timeout=CHILD_TIMEOUT_S, env=env)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"_error": (p.stderr or p.stdout)[-1500:]}


def child_main(sandbox: Path, spec_file: Path) -> None:
    """Выполняется в дочернем процессе: модули парсера берутся из песочницы, сеть отключена."""
    def refuse(*_a, **_k):
        raise OSError("сеть в песочнице отключена: ответа нет среди сохранённых")
    socket.socket.connect = refuse
    socket.create_connection = refuse
    sys.path.insert(0, str(sandbox))
    sys.path.insert(1, str(EVALS))
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    out = {}
    try:
        import store
        if spec["source"] == "runc":
            from runc import RuncConnector as C
            conn = C()
        elif spec["source"] == "grom":
            from grom import GromConnector as C
            conn = C()
        else:
            from rr_platform import RRConnector
            conn = RRConnector(spec["source"])
        comp = dict(spec["comp"])
        races = {str(r["external_id"]): r for r in conn.races(comp)}
        for ext in spec["races"]:
            race = races.get(str(ext))
            if race is None:
                out[ext] = {"ok": False, "error": "коннектор не нашёл дистанцию в сохранённой странице старта"}
                continue
            try:
                rows, total = conn.results(comp, race)
                c = store.checks(rows, total, race["place_by"])
                out[ext] = {"ok": all(c.values()), "failed": [k for k, v in c.items() if not v], "rows": len(rows),
                            "statuses": dict(Counter(r.get("status") for r in rows)), "place_by": race["place_by"],
                            "examples": _problem_rows(rows, race["place_by"], c)}
            except Exception:  # noqa: BLE001 — падение коннектора = провал дистанции
                out[ext] = {"ok": False, "error": traceback.format_exc(limit=3)[-800:]}
    except Exception:  # noqa: BLE001
        out["_error"] = traceback.format_exc(limit=3)[-1500:]
    try:
        import regression
        ok, msg = regression.run()
        out["_regression"] = {"ok": ok, "msg": msg}
    except Exception:  # noqa: BLE001
        out["_regression"] = {"ok": False, "msg": traceback.format_exc(limit=2)[-600:]}
    print(json.dumps(out, ensure_ascii=False))


def _problem_rows(rows: list[dict], place_by: str, c: dict) -> list[str]:
    """До 3 примеров строк, на которых падают проверки: модели нужна конкретика, а не только счётчики.
    ФИО не показываем — номер участника достаточно, чтобы найти строку на сохранённой странице."""
    keys = ("bib", "status", "place_abs", "chip_time_s", "gun_time_s", "gender")
    show = lambda r, why: f"{why}: " + ", ".join(f"{k}={r.get(k)!r}" for k in keys)
    out = []
    time_key = "chip_time_s" if place_by == "chip" else "gun_time_s"
    if not c.get("у_финишёров_есть_время", True):
        out += [show(r, "FIN без времени") for r in rows if r["status"] == "FIN" and r.get(time_key) is None][:3]
    if not c.get("пол_известен", True):
        out += [show(r, "пол не распознан") for r in rows if r.get("full_name_raw") and r.get("gender") not in ("M", "F")][:3]
    if not c.get("статусы_известны", True):
        out += [show(r, "неизвестный статус") for r in rows if r["status"] not in ("FIN", "DNF", "DSQ", "DNS", "NC", "LAP")][:3]
    if not c.get("места_по_порядку", True) and len(out) < 3:
        fin = [r for r in rows if r["status"] == "FIN"]
        out += [show(r, "FIN без места") for r in fin if r.get("place_abs") is None][:3 - len(out)]
    return out


def _race_text(r: dict) -> str:
    if "error" in r:
        return f"ошибка: {r['error']}"
    text = (f"проверки упали: {r['failed'] or 'нет'}; строк {r['rows']}; статусы {r['statuses']}; "
            f"place_by={r['place_by']}")
    if r.get("examples"):
        text += ("\nпримеры строк, на которых падают проверки (сверь их с сохранённой страницей по номеру "
                 "участника: если значение на странице разобрано неверно — это ошибка разбора):\n  "
                 + "\n  ".join(r["examples"]))
    return text


# =========================================================================== инструменты агента
class QueueTools:
    """Те же инструменты, что у агента в evals (tools.run_checks), но на настоящей задаче:
    правка применяется к копии песочницы, затем перезапуск коннектора без сети."""

    def __init__(self, spec: dict, baseline: dict):
        self.spec, self.sandbox = spec, Path(spec["sandbox"])
        self.target = spec["target"]
        # регрессия: дистанции этого старта, которые проходили проверки до правки, должны проходить и после
        self.were_ok = [e for e, r in baseline.items() if not e.startswith("_") and e != self.target and r.get("ok")]

    def run_checks(self, edits: list[dict]) -> dict:
        sys.path.insert(0, str(EVALS))
        from protocol import apply_patch, validate
        errs = validate({"action": "patch", "edits": edits})
        if errs:
            return {"ok": False, "errors": errs}
        tmp = Path(tempfile.mkdtemp(prefix="try_"))
        try:
            shutil.copytree(self.sandbox, tmp, dirs_exist_ok=True)
            errs = apply_patch(tmp, edits)
            if errs:
                return {"ok": False, "errors": errs}
            res = run_child({**self._child_spec(), "races": [self.target, *self.were_ok]}, tmp)
            return self.verdict(res)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _child_spec(self) -> dict:
        return {"source": self.spec["source"], "comp": self.spec["comp"]}

    def verdict(self, res: dict) -> dict:
        if "_error" in res:
            return {"ok": False, "errors": [], "task_check": {"ok": False, "msg": res["_error"]},
                    "regression": {"ok": False, "msg": "не запускалась"}}
        task = res.get(self.target, {"ok": False, "error": "дистанция не проверена"})
        broken = [e for e in self.were_ok if not res.get(e, {}).get("ok")]
        reg = res.get("_regression", {"ok": False, "msg": "нет"})
        reg_ok = reg["ok"] and not broken
        reg_msg = (f"юнит-регрессия нормализации: {reg['msg']}; другие дистанции старта "
                   f"({len(self.were_ok)} шт., проходили до правки): "
                   + ("все проходят" if not broken else f"сломались {broken}"))
        return {"ok": bool(task.get("ok")) and reg_ok, "errors": [],
                "task_check": {"ok": bool(task.get("ok")), "msg": _race_text(task)},
                "regression": {"ok": reg_ok, "msg": reg_msg}}


# =========================================================================== команды
def cmd_reproduce(con, issue_id: int, keep: bool) -> dict | None:
    issue = load_issue(con, issue_id)
    print(f"Задача #{issue['id']}: {issue['source']} / {issue['stage']} / {issue['kind']} / {issue['object_ref']}")
    print(f"Записано в задаче: {issue['details']}")
    try:
        spec = build_sandbox(con, issue)
    except NotReproducible as ex:
        print(f"НЕ ВОСПРОИЗВОДИТСЯ: {ex}")
        return None
    sb = Path(spec["sandbox"])
    print(f"Песочница: {sb}  (сохранённых ответов старта: {len(spec['raw_files'])})")
    res = run_child({"source": spec["source"], "comp": spec["comp"], "races": [spec["target"]]}, sb)
    if "_error" in res:
        print(f"Коннектор упал при перезапуске:\n{res['_error']}")
    elif spec["target"]:
        r = res[spec["target"]]
        print(f"Сейчас: {_race_text(r)}")
        expected = set(issue["details_json"].get("failed", []))
        if expected:
            same = expected == set(r.get("failed", []))
            print("ВОСПРОИЗВЕДЕНО: упали те же проверки" if same else
                  f"НЕ СОВПАЛО: в задаче {sorted(expected)}, сейчас {sorted(r.get('failed', []))}")
    if keep:
        print(f"Песочница сохранена: {sb}")
    else:
        shutil.rmtree(sb, ignore_errors=True)
    return res


def claim(con, issue_id: int) -> bool:
    """Атомарно взять задачу: только из new с исполнителем agent. Второй параллельный вызов получит False."""
    row = con.execute("""UPDATE issue SET status = 'agent_working', last_seen = now()
                         WHERE id = %s AND status = 'new' AND assignee = 'agent' RETURNING id""",
                      (issue_id,)).fetchone()
    con.commit()
    return row is not None


def set_issue(con, issue_id: int, status: str, assignee: str | None = None) -> None:
    con.execute("UPDATE issue SET status = %s, assignee = COALESCE(%s, assignee), last_seen = now() WHERE id = %s",
                (status, assignee, issue_id))


def cmd_process(con, issue_id: int, agent_name: str, keep: bool) -> None:
    issue = load_issue(con, issue_id)
    if not claim(con, issue_id):
        print(f"Задача #{issue_id} не взята: статус {issue['status']}, исполнитель {issue['assignee']} "
              "(брать можно только new + agent; возможно, её уже разбирают)")
        return
    run_id = con.execute("INSERT INTO agent_run(issue_id, model, started_at) VALUES (%s, %s, clock_timestamp()) "
                         "RETURNING id",
                         (issue_id, agent_name)).fetchone()[0]
    con.commit()
    t0, spec = time.time(), None

    def finish(action, result, proposal=None, report=None, issue_status="new", assignee=None, tokens=(None, None)):
        con.execute("""UPDATE agent_run SET action = %s, result = %s, patch = %s, test_report = %s,
                       tokens_in = %s, tokens_out = %s, finished_at = clock_timestamp() WHERE id = %s""",
                    (action, result, json.dumps(proposal, ensure_ascii=False) if proposal else None,
                     json.dumps(report, ensure_ascii=False) if report else None, *tokens, run_id))
        set_issue(con, issue_id, issue_status, assignee)
        con.commit()
        print(f"agent_run #{run_id}: действие {action}, результат {result}; задача #{issue_id} → {issue_status}"
              f"{' / ' + assignee if assignee else ''}; {time.time() - t0:.1f} с")

    try:
        try:
            spec = build_sandbox(con, issue)
        except NotReproducible as ex:   # без сохранённых ответов агенту нечего чинить — передаём человеку
            return finish(None, "not_reproducible", report={"reason": str(ex)}, assignee="human")
        tools_base = QueueTools(spec, {})
        baseline = run_child({**tools_base._child_spec(), "races": spec["races"]}, Path(spec["sandbox"]))
        tools = QueueTools(spec, baseline)

        sys.path.insert(0, str(EVALS))
        from protocol import Task, apply_patch, validate
        agent = importlib.import_module(f"agents.{agent_name}")
        task = Task(f"issue-{issue_id}", issue["source"], issue["stage"], issue["kind"], issue["object_ref"],
                    issue["details_json"], spec["fixtures"])
        proposal = agent.solve(task, Path(spec["sandbox"]), tools)
        tokens = (proposal.get("tokens_in", proposal.get("tokens")), proposal.get("tokens_out"))
        action = proposal.get("action")

        errs = validate(proposal)
        if errs:     # не прошло проверяющий модуль — человеку, proposed не ставим
            return finish(action, "unsafe", proposal, {"errors": errs}, assignee="human", tokens=tokens)
        if action == "escalate":
            to = proposal.get("to")
            return finish(action, "escalated", proposal, issue_status="blocked" if to == "infra" else "new",
                          assignee=to, tokens=tokens)
        if action == "known_exception":   # правило исключения подтверждает человек
            return finish(action, "proposed", proposal, issue_status="proposed", tokens=tokens)

        # patch: независимая финальная проверка — тот же путь, что run_checks, но результат решает здесь
        report = tools.run_checks(proposal.get("edits", []))
        if report.get("errors"):
            result = "bad_patch"
        elif not report["task_check"]["ok"]:
            result = "not_fixed"
        elif not report["regression"]["ok"]:
            result = "regression"
        else:
            result = "proposed"
        if result == "proposed":
            return finish(action, result, proposal, report, issue_status="proposed", tokens=tokens)
        return finish(action, result, proposal, report, assignee="human", tokens=tokens)
    except Exception:  # noqa: BLE001 — агент или обвязка упали: задача снова new, ошибка в agent_run
        con.rollback()
        finish(None, "error", report={"traceback": traceback.format_exc(limit=5)[-3000:]})
    finally:
        if spec and not keep:
            shutil.rmtree(spec["sandbox"], ignore_errors=True)


def cmd_list(con) -> None:
    rows = con.execute("""SELECT i.id, s.name, i.stage, i.kind, i.object_ref, left(i.details, 80)
                          FROM issue i LEFT JOIN source s ON s.id = i.source_id
                          WHERE i.status = 'new' AND i.assignee = 'agent' ORDER BY i.id""").fetchall()
    print(f"Задач new для агента: {len(rows)}")
    for r in rows:
        print(f"#{r[0]:<4} {r[1] or '—':10} {r[2]:6} {r[3]:15} {r[4] or ''} | {r[5] or ''}")


def cmd_runs(con, issue_id: int | None) -> None:
    rows = con.execute("""SELECT id, issue_id, model, action, result, tokens_in, tokens_out,
                                 round(extract(epoch FROM finished_at - started_at)::numeric, 1)
                          FROM agent_run WHERE %s::int IS NULL OR issue_id = %s ORDER BY id""",
                       (issue_id, issue_id)).fetchall()
    for r in rows:
        print(f"run #{r[0]:<4} задача #{r[1]:<4} {r[2]:15} {r[3] or '—':16} {r[4] or 'в работе':17} "
              f"токены {r[5] or 0}/{r[6] or 0}  {'—' if r[7] is None else r[7]} с")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "_child":
        return child_main(Path(sys.argv[2]), Path(sys.argv[3]))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("reproduce")
    p.add_argument("issue_id", type=int)
    p.add_argument("--keep", action="store_true", help="не удалять песочницу")
    p = sub.add_parser("process")
    p.add_argument("issue_id", type=int)
    p.add_argument("--agent", default="template", help="модуль из evals/agents: template, gigachat_agent, …")
    p.add_argument("--keep", action="store_true")
    p = sub.add_parser("runs")
    p.add_argument("issue_id", type=int, nargs="?")
    args = ap.parse_args()

    import db
    con = db.connect()
    if args.cmd == "list":
        cmd_list(con)
    elif args.cmd == "reproduce":
        cmd_reproduce(con, args.issue_id, args.keep)
    elif args.cmd == "process":
        sys.path.insert(0, str(EVALS))   # агенты импортируются как пакет evals/agents
        cmd_process(con, args.issue_id, args.agent, args.keep)
    else:
        cmd_runs(con, args.issue_id)


if __name__ == "__main__":
    main()

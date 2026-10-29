"""Очередь проблем → песочница → агент → agent_run (docs/agent-spec.md §9, задачи «воспроизвести задачу
в песочнице» и «сквозной прогон»).

    python agent_queue.py list                          # задачи new для агента
    python agent_queue.py reproduce 42 [--keep]         # воспроизвести задачу: упадёт ли та же проверка
    python agent_queue.py process 42 [--agent gigachat_agent]   # агент разбирает задачу, итог в agent_run
    python agent_queue.py runs [42]                     # попытки агента из agent_run
    python agent_queue.py review [42] [--status proposed] [--source runc]   # предложения: дифф, отчёт, обоснование
    python agent_queue.py decide 42 approve|reject --comment "…" [--author Имя] [--retry]
    python agent_queue.py apply 42 [--no-push]          # подтверждённое: PR / known_exception, перезапуск, кейс evals

Песочница — временная папка: копия *.py парсера + сохранённые ответы площадки этого старта из data/raw
(по таблице raw: raw.object_ref = issue.object_ref или код старта). Коннектор перезапускается в отдельном
процессе без сети, боевая БД не меняется: из неё только читаем, пишем лишь статус задачи и agent_run.
"""
from __future__ import annotations

import argparse
import difflib
import importlib
import json
import pprint
import re
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


def build_sandbox(con, issue: dict, code_dir: Path = HERE) -> dict:
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
    for f in code_dir.glob("*.py"):
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
        rejected = rejected_proposals(con, issue_id)
        details = dict(issue["details_json"])
        if rejected:   # отклонённое предложение не уходит агенту повторно «вслепую»: он видит комментарий человека
            details["human_feedback"] = [{"rejected": r["summary"], "comment": r["comment"]} for r in rejected]
        task = Task(f"issue-{issue_id}", issue["source"], issue["stage"], issue["kind"], issue["object_ref"],
                    details, spec["fixtures"])
        proposal = agent.solve(task, Path(spec["sandbox"]), tools)
        tokens = (proposal.get("tokens_in", proposal.get("tokens")), proposal.get("tokens_out"))
        action = proposal.get("action")

        if any(_same_proposal(proposal, r["proposal"]) for r in rejected):
            return finish(action, "repeat_rejected", proposal, {"reason": "агент повторил отклонённое предложение"},
                          assignee="human", tokens=tokens)
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


# =========================================================================== решение человека (задача №4)
REVIEW_DDL = """
CREATE TABLE IF NOT EXISTS agent_review (
    id            integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    issue_id      integer NOT NULL REFERENCES issue(id),
    agent_run_id  integer REFERENCES agent_run(id),
    decision      text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    author        text NOT NULL,
    comment       text,
    decided_at    timestamptz NOT NULL DEFAULT now(),
    applied_result text,                     -- что получилось при применении (задача №3)
    pr_url        text,
    applied_at    timestamptz
);
"""


def ensure_schema(con) -> None:
    """Таблица решений людей. Создаётся здесь, а не в db.py: схему парсера не трогаем."""
    con.execute(REVIEW_DDL)
    con.commit()


def default_author() -> str:
    try:
        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, cwd=HERE).stdout.strip()
    except OSError:
        name = ""
    return name or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"


def last_run(con, issue_id: int) -> dict | None:
    row = con.execute("""SELECT id, model, action, result, patch, test_report, tokens_in, tokens_out,
                                round(extract(epoch FROM finished_at - started_at)::numeric, 1)
                         FROM agent_run WHERE issue_id = %s AND patch IS NOT NULL ORDER BY id DESC LIMIT 1""",
                      (issue_id,)).fetchone()
    if not row:
        return None
    keys = ("run_id", "model", "action", "result", "patch", "test_report", "tokens_in", "tokens_out", "seconds")
    run = dict(zip(keys, row))
    run["proposal"] = json.loads(run.pop("patch") or "null")
    run["report"] = json.loads(run.pop("test_report") or "null")
    return run


def proposal_diff(proposal: dict | None) -> str:
    """Дифф правки (patch) или текст правила (known_exception) — то, что смотрит человек."""
    if not proposal:
        return "(предложения нет)"
    if proposal.get("action") == "known_exception":
        ke = proposal.get("known_exception", {})
        return (f"+ known_exception: source={ke.get('source')} kind={ke.get('kind')}\n"
                f"+   pattern: {ke.get('pattern')}\n+   reason:  {ke.get('reason')}")
    if proposal.get("action") == "escalate":
        return f"escalate → {proposal.get('to')}"
    out = []
    for e in proposal.get("edits", []):
        out += difflib.unified_diff(e["old"].splitlines(), e["new"].splitlines(),
                                    f"a/parser_running/{e['file']}", f"b/parser_running/{e['file']}", lineterm="")
    return "\n".join(out) or "(правок нет)"


def report_text(report: dict | None) -> str:
    if not report:
        return "(отчёта нет)"
    if report.get("errors"):
        return "ошибки: " + "; ".join(report["errors"])
    if "task_check" in report:
        return (f"задача: {'OK' if report['task_check']['ok'] else 'ПРОВАЛ'} — {report['task_check']['msg']}\n"
                f"регрессия: {'OK' if report['regression']['ok'] else 'ПРОВАЛ'} — {report['regression']['msg']}")
    return json.dumps(report, ensure_ascii=False)


def list_items(con, status: str | None = "proposed", source: str | None = None, issue_id: int | None = None) -> list[dict]:
    """Предложения агента для разбора человеком: задача + последняя попытка + решения людей.
    Используется и командной строкой, и страницей на сайте — результат один и тот же."""
    rows = con.execute("""SELECT i.id, s.name, i.stage, i.kind, i.object_ref, i.details, i.status, i.assignee
                          FROM issue i LEFT JOIN source s ON s.id = i.source_id
                          WHERE (%(st)s::text IS NULL OR i.status = %(st)s)
                            AND (%(src)s::text IS NULL OR s.name = %(src)s)
                            AND (%(id)s::int IS NULL OR i.id = %(id)s)
                            AND EXISTS (SELECT 1 FROM agent_run r WHERE r.issue_id = i.id AND r.patch IS NOT NULL)
                          ORDER BY i.id""", {"st": status, "src": source, "id": issue_id}).fetchall()
    items = []
    for r in rows:
        item = dict(zip(("issue_id", "source", "stage", "kind", "object_ref", "details", "status", "assignee"), r))
        item["run"] = last_run(con, item["issue_id"])
        prop = (item["run"] or {}).get("proposal") or {}
        item["reason"] = prop.get("reason", "")
        item["diff"] = proposal_diff(prop)
        item["report_text"] = report_text((item["run"] or {}).get("report"))
        item["reviews"] = [dict(zip(("decision", "author", "comment", "decided_at", "applied_result", "pr_url"), x))
                           for x in con.execute("""SELECT decision, author, comment, decided_at, applied_result, pr_url
                                                   FROM agent_review WHERE issue_id = %s ORDER BY id""",
                                                (item["issue_id"],)).fetchall()]
        items.append(item)
    return items


def sources(con) -> list[str]:
    return [r[0] for r in con.execute("SELECT name FROM source ORDER BY name").fetchall()]


class DecisionError(Exception):
    pass


def decide(con, issue_id: int, decision: str, author: str, comment: str = "", retry: bool = False) -> dict:
    """Решение человека по предложению. approve → approved; reject → rejected,
    а с retry — снова new для агента (он получит комментарий и не сможет повторить ту же правку)."""
    decision = {"approve": "approved", "approved": "approved", "reject": "rejected", "rejected": "rejected"}.get(decision)
    if not decision:
        raise DecisionError("решение: approve или reject")
    if not author.strip():
        raise DecisionError("нужен автор решения")
    if decision == "rejected" and not comment.strip():
        raise DecisionError("при отклонении нужен комментарий: по нему агент поймёт, что не так")
    row = con.execute("SELECT status FROM issue WHERE id = %s FOR UPDATE", (issue_id,)).fetchone()
    if not row:
        raise DecisionError(f"задачи #{issue_id} нет")
    if row[0] != "proposed":
        con.rollback()
        raise DecisionError(f"решать можно только по задаче в статусе proposed, а у #{issue_id} — {row[0]}")
    run = last_run(con, issue_id)
    con.execute("""INSERT INTO agent_review(issue_id, agent_run_id, decision, author, comment)
                   VALUES (%s, %s, %s, %s, %s)""", (issue_id, run and run["run_id"], decision, author, comment))
    if decision == "approved":
        set_issue(con, issue_id, "approved")
        status = "approved"
    elif retry:
        set_issue(con, issue_id, "new", "agent")
        status = "new"
    else:
        set_issue(con, issue_id, "rejected", "human")
        status = "rejected"
    con.commit()
    return {"issue_id": issue_id, "decision": decision, "status": status, "author": author}


def rejected_proposals(con, issue_id: int) -> list[dict]:
    rows = con.execute("""SELECT v.comment, r.patch FROM agent_review v JOIN agent_run r ON r.id = v.agent_run_id
                          WHERE v.issue_id = %s AND v.decision = 'rejected' ORDER BY v.id""", (issue_id,)).fetchall()
    out = []
    for comment, patch in rows:
        prop = json.loads(patch or "null") or {}
        out.append({"comment": comment, "proposal": prop,
                    "summary": f"{prop.get('action')}: {prop.get('reason', '')}\n{proposal_diff(prop)}"[:1500]})
    return out


def _same_proposal(a: dict, b: dict) -> bool:
    norm = lambda p: (p.get("action"), [(e.get("file"), e.get("old"), e.get("new")) for e in p.get("edits", [])],
                      (p.get("known_exception") or {}).get("pattern"), p.get("to"))
    return bool(a and b) and norm(a) == norm(b)


def cmd_review(con, issue_id: int | None, status: str | None, source: str | None) -> None:
    items = list_items(con, None if issue_id else status, source, issue_id)
    if not items:
        print("Предложений нет" + (f" (статус {status})" if status and not issue_id else ""))
    for it in items:
        run = it["run"] or {}
        print("=" * 100)
        print(f"Задача #{it['issue_id']}  {it['source']} / {it['kind']} / {it['object_ref']}   статус: {it['status']}")
        print(f"Что упало: {it['details']}")
        print(f"Попытка agent_run #{run.get('run_id')}: {run.get('model')}, {run.get('action')} → {run.get('result')}, "
              f"токены {run.get('tokens_in') or 0}/{run.get('tokens_out') or 0}, {run.get('seconds')} с")
        print(f"\nОбоснование агента: {it['reason']}\n\nПравка:\n{it['diff']}\n\nОтчёт проверок:\n{it['report_text']}")
        for rv in it["reviews"]:
            print(f"\nРешение: {rv['decision']} — {rv['author']}, {rv['decided_at']:%Y-%m-%d %H:%M}: {rv['comment'] or ''}"
                  + (f" | применение: {rv['applied_result']} {rv['pr_url'] or ''}" if rv["applied_result"] else ""))


# =========================================================================== применение (задача №3)
def _git(*args, cwd: Path = HERE.parent, check: bool = True) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(p.stderr or p.stdout).strip()[:500]}")
    return p.stdout.strip()


def pr_link(branch: str, base: str, title: str, body: str) -> str:
    """PR через gh, если он установлен и авторизован; иначе — ссылка, по которой PR создаётся в один клик."""
    if shutil.which("gh"):
        p = subprocess.run(["gh", "pr", "create", "--head", branch, "--base", base, "--title", title, "--body", body],
                           cwd=HERE.parent, capture_output=True, text=True, encoding="utf-8")
        if p.returncode == 0 and "http" in p.stdout:
            return p.stdout.strip().splitlines()[-1]
    remote = _git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
    return f"https://github.com/{m.group(1)}/compare/{base}...{branch}?expand=1" if m else f"(создайте PR {branch} → {base})"


def ke_neighbors(con, issue: dict) -> list[str]:
    """Строки соседних дистанций того же старта: правило-исключение не должно их ловить."""
    code, _, race_ext = (issue["object_ref"] or "").partition("/")
    failed = issue["details_json"].get("failed", [])
    rows = con.execute("""SELECT r.external_id, r.name FROM race r JOIN competition c ON c.id = r.competition_id
                          WHERE c.source_id = %s AND c.code = %s AND r.external_id <> %s""",
                       (issue["source_id"], code, race_ext)).fetchall()
    return [f"{code}/{ext} {json.dumps({'name': name, 'failed': failed}, ensure_ascii=False)}" for ext, name in rows]


def write_eval_draft(issue: dict, proposal: dict, neighbors: list[str], pr_url: str | None) -> Path:
    """Заготовка кейса для стенда evals из закрытой задачи. Лежит в cases/drafts/ — run_evals её не запускает,
    пока человек не допишет синтетические данные и не перенесёт файл в cases/."""
    drafts = EVALS / "cases" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    f = drafts / f"issue_{issue['id']}.py"
    expected = "fix" if proposal["action"] == "patch" else proposal["action"]
    title = f"{issue['source']}: {issue['details_json'].get('name', issue['object_ref'])} — {proposal.get('reason', '')}"[:120]
    lines = [
        f'"""Заготовка кейса из задачи #{issue["id"]} очереди issue ({issue["source"]} / {issue["kind"]}).',
        f"Решение агента подтверждено человеком{'; PR: ' + pr_url if pr_url else ''}.",
        "ПЕРЕД ПЕРЕНОСОМ В cases/: заменить реальные данные синтетическими (fixtures_lib, выдуманные фамилии),",
        'дописать FIXTURES и check() по образцу соседних кейсов. Реальные ФИО сюда не кладём."""',
        "from protocol import Task", "",
        f"META = {{'id': 'I{issue['id']}', 'title': {title!r}, 'expected': {expected!r}}}",
        "ORACLE = " + pprint.pformat({k: v for k, v in proposal.items() if k in ("action", "reason", "edits",
                                                                                  "known_exception", "to")}, width=110),
    ]
    if proposal["action"] == "patch":
        mutations = [{"file": e["file"], "old": e["new"], "new": e["old"]} for e in proposal["edits"]]
        lines += ["# обратная правка: возвращает ошибку в код, чтобы агент её чинил",
                  "MUTATIONS = " + pprint.pformat(mutations, width=110),
                  "FIXTURES = {}  # TODO: синтетическая страница площадки (fixtures_lib.runc_page / grom_page)", "",
                  "def check(sb):", "    raise NotImplementedError('TODO: критерий «починено» по образцу cases/e20_runc_dnf.py')"]
    else:
        own = f"{issue['object_ref']} {json.dumps({k: issue['details_json'][k] for k in ('name', 'failed') if k in issue['details_json']}, ensure_ascii=False)}"
        lines += ["KE_MUST_MATCH = " + pprint.pformat([own], width=110),
                  "KE_MUST_NOT_MATCH = " + pprint.pformat(neighbors, width=110)]
    lines += ["", "", "def task() -> Task:",
              f"    return Task('I{issue['id']}', {issue['source']!r}, {issue['stage']!r}, {issue['kind']!r}, "
              f"{issue['object_ref']!r},", f"                {issue['details_json']!r}, [])", ""]
    f.write_text("\n".join(lines), encoding="utf-8")
    return f


def apply_approved(con, issue_id: int, push: bool = True) -> dict:
    """Применить подтверждённое предложение: patch → ветка и PR (рабочая папка не трогается),
    known_exception → правило. Затем перезапуск задачи на сохранённых ответах: resolved / known или снова new."""
    issue = load_issue(con, issue_id)
    if issue["status"] != "approved":
        raise DecisionError(f"применять можно только approved, а у #{issue_id} — {issue['status']}")
    run = last_run(con, issue_id)
    proposal = (run or {}).get("proposal") or {}
    review_id = con.execute("SELECT max(id) FROM agent_review WHERE issue_id = %s AND decision = 'approved'",
                            (issue_id,)).fetchone()[0]
    result, pr_url, status, detail = None, None, "new", ""

    if proposal.get("action") == "known_exception":
        ke = proposal["known_exception"]
        neighbors = ke_neighbors(con, issue)
        own = f"{issue['object_ref']} {issue['details'] or ''}"
        if not re.search(ke["pattern"], own):
            result, detail = "ke_not_matching", "правило не ловит свою задачу"
        elif caught := [n for n in neighbors if re.search(ke["pattern"], n)]:
            result, detail = "ke_too_broad", f"правило ловит соседние дистанции: {caught[:3]}"
        else:
            con.execute("""INSERT INTO known_exception(source, kind, pattern, reason, journal_ref)
                           VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                        (issue["source"], issue["kind"], ke["pattern"], ke.get("reason") or proposal.get("reason", ""),
                         f"issue-{issue_id}"))
            result, status = "known_exception_added", "known"
        draft = write_eval_draft(issue, proposal, neighbors, None) if status == "known" else None

    elif proposal.get("action") == "patch":
        sys.path.insert(0, str(EVALS))
        from protocol import apply_patch, validate
        if errs := validate(proposal):
            raise DecisionError("предложение не проходит проверяющий модуль: " + "; ".join(errs))
        base = _git("rev-parse", "--abbrev-ref", "HEAD")
        branch = f"agent/issue-{issue_id}-run-{run['run_id']}"
        wt = Path(tempfile.mkdtemp(prefix=f"wt_issue_{issue_id}_"))
        shutil.rmtree(wt)
        _git("worktree", "add", "-b", branch, str(wt), "HEAD")   # отдельная копия: рабочая папка не меняется
        try:
            errs = apply_patch(wt / "parser_running", proposal["edits"])
            if errs:
                raise DecisionError("правка не накладывается на текущий код: " + "; ".join(errs))
            # перезапуск на сохранённых ответах уже с правкой
            spec = build_sandbox(con, issue, code_dir=wt / "parser_running")
            baseline = run_child({"source": spec["source"], "comp": spec["comp"], "races": spec["races"]},
                                 Path(spec["sandbox"]))
            target = baseline.get(spec["target"], {})
            reg = baseline.get("_regression", {})
            others_bad = [e for e, r in baseline.items() if not e.startswith("_") and e != spec["target"] and not r.get("ok")]
            shutil.rmtree(spec["sandbox"], ignore_errors=True)
            detail = f"после правки: {_race_text(target) if target else baseline.get('_error', '?')}"
            if target.get("ok") and reg.get("ok"):
                title = f"Агент: {issue['source']} {issue['object_ref']} — {proposal.get('reason', '')}"[:120]
                body = (f"Предложение агента по задаче #{issue_id} очереди issue, подтверждено человеком.\n\n"
                        f"Обоснование: {proposal.get('reason', '')}\n\nПерезапуск на сохранённых ответах: {detail}\n"
                        f"Другие дистанции старта с проблемами после правки: {others_bad or 'нет'}\n"
                        f"Юнит-регрессия нормализации: {reg.get('msg')}\n\nagent_run #{run['run_id']}, {run.get('model')}")
                _git("add", "-A", cwd=wt)
                _git("-c", "user.name=" + default_author(), "commit", "-m", title + f"\n\nissue #{issue_id}, agent_run #{run['run_id']}",
                     cwd=wt)
                if push:
                    _git("push", "-u", "origin", branch, cwd=wt)
                    pr_url = pr_link(branch, base, title, body)
                else:
                    pr_url = f"(ветка {branch} создана локально, не запушена)"
                result, status = "pr_created" if push else "branch_created", "resolved"
            else:
                result = "rerun_failed"
        finally:
            _git("worktree", "remove", "--force", str(wt), check=False)
            if result not in ("pr_created", "branch_created"):
                _git("branch", "-D", branch, check=False)
        draft = write_eval_draft(issue, proposal, [], pr_url) if status == "resolved" else None
    else:
        raise DecisionError(f"нечего применять: действие {proposal.get('action')}")

    con.execute("""UPDATE agent_review SET applied_result = %s, pr_url = %s, applied_at = clock_timestamp()
                   WHERE id = %s""", (result, pr_url, review_id))
    con.execute("UPDATE issue SET status = %s, resolved_at = CASE WHEN %s IN ('resolved', 'known') THEN now() END, "
                "assignee = CASE WHEN %s = 'new' THEN 'agent' ELSE assignee END WHERE id = %s",
                (status, status, status, issue_id))
    con.commit()
    return {"issue_id": issue_id, "result": result, "status": status, "pr_url": pr_url, "detail": detail,
            "eval_draft": str(draft) if draft else None}


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
    p = sub.add_parser("review")
    p.add_argument("issue_id", type=int, nargs="?")
    p.add_argument("--status", default="proposed", help="proposed (по умолчанию), approved, rejected, resolved, …")
    p.add_argument("--source", help="площадка: runc, grom, russiarunning, …")
    p = sub.add_parser("decide")
    p.add_argument("issue_id", type=int)
    p.add_argument("decision", choices=["approve", "reject"])
    p.add_argument("--comment", default="")
    p.add_argument("--author", default=None)
    p.add_argument("--retry", action="store_true", help="при отклонении вернуть задачу агенту с комментарием")
    p = sub.add_parser("apply")
    p.add_argument("issue_id", type=int)
    p.add_argument("--no-push", action="store_true", help="только локальная ветка, без push и PR")
    args = ap.parse_args()

    import db
    con = db.connect()
    ensure_schema(con)
    if args.cmd == "list":
        cmd_list(con)
    elif args.cmd == "reproduce":
        cmd_reproduce(con, args.issue_id, args.keep)
    elif args.cmd == "process":
        sys.path.insert(0, str(EVALS))   # агенты импортируются как пакет evals/agents
        cmd_process(con, args.issue_id, args.agent, args.keep)
    elif args.cmd == "runs":
        cmd_runs(con, args.issue_id)
    elif args.cmd == "review":
        cmd_review(con, args.issue_id, args.status, args.source)
    else:
        try:
            if args.cmd == "decide":
                r = decide(con, args.issue_id, args.decision, args.author or default_author(), args.comment, args.retry)
                print(f"Задача #{r['issue_id']}: {r['decision']} ({r['author']}) → статус {r['status']}")
            else:
                r = apply_approved(con, args.issue_id, push=not args.no_push)
                print(f"Задача #{r['issue_id']}: {r['result']} → статус {r['status']}\n{r['detail']}")
                if r["pr_url"]:
                    print(f"PR: {r['pr_url']}")
                if r["eval_draft"]:
                    print(f"Заготовка кейса для стенда: {r['eval_draft']}")
        except DecisionError as ex:
            print(f"Не выполнено: {ex}")


if __name__ == "__main__":
    main()

"""Экран подтверждения правок агента (agent-spec §9 п. 6, SPEC §10.3).

Логику не дублирует: вызывает те же функции, что командная строка parser_running/agent_queue.py
(list_items, decide, apply_approved), поэтому результат решений одинаковый.
Данные — в PostgreSQL парсера (DATABASE_URL из .env), а не в SQLite сайта.

В составе сайта: /agent-review (роутер подключён в app/main.py).
Отдельно, без SQLite сайта:
    python -m uvicorn app.agent_review:standalone --port 8001     → http://127.0.0.1:8001/agent-review
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

PARSER_DIR = Path(__file__).resolve().parents[1] / "parser_running"
if str(PARSER_DIR) not in sys.path:
    sys.path.insert(0, str(PARSER_DIR))

import agent_queue as aq          # noqa: E402  (модули парсера: путь добавлен выше)
import db as parser_db            # noqa: E402

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
router = APIRouter(prefix="/agent-review", tags=["agent-review"])
STATUSES = ["proposed", "approved", "rejected", "resolved", "known", "new", "all"]


def _con():
    con = parser_db.connect()
    aq.ensure_schema(con)
    return con


class DecisionIn(BaseModel):
    decision: str            # approve | reject
    author: str
    comment: str = ""
    retry: bool = False


class ApplyIn(BaseModel):
    push: bool = False


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def review_page(request: Request, status: str = Query("proposed"), source: str | None = Query(None)):
    db_error = None
    try:
        con = _con()
    except (RuntimeError, Exception) as ex:
        return templates.TemplateResponse(request=request, name="agent_review.html", context={
            "items": [], "sources": [], "statuses": STATUSES, "status": status,
            "source": source or "", "default_author": "operator", "db_error": str(ex),
        }, status_code=503)
    try:
        items = aq.list_items(con, None if status == "all" else status, source or None)
        sources = aq.sources(con)
    finally:
        con.close()
    return templates.TemplateResponse(request=request, name="agent_review.html", context={
        "items": items, "sources": sources, "statuses": STATUSES, "status": status, "source": source or "",
        "default_author": aq.default_author()})


@router.get("/api/items")
def api_items(status: str = "proposed", source: str | None = None):
    try:
        con = _con()
    except (RuntimeError, Exception) as ex:
        raise HTTPException(503, str(ex)) from ex
    try:
        items = aq.list_items(con, None if status == "all" else status, source)
    finally:
        con.close()
    for it in items:   # даты — в строки для JSON
        for rv in it["reviews"]:
            rv["decided_at"] = str(rv["decided_at"])
    return items


@router.post("/api/{issue_id}/decide")
def api_decide(issue_id: int, body: DecisionIn):
    try:
        con = _con()
    except (RuntimeError, Exception) as ex:
        raise HTTPException(503, str(ex)) from ex
    try:
        return aq.decide(con, issue_id, body.decision, body.author, body.comment, body.retry)
    except aq.DecisionError as ex:
        raise HTTPException(400, str(ex)) from ex
    finally:
        con.close()


@router.post("/api/{issue_id}/reset")
def api_reset(issue_id: int):
    try:
        con = _con()
    except (RuntimeError, Exception) as ex:
        raise HTTPException(503, str(ex)) from ex
    try:
        con.execute("DELETE FROM agent_review WHERE issue_id = %s", (issue_id,))
        con.execute("UPDATE issue SET status = 'proposed', assignee = 'human' WHERE id = %s", (issue_id,))
        con.commit()
        return {"issue_id": issue_id, "status": "proposed"}
    finally:
        con.close()


@router.post("/api/reset-demo")
def api_reset_demo():
    try:
        con = _con()
    except (RuntimeError, Exception) as ex:
        raise HTTPException(503, str(ex)) from ex
    try:
        con.execute("DELETE FROM agent_review WHERE issue_id in (20, 28)")
        con.execute("UPDATE issue SET status = 'proposed', assignee = 'human' WHERE id in (20, 28)")
        con.commit()
        return {"status": "success", "reset_issues": [20, 28]}
    finally:
        con.close()



def _cleanup_issue_files(con, issue_id: int) -> list[str]:
    """Удаляет с диска сгенерированные скрипты парсера и тесты при удалении задачи."""
    row = con.execute("""
        SELECT s.name, i.object_ref 
        FROM issue i 
        LEFT JOIN source s ON s.id = i.source_id 
        WHERE i.id = %s
    """, (issue_id,)).fetchone()
    source_name = row[0] if row and row[0] else None

    files_to_remove = set()

    runs = con.execute("SELECT patch FROM agent_run WHERE issue_id = %s AND patch IS NOT NULL", (issue_id,)).fetchall()
    for r in runs:
        try:
            patch = json.loads(r[0]) if isinstance(r[0], str) else r[0]
            if isinstance(patch, dict) and "edits" in patch:
                for edit in patch["edits"]:
                    if "file" in edit:
                        files_to_remove.add(Path(edit["file"]).name)
        except Exception:
            pass

    if source_name:
        clean = source_name.split('.')[0].lower()
        files_to_remove.add(f"parser_{clean}.py")
        files_to_remove.add(f"test_{clean}_parser.py")

    project_root = Path(__file__).resolve().parents[1]
    search_dirs = [project_root, project_root / "parser_running"]

    deleted = []
    for fname in files_to_remove:
        for sdir in search_dirs:
            target = sdir / fname
            if target.is_file():
                try:
                    target.unlink()
                    deleted.append(str(target.name))
                except Exception:
                    pass
    return deleted


@router.delete("/api/{issue_id}")
def api_delete_issue(issue_id: int):
    try:
        con = _con()
    except (RuntimeError, Exception) as ex:
        raise HTTPException(503, str(ex)) from ex
    try:
        deleted = _cleanup_issue_files(con, issue_id)
        con.execute("DELETE FROM agent_review WHERE issue_id = %s", (issue_id,))
        con.execute("DELETE FROM agent_run WHERE issue_id = %s", (issue_id,))
        con.execute("DELETE FROM issue WHERE id = %s", (issue_id,))
        con.commit()
        return {"status": "deleted", "issue_id": issue_id, "deleted_files": deleted}
    finally:
        con.close()


@router.delete("/api/clear-all")
def api_clear_all():
    try:
        con = _con()
    except (RuntimeError, Exception) as ex:
        raise HTTPException(503, str(ex)) from ex
    try:
        all_ids = [r[0] for r in con.execute("SELECT id FROM issue").fetchall()]
        all_deleted = []
        for i_id in all_ids:
            all_deleted.extend(_cleanup_issue_files(con, i_id))
        con.execute("DELETE FROM agent_review;")
        con.execute("DELETE FROM agent_run;")
        con.execute("DELETE FROM issue;")
        con.commit()
        return {"status": "cleared", "deleted_files": all_deleted}
    finally:
        con.close()



@router.post("/api/{issue_id}/apply")
def api_apply(issue_id: int, body: ApplyIn):
    try:
        con = _con()
    except (RuntimeError, Exception) as ex:
        raise HTTPException(503, str(ex)) from ex
    try:
        return aq.apply_approved(con, issue_id, push=body.push)
    except aq.DecisionError as ex:
        raise HTTPException(400, str(ex)) from ex
    except (RuntimeError, Exception) as ex:      # ошибки git
        raise HTTPException(500, str(ex)) from ex
    finally:
        con.close()


# отдельный запуск без SQLite-базы сайта
standalone = FastAPI(title="Подтверждение правок агента")
standalone.include_router(router)
standalone.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")


@standalone.get("/", include_in_schema=False)
def _root():
    return RedirectResponse("/agent-review")

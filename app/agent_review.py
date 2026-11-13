"""Экран подтверждения правок агента (agent-spec §9 п. 6, SPEC §10.3).

Логику не дублирует: вызывает те же функции, что командная строка parser_running/agent_queue.py
(list_items, decide, apply_approved), поэтому результат решений одинаковый.
Данные — в PostgreSQL парсера (DATABASE_URL из .env), а не в SQLite сайта.

Здесь только JSON API (/api/agent-review/...), страницу рисует React (frontend/src/pages/AgentReviewPage.tsx).
В составе сайта: роутер подключён в app/main.py, страница — /agent-review.
Отдельно, без SQLite сайта (нужна сборка frontend/dist):
    python -m uvicorn app.agent_review:standalone --port 8001     → http://127.0.0.1:8001/agent-review
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

PARSER_DIR = Path(__file__).resolve().parents[1] / "parser_running"
if str(PARSER_DIR) not in sys.path:
    sys.path.insert(0, str(PARSER_DIR))

import agent_queue as aq          # noqa: E402  (модули парсера: путь добавлен выше)
import db as parser_db            # noqa: E402

router = APIRouter(prefix="/api/agent-review", tags=["agent-review"])
STATUSES = ["proposed", "approved", "rejected", "resolved", "known", "new", "all"]


CONNECT_TIMEOUT_S = 5


def _with_connect_timeout(url: str) -> str:
    """Без connect_timeout недоступная база держит запрос минуту и больше — экран «висит».
    Ограничиваем ожидание, чтобы страница быстро показала сообщение об ошибке."""
    if "connect_timeout=" in url:
        return url
    return f"{url}{'&' if '?' in url else '?'}connect_timeout={CONNECT_TIMEOUT_S}"


def _con():
    con = parser_db.connect(_with_connect_timeout(parser_db.database_url()))
    aq.ensure_schema(con)
    return con


class DecisionIn(BaseModel):
    decision: str            # approve | reject
    author: str
    comment: str = ""
    retry: bool = False


class ApplyIn(BaseModel):
    push: bool = False


@router.get("/page")
def api_page(status: str = Query("proposed"), source: str | None = Query(None)):
    """Всё для экрана проверки: задачи, фильтры и автор по умолчанию.
    Если база парсера недоступна — 200 с db_error, чтобы экран показал понятное сообщение."""
    base = {"statuses": STATUSES, "status": status, "source": source or ""}
    try:
        con = _con()
    except (RuntimeError, Exception) as ex:
        return {**base, "items": [], "sources": [], "default_author": "operator", "db_error": str(ex)}
    try:
        items = aq.list_items(con, None if status == "all" else status, source or None)
        sources = aq.sources(con)
    finally:
        con.close()
    return jsonable_encoder({**base, "items": items, "sources": sources,
                             "default_author": aq.default_author(), "db_error": None})


@router.get("/items")
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


@router.post("/{issue_id}/decide")
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


@router.post("/{issue_id}/reset")
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


@router.post("/reset-demo")
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


@router.delete("/clear-all")
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


@router.delete("/{issue_id}")
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


@router.post("/{issue_id}/apply")
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


@standalone.get("/", include_in_schema=False)
def _root():
    return RedirectResponse("/agent-review")


from app.frontend import mount_frontend  # noqa: E402

mount_frontend(standalone)

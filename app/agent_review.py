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
    con = _con()
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
    con = _con()
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
    con = _con()
    try:
        return aq.decide(con, issue_id, body.decision, body.author, body.comment, body.retry)
    except aq.DecisionError as ex:
        raise HTTPException(400, str(ex)) from ex
    finally:
        con.close()


@router.post("/api/{issue_id}/apply")
def api_apply(issue_id: int, body: ApplyIn):
    con = _con()
    try:
        return aq.apply_approved(con, issue_id, push=body.push)
    except aq.DecisionError as ex:
        raise HTTPException(400, str(ex)) from ex
    except RuntimeError as ex:      # ошибки git
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

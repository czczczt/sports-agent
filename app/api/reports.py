"""Роутер для заявок и обращений пользователей (SPEC v1.3 §3.2, §8.4).

Типы заявок (kind):
- not_me: «это не мой результат» (отвязка ошибочного старта)
- add_start: «добавьте мой старт» (ссылка на протокол)
- other_club: «я выступал за другой клуб» (привязка стартов)
- hide_me: «скрыть меня» (скрыть из рейтинга)
- link_me: «связать меня со спортсменом»
- data_error: «ошибка в данных»
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.db import AsyncPGConnection, get_db
from app.api.auth import get_current_user
from app.models import ReportCreateRequest, ReportOut, UserOut

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreateRequest,
    conn: AsyncPGConnection = Depends(get_db),
    current_user: UserOut = Depends(get_current_user),
):
    """Создаёт обращение / заявку пользователя."""
    valid_kinds = {"not_me", "add_start", "other_club", "hide_me", "link_me", "data_error"}
    if payload.kind not in valid_kinds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимый тип заявки: {payload.kind}. Допустимые: {', '.join(sorted(valid_kinds))}",
        )

    row = await conn.fetchrow(
        """
        INSERT INTO report (kind, user_id, athlete_id, result_id, event_id, url, message, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
        RETURNING id, kind, user_id, athlete_id, result_id, event_id, url, message, status, created_at
        """,
        payload.kind,
        None,  # user_id пока связывается по имени/токена
        payload.athlete_id,
        payload.result_id,
        payload.event_id,
        payload.url,
        payload.message,
    )

    return ReportOut(
        id=row["id"],
        kind=row["kind"],
        user_id=row["user_id"],
        athlete_id=row["athlete_id"],
        result_id=row["result_id"],
        event_id=row["event_id"],
        url=row["url"],
        message=row["message"],
        status=row["status"],
        created_at=str(row["created_at"]) if row["created_at"] else None,
    )


@router.get("", response_model=List[ReportOut])
async def list_reports(
    status_filter: Optional[str] = None,
    conn: AsyncPGConnection = Depends(get_db),
    current_user: UserOut = Depends(get_current_user),
):
    """Список заявок (для модератора и админа)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещён")

    if status_filter:
        rows = await conn.fetch(
            "SELECT id, kind, user_id, athlete_id, result_id, event_id, url, message, status, created_at FROM report WHERE status = ? ORDER BY id DESC",
            status_filter,
        )
    else:
        rows = await conn.fetch(
            "SELECT id, kind, user_id, athlete_id, result_id, event_id, url, message, status, created_at FROM report ORDER BY id DESC"
        )

    return [
        ReportOut(
            id=r["id"],
            kind=r["kind"],
            user_id=r["user_id"],
            athlete_id=r["athlete_id"],
            result_id=r["result_id"],
            event_id=r["event_id"],
            url=r["url"],
            message=r["message"],
            status=r["status"],
            created_at=str(r["created_at"]) if r["created_at"] else None,
        )
        for r in rows
    ]

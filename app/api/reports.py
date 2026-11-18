"""Роутер для заявок и обращений пользователей (SPEC v1.3 §3.2, §8.4).

Типы заявок (kind):
- not_me: «это не мой результат» (отвязка ошибочного старта)
- add_start: «добавьте мой старт» (ссылка на протокол)
- other_club: «я выступал за другой клуб» (привязка стартов)
- hide_me: «скрыть меня» (скрыть из рейтинга)
- link_me: «связать меня со спортсменом»
- data_error: «ошибка в данных»
- merge_profile: «объединить дубликаты профилей»
- other: «произвольный вопрос»
"""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.db import AsyncPGConnection, get_db
from app.api.auth import get_current_user, require_captain_or_admin
from app.models import ReportCreateRequest, ReportDecisionRequest, ReportOut, UserOut

router = APIRouter(prefix="/reports", tags=["reports"])


VALID_KINDS = {
    "not_me", "add_start", "other_club", "hide_me",
    "link_me", "data_error", "merge_profile", "other"
}


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreateRequest,
    conn: AsyncPGConnection = Depends(get_db),
    current_user: UserOut = Depends(get_current_user),
):
    """Создаёт обращение / заявку пользователя (SPEC v1.3 §8.4)."""
    if payload.kind not in VALID_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимый тип заявки: {payload.kind}. Допустимые: {', '.join(sorted(VALID_KINDS))}",
        )

    row = await conn.fetchrow(
        """
        INSERT INTO report (kind, user_id, athlete_id, result_id, event_id, url, message, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
        RETURNING id, kind, user_id, athlete_id, result_id, event_id, url, message, status, decided_by, decided_at, moderator_comment, created_at, updated_at
        """,
        payload.kind,
        current_user.id,
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
        decided_by=row["decided_by"],
        decided_at=str(row["decided_at"]) if row["decided_at"] else None,
        moderator_comment=row["moderator_comment"],
        created_at=str(row["created_at"]) if row["created_at"] else None,
        updated_at=str(row["updated_at"]) if row["updated_at"] else None,
    )


@router.get("", response_model=List[ReportOut])
async def list_reports(
    status_filter: Optional[str] = None,
    conn: AsyncPGConnection = Depends(get_db),
    current_user: UserOut = Depends(require_captain_or_admin),
):
    """
    Список всех заявок (только для капитанов и администраторов, SPEC v1.3 §8.4, §11).
    Поддерживает фильтр по статусу (new, accepted, rejected, etc.).
    """
    if status_filter:
        rows = await conn.fetch(
            """
            SELECT id, kind, user_id, athlete_id, result_id, event_id, url, message, 
                   status, decided_by, decided_at, moderator_comment, created_at, updated_at 
            FROM report 
            WHERE status = ? 
            ORDER BY id DESC
            """,
            status_filter,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, kind, user_id, athlete_id, result_id, event_id, url, message, 
                   status, decided_by, decided_at, moderator_comment, created_at, updated_at 
            FROM report 
            ORDER BY id DESC
            """
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
            decided_by=r["decided_by"],
            decided_at=str(r["decided_at"]) if r["decided_at"] else None,
            moderator_comment=r["moderator_comment"],
            created_at=str(r["created_at"]) if r["created_at"] else None,
            updated_at=str(r["updated_at"]) if r["updated_at"] else None,
        )
        for r in rows
    ]


@router.get("/my", response_model=List[ReportOut])
async def list_my_reports(
    conn: AsyncPGConnection = Depends(get_db),
    current_user: UserOut = Depends(get_current_user),
):
    """Список обращений текущего авторизованного пользователя."""
    rows = await conn.fetch(
        """
        SELECT id, kind, user_id, athlete_id, result_id, event_id, url, message, 
               status, decided_by, decided_at, moderator_comment, created_at, updated_at 
        FROM report 
        WHERE user_id = ? 
        ORDER BY id DESC
        """,
        current_user.id,
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
            decided_by=r["decided_by"],
            decided_at=str(r["decided_at"]) if r["decided_at"] else None,
            moderator_comment=r["moderator_comment"],
            created_at=str(r["created_at"]) if r["created_at"] else None,
            updated_at=str(r["updated_at"]) if r["updated_at"] else None,
        )
        for r in rows
    ]


@router.post("/{report_id}/decision", response_model=ReportOut)
async def decide_report(
    report_id: int,
    payload: ReportDecisionRequest,
    conn: AsyncPGConnection = Depends(get_db),
    current_user: UserOut = Depends(require_captain_or_admin),
):
    """
    Принятие решения по заявке модератором (админ или капитан, SPEC v1.3 §8.4, §11).
    Решения: accepted, resolved, rejected.
    """
    valid_decisions = {"accepted", "resolved", "rejected"}
    if payload.decision not in valid_decisions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимое решение: {payload.decision}. Допустимые: {', '.join(sorted(valid_decisions))}",
        )

    report_row = await conn.fetchrow("SELECT * FROM report WHERE id = ?", report_id)
    if not report_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

    # Обновление заявки
    updated_row = await conn.fetchrow(
        """
        UPDATE report
        SET status = ?,
            decided_by = ?,
            decided_at = NOW(),
            moderator_comment = ?,
            updated_at = NOW()
        WHERE id = ?
        RETURNING id, kind, user_id, athlete_id, result_id, event_id, url, message, 
                  status, decided_by, decided_at, moderator_comment, created_at, updated_at
        """,
        payload.decision,
        str(current_user.id),
        payload.moderator_comment,
        report_id,
    )

    # Применение сайд-эффектов заявки
    if payload.decision in ("accepted", "resolved"):
        # Если заявка «скрыть меня» — ставим спортсмену флаг is_hidden = TRUE (SPEC v1.3 §8.4)
        if report_row["kind"] == "hide_me" and report_row["athlete_id"]:
            await conn.execute(
                "UPDATE athlete SET is_hidden = TRUE WHERE id = ?",
                report_row["athlete_id"],
            )

    # Логирование в audit_log
    await conn.execute(
        """
        INSERT INTO audit_log (user_id, action, entity, entity_id, diff)
        VALUES (?, 'report_decision', 'report', ?, ?)
        """,
        current_user.id,
        report_id,
        json.dumps({
            "decision": payload.decision,
            "comment": payload.moderator_comment,
            "kind": report_row["kind"],
            "athlete_id": report_row["athlete_id"],
        }, ensure_ascii=False),
    )

    return ReportOut(
        id=updated_row["id"],
        kind=updated_row["kind"],
        user_id=updated_row["user_id"],
        athlete_id=updated_row["athlete_id"],
        result_id=updated_row["result_id"],
        event_id=updated_row["event_id"],
        url=updated_row["url"],
        message=updated_row["message"],
        status=updated_row["status"],
        decided_by=updated_row["decided_by"],
        decided_at=str(updated_row["decided_at"]) if updated_row["decided_at"] else None,
        moderator_comment=updated_row["moderator_comment"],
        created_at=str(updated_row["created_at"]) if updated_row["created_at"] else None,
        updated_at=str(updated_row["updated_at"]) if updated_row["updated_at"] else None,
    )

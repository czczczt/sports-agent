"""Роутер для заявок на доступ и модерации регистраций (SPEC v1.3 §3.1, §8.6, §11).

Капитаны и администраторы:
- Просматривают очередь заявок на доступ (статус 'pending').
- Видят автоматически подобранного кандидата-спортсмена по ФИО и дате/году рождения.
- Принимают решение: одобрить со связью/без связи со спортсменом либо отклонить.
"""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.db import AsyncPGConnection, get_db
from app.api.auth import require_captain_or_admin
from app.models import AccessRequestOut, AccessRequestDecision, UserOut
from app.services.athlete_service import normalize_term

router = APIRouter(prefix="/admin/access-requests", tags=["access-requests"])


@router.get("", response_model=List[AccessRequestOut])
async def list_access_requests(
    status_filter: Optional[str] = Query("pending", description="Статус заявки (pending, active, rejected)"),
    conn: AsyncPGConnection = Depends(get_db),
    current_user: UserOut = Depends(require_captain_or_admin),
):
    """
    Получить очередь заявок на доступ (SPEC v1.3 §8.6).
    Автоматически подбирает кандидата-спортсмена из таблицы athlete по ФИО и году/дате рождения.
    """
    if status_filter:
        rows = await conn.fetch(
            """
            SELECT id, username, email, role, status, first_name, last_name, middle_name,
                   birth_date, city, athlete_id, created_at
            FROM app_user
            WHERE status = ?
            ORDER BY id ASC
            """,
            status_filter,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, username, email, role, status, first_name, last_name, middle_name,
                   birth_date, city, athlete_id, created_at
            FROM app_user
            ORDER BY id ASC
            """
        )

    results = []
    for r in rows:
        cand_id = None
        cand_name = None

        if r["athlete_id"]:
            # Уже привязан
            ath = await conn.fetchrow("SELECT id, display_name FROM athlete WHERE id = ?", r["athlete_id"])
            if ath:
                cand_id = ath["id"]
                cand_name = ath["display_name"]
        elif r["last_name"] and r["first_name"]:
            # Поиск кандидата-спортсмена на лету
            norm_name = normalize_term(f"{r['last_name']} {r['first_name']}")
            pattern = f"%{norm_name}%"

            birth_year = r["birth_date"].year if r["birth_date"] else None
            if birth_year:
                cand_row = await conn.fetchrow(
                    """
                    SELECT id, display_name
                    FROM athlete
                    WHERE name_key LIKE ?
                      AND birth_year BETWEEN ? - 1 AND ? + 1
                    ORDER BY starts_count DESC
                    LIMIT 1
                    """,
                    pattern,
                    birth_year,
                    birth_year,
                )
            else:
                cand_row = await conn.fetchrow(
                    """
                    SELECT id, display_name
                    FROM athlete
                    WHERE name_key LIKE ?
                    ORDER BY starts_count DESC
                    LIMIT 1
                    """,
                    pattern,
                )

            if cand_row:
                cand_id = cand_row["id"]
                cand_name = cand_row["display_name"]

        results.append(
            AccessRequestOut(
                id=r["id"],
                username=r["username"],
                email=r["email"],
                role=r["role"],
                status=r["status"],
                first_name=r["first_name"],
                last_name=r["last_name"],
                middle_name=r["middle_name"],
                birth_date=str(r["birth_date"]) if r["birth_date"] else None,
                city=r["city"],
                athlete_id=r["athlete_id"],
                candidate_athlete_id=cand_id,
                candidate_athlete_name=cand_name,
                created_at=str(r["created_at"]) if r["created_at"] else None,
            )
        )

    return results


@router.post("/{user_id}/decision", response_model=AccessRequestOut)
async def decide_access_request(
    user_id: int,
    payload: AccessRequestDecision,
    conn: AsyncPGConnection = Depends(get_db),
    current_user: UserOut = Depends(require_captain_or_admin),
):
    """
    Решение по заявке на доступ (SPEC v1.3 §8.6):
    - approve (с привязкой к athlete_id или без неё) -> status = 'active'
    - reject -> status = 'rejected'
    Фиксация в audit_log.
    """
    if payload.decision not in ("approve", "reject"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Решение должно быть 'approve' или 'reject'",
        )

    target_user = await conn.fetchrow("SELECT * FROM app_user WHERE id = ?", user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    new_status = "active" if payload.decision == "approve" else "rejected"
    linked_athlete_id = payload.athlete_id if payload.decision == "approve" else None

    # Если одобрено со связкой со спортсменом, проверяем существование спортсмена
    if linked_athlete_id:
        ath = await conn.fetchrow("SELECT id, employee_status FROM athlete WHERE id = ?", linked_athlete_id)
        if not ath:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Указанный спортсмен не найден")
        # Если статус не confirmed, устанавливаем presumed
        if ath["employee_status"] != "confirmed":
            await conn.execute(
                "UPDATE athlete SET employee_status = 'presumed' WHERE id = ?",
                linked_athlete_id,
            )

    updated_user = await conn.fetchrow(
        """
        UPDATE app_user
        SET status = ?,
            athlete_id = COALESCE(?, athlete_id),
            approved_by = ?,
            approved_at = NOW(),
            updated_at = NOW()
        WHERE id = ?
        RETURNING id, username, email, role, status, first_name, last_name, middle_name,
                  birth_date, city, athlete_id, created_at
        """,
        new_status,
        linked_athlete_id,
        current_user.id,
        user_id,
    )

    # Запись в audit_log (SPEC v1.3 §5, §8.6)
    await conn.execute(
        """
        INSERT INTO audit_log (user_id, action, entity, entity_id, diff)
        VALUES (?, ?, 'app_user', ?, ?)
        """,
        current_user.id,
        f"{payload.decision}_access_request",
        user_id,
        json.dumps({
            "decision": payload.decision,
            "old_status": target_user["status"],
            "new_status": new_status,
            "athlete_id": linked_athlete_id,
            "comment": payload.comment,
        }, ensure_ascii=False),
    )

    return AccessRequestOut(
        id=updated_user["id"],
        username=updated_user["username"],
        email=updated_user["email"],
        role=updated_user["role"],
        status=updated_user["status"],
        first_name=updated_user["first_name"],
        last_name=updated_user["last_name"],
        middle_name=updated_user["middle_name"],
        birth_date=str(updated_user["birth_date"]) if updated_user["birth_date"] else None,
        city=updated_user["city"],
        athlete_id=updated_user["athlete_id"],
        candidate_athlete_id=linked_athlete_id,
        created_at=str(updated_user["created_at"]) if updated_user["created_at"] else None,
    )

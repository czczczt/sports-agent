"""Роутер для заявок на доступ и модерации регистраций (SPEC v1.3 §3.1, §8.6, §11).

Капитаны и администраторы:
- Просматривают очередь заявок на доступ (статус 'pending').
- Видят автоматически подобранного кандидата-спортсмена по ФИО и дате/году рождения.
- Принимают решение: одобрить со связью/без связи со спортсменом либо отклонить.
"""

import json

from fastapi import APIRouter, HTTPException, Query, status

from app.api.auth import CaptainOrAdminDep
from app.models import AccessRequestDecision, AccessRequestOut
from app.modules.access_requests.dependencies import AccessRequestsServiceDep

router = APIRouter(prefix="/admin/access-requests", tags=["access-requests"])


@router.get("", response_model=list[AccessRequestOut])
async def list_access_requests(
    current_user: CaptainOrAdminDep,
    conn: AccessRequestsServiceDep,
    status_filter: str | None = Query(
        "pending", description="Статус заявки (pending, active, rejected)"
    ),
):
    """
    Получить очередь заявок на доступ (SPEC v1.3 §8.6).
    Автоматически подбирает кандидата-спортсмена из таблицы athlete по ФИО и году/дате рождения.
    """
    if status_filter and status_filter != "all":
        rows = await conn.list_by_status(status_filter)
    else:
        rows = await conn.list_all()

    candidates = await conn.candidates(rows)
    results = []
    for r in rows:
        candidate = candidates.get(r["id"])
        cand_id = candidate["id"] if candidate else None
        cand_name = candidate["display_name"] if candidate else None

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
    current_user: CaptainOrAdminDep,
    conn: AccessRequestsServiceDep,
    user_id: int,
    payload: AccessRequestDecision,
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

    target_user = await conn.get_user(user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден"
        )

    new_status = "active" if payload.decision == "approve" else "rejected"
    linked_athlete_id = payload.athlete_id if payload.decision == "approve" else None

    # Если одобрено и запрошено создание нового спортсмена (SPEC v1.3 §8.6)
    if payload.decision == "approve" and payload.create_athlete and not linked_athlete_id:
        linked_athlete_id = await conn.create_athlete_from_user(target_user)
    elif linked_athlete_id:
        ath = await conn.get_athlete(linked_athlete_id)
        if not ath:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Указанный спортсмен не найден",
            )
        # Если статус не confirmed, устанавливаем presumed
        if ath["employee_status"] != "confirmed":
            await conn.mark_presumed(linked_athlete_id)

    updated_user = await conn.update_decision(
        new_status, linked_athlete_id, current_user.id, user_id
    )

    # Запись в audit_log (SPEC v1.3 §5, §8.6)
    await conn.audit_decision(
        current_user.id,
        f"{payload.decision}_access_request",
        user_id,
        json.dumps(
            {
                "decision": payload.decision,
                "old_status": target_user["status"],
                "new_status": new_status,
                "athlete_id": linked_athlete_id,
                "comment": payload.comment,
            },
            ensure_ascii=False,
        ),
    )

    await conn.commit()
    return AccessRequestOut(
        id=updated_user["id"],
        username=updated_user["username"],
        email=updated_user["email"],
        role=updated_user["role"],
        status=updated_user["status"],
        first_name=updated_user["first_name"],
        last_name=updated_user["last_name"],
        middle_name=updated_user["middle_name"],
        birth_date=str(updated_user["birth_date"])
        if updated_user["birth_date"]
        else None,
        city=updated_user["city"],
        athlete_id=updated_user["athlete_id"],
        candidate_athlete_id=linked_athlete_id,
        created_at=str(updated_user["created_at"])
        if updated_user["created_at"]
        else None,
    )

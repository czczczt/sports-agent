"""Роутер очереди «не проверен» для топ-N рейтинга (SPEC v1.3 §3.5, §5, §10.4).

Администраторы и капитаны:
- Просматривают спортсменов в топ-N (по умолчанию 10) каждого рейтинга (вид × пол),
  у которых статус сотрудника ещё не подтверждён (employee_status != 'confirmed').
- Принимают решение по каждому спортсмену:
  - 'confirmed' — статус подтверждён в «Пульсе»;
  - 'not_employee' — не сотрудник (спортсмен исключается из рейтинга, а любая
    связанная учётная запись автоматически блокируется).
- Все действия логируются в audit_log.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.api.auth import CaptainOrAdminDep
from app.core.postgres import SessionDep
from app.core.repository import ReadRepository
from app.models import (
    VerifyQueueDecision,
    VerifyQueueDecisionResponse,
    VerifyQueueItem,
)

router = APIRouter(prefix="/admin/verify-queue", tags=["verify-queue"])


class VerifyQueueRepository(ReadRepository):
    async def list_unverified_top(self, top_n: int = 10, sport: str | None = None) -> list[dict[str, Any]]:
        # Сначала проверяем, есть ли опубликованный рейтинг в rating_version
        sql = """
        WITH latest_period AS (
            SELECT period_start, period_end
            FROM running_athlete_rating
            WHERE formula_version = 'run-v1'
            ORDER BY period_end DESC
            LIMIT 1
        ),
        ranked_athletes AS (
            SELECT
                a.id AS athlete_id,
                a.display_name,
                a.first_name,
                a.last_name,
                a.middle_name,
                a.gender,
                a.birth_date,
                a.birth_year,
                a.employee_status,
                ar.points,
                ar.starts_count,
                'run' AS sport,
                ROW_NUMBER() OVER (
                    PARTITION BY a.gender
                    ORDER BY ar.points DESC, ar.best_points DESC, ar.starts_count DESC, a.id
                ) AS rank
            FROM running_athlete_rating ar
            JOIN latest_period lp ON lp.period_start = ar.period_start AND lp.period_end = ar.period_end
            JOIN athlete a ON a.id = ar.athlete_id
            WHERE ar.formula_version = 'run-v1'
              AND a.is_hidden = FALSE
              AND (a.employee_status IS NULL OR a.employee_status != 'not_employee')
        )
        SELECT
            ra.athlete_id,
            ra.display_name,
            ra.first_name,
            ra.last_name,
            ra.middle_name,
            ra.gender,
            ra.birth_date,
            ra.birth_year,
            ra.sport,
            ra.rank,
            ra.points,
            ra.starts_count,
            ra.employee_status,
            u.id AS linked_user_id,
            u.username AS linked_username,
            u.email AS linked_user_email
        FROM ranked_athletes ra
        LEFT JOIN app_user u ON u.athlete_id = ra.athlete_id
        WHERE ra.rank <= :top_n
          AND (ra.employee_status IS NULL OR ra.employee_status != 'confirmed')
        ORDER BY ra.sport, ra.gender, ra.rank;
        """
        rows = await self.rows(sql, {"top_n": top_n})
        if sport:
            rows = [r for r in rows if r["sport"] == sport]
        return rows

    async def get_athlete(self, athlete_id: int):
        return await self.row(
            "SELECT id, display_name, employee_status FROM athlete WHERE id = :athlete_id",
            {"athlete_id": athlete_id},
        )

    async def update_employee_status(self, athlete_id: int, new_status: str):
        await self.execute(
            """
            UPDATE athlete
            SET employee_status = :new_status
            WHERE id = :athlete_id
            """,
            {"athlete_id": athlete_id, "new_status": new_status},
        )

    async def get_linked_users(self, athlete_id: int):
        return await self.rows(
            "SELECT id, username, status FROM app_user WHERE athlete_id = :athlete_id",
            {"athlete_id": athlete_id},
        )

    async def block_user(self, user_id: int):
        await self.execute(
            "UPDATE app_user SET status = 'blocked', updated_at = NOW() WHERE id = :user_id",
            {"user_id": user_id},
        )

    async def log_audit(self, user_id: int, action: str, entity: str, entity_id: int, diff: dict):
        await self.execute(
            """
            INSERT INTO audit_log (user_id, action, entity, entity_id, diff, created_at)
            VALUES (:user_id, :action, :entity, :entity_id, CAST(:diff AS jsonb), NOW())
            """,
            {"user_id": user_id, "action": action, "entity": entity, "entity_id": entity_id, "diff": json.dumps(diff)},
        )


@router.get("", response_model=list[VerifyQueueItem])
async def get_verify_queue(
    current_user: CaptainOrAdminDep,
    session: SessionDep,
    top_n: int = Query(10, ge=1, le=100, description="Глубина топа по каждому полу (SPEC §3.5)"),
    sport: str | None = Query(None, description="Фильтр по виду спорта"),
):
    """Возвращает список неподтверждённых спортсменов (presumed) из топ-N каждого рейтинга (SPEC §3.5, §10.4)."""
    repo = VerifyQueueRepository(session)

    # Капитан может просматривать очередь только по своим видам спорта
    if current_user.role == "captain" and current_user.captain_sports:
        if sport and sport not in current_user.captain_sports:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"У вас нет прав на просмотр очереди по виду спорта '{sport}'",
            )
        if not sport:
            sport = list(current_user.captain_sports)[0]

    rows = await repo.list_unverified_top(top_n=top_n, sport=sport)

    results: list[VerifyQueueItem] = []
    for r in rows:
        results.append(
            VerifyQueueItem(
                athlete_id=r["athlete_id"],
                display_name=r["display_name"],
                first_name=r["first_name"],
                last_name=r["last_name"],
                middle_name=r["middle_name"],
                gender=r["gender"],
                birth_date=str(r["birth_date"]) if r["birth_date"] else None,
                birth_year=r["birth_year"],
                sport=r["sport"],
                rank=r["rank"],
                points=float(r["points"]),
                starts_count=r["starts_count"] or 0,
                employee_status=r["employee_status"] or "presumed",
                linked_user_id=r["linked_user_id"],
                linked_username=r["linked_username"],
                linked_user_email=r["linked_user_email"],
            )
        )
    return results


@router.post("/{athlete_id}/decision", response_model=VerifyQueueDecisionResponse)
async def decide_verify_queue_item(
    athlete_id: int,
    decision: VerifyQueueDecision,
    current_user: CaptainOrAdminDep,
    session: SessionDep,
):
    """Принимает решение по спортсмену в очереди проверки: 'confirmed' или 'not_employee' (SPEC §3.5, §5, §10.4)."""
    repo = VerifyQueueRepository(session)

    athlete = await repo.get_athlete(athlete_id)
    if not athlete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Спортсмен не найден")

    old_status = athlete["employee_status"] or "presumed"
    new_status = decision.status
    moderator_name = current_user.username

    # Обновляем статус спортсмена
    await repo.update_employee_status(athlete_id, new_status)

    # Аудит решения по спортсмену
    audit_diff = {
        "old_status": old_status,
        "new_status": new_status,
        "moderator": moderator_name,
        "comment": decision.comment,
    }
    await repo.log_audit(
        user_id=current_user.id,
        action="verify_employee_status",
        entity="athlete",
        entity_id=athlete_id,
        diff=audit_diff,
    )

    auto_blocked = False
    # При not_employee автоматически блокируем связанную учётную запись (SPEC §5, §8.7)
    if new_status == "not_employee":
        linked_users = await repo.get_linked_users(athlete_id)
        for u in linked_users:
            if u["status"] != "blocked":
                await repo.block_user(u["id"])
                auto_blocked = True
                await repo.log_audit(
                    user_id=current_user.id,
                    action="auto_block_not_employee",
                    entity="app_user",
                    entity_id=u["id"],
                    diff={"reason": "athlete_marked_not_employee", "athlete_id": athlete_id},
                )

    await session.commit()

    action_text = "подтверждён как сотрудник" if new_status == "confirmed" else "отмечен как не сотрудник"
    return VerifyQueueDecisionResponse(
        success=True,
        athlete_id=athlete_id,
        new_status=new_status,
        auto_blocked_user=auto_blocked,
        message=f"Спортсмен #{athlete_id} {action_text}",
    )

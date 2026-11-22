"""Роутер для управления пользователями, ролями и видами спорта капитанов (SPEC v1.3 §2, §3.5, §5).

Капитану изменение ролей и пользователей ЗАПРЕЩЕНО (403 Forbidden).
Только администратор (AdminDep) может просматривать и менять роли.
Все действия логируются в audit_log.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.api.auth import AdminDep
from app.core.postgres import SessionDep
from app.core.repository import ReadRepository
from app.models import AdminUserOut, AdminUserUpdate

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


class AdminUsersRepository(ReadRepository):
    async def list_users(
        self, role: str | None = None, status_filter: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        clauses = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if role:
            clauses.append("u.role = :role")
            params["role"] = role
        if status_filter:
            clauses.append("u.status = :status_filter")
            params["status_filter"] = status_filter

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT u.id, u.username, u.email, u.role, u.status, u.display_name,
                   u.athlete_id, u.created_at
            FROM app_user u
            {where_str}
            ORDER BY u.id ASC
            LIMIT :limit OFFSET :offset
        """
        rows = await self.rows(sql, params)
        result = []
        for r in rows:
            sports = await self.get_captain_sports(r["id"])
            item = dict(r)
            item["captain_sports"] = sports
            item["created_at"] = str(r["created_at"]) if r["created_at"] else None
            result.append(item)
        return result

    async def get_user_detail(self, user_id: int) -> dict[str, Any] | None:
        row = await self.row(
            """
            SELECT u.id, u.username, u.email, u.role, u.status, u.display_name,
                   u.athlete_id, u.created_at
            FROM app_user u
            WHERE u.id = :user_id
            """,
            {"user_id": user_id},
        )
        if not row:
            return None
        res = dict(row)
        res["captain_sports"] = await self.get_captain_sports(user_id)
        res["created_at"] = str(row["created_at"]) if row["created_at"] else None
        return res

    async def get_captain_sports(self, user_id: int) -> list[str]:
        rows = await self.rows(
            "SELECT sport FROM captain_sport WHERE user_id = :user_id ORDER BY sport",
            {"user_id": user_id},
        )
        return [r["sport"] for r in rows if r["sport"]]

    async def set_captain_sports(self, user_id: int, sports: list[str]) -> None:
        await self.execute("DELETE FROM captain_sport WHERE user_id = :user_id", {"user_id": user_id})
        for sport in sports:
            norm_sport = sport.strip().lower()
            if norm_sport:
                await self.execute(
                    "INSERT INTO captain_sport (user_id, sport) VALUES (:user_id, :sport) ON CONFLICT DO NOTHING",
                    {"user_id": user_id, "sport": norm_sport},
                )

    async def update_user(self, user_id: int, updates: dict[str, Any]) -> None:
        set_clauses = []
        params: dict[str, Any] = {"user_id": user_id}
        for k, v in updates.items():
            set_clauses.append(f"{k} = :{k}")
            params[k] = v

        if set_clauses:
            sql = f"UPDATE app_user SET {', '.join(set_clauses)} WHERE id = :user_id"
            await self.execute(sql, params)

    async def log_audit(
        self,
        user_id: int | None,
        action: str,
        entity: str,
        entity_id: int | None = None,
        diff: dict | None = None,
    ) -> None:
        await self.execute(
            """
            INSERT INTO audit_log (user_id, action, entity, entity_id, diff, created_at)
            VALUES (:user_id, :action, :entity, :entity_id, CAST(:diff AS jsonb), NOW())
            """,
            {
                "user_id": user_id,
                "action": action,
                "entity": entity,
                "entity_id": entity_id,
                "diff": json.dumps(diff or {}),
            },
        )


@router.get("", response_model=list[AdminUserOut])
async def list_admin_users(
    current_user: AdminDep,
    session: SessionDep,
    role: str | None = Query(None, description="Фильтр по роли"),
    status_filter: str | None = Query(None, alias="status", description="Фильтр по статусу"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Список пользователей и их ролей. Доступно только администратору (SPEC v1.3 §2)."""
    repo = AdminUsersRepository(session)
    users = await repo.list_users(role=role, status_filter=status_filter, limit=limit, offset=offset)
    return [AdminUserOut(**u) for u in users]


@router.get("/{user_id}", response_model=AdminUserOut)
async def get_admin_user(
    user_id: int,
    current_user: AdminDep,
    session: SessionDep,
):
    """Карточка пользователя с ролями и видами спорта капитана (SPEC v1.3 §2)."""
    repo = AdminUsersRepository(session)
    user = await repo.get_user_detail(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return AdminUserOut(**user)


@router.patch("/{user_id}", response_model=AdminUserOut)
async def update_admin_user(
    user_id: int,
    data: AdminUserUpdate,
    current_user: AdminDep,
    session: SessionDep,
):
    """Назначение ролей и видов спорта капитана. Доступно только администратору (SPEC v1.3 §2, §3.5)."""
    repo = AdminUsersRepository(session)
    existing = await repo.get_user_detail(user_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    raw_data = data.model_dump(exclude_unset=True)
    updates: dict[str, Any] = {}

    if "role" in raw_data:
        updates["role"] = raw_data["role"]
    if "status" in raw_data:
        updates["status"] = raw_data["status"]
    if "display_name" in raw_data:
        updates["display_name"] = raw_data["display_name"]
    if "athlete_id" in raw_data:
        updates["athlete_id"] = raw_data["athlete_id"]

    if updates:
        await repo.update_user(user_id, updates)

    if "captain_sports" in raw_data and raw_data["captain_sports"] is not None:
        await repo.set_captain_sports(user_id, raw_data["captain_sports"])

    await repo.log_audit(
        user_id=current_user.id,
        action="update_user_roles",
        entity="app_user",
        entity_id=user_id,
        diff={
            "updates": raw_data,
            "old": {
                "role": existing["role"],
                "status": existing["status"],
                "captain_sports": existing["captain_sports"],
            },
            "admin": current_user.username,
        },
    )
    await session.commit()

    updated = await repo.get_user_detail(user_id)
    return AdminUserOut(**updated)

"""Роутер для управления источниками данных (SPEC v1.3 §2, §5, §12).

Капитану изменение источников ЗАПРЕЩЕНО (403 Forbidden).
Только администратор (AdminDep) может настраивать источники.
Все действия логируются в audit_log.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.api.auth import AdminDep
from app.core.postgres import SessionDep
from app.core.repository import ReadRepository
from app.models import AdminSourceOut, AdminSourceUpdate

router = APIRouter(prefix="/admin/sources", tags=["admin-sources"])


class AdminSourcesRepository(ReadRepository):
    async def list_sources(self) -> list[dict[str, Any]]:
        rows = await self.rows(
            """
            SELECT id, name, base_url, platform, enabled, priority, sport_types
            FROM source
            ORDER BY priority ASC, id ASC
            """
        )
        return [dict(r) for r in rows]

    async def get_source(self, source_id: int) -> dict[str, Any] | None:
        row = await self.row(
            """
            SELECT id, name, base_url, platform, enabled, priority, sport_types
            FROM source
            WHERE id = :source_id
            """,
            {"source_id": source_id},
        )
        return dict(row) if row else None

    async def update_source(self, source_id: int, updates: dict[str, Any]) -> None:
        set_clauses = []
        params: dict[str, Any] = {"source_id": source_id}
        for k, v in updates.items():
            set_clauses.append(f"{k} = :{k}")
            params[k] = v

        if set_clauses:
            sql = f"UPDATE source SET {', '.join(set_clauses)} WHERE id = :source_id"
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


@router.get("", response_model=list[AdminSourceOut])
async def list_admin_sources(
    current_user: AdminDep,
    session: SessionDep,
):
    """Список источников данных. Доступно только администратору (SPEC v1.3 §2, §5)."""
    repo = AdminSourcesRepository(session)
    return [AdminSourceOut(**s) for s in await repo.list_sources()]


@router.patch("/{source_id}", response_model=AdminSourceOut)
async def update_admin_source(
    source_id: int,
    data: AdminSourceUpdate,
    current_user: AdminDep,
    session: SessionDep,
):
    """Управление источником данных. Доступно только администратору (SPEC v1.3 §2, §5)."""
    repo = AdminSourcesRepository(session)
    existing = await repo.get_source(source_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Источник не найден")

    raw_data = data.model_dump(exclude_unset=True)
    if raw_data:
        await repo.update_source(source_id, raw_data)

    await repo.log_audit(
        user_id=current_user.id,
        action="update_source",
        entity="source",
        entity_id=source_id,
        diff={"updates": raw_data, "old": existing, "admin": current_user.username},
    )
    await session.commit()

    updated = await repo.get_source(source_id)
    return AdminSourceOut(**updated)

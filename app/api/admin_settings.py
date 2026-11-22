"""Роутер для системных настроек (SPEC v1.3 §2, §5, §11).

Капитану изменение настроек ЗАПРЕЩЕНО (403 Forbidden).
Только администратор (AdminDep) может управлять настройками.
Все действия логируются в audit_log.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter

from app.api.auth import AdminDep
from app.core.postgres import SessionDep
from app.core.repository import ReadRepository
from app.models import AdminSettingItem, AdminSettingUpdate

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


DEFAULT_SETTINGS = {
    "top_n_verify": 10,
    "match_threshold": 0.90,
    "raw_ttl_days": 90,
    "match_window_days": 30,
    "rating_period": "rolling_365",
}


class AdminSettingsRepository(ReadRepository):
    async def get_all_settings(self) -> list[dict[str, Any]]:
        rows = await self.rows("SELECT key, value, updated_at, updated_by FROM setting ORDER BY key")
        existing_keys = {r["key"] for r in rows}
        results = []
        for r in rows:
            results.append({
                "key": r["key"],
                "value": r["value"],
                "updated_at": str(r["updated_at"]) if r["updated_at"] else None,
                "updated_by": r["updated_by"],
            })
        # Добавляем дефолтные, если их ещё нет в БД
        for k, v in DEFAULT_SETTINGS.items():
            if k not in existing_keys:
                results.append({"key": k, "value": v, "updated_at": None, "updated_by": None})
        return results

    async def upsert_setting(self, key: str, value: Any, user_id: int) -> dict[str, Any]:
        val_json = json.dumps(value)
        row = await self.row(
            """
            INSERT INTO setting (key, value, updated_at, updated_by)
            VALUES (:key, CAST(:value AS jsonb), NOW(), :user_id)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = NOW(), updated_by = EXCLUDED.updated_by
            RETURNING key, value, updated_at, updated_by
            """,
            {"key": key, "value": val_json, "user_id": user_id},
        )
        return {
            "key": row["key"],
            "value": row["value"],
            "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
            "updated_by": row["updated_by"],
        }

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


@router.get("", response_model=list[AdminSettingItem])
async def list_admin_settings(
    current_user: AdminDep,
    session: SessionDep,
):
    """Список настроек системы. Доступно только администратору (SPEC v1.3 §2, §5)."""
    repo = AdminSettingsRepository(session)
    return [AdminSettingItem(**s) for s in await repo.get_all_settings()]


@router.patch("", response_model=AdminSettingItem)
async def update_admin_setting(
    data: AdminSettingUpdate,
    current_user: AdminDep,
    session: SessionDep,
):
    """Обновление настройки системы. Доступно только администратору (SPEC v1.3 §2, §5)."""
    repo = AdminSettingsRepository(session)
    res = await repo.upsert_setting(data.key, data.value, current_user.id)

    await repo.log_audit(
        user_id=current_user.id,
        action="update_setting",
        entity="setting",
        entity_id=None,
        diff={"key": data.key, "new_value": data.value, "admin": current_user.username},
    )
    await session.commit()
    return AdminSettingItem(**res)

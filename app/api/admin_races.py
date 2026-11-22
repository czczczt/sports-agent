"""Роутер для управления стартами, дистанциями и протоколами (SPEC v1.3 §2, §3.2, §3.5, §5, §8.5).

Капитан может:
- Менять класс дистанции, D+ (набор высоты), RL-статус старта (марафон RL), вид спорта и статус ЧМ/Кона ТОЛЬКО по своим видам спорта (иначе 403).
- Грузить протоколы вручную ТОЛЬКО по своим видам спорта (иначе 403).
- Капитану ЗАПРЕЩЕНО удалять протоколы (403 Forbidden).

Администратор может всё без ограничений по видам спорта, включая удаление протоколов.
Все действия логируются в audit_log.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.api.auth import AdminDep, CaptainOrAdminDep, check_captain_sport_scope
from app.core.postgres import SessionDep
from app.core.repository import ReadRepository
from app.models import (
    AdminRaceDetail,
    AdminRaceUpdate,
    DeleteProtocolResponse,
    ManualProtocolUploadRequest,
    ManualProtocolUploadResponse,
)

router = APIRouter(prefix="/admin/races", tags=["admin-races"])


class AdminRacesRepository(ReadRepository):
    async def get_race_with_sport(self, race_id: int) -> dict[str, Any] | None:
        return await self.row(
            """
            SELECT r.*, COALESCE(r.sport, c.sport_type, 'run') AS effective_sport
            FROM race r
            LEFT JOIN competition c ON c.id = r.competition_id
            WHERE r.id = :race_id
            """,
            {"race_id": race_id},
        )

    async def update_race(self, race_id: int, updates: dict[str, Any]) -> None:
        set_clauses = []
        params: dict[str, Any] = {"race_id": race_id}
        for k, v in updates.items():
            set_clauses.append(f"{k} = :{k}")
            params[k] = v

        if not set_clauses:
            return

        sql = f"UPDATE race SET {', '.join(set_clauses)} WHERE id = :race_id"
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

    async def insert_manual_result(self, race_id: int, row_data: dict[str, Any]) -> int:
        res = await self.row(
            """
            INSERT INTO result (
                race_id, bib, full_name_raw, gender, birth_year, birth_date,
                club_raw, status, position, position_gender, chip_time_s, gun_time_s
            )
            VALUES (
                :race_id, :bib, :full_name_raw, :gender, :birth_year, :birth_date,
                :club_raw, :status, :place_abs, :place_gender, :chip_time_s, :gun_time_s
            )
            RETURNING id
            """,
            {
                "race_id": race_id,
                "bib": row_data.get("bib"),
                "full_name_raw": row_data.get("full_name_raw"),
                "gender": row_data.get("gender"),
                "birth_year": row_data.get("birth_year"),
                "birth_date": row_data.get("birth_date"),
                "club_raw": row_data.get("club_raw"),
                "status": row_data.get("status") or "FIN",
                "place_abs": row_data.get("place_abs"),
                "place_gender": row_data.get("place_gender"),
                "chip_time_s": row_data.get("chip_time_s"),
                "gun_time_s": row_data.get("gun_time_s"),
            },
        )
        return res["id"]

    async def delete_race_results(self, race_id: int) -> int:
        deleted = await self.scalar(
            """
            WITH deleted AS (
                DELETE FROM result WHERE race_id = :race_id RETURNING id
            )
            SELECT COUNT(*) FROM deleted
            """,
            {"race_id": race_id},
        )
        return deleted or 0


@router.patch("/{race_id}", response_model=AdminRaceDetail)
async def update_admin_race(
    race_id: int,
    data: AdminRaceUpdate,
    current_user: CaptainOrAdminDep,
    session: SessionDep,
):
    """Капитан или администратор правит класс, D+, RL-статус дистанции (SPEC v1.3 §2, §3.2, §8.5).

    Капитан может править только дистанции своего вида спорта (иначе 403).
    """
    repo = AdminRacesRepository(session)
    race = await repo.get_race_with_sport(race_id)
    if not race:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Дистанция не найдена"
        )

    effective_sport = race["effective_sport"]

    # Проверка скоупа капитана по видам спорта
    check_captain_sport_scope(
        current_user, effective_sport, "редактирование дистанции"
    )

    updates: dict[str, Any] = {}
    raw_data = data.model_dump(exclude_unset=True)

    if "scoring_class" in raw_data:
        updates["scoring_class"] = raw_data["scoring_class"]
        # Синхронизируем с distance_class_override
        updates["distance_class_override"] = raw_data["scoring_class"]

    if "distance_class_override" in raw_data:
        updates["distance_class_override"] = raw_data["distance_class_override"]
        if "scoring_class" not in raw_data:
            updates["scoring_class"] = raw_data["distance_class_override"]

    if "elevation_gain_m" in raw_data:
        updates["elevation_gain_m"] = raw_data["elevation_gain_m"]

    if "is_rl_series" in raw_data:
        updates["is_rl_series"] = raw_data["is_rl_series"]

    if "sport" in raw_data:
        new_sport = raw_data["sport"]
        check_captain_sport_scope(current_user, new_sport, "смена вида спорта")
        updates["sport"] = new_sport

    if "special" in raw_data:
        updates["special"] = raw_data["special"]

    if updates:
        await repo.update_race(race_id, updates)

    await repo.log_audit(
        user_id=current_user.id,
        action="update_race",
        entity="race",
        entity_id=race_id,
        diff={
            "updates": raw_data,
            "old": {
                "scoring_class": race.get("scoring_class"),
                "elevation_gain_m": race.get("elevation_gain_m"),
                "is_rl_series": race.get("is_rl_series"),
                "sport": effective_sport,
                "special": race.get("special"),
            },
        },
    )
    await session.commit()

    updated = await repo.get_race_with_sport(race_id)
    return AdminRaceDetail(
        id=updated["id"],
        competition_id=updated["competition_id"],
        name=updated.get("name"),
        sport=updated.get("sport") or updated.get("effective_sport"),
        scoring_class=updated.get("scoring_class")
        or updated.get("distance_class_override"),
        distance_class_override=updated.get("distance_class_override"),
        distance_m=updated.get("distance_m"),
        distance_km_raw=updated.get("distance_km_raw"),
        elevation_gain_m=updated.get("elevation_gain_m"),
        is_rl_series=bool(updated.get("is_rl_series")),
        special=updated.get("special") or "regular",
        total_count=updated.get("total_count") or 0,
    )


@router.post("/{race_id}/manual-upload", response_model=ManualProtocolUploadResponse)
async def manual_upload_protocol(
    race_id: int,
    data: ManualProtocolUploadRequest,
    current_user: CaptainOrAdminDep,
    session: SessionDep,
):
    """Ручная загрузка результатов протокола (SPEC v1.3 §2, §3.2, §3.5).

    Капитан может загружать результаты только для своего вида спорта (иначе 403).
    """
    repo = AdminRacesRepository(session)
    race = await repo.get_race_with_sport(race_id)
    if not race:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Дистанция не найдена"
        )

    effective_sport = race["effective_sport"]
    check_captain_sport_scope(
        current_user, effective_sport, "ручная загрузка протокола"
    )

    imported_count = 0
    for row in data.rows:
        await repo.insert_manual_result(race_id, row.model_dump())
        imported_count += 1

    # Обновляем total_count у race
    await repo.execute(
        "UPDATE race SET total_count = COALESCE(total_count, 0) + :added WHERE id = :race_id",
        {"added": imported_count, "race_id": race_id},
    )

    await repo.log_audit(
        user_id=current_user.id,
        action="manual_protocol_upload",
        entity="race",
        entity_id=race_id,
        diff={
            "imported_count": imported_count,
            "sport": effective_sport,
            "moderator": current_user.username,
        },
    )
    await session.commit()

    return ManualProtocolUploadResponse(
        success=True,
        race_id=race_id,
        imported_count=imported_count,
        message=f"Успешно импортировано {imported_count} строк протокола",
    )


@router.delete("/{race_id}/protocol", response_model=DeleteProtocolResponse)
async def delete_race_protocol(
    race_id: int,
    current_user: AdminDep,
    session: SessionDep,
):
    """Удаление протокола дистанции (SPEC v1.3 §2, §3.5).

    Капитану удаление протокола ЗАПРЕЩЕНО (403 Forbidden). Доступно только администратору.
    """
    repo = AdminRacesRepository(session)
    race = await repo.get_race_with_sport(race_id)
    if not race:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Дистанция не найдена"
        )

    deleted_count = await repo.delete_race_results(race_id)
    await repo.execute(
        "UPDATE race SET total_count = 0 WHERE id = :race_id",
        {"race_id": race_id},
    )

    await repo.log_audit(
        user_id=current_user.id,
        action="delete_protocol",
        entity="race",
        entity_id=race_id,
        diff={"deleted_count": deleted_count, "admin": current_user.username},
    )
    await session.commit()

    return DeleteProtocolResponse(
        success=True,
        race_id=race_id,
        deleted_count=deleted_count,
        message=f"Протокол успешно удалён ({deleted_count} результатов)",
    )

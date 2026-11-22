"""Роутер для управления сериями и планируемыми стартами (SPEC v1.3 §3.4, §3.5, §5, §8)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.api.auth import CaptainOrAdminDep, check_captain_sport_scope
from app.core.postgres import SessionDep
from app.core.repository import ReadRepository
from app.models import (
    EventDuplicateCandidate,
    EventItem,
    EventMergeRequest,
    EventSeriesAttachRequest,
    PlannedEventCreate,
    RaceItem,
    SeriesSuggestItem,
)

router = APIRouter(prefix="/admin/events", tags=["admin-events"])


def _normalize_title(text: str) -> str:
    cleaned = re.sub(r"\b20\d\d\b", "", text)
    cleaned = re.sub(r"(?i)\b(марафон|полумарафон|забег|лыжня|трейл|триатлон|спринт)\b", "", cleaned)
    words = re.findall(r"\w+", cleaned.lower().replace("ё", "е"))
    return " ".join(words)


class AdminEventsRepo(ReadRepository):
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
                "diff": json.dumps(diff, ensure_ascii=False) if diff else None,
            },
        )


@router.post("/planned", response_model=EventItem)
async def create_planned_event(
    body: PlannedEventCreate,
    user: CaptainOrAdminDep,
    session: SessionDep,
):
    """Создаёт запланированный старт капитаном или администратором (SPEC v1.3 §3.4, §8)."""
    check_captain_sport_scope(user, body.sport)
    repo = AdminEventsRepo(session)

    # 1. Создание старта
    d_start = (
        date.fromisoformat(str(body.planned_date_start))
        if isinstance(body.planned_date_start, str)
        else body.planned_date_start
    )
    d_finish = (
        date.fromisoformat(str(body.planned_date_end))
        if isinstance(body.planned_date_end, str) and body.planned_date_end
        else d_start
    )
    ext_id = f"planned_{uuid.uuid4().hex[:12]}"

    event_row = await repo.row(
        """
        INSERT INTO competition (
            source_id, external_id, name, date_begin, date_end, location, address,
            sport_type, status, sport, planned_date_start, planned_date_end, planned_note,
            created_by, series_id
        ) VALUES (
            1, :ext_id, :name, :d_begin, :d_end, :city, :address,
            :sport, 'planned', :sport, :p_start, :p_end, :note,
            :user_id, :series_id
        ) RETURNING id, source_id, name AS title, date_begin, date_end, location AS place, address, status, sport, series_id
        """,
        {
            "ext_id": ext_id,
            "name": body.title,
            "d_begin": d_start,
            "d_end": d_finish,
            "city": body.city,
            "address": body.address,
            "sport": body.sport,
            "p_start": d_start,
            "p_end": d_finish,
            "note": body.planned_note,
            "user_id": user.id,
            "series_id": body.series_id,
        },
    )
    event_id = event_row["id"]

    # 2. Создание запланированных дистанций
    races: list[RaceItem] = []
    for i, race_data in enumerate(body.races, 1):
        race_row = await repo.row(
            """
            INSERT INTO race (competition_id, external_id, name, distance_m, distance_km_raw, sport)
            VALUES (:comp_id, :ext_id, :name, :dist_m, :dist_km, :sport)
            RETURNING id, name AS name_raw, distance_m, distance_km_raw
            """,
            {
                "comp_id": event_id,
                "ext_id": f"planned_race_{event_id}_{i}_{uuid.uuid4().hex[:6]}",
                "name": race_data.name,
                "dist_m": race_data.distance_m,
                "dist_km": race_data.distance_km,
                "sport": body.sport,
            },
        )
        races.append(
            RaceItem(
                id=race_row["id"],
                name_raw=race_row["name_raw"] or "Дистанция",
                distance_m=race_row["distance_m"],
                distance_km_raw=race_row["distance_km_raw"],
            )
        )

    # 3. Поиск возможного дубля среди фактических стартов
    possible_dup_id = None
    dup_cand = await repo.row(
        """
        SELECT id, name, location, date_begin
        FROM competition
        WHERE status = 'done'
          AND id != :event_id
          AND (
              (CAST(:city AS text) IS NOT NULL AND location = CAST(:city AS text))
              OR strpos(lower(name), lower(CAST(:norm_name AS text))) > 0
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        {
            "event_id": event_id,
            "city": body.city,
            "norm_name": _normalize_title(body.title)[:15] or body.title[:15],
        },
    )
    if dup_cand:
        possible_dup_id = dup_cand["id"]
        await repo.execute(
            "UPDATE competition SET possible_duplicate_id = :dup_id WHERE id = :event_id",
            {"dup_id": possible_dup_id, "event_id": event_id},
        )
        await repo.execute(
            "UPDATE competition SET possible_duplicate_id = :event_id WHERE id = :dup_id",
            {"dup_id": possible_dup_id, "event_id": event_id},
        )

    await repo.log_audit(
        user_id=user.id,
        action="create_planned_event",
        entity="competition",
        entity_id=event_id,
        diff={"title": body.title, "sport": body.sport, "possible_duplicate_id": possible_dup_id},
    )
    await session.commit()

    return EventItem(
        id=event_id,
        source_id=event_row["source_id"],
        source_name="planned",
        title=event_row["title"],
        date_begin=str(event_row["date_begin"]) if event_row["date_begin"] else None,
        date_end=str(event_row["date_end"]) if event_row["date_end"] else None,
        place=event_row["place"],
        address=event_row["address"],
        status="planned",
        sport=body.sport,
        series_id=body.series_id,
        possible_duplicate_id=possible_dup_id,
        races=races,
    )


@router.get("/series/suggest", response_model=list[SeriesSuggestItem])
async def suggest_series(
    event_id: int = Query(..., description="ID старта"),
    session: SessionDep = None,
):
    """Автоподсказка серии по названию, городу и виду спорта (SPEC v1.3 §3.4, §8)."""
    repo = AdminEventsRepo(session)
    event = await repo.row("SELECT name, location, sport FROM competition WHERE id = :id", {"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Старт не найден")

    norm = _normalize_title(event["name"])
    city = event.get("location")
    sport = event.get("sport") or "run"

    series_rows = await repo.rows(
        """
        SELECT id, name, city, sport
        FROM event_series
        WHERE sport = :sport
          AND (
              (CAST(:city AS text) IS NOT NULL AND city = CAST(:city AS text))
              OR strpos(name_norm, CAST(:norm AS text)) > 0
              OR strpos(CAST(:norm AS text), name_norm) > 0
          )
        LIMIT 5
        """,
        {"sport": sport, "city": city, "norm": norm[:15] if norm else "nonexistent"},
    )

    return [
        SeriesSuggestItem(
            series_id=r["id"],
            series_name=r["name"],
            city=r.get("city"),
            sport=r.get("sport", "run"),
            similarity=1.0,
        )
        for r in series_rows
    ]


@router.post("/{event_id}/series")
async def attach_event_to_series(
    event_id: int,
    body: EventSeriesAttachRequest,
    user: CaptainOrAdminDep,
    session: SessionDep,
):
    """Подтверждение привязки старта к серии администратором или капитаном (SPEC v1.3 §8)."""
    repo = AdminEventsRepo(session)
    event = await repo.row("SELECT id, sport FROM competition WHERE id = :id", {"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Старт не найден")

    check_captain_sport_scope(user, event.get("sport") or "run")

    await repo.execute(
        "UPDATE competition SET series_id = :series_id WHERE id = :event_id",
        {"series_id": body.series_id, "event_id": event_id},
    )
    await repo.log_audit(
        user_id=user.id,
        action="attach_series",
        entity="competition",
        entity_id=event_id,
        diff={"series_id": body.series_id},
    )
    await session.commit()
    return {"ok": True, "event_id": event_id, "series_id": body.series_id}


@router.get("/{event_id}/duplicates", response_model=list[EventDuplicateCandidate])
async def get_event_duplicate_candidates(
    event_id: int,
    session: SessionDep,
):
    """Кандидаты на склейку planned ↔ done (SPEC v1.3 §3.4, §8)."""
    repo = AdminEventsRepo(session)
    event = await repo.row("SELECT id, name, location, status, possible_duplicate_id FROM competition WHERE id = :id", {"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Старт не найден")

    candidates = []
    # If explicitly flagged
    if event.get("possible_duplicate_id"):
        dup = await repo.row(
            "SELECT id, name, date_begin, location, status FROM competition WHERE id = :dup_id",
            {"dup_id": event["possible_duplicate_id"]},
        )
        if dup:
            candidates.append(
                EventDuplicateCandidate(
                    event_id=dup["id"],
                    title=dup["name"],
                    date_begin=str(dup["date_begin"]) if dup["date_begin"] else None,
                    place=dup["location"],
                    status=dup["status"] or "done",
                    similarity_reason="Автоматически отмеченный дубль",
                )
            )

    return candidates


@router.post("/merge")
async def merge_events(
    body: EventMergeRequest,
    user: CaptainOrAdminDep,
    session: SessionDep,
):
    """Склейка planned ↔ done старта с переносом данных (SPEC v1.3 §3.4, §8)."""
    repo = AdminEventsRepo(session)
    planned = await repo.row("SELECT * FROM competition WHERE id = :id", {"id": body.planned_event_id})
    actual = await repo.row("SELECT * FROM competition WHERE id = :id", {"id": body.actual_event_id})
    if not planned or not actual:
        raise HTTPException(status_code=404, detail="Один из стартов для склейки не найден")

    check_captain_sport_scope(user, actual.get("sport") or planned.get("sport") or "run")

    # Переносим series_id из planned, если у actual не задан
    new_series_id = actual.get("series_id") or planned.get("series_id")
    await repo.execute(
        """
        UPDATE competition
        SET series_id = :series_id,
            possible_duplicate_id = NULL
        WHERE id = :actual_id
        """,
        {"series_id": new_series_id, "actual_id": body.actual_event_id},
    )
    await repo.execute(
        """
        UPDATE competition
        SET status = 'done',
            possible_duplicate_id = NULL
        WHERE id = :planned_id
        """,
        {"planned_id": body.planned_event_id},
    )

    await repo.log_audit(
        user_id=user.id,
        action="merge_events",
        entity="competition",
        entity_id=body.actual_event_id,
        diff={"merged_with_planned": body.planned_event_id, "series_id": new_series_id},
    )
    await session.commit()

    return {"ok": True, "actual_event_id": body.actual_event_id, "planned_event_id": body.planned_event_id}

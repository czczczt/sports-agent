"""Сводка для администратора (SPEC v1.3 §2, §3.5).

Включает:
- Переводы спортсменов в not_employee, сделанные капитанами;
- Очереди заявок на доступ, обращений и не проверенных топ-N;
- Трейлы без набора высоты (D+);
- Статус адаптеров.
"""

from __future__ import annotations

import json

from fastapi import APIRouter

from app.api.auth import AdminDep
from app.core.postgres import SessionDep
from app.core.repository import ReadRepository
from app.models import AdminSummaryResponse, CaptainNotEmployeeItem

router = APIRouter(prefix="/admin/summary", tags=["admin-summary"])


class AdminSummaryRepository(ReadRepository):
    async def get_captain_not_employee_changes(self, limit: int = 50) -> list[CaptainNotEmployeeItem]:
        rows = await self.rows(
            """
            SELECT l.id AS audit_id, l.entity_id AS athlete_id, l.diff, l.created_at,
                   COALESCE(u.username, 'unknown') AS moderator_username,
                   a.display_name AS athlete_name
            FROM audit_log l
            LEFT JOIN app_user u ON u.id = l.user_id
            LEFT JOIN athlete a ON a.id = l.entity_id
            WHERE l.action = 'captain_set_not_employee'
               OR (l.action = 'update_athlete' AND l.diff->>'new_status' = 'not_employee' AND l.diff->>'moderator_role' = 'captain')
            ORDER BY l.created_at DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
        results = []
        for r in rows:
            diff = r["diff"] if isinstance(r["diff"], dict) else json.loads(r["diff"] or "{}")
            athlete_name = r.get("athlete_name") or diff.get("athlete_name") or f"Спортсмен #{r['athlete_id']}"
            results.append(
                CaptainNotEmployeeItem(
                    audit_id=r["audit_id"],
                    athlete_id=r["athlete_id"],
                    athlete_name=athlete_name,
                    moderator_username=diff.get("moderator") or r["moderator_username"],
                    old_status=diff.get("old_status"),
                    new_status="not_employee",
                    created_at=str(r["created_at"]),
                    comment=diff.get("comment"),
                )
            )
        return results

    async def get_pending_access_requests_count(self) -> int:
        cnt = await self.scalar("SELECT count(*) FROM app_user WHERE status = 'pending'")
        return cnt or 0

    async def get_pending_reports_count(self) -> int:
        cnt = await self.scalar("SELECT count(*) FROM report WHERE status = 'new'")
        return cnt or 0

    async def get_unverified_top_n_count(self, top_n: int = 10) -> int:
        cnt = await self.scalar(
            """
            WITH ranked AS (
                SELECT a.id,
                       ROW_NUMBER() OVER (
                           PARTITION BY a.gender
                           ORDER BY COALESCE(r.points, 0) DESC
                       ) as rank
                FROM athlete a
                JOIN running_athlete_rating r ON r.athlete_id = a.id
                WHERE a.employee_status IS NULL OR a.employee_status != 'confirmed'
            )
            SELECT COUNT(*) FROM ranked WHERE rank <= :top_n
            """,
            {"top_n": top_n},
        )
        return cnt or 0

    async def get_trails_without_elevation_count(self) -> int:
        cnt = await self.scalar(
            """
            SELECT count(*)
            FROM race r
            LEFT JOIN competition c ON c.id = r.competition_id
            WHERE (r.sport = 'trail' OR c.sport_type = 'trail' OR r.name ILIKE '%трейл%' OR r.name ILIKE '%trail%')
              AND r.elevation_gain_m IS NULL
            """
        )
        return cnt or 0

    async def get_failed_adapters_count(self) -> int:
        cnt = await self.scalar(
            """
            SELECT count(DISTINCT source_id)
            FROM issue
            WHERE status = 'new'
            """
        )
        return cnt or 0


@router.get("", response_model=AdminSummaryResponse)
async def get_admin_summary(
    current_user: AdminDep,
    session: SessionDep,
):
    """Сводка данных для администратора (SPEC v1.3 §3.5). Доступно только администратору."""
    repo = AdminSummaryRepository(session)
    captain_changes = await repo.get_captain_not_employee_changes()
    pending_access = await repo.get_pending_access_requests_count()
    pending_reports = await repo.get_pending_reports_count()
    unverified = await repo.get_unverified_top_n_count()
    trails_no_elev = await repo.get_trails_without_elevation_count()
    failed_adapters = await repo.get_failed_adapters_count()

    return AdminSummaryResponse(
        captain_not_employee_changes=captain_changes,
        pending_access_requests_count=pending_access,
        pending_reports_count=pending_reports,
        unverified_top_n_count=unverified,
        trails_without_elevation_count=trails_no_elev,
        failed_adapters_count=failed_adapters,
    )

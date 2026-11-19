"""System status and adapter observability API per SPEC v1.3 §12."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.auth import get_optional_current_user
from app.core.postgres import SessionDep
from app.models import UserOut

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", summary="Get system status, queue metrics and adapter health")
async def get_system_status(
    session: SessionDep,
    current_user: UserOut | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    t0 = time.perf_counter()
    db_ok = True
    db_latency_ms = 0.0

    try:
        await session.execute(text("SELECT 1"))
        db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    except Exception:
        db_ok = False

    # 1. Background queue status (Procrastinate)
    queue_info: dict[str, Any] = {"status": "available", "jobs_pending": 0, "jobs_failed": 0, "jobs_done": 0}
    try:
        q_res = await session.execute(
            text(
                """
                SELECT status, count(*)
                FROM procrastinate_jobs
                GROUP BY status
                """
            )
        )
        counts = dict(q_res.fetchall())
        queue_info["jobs_pending"] = counts.get("todo", 0)
        queue_info["jobs_doing"] = counts.get("doing", 0)
        queue_info["jobs_failed"] = counts.get("error", 0)
        queue_info["jobs_done"] = counts.get("succeeded", 0)
    except Exception:
        queue_info["status"] = "schema_not_initialized"

    # 2. Sources / Adapters health
    sources: list[dict[str, Any]] = []
    try:
        src_res = await session.execute(
            text(
                """
                SELECT s.id, s.name, s.base_url, s.platform, s.sport_types, s.enabled,
                       COUNT(DISTINCT c.id) AS competitions_count,
                       COUNT(DISTINCT r.id) AS results_count,
                       COUNT(DISTINCT i.id) AS issues_count
                FROM source s
                LEFT JOIN competition c ON c.source_id = s.id
                LEFT JOIN race ra ON ra.competition_id = c.id
                LEFT JOIN result r ON r.race_id = ra.id
                LEFT JOIN issue i ON i.source_id = s.id AND i.status = 'new'
                GROUP BY s.id, s.name, s.base_url, s.platform, s.sport_types, s.enabled
                ORDER BY s.priority ASC, s.name ASC
                """
            )
        )
        for row in src_res.fetchall():
            sources.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "base_url": row[2],
                    "platform": row[3],
                    "sport_types": row[4],
                    "enabled": row[5],
                    "competitions_count": row[6],
                    "results_count": row[7],
                    "open_issues_count": row[8],
                    "status": "healthy" if row[5] and row[8] == 0 else ("warning" if row[8] > 0 else "disabled"),
                }
            )
    except Exception:
        pass

    # 3. Overall counts
    overview: dict[str, int] = {}
    try:
        ath_cnt = await session.scalar(text("SELECT count(*) FROM athlete")) or 0
        comp_cnt = await session.scalar(text("SELECT count(*) FROM competition")) or 0
        res_cnt = await session.scalar(text("SELECT count(*) FROM result")) or 0
        overview = {
            "athletes": ath_cnt,
            "competitions": comp_cnt,
            "results": res_cnt,
        }
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "timestamp": int(time.time()),
        "database": {
            "connected": db_ok,
            "latency_ms": db_latency_ms,
            "engine": "PostgreSQL 16",
        },
        "queue": queue_info,
        "adapters": sources,
        "overview": overview,
    }

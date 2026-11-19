from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import RAW_TTL_DAYS
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def anonymize_non_employee_results(session: AsyncSession) -> int:
    query = text(
        """
        UPDATE result r
        SET full_name_raw = 'Участник',
            bib = NULL,
            club_raw = NULL,
            city = NULL,
            country = NULL,
            is_anonymized = true
        WHERE r.is_anonymized IS NOT TRUE
          AND (
            NOT EXISTS (
                SELECT 1 FROM result_athlete ra
                JOIN athlete a ON a.id = ra.athlete_id
                WHERE ra.result_id = r.id AND a.employee_status != 'not_employee'
            )
          )
        """
    )
    res = await session.execute(query)
    return res.rowcount or 0


async def purge_expired_raw_records(
    session: AsyncSession,
    days: int = RAW_TTL_DAYS,
    cutoff_time: datetime | None = None,
) -> int:
    if cutoff_time is None:
        cutoff_time = datetime.now(UTC) - timedelta(days=days)

    select_query = text(
        """
        SELECT id, storage_path
        FROM raw
        WHERE fetched_at < :cutoff AND purged_at IS NULL
        """
    )
    rows = (await session.execute(select_query, {"cutoff": cutoff_time})).fetchall()
    if not rows:
        return 0

    for row in rows:
        storage_path = row[1]
        if storage_path:
            try:
                p = Path(storage_path)
                if p.is_file():
                    p.unlink()
            except OSError:
                pass

    update_query = text(
        """
        UPDATE raw
        SET purged_at = now()
        WHERE fetched_at < :cutoff AND purged_at IS NULL
        """
    )
    res = await session.execute(update_query, {"cutoff": cutoff_time})
    return res.rowcount or 0

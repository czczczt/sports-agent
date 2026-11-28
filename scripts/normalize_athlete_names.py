"""Идемпотентная нормализация регистра display_name у существующих спортсменов в PostgreSQL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import DATABASE_URL, normalize_postgres_url  # noqa: E402
from parser_running.normalize import format_display_name  # noqa: E402


def normalize_existing_athletes(dsn: str, *, dry_run: bool = False) -> int:
    """Приводит athlete.display_name к нормальному регистру без изменения name_key.

    Возвращает количество обновлённых строк.
    """
    dsn = normalize_postgres_url(dsn)
    updated = 0
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """
            SELECT id, display_name
            FROM athlete
            WHERE display_name IS NOT NULL
              AND (display_name = UPPER(display_name)
                   OR display_name = LOWER(display_name)
                   OR display_name ~ '[А-ЯЁA-Z]{2,}')
            """
        ).fetchall()

        updates: list[tuple[str, int]] = []
        for athlete_id, raw_name in rows:
            fixed = format_display_name(raw_name)
            if fixed and fixed != raw_name:
                updates.append((fixed, athlete_id))

        updated = len(updates)
        if updates and not dry_run:
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE athlete SET display_name = %s WHERE id = %s",
                    updates,
                )
            conn.commit()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize athlete.display_name case in PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Показать число изменений без записи в БД")
    args = parser.parse_args()
    count = normalize_existing_athletes(DATABASE_URL, dry_run=args.dry_run)
    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}Normalized athlete.display_name rows: {count}")


if __name__ == "__main__":
    main()

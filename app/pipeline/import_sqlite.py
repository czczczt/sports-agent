"""One-time, verified import into an EMPTY PostgreSQL database after Alembic.

Source is opened read-only and backed up to a consistent temporary SQLite snapshot.
Explicit IDs are preserved only because the destination is empty. Existing PostgreSQL
data is never cleared or assumed to share SQLite IDs. All inserts and sequence changes roll back on mismatch.

Legacy SQLite CURRENT_TIMESTAMP columns are UTC. Naive legacy timestamps are
interpreted as UTC; offset-aware timestamps preserve their instant. Verification
normalizes both sides to UTC, including microseconds. Calendar dates intentionally
retain their YYYY-MM-DD portion because the parser schema stores PostgreSQL date.
"""

import argparse
import hashlib
import json
import logging
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from app.config import DATABASE_URL, normalize_postgres_url

logger = logging.getLogger(__name__)

# destination column -> SQLite expression. Controlled schema, never user-provided SQL.
TABLES = {
    "source": (
        "source",
        {
            "id": "id",
            "name": "name",
            "base_url": "coalesce(base_url,'')",
            "platform": "coalesce(platform,'unknown')",
        },
    ),
    "competition": (
        "event",
        {
            "id": "id",
            "source_id": "source_id",
            "external_id": "external_id",
            "code": "code",
            "name": "title",
            "date_begin": "substr(date_begin,1,10)",
            "date_end": "substr(date_end,1,10)",
            "location": "place",
            "address": "address",
            "sport_type": "sport",
            "source_url": "url",
            "canonical_competition_id": "canonical_event_id",
            "fetched_at": "fetched_at",
        },
    ),
    "race": (
        "race",
        {
            "id": "id",
            "competition_id": "event_id",
            "external_id": "external_id",
            "name": "name_raw",
            "distance_km_raw": "distance_km_raw",
            "distance_m": "distance_m",
            "distance_type": "norm_distance",
            "race_type": "race_type",
            "place_by": "place_by",
            "is_final_protocol": "is_final_protocol",
            "total_count": "total_count",
        },
    ),
    "athlete": (
        "athlete",
        {
            k: k
            for k in (
                "id",
                "display_name",
                "name_key",
                "gender",
                "birth_year",
                "city",
                "region",
                "club",
                "starts_count",
                "results_count",
                "created_at",
            )
        },
    ),
    "result": (
        "result r",
        {
            "id": "r.id",
            "race_id": "race_id",
            "external_participant_id": "cast(external_participant_id as text)",
            "bib": "cast(bib as text)",
            "full_name_raw": "full_name_raw",
            "gender": "gender",
            "age": "age",
            "birth_date": "substr(birth_date,1,10)",
            "birth_year": "birth_year",
            "country": "country",
            "region": "region",
            "city": "city",
            "club_raw": "club_raw",
            "club_source": "club_source",
            "status": "status",
            "position": "place_abs",
            "position_gender": "place_gender",
            "age_group": "age_group",
            "chip_time_s": "chip_time_s",
            "gun_time_s": "gun_time_s",
            "duplicate_of": "duplicate_of",
        },
    ),
    "result_athlete": (
        "result_athlete",
        {"result_id": "result_id", "athlete_id": "athlete_id"},
    ),
    "athlete_assessment_cache": (
        "athlete_assessment_cache",
        {
            "athlete_id": "athlete_id",
            "assessment_text": "assessment_text",
            "metrics_json": "metrics_json",
            "model": "model",
            "created_at": "created_at",
        },
    ),
}


def digest_rows(rows, columns):
    digest, count = hashlib.sha256(), 0
    for row in rows:
        normalized = []
        for column, value in zip(columns, row):
            if column in ("is_final_protocol", "is_hidden") and value is not None:
                value = bool(value)
            if (
                column in ("chip_time_s", "gun_time_s", "distance_km_raw")
                and value is not None
            ):
                value = float(value)
            if column in ("fetched_at", "created_at") and value is not None:
                if isinstance(value, str):
                    value = datetime.fromisoformat(value)
                if value.tzinfo is None:
                    value = value.replace(tzinfo=UTC)
                value = value.astimezone(UTC).isoformat()
            normalized.append(value)
        digest.update(
            json.dumps(
                normalized, ensure_ascii=False, default=str, allow_nan=False
            ).encode()
        )
        digest.update(b"\n")
        count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


RATING_TABLES = {
    "rating_norm": (
        "year,distance_class,gender,value,unit",
        "year,distance_class,gender",
    ),
    "rating_score": (
        "result_id,formula_version,points,reason,breakdown_json",
        "result_id,formula_version",
    ),
    "running_athlete_rating": (
        "athlete_id,formula_version,period_start,period_end,points,best_points,starts_count,rank",
        "athlete_id,formula_version,period_start,period_end",
    ),
}


def target_digest(target, table, columns, ordering):
    with target.cursor(name="verify_" + table) as cursor:
        cursor.execute(
            sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
                sql.SQL(",").join(map(sql.Identifier, columns)),
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, ordering)),
            )
        )
        return digest_rows(cursor, columns)


def import_snapshot(snapshot: Path, dsn: str):
    dsn = normalize_postgres_url(dsn)
    with snapshot.open("rb") as file:
        source_hash = hashlib.file_digest(file, "sha256").hexdigest()
    with (
        closing(sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)) as source,
        psycopg.connect(dsn) as target,
    ):
        target.execute("SET LOCAL TIME ZONE 'UTC'")
        target.execute("SELECT pg_advisory_xact_lock(918200)")
        mappings = {
            table: (name, dict(mapping)) for table, (name, mapping) in TABLES.items()
        }
        athlete_columns = {
            row[1] for row in source.execute("PRAGMA table_info(athlete)")
        }
        for column in (
            "first_name",
            "last_name",
            "middle_name",
            "birth_date",
            "employee_status",
            "is_hidden",
        ):
            if column in athlete_columns:
                mappings["athlete"][1][column] = column
        ordering = {table: ["id"] for table in mappings}
        ordering["result_athlete"] = ["result_id"]
        ordering["athlete_assessment_cache"] = ["athlete_id"]
        for table, (columns, order) in RATING_TABLES.items():
            if source.execute(
                "SELECT 1 FROM sqlite_master WHERE name=? AND type='table'", (table,)
            ).fetchone():
                mappings[table] = (
                    table,
                    {column: column for column in columns.split(",")},
                )
                ordering[table] = order.split(",")
        guarded_tables = [
            row[0]
            for row in target.execute(
                """SELECT tablename FROM pg_tables
                   WHERE schemaname = current_schema()
                     AND tablename NOT IN (
                         'alembic_version', 'migration_owned_table', 'migration_dev_owned_table',
                         'procrastinate_workers',
                         'procrastinate_events', 'procrastinate_periodic_defers'
                     )
                   ORDER BY tablename"""
            )
        ]
        for table in guarded_tables:
            target.execute(
                sql.SQL("LOCK TABLE {} IN EXCLUSIVE MODE").format(sql.Identifier(table))
            )
        previous = target.execute(
            "SELECT report FROM migration_import WHERE source_hash=%s", (source_hash,)
        ).fetchone()
        if previous:
            for table, (_, mapping) in mappings.items():
                if (
                    target_digest(target, table, list(mapping), ordering[table])
                    != previous[0]["tables"][table]
                ):
                    raise ValueError(
                        f"Previously imported destination has changed: {table}"
                    )
            return previous[0] | {"already_imported": True}
        for table in guarded_tables:
            if table == "procrastinate_jobs":
                # The table lock also prevents a worker from claiming or enqueueing jobs during import.
                if target.execute(
                    "SELECT 1 FROM procrastinate_jobs "
                    "WHERE status NOT IN ('succeeded', 'failed', 'cancelled', 'aborted') LIMIT 1"
                ).fetchone():
                    raise ValueError("Destination has unfinished background jobs; retry after they finish.")
                continue
            if target.execute(
                sql.SQL("SELECT EXISTS(SELECT 1 FROM {})").format(sql.Identifier(table))
            ).fetchone()[0]:
                raise ValueError(
                    f"Destination {table} is not empty; use a new database. No data was changed."
                )
        violations = source.execute("PRAGMA foreign_key_check").fetchmany(5)
        if violations:
            raise ValueError(f"Source contains broken foreign keys: {violations}")
        orphan_links = source.execute("""
            SELECT count(*) FROM result_athlete l LEFT JOIN result r ON r.id=l.result_id
            LEFT JOIN athlete a ON a.id=l.athlete_id WHERE r.id IS NULL OR a.id IS NULL
        """).fetchone()[0]
        if orphan_links:
            raise ValueError("Source contains broken athlete links")
        report = {"source_sha256": source_hash, "tables": {}}
        for table, (source_table, mapping) in mappings.items():
            columns = list(mapping)
            source_order = "r.id" if table == "result" else ",".join(ordering[table])
            query = f"SELECT {','.join(mapping.values())} FROM {source_table} ORDER BY {source_order}"
            expected = digest_rows(source.execute(query), columns)
            with target.cursor().copy(
                sql.SQL("COPY {} ({}) FROM STDIN").format(
                    sql.Identifier(table),
                    sql.SQL(",").join(map(sql.Identifier, columns)),
                )
            ) as copy:
                for row in source.execute(query):
                    values = list(row)
                    for boolean_column in ("is_final_protocol", "is_hidden"):
                        if boolean_column in columns:
                            i = columns.index(boolean_column)
                            values[i] = (
                                bool(values[i]) if values[i] is not None else None
                            )
                    copy.write_row(values)
            actual = target_digest(target, table, columns, ordering[table])
            if expected != actual:
                raise ValueError(
                    f"Verification mismatch in {table}: {expected} != {actual}"
                )
            report["tables"][table] = actual
            logger.info("Verified import table %s: %s rows", table, actual["rows"])
            if "id" in columns:
                sequence, next_id = target.execute(
                    sql.SQL(
                        "SELECT pg_get_serial_sequence(%s,'id'),coalesce(max(id),0)+1 FROM {}"
                    ).format(sql.Identifier(table)),
                    (table,),
                ).fetchone()
                target.execute(
                    sql.SQL("ALTER SEQUENCE {} RESTART WITH {}").format(
                        sql.Identifier(*sequence.split(".")), sql.Literal(next_id)
                    )
                )
        links = report["tables"]["result_athlete"]["rows"]
        if (
            links
            != target.execute(
                "SELECT count(*) FROM web_result WHERE athlete_id IS NOT NULL"
            ).fetchone()[0]
        ):
            raise ValueError("Athlete link count mismatch")
        report["athlete_links"] = links
        target.execute("SET CONSTRAINTS ALL IMMEDIATE")
        target.execute(
            "INSERT INTO migration_import(source_hash,report) VALUES (%s,%s)",
            (source_hash, Jsonb(report)),
        )
        return report


def migrate(source_path: Path, dsn: str):
    source_path = source_path.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="sports-import-") as directory:
        snapshot = Path(directory) / "snapshot.db"
        with (
            closing(
                sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
            ) as source,
            closing(sqlite3.connect(snapshot)) as destination,
        ):
            source.backup(destination)
        return import_snapshot(snapshot, dsn)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, DATABASE_URL), ensure_ascii=False, indent=2))

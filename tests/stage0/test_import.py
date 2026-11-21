import sqlite3
from datetime import UTC

import psycopg
import pytest

from app.pipeline.import_sqlite import migrate
from tests.conftest import alembic


def test_import_preserves_fields_links_ranks_and_is_idempotent(
    migrated_url, sqlite_source
):
    before = sqlite_source.read_bytes()
    with psycopg.connect(migrated_url) as connection:
        job_id = connection.execute(
            "INSERT INTO procrastinate_jobs(queue_name, task_name) VALUES ('default', 'test') RETURNING id"
        ).fetchone()[0]
        connection.execute("UPDATE procrastinate_jobs SET status='cancelled' WHERE id=%s", (job_id,))
    report = migrate(sqlite_source, migrated_url)
    assert sqlite_source.read_bytes() == before
    assert report["athlete_links"] == 2
    assert report["tables"]["result"]["rows"] == 3
    assert migrate(sqlite_source, migrated_url)["already_imported"] is True
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM procrastinate_events WHERE job_id = %s", (job_id,)
        ).fetchone()[0] > 0
        assert connection.execute(
            "SELECT bib,athlete_id FROM web_result ORDER BY id"
        ).fetchall() == [("A-7", 1), (None, 2), ("003", None)]
        assert connection.execute(
            "SELECT athlete_id FROM result ORDER BY id"
        ).fetchall() == [(None,), (None,), (None,)]
        assert connection.execute(
            "SELECT athlete_id,points,rank FROM running_athlete_rating ORDER BY athlete_id"
        ).fetchall() == [(1, 123.456, 7), (2, 87.125, 3)]
        assert (
            connection.execute("SELECT breakdown_json FROM rating_score").fetchone()[0]
            == '{"original":true}'
        )
        connection.execute("UPDATE athlete SET city='changed' WHERE id=1")
    with pytest.raises(ValueError, match="has changed"):
        migrate(sqlite_source, migrated_url)


@pytest.mark.parametrize("job_status", ["todo", "doing"])
def test_unfinished_rebuild_blocks_import(migrated_url, sqlite_source, job_status):
    with psycopg.connect(migrated_url) as connection:
        job_id = connection.execute(
            "INSERT INTO procrastinate_jobs(queue_name, task_name, status) "
            "VALUES ('rebuild','app.worker.rebuild_rating_task',%s) RETURNING id",
            (job_status,),
        ).fetchone()[0]
    with pytest.raises(ValueError, match="unfinished"):
        migrate(sqlite_source, migrated_url)
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT count(*) FROM athlete").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM migration_import").fetchone() == (0,)
        assert connection.execute(
            "SELECT status FROM procrastinate_jobs WHERE id=%s", (job_id,)
        ).fetchone() == (job_status,)


def test_populated_target_rejected_without_changes(migrated_url, sqlite_source):
    with psycopg.connect(migrated_url) as connection:
        connection.execute(
            "INSERT INTO source(name,base_url,platform) VALUES('existing','url','test')"
        )
    with pytest.raises(ValueError, match="not empty"):
        migrate(sqlite_source, migrated_url)
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT name FROM source").fetchall() == [
            ("existing",)
        ]
        assert connection.execute("SELECT count(*) FROM athlete").fetchone()[0] == 0


def test_broken_link_rejected_and_failure_rolls_back(migrated_url, sqlite_source):
    with sqlite3.connect(sqlite_source) as connection:
        connection.execute("INSERT INTO result_athlete VALUES(999,1)")
    with pytest.raises(ValueError, match="broken athlete links"):
        migrate(sqlite_source, migrated_url)
    with sqlite3.connect(sqlite_source) as connection:
        connection.execute("DELETE FROM result_athlete WHERE result_id=999")
        connection.execute("UPDATE result SET race_id=999 WHERE id=3")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrate(sqlite_source, migrated_url)
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT count(*) FROM source").fetchone()[0] == 0
        assert (
            connection.execute("SELECT count(*) FROM migration_import").fetchone()[0]
            == 0
        )


def test_migration_roundtrip(postgres_url):
    alembic(postgres_url)
    alembic(postgres_url, "base")
    alembic(postgres_url)
    with psycopg.connect(postgres_url) as connection:
        assert connection.execute(
            "SELECT extname FROM pg_extension WHERE extname IN ('pg_trgm','unaccent') ORDER BY extname"
        ).fetchall() == [("pg_trgm",), ("unaccent",)]


def test_parser_adoption_and_replacement(postgres_url, monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "parser_running")
    )
    from parser_running.db import DDL
    from parser_running.store import save_results

    with psycopg.connect(postgres_url) as connection:
        connection.execute(DDL)
        connection.execute(
            "INSERT INTO source(name,base_url,platform) VALUES('preserved','url','test')"
        )
    alembic(postgres_url)
    with psycopg.connect(postgres_url) as connection:
        assert connection.execute("SELECT name FROM source").fetchall() == [
            ("preserved",)
        ]
    alembic(postgres_url, "base")
    with psycopg.connect(postgres_url) as connection:
        assert connection.execute("SELECT name FROM source").fetchall() == [
            ("preserved",)
        ]
    alembic(postgres_url)
    with psycopg.connect(postgres_url) as connection:
        connection.execute(
            "INSERT INTO competition(source_id,external_id) VALUES(1,'event')"
        )
        connection.execute(
            "INSERT INTO race(competition_id,external_id) VALUES(1,'race')"
        )
        connection.execute(
            "INSERT INTO athlete(display_name,name_key) VALUES('Test','test')"
        )
        connection.execute("INSERT INTO result(race_id) VALUES(1)")
        connection.execute("INSERT INTO result_athlete VALUES(1,1)")
        save_results(
            connection,
            1,
            [
                {
                    "bib": "A-123",
                    "status": "FIN",
                    "full_name_raw": "New runner",
                    "gender": "M",
                }
            ],
        )
        assert (
            connection.execute("SELECT count(*) FROM result_athlete").fetchone()[0] == 0
        )
        assert connection.execute("SELECT bib FROM result").fetchall() == [("A-123",)]


def test_import_accepts_asyncpg_url_and_preserves_extended_fields(
    migrated_url, sqlite_source
):
    migrate(
        sqlite_source, migrated_url.replace("postgresql:", "postgresql+asyncpg:", 1)
    )
    with psycopg.connect(migrated_url) as connection:
        row = connection.execute(
            "SELECT first_name,last_name,middle_name,birth_date,employee_status,is_hidden FROM athlete WHERE id=1"
        ).fetchone()
        assert tuple(str(value) for value in row) == (
            "Иван",
            "Фёдоров",
            "Иванович",
            "1990-05-15",
            "presumed",
            "False",
        )
        assert connection.execute("SELECT count(*) FROM app_user").fetchone()[0] == 0


def test_timestamp_policy_keeps_instants_and_microseconds(migrated_url, sqlite_source):
    from datetime import datetime

    with sqlite3.connect(sqlite_source) as connection:
        connection.execute(
            "UPDATE event SET fetched_at='2026-11-02T15:20:30.123456+05:00'"
        )
        connection.execute("UPDATE athlete SET created_at='2026-11-02 10:20:30.654321'")
        connection.execute(
            "INSERT INTO athlete_assessment_cache VALUES(1,'cached text','{}','legacy','2026-11-02 10:20:30.999999')"
        )
    migrate(sqlite_source, migrated_url)
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT fetched_at FROM competition").fetchone()[
            0
        ] == datetime(2026, 11, 2, 10, 20, 30, 123456, tzinfo=UTC)
        assert connection.execute(
            "SELECT created_at FROM athlete WHERE id=1"
        ).fetchone()[0] == datetime(2026, 11, 2, 10, 20, 30, 654321, tzinfo=UTC)
        assert connection.execute(
            "SELECT created_at FROM athlete_assessment_cache"
        ).fetchone()[0] == datetime(2026, 11, 2, 10, 20, 30, 999999, tzinfo=UTC)


def test_dev_schema_adopts_existing_users_without_seeding(postgres_url):
    import os
    from datetime import date
    from unittest.mock import patch

    from alembic import command
    from alembic.config import Config

    with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
        command.upgrade(Config("alembic.ini"), "20261118_01")
    with psycopg.connect(postgres_url) as connection:
        connection.execute("ALTER TABLE athlete ADD COLUMN birth_date text")
        connection.execute(
            "INSERT INTO athlete(display_name,name_key,birth_date) VALUES('Existing','existing','1990-05-15')"
        )
        connection.execute(
            "CREATE TABLE app_user(id serial PRIMARY KEY,username varchar(100) UNIQUE NOT NULL,email varchar(255) UNIQUE,password_hash text NOT NULL,role varchar(20) NOT NULL DEFAULT 'user',status varchar(20) NOT NULL DEFAULT 'active',display_name text,athlete_id bigint REFERENCES athlete(id) ON DELETE SET NULL,created_at timestamptz DEFAULT now())"
        )
        connection.execute(
            "INSERT INTO app_user(username,password_hash,status) VALUES('existing','unchanged hash','blocked')"
        )
    alembic(postgres_url)
    with psycopg.connect(postgres_url) as connection:
        assert connection.execute(
            "SELECT username,password_hash,status FROM app_user"
        ).fetchall() == [("existing", "unchanged hash", "blocked")]
        assert connection.execute("SELECT birth_date FROM athlete").fetchone()[
            0
        ] == date(1990, 5, 15)


def test_dev_schema_rejects_incompatible_named_event_fk(postgres_url):
    import os
    import subprocess
    from unittest.mock import patch

    from alembic import command
    from alembic.config import Config

    with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
        command.upgrade(Config("alembic.ini"), "20261118_01")
    with psycopg.connect(postgres_url) as connection:
        connection.execute("CREATE TABLE legacy_event(id integer PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE report(id integer PRIMARY KEY,kind text NOT NULL,user_id integer,athlete_id bigint,result_id bigint,event_id integer,url text,message text,status text,decided_by text,decided_at timestamptz,created_at timestamptz,CONSTRAINT fk_report_event FOREIGN KEY(event_id) REFERENCES legacy_event(id) ON DELETE SET NULL)"
        )
        connection.execute(
            "INSERT INTO report(id,kind,message) VALUES(99,'other','preserve me')"
        )
    with pytest.raises(subprocess.CalledProcessError) as failure:
        alembic(postgres_url)
    assert "incompatible with the unified schema" in failure.value.stderr
    with psycopg.connect(postgres_url) as connection:
        assert (
            connection.execute("SELECT message FROM report WHERE id=99").fetchone()[0]
            == "preserve me"
        )
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "20261118_01"
        )

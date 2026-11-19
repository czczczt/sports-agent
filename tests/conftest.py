import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

os.environ.setdefault(
    "DATABASE_URL", "postgresql://stage0_disabled@127.0.0.1:1/stage0_disabled"
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def postgres_url():
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip(
            "TEST_POSTGRES_ADMIN_URL must point to a disposable PostgreSQL test server"
        )
    database = "stage0_" + uuid.uuid4().hex
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
        )
    params = conninfo_to_dict(admin_url)
    params["dbname"] = database
    # SQLAlchemy and settings require URL syntax rather than libpq keyword DSNs.
    from sqlalchemy.engine import URL

    url = URL.create(
        "postgresql",
        username=params.get("user"),
        password=params.get("password"),
        host=params.get("host"),
        port=int(params.get("port", 5432)),
        database=database,
    )
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                (database,),
            )
            connection.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(database))
            )


def alembic(url, revision="head"):
    environment = os.environ | {"DATABASE_URL": url}
    action = "downgrade" if revision == "base" else "upgrade"
    subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def migrated_url(postgres_url):
    alembic(postgres_url)
    return postgres_url


@pytest.fixture
def sqlite_source(tmp_path):
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
        CREATE TABLE source(id INTEGER PRIMARY KEY,name TEXT,base_url TEXT,platform TEXT);
        CREATE TABLE event(id INTEGER PRIMARY KEY,source_id INTEGER,external_id TEXT,code TEXT,title TEXT,
          date_begin TEXT,date_end TEXT,place TEXT,address TEXT,sport TEXT,url TEXT,canonical_event_id INTEGER,fetched_at TEXT);
        CREATE TABLE race(id INTEGER PRIMARY KEY,event_id INTEGER,external_id TEXT,name_raw TEXT,
          distance_km_raw REAL,distance_m INTEGER,norm_distance TEXT,race_type TEXT,place_by TEXT,is_final_protocol INTEGER,total_count INTEGER);
        CREATE TABLE athlete(id INTEGER PRIMARY KEY,display_name TEXT,name_key TEXT,gender TEXT,birth_year INTEGER,
          city TEXT,region TEXT,club TEXT,starts_count INTEGER,results_count INTEGER,created_at TEXT);
        CREATE TABLE result(id INTEGER PRIMARY KEY,race_id INTEGER,external_participant_id TEXT,bib TEXT,
          full_name_raw TEXT,gender TEXT,age INTEGER,birth_date TEXT,birth_year INTEGER,country TEXT,region TEXT,city TEXT,
          club_raw TEXT,club_source TEXT,status TEXT,place_abs INTEGER,place_gender INTEGER,age_group TEXT,
          chip_time_s REAL,gun_time_s REAL,duplicate_of INTEGER);
        CREATE TABLE result_athlete(result_id INTEGER PRIMARY KEY,athlete_id INTEGER NOT NULL REFERENCES athlete(id));
        CREATE TABLE athlete_assessment_cache(athlete_id INTEGER PRIMARY KEY,assessment_text TEXT,metrics_json TEXT,model TEXT,created_at TEXT);
        CREATE TABLE rating_norm(year INTEGER,distance_class TEXT,gender TEXT,value REAL,unit TEXT);
        CREATE TABLE rating_score(result_id INTEGER,formula_version TEXT,points REAL,reason TEXT,breakdown_json TEXT);
        CREATE TABLE running_athlete_rating(athlete_id INTEGER,formula_version TEXT,period_start TEXT,period_end TEXT,
          points REAL,best_points REAL,starts_count INTEGER,rank INTEGER);
        INSERT INTO source VALUES(1,'test','https://example.test','test');
        INSERT INTO event VALUES(1,1,'e1','e1','Test event','2026-11-01','2026-11-01','Test city',NULL,'run',NULL,NULL,'2026-11-02 10:20:30');
        INSERT INTO race VALUES(1,1,'r1','10 km',10,10000,'10k','individual','chip',1,3);
        INSERT INTO athlete VALUES(1,'Фёдоров Иван','иван федоров','M',1990,'city','region','club',1,1,'2026-11-02 10:20:30');
        INSERT INTO athlete VALUES(2,'Иванова Анна','анна иванова','F',1991,NULL,NULL,NULL,1,1,'2026-11-02 10:20:30');
        INSERT INTO result(id,race_id,bib,full_name_raw,gender,birth_year,status,place_abs,place_gender,chip_time_s,gun_time_s)
          VALUES(1,1,'A-7','Фёдоров Иван','M',1990,'FIN',1,1,2400,2403),
                (2,1,NULL,'Иванова Анна','F',1991,'FIN',2,1,2500,2504),
                (3,1,'003','Other Runner','M',1980,'FIN',3,2,2600,2605);
        INSERT INTO result_athlete VALUES(1,1),(2,2);
        INSERT INTO rating_norm VALUES(2026,'10k','M',2300,'s');
        INSERT INTO rating_score VALUES(1,'run-v1',123.456,NULL,'{"original":true}');
        INSERT INTO running_athlete_rating VALUES(1,'run-v1','2025-11-19','2026-11-19',123.456,123.456,1,7),
          (2,'run-v1','2025-11-19','2026-11-19',87.125,87.125,1,3);
        ALTER TABLE athlete ADD COLUMN first_name TEXT;
        ALTER TABLE athlete ADD COLUMN last_name TEXT;
        ALTER TABLE athlete ADD COLUMN middle_name TEXT;
        ALTER TABLE athlete ADD COLUMN birth_date TEXT;
        ALTER TABLE athlete ADD COLUMN employee_status TEXT DEFAULT 'presumed';
        ALTER TABLE athlete ADD COLUMN is_hidden INTEGER DEFAULT 0;
        UPDATE athlete SET first_name='Иван',last_name='Фёдоров',middle_name='Иванович',birth_date='1990-05-15' WHERE id=1;
        UPDATE athlete SET first_name='Анна',last_name='Иванова',middle_name='Петровна',birth_date='1991-06-17' WHERE id=2;
        """)
    return path


@pytest.fixture
def imported_url(migrated_url, sqlite_source):
    from app.pipeline.import_sqlite import migrate

    migrate(sqlite_source, migrated_url)
    return migrated_url


def seed_users(url):
    from argon2 import PasswordHasher

    hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    with psycopg.connect(url) as connection:
        for username, role, display in (
            ("user", "user", "Пользователь"),
            ("admin", "admin", "Администратор"),
            ("captain", "captain", "Капитан"),
        ):
            connection.execute(
                "INSERT INTO app_user(username,email,password_hash,role,status,display_name) VALUES(%s,%s,%s,%s,'active',%s)",
                (
                    username,
                    username + "@example.test",
                    hasher.hash(username),
                    role,
                    display,
                ),
            )


@pytest.fixture
def client(imported_url, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "DATABASE_URL", imported_url)
    seed_users(imported_url)
    with TestClient(main.app) as value:
        yield value


@pytest.fixture
def empty_client(migrated_url, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "DATABASE_URL", migrated_url)
    seed_users(migrated_url)
    with TestClient(main.app) as value:
        yield value


@pytest.fixture
def auth_headers(client):
    def login(username="user"):
        client.cookies.clear()
        response = client.post(
            "/api/auth/login", json={"username": username, "password": username}
        )
        assert response.status_code == 200, response.text
        client.cookies.clear()
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    return login

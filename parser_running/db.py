"""SQLite: таблицы, которые парсер заполняет уже сейчас (целевая схема — docs/parser-db-spec.md)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "running.db"

DDL = """
CREATE TABLE IF NOT EXISTS source (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    base_url TEXT NOT NULL,
    platform TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES source(id),
    external_id TEXT NOT NULL,
    code TEXT,
    title TEXT,
    date_begin TEXT,
    date_end TEXT,
    place TEXT,
    address TEXT,
    sport TEXT,
    url TEXT,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_id, external_id)
);
CREATE TABLE IF NOT EXISTS race (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES event(id),
    external_id TEXT NOT NULL,
    name_raw TEXT,
    distance_km_raw REAL,
    distance_m INTEGER,
    norm_distance TEXT,
    race_type TEXT,
    place_by TEXT,
    is_final_protocol INTEGER,
    total_count INTEGER,
    UNIQUE (event_id, external_id)
);
CREATE TABLE IF NOT EXISTS result (
    id INTEGER PRIMARY KEY,
    race_id INTEGER NOT NULL REFERENCES race(id),
    external_participant_id TEXT,
    bib INTEGER,
    full_name_raw TEXT,
    gender TEXT,
    age INTEGER,
    birth_date TEXT,
    birth_year INTEGER,
    country TEXT,
    region TEXT,
    city TEXT,
    club_raw TEXT,
    status TEXT,
    place_abs INTEGER,
    place_gender INTEGER,
    age_group TEXT,
    chip_time_s REAL,
    gun_time_s REAL
);
CREATE INDEX IF NOT EXISTS result_race ON result(race_id);
CREATE TABLE IF NOT EXISTS crawl_error (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES source(id),
    stage TEXT,
    object_ref TEXT,
    error TEXT,
    at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


# Колонки дедупликации (spec, раздел 7). Добавляются и в уже существующую базу.
DEDUP_COLUMNS = {"event": "canonical_event_id INTEGER REFERENCES event(id)",
                 "result": "duplicate_of INTEGER REFERENCES result(id)"}


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(DDL)
    for table, col in DEDUP_COLUMNS.items():
        if col.split()[0] not in {r[1] for r in con.execute(f"PRAGMA table_info({table})")}:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
    return con


def source_id(con: sqlite3.Connection, name: str, base_url: str, platform: str) -> int:
    con.execute("INSERT OR IGNORE INTO source(name, base_url, platform) VALUES (?, ?, ?)",
                (name, base_url, platform))
    return con.execute("SELECT id FROM source WHERE name = ?", (name,)).fetchone()[0]


def log_error(con: sqlite3.Connection, src: int, stage: str, ref: str, err: str) -> None:
    con.execute("INSERT INTO crawl_error(source_id, stage, object_ref, error) VALUES (?, ?, ?, ?)",
                (src, stage, ref, err[:2000]))

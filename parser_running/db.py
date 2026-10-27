"""SQLite: таблицы, которые парсер заполняет уже сейчас (целевая схема — docs/parser-db-spec.md)."""
from __future__ import annotations

import hashlib
import json
import re
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
-- Очередь проблем (spec 4, «issue»): её разбирает агент или человек. Одна проблема = одна строка
-- (fingerprint), повторы увеличивают occurrences. Статусы:
--   new -> agent_working -> proposed -> approved | rejected -> resolved;
--   known — совпало с known_exception (не ошибка); blocked — ждёт внешнего (сеть, заказчик).
CREATE TABLE IF NOT EXISTS issue (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES source(id),
    stage TEXT NOT NULL,          -- fetch / parse / check / store / dedup / match
    kind TEXT NOT NULL,           -- fetch_failed / zero_rows / check_failed / geo_block / ...
    object_ref TEXT,              -- старт/дистанция
    fingerprint TEXT NOT NULL UNIQUE,
    details TEXT,                 -- JSON: что упало
    status TEXT NOT NULL DEFAULT 'new',
    assignee TEXT,                -- agent / human / infra
    journal_ref TEXT,             -- номер в ERRORS.md (E1…)
    occurrences INTEGER NOT NULL DEFAULT 1,
    first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);
-- То, что выглядит как ошибка, но ею не является (агент не должен это «чинить»).
CREATE TABLE IF NOT EXISTS known_exception (
    id INTEGER PRIMARY KEY,
    source TEXT,                  -- имя площадки; NULL = любая
    kind TEXT NOT NULL,
    pattern TEXT NOT NULL,        -- regex по «object_ref + details»
    reason TEXT NOT NULL,
    journal_ref TEXT,
    UNIQUE (source, kind, pattern)
);
"""


# Колонки, добавленные после первой версии схемы. Добавляются и в уже существующую базу.
ADDED_COLUMNS = [("event", "canonical_event_id INTEGER REFERENCES event(id)"),      # дедуп (spec 7)
                 ("result", "duplicate_of INTEGER REFERENCES result(id)"),         # дедуп (spec 7)
                 ("result", "club_source TEXT")]                                   # protocol / filter (E35)


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(DDL)
    for table, col in ADDED_COLUMNS:
        if col.split()[0] not in {r[1] for r in con.execute(f"PRAGMA table_info({table})")}:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
    return con


def source_id(con: sqlite3.Connection, name: str, base_url: str, platform: str) -> int:
    con.execute("INSERT OR IGNORE INTO source(name, base_url, platform) VALUES (?, ?, ?)",
                (name, base_url, platform))
    return con.execute("SELECT id FROM source WHERE name = ?", (name,)).fetchone()[0]


def report_issue(con: sqlite3.Connection, src: int | None, stage: str, kind: str, ref: str,
                 details: dict | str, assignee: str = "agent") -> str:
    """Зарегистрировать проблему в очереди. Возвращает её статус.
    Совпала с known_exception -> 'known'; повтор закрытой проблемы -> снова 'new' (регрессия)."""
    text = details if isinstance(details, str) else json.dumps(details, ensure_ascii=False)
    fp = hashlib.sha1(f"{src}|{stage}|{kind}|{ref}".encode()).hexdigest()
    src_name = con.execute("SELECT name FROM source WHERE id=?", (src,)).fetchone() if src else None
    known = next(((jref,) for s, pattern, jref in con.execute(
        "SELECT source, pattern, journal_ref FROM known_exception WHERE kind=?", (kind,))
        if (s is None or (src_name and s == src_name[0])) and re.search(pattern, f"{ref} {text}")), None)
    status = "known" if known else "new"
    con.execute("""INSERT INTO issue(source_id, stage, kind, object_ref, fingerprint, details, status, assignee,
                   journal_ref) VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(fingerprint) DO UPDATE SET occurrences = occurrences + 1,
                   last_seen = CURRENT_TIMESTAMP, details = excluded.details,
                   status = CASE WHEN issue.status = 'resolved' THEN excluded.status ELSE issue.status END,
                   resolved_at = CASE WHEN issue.status = 'resolved' THEN NULL ELSE issue.resolved_at END""",
                (src, stage, kind, ref, fp, text[:4000], status, None if known else assignee,
                 known[0] if known else None))
    return con.execute("SELECT status FROM issue WHERE fingerprint=?", (fp,)).fetchone()[0]

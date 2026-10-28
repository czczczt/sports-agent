import sqlite3
from typing import Generator
from app.config import SQLITE_DB_PATH


def get_db_connection() -> sqlite3.Connection:
    """Возвращает соединение с базой данных SQLite."""
    conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Dependency для FastAPI."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

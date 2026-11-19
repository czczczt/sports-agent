"""Synchronous PostgreSQL access for diagnostic scripts. HTTP uses core.postgres."""
from typing import Any
import psycopg
from psycopg.rows import dict_row
from app.config import DATABASE_URL

class _PGCompatCursor:
    def __init__(self, cursor: psycopg.Cursor):
        self._cur = cursor

    def execute(self, query: str, params: Any = None) -> Any:
        if params is not None and "?" in query:
            query = query.replace("?", "%s")
        if params is not None:
            return self._cur.execute(query, params)
        return self._cur.execute(query)

    def executemany(self, query: str, seq_of_params: Any) -> Any:
        if "?" in query:
            query = query.replace("?", "%s")
        return self._cur.executemany(query, seq_of_params)

    def fetchone(self) -> Any:
        return self._cur.fetchone()

    def fetchall(self) -> Any:
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)

    def close(self):
        self._cur.close()


class _PGCompatConnection:
    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def cursor(self) -> _PGCompatCursor:
        return _PGCompatCursor(self._conn.cursor())

    def execute(self, query: str, params: Any = None) -> _PGCompatCursor:
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def executemany(self, query: str, seq_of_params: Any) -> _PGCompatCursor:
        cur = self.cursor()
        cur.executemany(query, seq_of_params)
        return cur

    def executescript(self, script: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(script)
        self.commit()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()


def get_db_connection() -> _PGCompatConnection:
    """Возвращает синхронное соединение с базой данных PostgreSQL."""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return _PGCompatConnection(conn)

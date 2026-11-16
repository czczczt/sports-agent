"""Асинхронный доступ к базе данных PostgreSQL (через asyncpg).

Предоставляет:
- get_db_pool / close_db_pool: управление пулом соединений asyncpg
- get_db: асинхронная зависимость FastAPI (AsyncPGConnection)
- get_db_connection: синхронное подключение для тестов (через psycopg)
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncIterator, List, Optional
import asyncpg
import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL

_POOL: Optional[asyncpg.Pool] = None


def prepare_sql(query: str) -> str:
    """Заменяет плейсхолдеры ? на $1, $2, ... для совместимости."""
    if "?" not in query:
        return query
    parts = query.split("?")
    out = []
    for i, p in enumerate(parts[:-1], 1):
        out.append(p)
        out.append(f"${i}")
    out.append(parts[-1])
    return "".join(out)


class AsyncPGConnection:
    """Обертка над asyncpg.Connection."""
    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    @property
    def raw_connection(self) -> asyncpg.Connection:
        return self._conn

    async def fetch(self, query: str, *args: Any) -> List[asyncpg.Record]:
        return await self._conn.fetch(prepare_sql(query), *args)

    async def fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        return await self._conn.fetchrow(prepare_sql(query), *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        return await self._conn.fetchval(prepare_sql(query), *args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self._conn.execute(prepare_sql(query), *args)


async def get_db_pool() -> asyncpg.Pool:
    """Возвращает глобальный пул соединений asyncpg для активного цикла событий."""
    global _POOL
    loop = asyncio.get_running_loop()
    if _POOL is None or getattr(_POOL, "_loop", None) is not loop or _POOL._closed:
        _POOL = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
    return _POOL


async def close_db_pool() -> None:
    """Закрывает пул соединений при остановке сервера."""
    global _POOL
    if _POOL is not None:
        try:
            if not _POOL._closed:
                await _POOL.close()
        except Exception:
            pass
        _POOL = None


async def get_db() -> AsyncIterator[AsyncPGConnection]:
    """Dependency для FastAPI эндпоинтов."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        yield AsyncPGConnection(conn)


# ---------- Синхронный адаптер для тестов и скриптов (psycopg) ----------

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

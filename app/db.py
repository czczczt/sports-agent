import re
import sqlite3
from typing import Generator
from app.config import SQLITE_DB_PATH


def match_city(query: str, place: str, address: str) -> bool:
    """Проверяет соответствие поискового запроса города строкам place и address.
    Использует поиск по токенам (словам), чтобы избежать ложных срабатываний
    (например, 'орск' внутри 'Приморский край' или 'Магнитогорск').
    """
    if not query:
        return True
    q = (query or "").lower().replace("ё", "е").strip()
    if not q:
        return True

    # Исключаем служебные префиксы/сокращения, если указано название города
    q_tokens = [t for t in re.findall(r"\w+", q) if t and t not in ("г", "город", "обл", "область", "край", "р", "рн", "район")]
    if not q_tokens:
        q_tokens = [t for t in re.findall(r"\w+", q) if t]
    if not q_tokens:
        return True

    text = f"{place or ''} {address or ''}".lower().replace("ё", "е")
    t_tokens = re.findall(r"\w+", text)
    if not t_tokens:
        return False

    for q_tok in q_tokens:
        stem = q_tok[:-1] if len(q_tok) >= 4 and q_tok[-1] in "аяеиыуюо" else q_tok
        if not any(t.startswith(q_tok) or (len(stem) >= 3 and t.startswith(stem)) for t in t_tokens):
            return False
    return True


def get_db_connection() -> sqlite3.Connection:
    """Возвращает соединение с базой данных SQLite."""
    conn = sqlite3.connect(SQLITE_DB_PATH, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.create_function("ru_lower", 1, lambda s: (s or "").lower().replace("ё", "е"))
    conn.create_function("match_city", 3, match_city)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Dependency для FastAPI."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

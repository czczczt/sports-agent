import asyncio

from sqlalchemy.engine import URL, make_url


def async_postgres_url(dsn: str) -> URL:
    url = make_url(dsn)
    if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL")
    return url.set(drivername="postgresql+asyncpg")


def postgres_event_loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()

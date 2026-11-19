import asyncio
import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()
url = make_url(os.environ["DATABASE_URL"])
if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
    raise ValueError("DATABASE_URL must be a PostgreSQL URL")
url = url.set(drivername="postgresql+asyncpg")


def migrate(connection: Connection) -> None:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())

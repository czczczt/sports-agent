import os

from alembic import context
from dotenv import load_dotenv
from psycopg import ClientCursor
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection, make_url

load_dotenv()
url = make_url(os.environ["DATABASE_URL"])
if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
    raise ValueError("DATABASE_URL must be a PostgreSQL URL")
url = url.set(drivername="postgresql+psycopg")


def migrate(connection: Connection) -> None:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    # SQL migrations contain multi-statement scripts and PL/pgSQL bodies.
    engine = create_engine(url, poolclass=pool.NullPool, connect_args={"cursor_factory": ClientCursor})
    try:
        with engine.connect() as connection:
            migrate(connection.execution_options(no_parameters=True))
    finally:
        engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    run_online()

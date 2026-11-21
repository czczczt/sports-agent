"""Unified schema, adopting parser tables without deleting their records.

Downgrade removes only tables this revision created. Additive columns/indexes on
adopted parser tables and shared extensions deliberately remain to preserve data.
"""

from pathlib import Path

from alembic import op
from sqlalchemy import inspect, text

revision = "20261118_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    existing = set(inspect(connection).get_table_names())
    connection.exec_driver_sql(
        "CREATE TABLE migration_owned_table (name text PRIMARY KEY)"
    )
    for statement in (
        Path(__file__).with_suffix(".sql").read_text(encoding="utf-8").split(";\n")
    ):
        if statement.strip():
            connection.exec_driver_sql(statement)
    for table in (
        set(inspect(connection).get_table_names())
        - existing
        - {"migration_owned_table"}
    ):
        connection.execute(
            text("INSERT INTO migration_owned_table VALUES (:name)"), {"name": table}
        )


def downgrade():
    connection = op.get_bind()
    for view in (
        "web_athlete_rating",
        "web_rating_score",
        "web_result",
        "web_race",
        "web_event",
    ):
        op.execute(f"DROP VIEW {view}")
    op.execute("DROP FUNCTION search_text(text)")
    owned = set(
        connection.execute(text("SELECT name FROM migration_owned_table")).scalars()
    )
    for table in reversed(inspect(connection).get_sorted_table_and_fkc_names()):
        name = table[0]
        if name in owned:
            op.drop_table(name)
    op.drop_table("migration_owned_table")

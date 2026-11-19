"""Adopt the dev authentication, athlete and request schema without seeding users.

Downgrade preserves additive fields on adopted tables; tables created by this
revision are tracked and removed in dependency order. Shared athlete fields are
removed with the stage-0 baseline only when that baseline owns the athlete table.
"""

from pathlib import Path

from alembic import op
from sqlalchemy import inspect, text

revision = "20261119_02"
down_revision = "20261118_01"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    existing = set(inspect(connection).get_table_names())
    connection.exec_driver_sql(
        "CREATE TABLE migration_dev_owned_table (name text PRIMARY KEY)"
    )
    for statement in (
        Path(__file__).with_suffix(".sql").read_text(encoding="utf-8").split(";\n")
    ):
        if statement.strip():
            connection.exec_driver_sql(statement)
    for table, definitions in {
        "report": {
            "fk_report_user": "FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE SET NULL",
            "fk_report_athlete": "FOREIGN KEY (athlete_id) REFERENCES athlete(id) ON DELETE SET NULL",
            "fk_report_result": "FOREIGN KEY (result_id) REFERENCES result(id) ON DELETE SET NULL",
            "fk_report_event": "FOREIGN KEY (event_id) REFERENCES competition(id) ON DELETE SET NULL",
        }
    }.items():
        constraints = {
            item["name"]: item for item in inspect(connection).get_foreign_keys(table)
        }
        for name, definition in definitions.items():
            if name in constraints:
                expected_table = definition.split("REFERENCES ", 1)[1].split("(", 1)[0]
                expected_column = definition.split("(", 1)[1].split(")", 1)[0]
                existing_fk = constraints[name]
                if (
                    existing_fk["referred_table"] != expected_table
                    or existing_fk["constrained_columns"] != [expected_column]
                    or existing_fk["referred_columns"] != ["id"]
                    or existing_fk.get("options", {}).get("ondelete") != "SET NULL"
                ):
                    raise ValueError(
                        f"Existing constraint {name} is incompatible with the unified schema"
                    )
            else:
                connection.exec_driver_sql(
                    f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" {definition}'
                )
    for table in (
        set(inspect(connection).get_table_names())
        - existing
        - {"migration_dev_owned_table"}
    ):
        connection.execute(
            text("INSERT INTO migration_dev_owned_table VALUES (:name)"),
            {"name": table},
        )


def downgrade():
    connection = op.get_bind()
    owned = set(
        connection.execute(text("SELECT name FROM migration_dev_owned_table")).scalars()
    )
    for name, _ in reversed(inspect(connection).get_sorted_table_and_fkc_names()):
        if name in owned:
            op.drop_table(name)
    op.drop_table("migration_dev_owned_table")

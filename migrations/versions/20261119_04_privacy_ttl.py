from pathlib import Path

from alembic import op

revision = "20261119_04"
down_revision = "20261119_03"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    for statement in (
        Path(__file__).with_suffix(".sql").read_text(encoding="utf-8").split(";\n")
    ):
        if statement.strip():
            connection.exec_driver_sql(statement)


def downgrade():
    op.drop_column("raw", "purged_at")
    op.drop_column("result", "is_anonymized")

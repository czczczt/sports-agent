from pathlib import Path

from alembic import op

revision = "20261123_11"
down_revision = "20261123_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
        DROP TABLE IF EXISTS rating_snapshot;
        DROP TABLE IF EXISTS rating_entry;
    """)

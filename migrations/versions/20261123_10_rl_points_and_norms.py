from pathlib import Path

from alembic import op

revision = "20261123_10"
down_revision = "20261123_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
        DROP TABLE IF EXISTS run_norm;
        DROP TABLE IF EXISTS rl_points;
    """)

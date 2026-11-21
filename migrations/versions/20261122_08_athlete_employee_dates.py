from pathlib import Path

from alembic import op

revision = "20261122_08"
down_revision = "20261120_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
        DROP INDEX IF EXISTS idx_athlete_employee_dates;
        ALTER TABLE athlete
            DROP COLUMN IF EXISTS employee_since,
            DROP COLUMN IF EXISTS employee_until;
    """)

from pathlib import Path

from alembic import op

revision = "20261123_09"
down_revision = "20261122_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
        DROP TABLE IF EXISTS setting;
        DROP INDEX IF EXISTS idx_race_scoring_class;
        DROP INDEX IF EXISTS idx_race_sport;
        ALTER TABLE race
            DROP COLUMN IF EXISTS special,
            DROP COLUMN IF EXISTS is_rl_series,
            DROP COLUMN IF EXISTS elevation_gain_m,
            DROP COLUMN IF EXISTS scoring_class,
            DROP COLUMN IF EXISTS sport;
        DROP TABLE IF EXISTS captain_sport;
    """)

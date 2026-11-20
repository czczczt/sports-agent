from pathlib import Path

from alembic import op

revision = "20261120_07"
down_revision = "20261120_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
        DROP TABLE rating_publication, rating_version_row;
        ALTER TABLE pilot_run DROP CONSTRAINT pilot_run_rating_version_fk;
        DROP TABLE rating_version, pilot_run;
    """)

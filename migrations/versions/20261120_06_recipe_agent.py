from pathlib import Path

from alembic import op

revision = "20261120_06"
down_revision = "20261120_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    op.get_bind().exec_driver_sql(sql)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
        ALTER TABLE result DROP COLUMN recipe_id;
        DROP TABLE golden_case, recipe_version, recipe_repair, recipe;
    """)

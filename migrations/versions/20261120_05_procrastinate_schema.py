from pathlib import Path

from alembic import op

revision = "20261120_05"
down_revision = "20261119_04"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    sql_text = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    connection.exec_driver_sql(sql_text)


def downgrade():
    connection = op.get_bind()
    connection.exec_driver_sql("""
        DROP TABLE IF EXISTS procrastinate_periodic_defers CASCADE;
        DROP TABLE IF EXISTS procrastinate_events CASCADE;
        DROP TABLE IF EXISTS procrastinate_jobs CASCADE;
    """)

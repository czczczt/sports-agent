from pathlib import Path

from alembic import op

revision = "20261123_12"
down_revision = "20261123_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
        DROP VIEW IF EXISTS web_event;
        CREATE VIEW web_event AS
        SELECT id, source_id, name AS title, date_begin::text, date_end::text,
               location AS place, address FROM competition;
        ALTER TABLE competition
            DROP COLUMN IF EXISTS possible_duplicate_id,
            DROP COLUMN IF EXISTS created_by,
            DROP COLUMN IF EXISTS sport,
            DROP COLUMN IF EXISTS planned_note,
            DROP COLUMN IF EXISTS planned_date_end,
            DROP COLUMN IF EXISTS planned_date_start,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS series_id;
        DROP TABLE IF EXISTS event_series;
    """)

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
    # PostgreSQL cannot drop the column while web_result exposes it, and
    # CREATE OR REPLACE VIEW cannot remove an existing view column.
    op.execute("DROP VIEW web_result")
    op.execute("""
        CREATE VIEW web_result AS
        SELECT r.id, r.id AS result_id, r.race_id, l.athlete_id, r.bib,
               r.full_name_raw, r.gender, r.age, r.birth_year, r.club_raw,
               r.position AS place_abs, r.position_gender AS place_gender,
               r.chip_time_s, r.gun_time_s, r.status, r.duplicate_of
        FROM result r
        LEFT JOIN result_athlete l ON l.result_id = r.id
    """)
    op.drop_column("raw", "purged_at")
    op.drop_column("result", "is_anonymized")

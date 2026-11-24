"""Remove superseded protocols from the public competition views."""

from alembic import op

revision = "20261125_15"
down_revision = "20261125_14"
branch_labels = None
depends_on = None


EVENT_VIEW = """
    CREATE OR REPLACE VIEW web_event AS
    SELECT c.id, c.source_id, c.name AS title, c.date_begin::text, c.date_end::text,
           c.location AS place, c.address, COALESCE(c.status, 'done') AS status,
           COALESCE(c.sport, 'run') AS sport, c.series_id, es.name AS series_name,
           c.possible_duplicate_id
    FROM competition c LEFT JOIN event_series es ON es.id=c.series_id
"""
RACE_VIEW = """
    CREATE OR REPLACE VIEW web_race AS
    SELECT id, competition_id AS event_id, name AS name_raw, distance_type AS norm_distance,
           distance_m, distance_km_raw, total_count FROM race
"""
RESULT_VIEW = """
    CREATE OR REPLACE VIEW web_result AS
    SELECT r.id, r.id AS result_id, r.race_id, l.athlete_id, r.bib, r.full_name_raw,
           r.gender, r.age, r.birth_year, r.club_raw, r.position AS place_abs,
           r.position_gender AS place_gender, r.chip_time_s, r.gun_time_s,
           r.status, r.duplicate_of, r.is_anonymized
    FROM result r LEFT JOIN result_athlete l ON l.result_id=r.id
"""


def upgrade() -> None:
    op.execute(EVENT_VIEW + """
        WHERE (c.status <> 'cancelled' OR c.canonical_competition_id IS NULL)
          AND (NOT EXISTS (SELECT 1 FROM race WHERE competition_id=c.id)
               OR EXISTS (SELECT 1 FROM race
                          WHERE competition_id=c.id AND superseded_by_race_id IS NULL))
    """)
    op.execute(RACE_VIEW + """
        WHERE superseded_by_race_id IS NULL
          AND EXISTS (SELECT 1 FROM web_event e WHERE e.id=race.competition_id)
    """)
    op.execute(RESULT_VIEW + """
        JOIN web_race ra ON ra.id=r.race_id
    """)


def downgrade() -> None:
    op.execute(RESULT_VIEW)
    op.execute(RACE_VIEW)
    op.execute(EVENT_VIEW)

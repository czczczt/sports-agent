"""Store source-specific protocol metadata without changing legacy imports."""
from alembic import op

revision = "20261121_08"
down_revision = "20261120_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE competition ADD COLUMN primary_protocol_url text,
            ADD COLUMN collection_canonical boolean NOT NULL DEFAULT false;
        CREATE INDEX competition_primary_protocol_url ON competition (primary_protocol_url)
            WHERE primary_protocol_url IS NOT NULL;
        ALTER TABLE race ADD COLUMN sport_type text, ADD COLUMN source_url text,
            ADD COLUMN source_discipline text, ADD COLUMN IF NOT EXISTS elevation_gain_m double precision, ADD COLUMN season text, ADD COLUMN series text;
        ALTER TABLE result ADD COLUMN source_profile_id text, ADD COLUMN position_age_group integer,
            ADD COLUMN official_time_s double precision,
            ADD COLUMN collection_review boolean NOT NULL DEFAULT false,
            ADD COLUMN collection_duplicate boolean NOT NULL DEFAULT false;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE result DROP COLUMN collection_duplicate, DROP COLUMN collection_review, DROP COLUMN position_age_group, DROP COLUMN source_profile_id, DROP COLUMN official_time_s;
        -- Keep the shared field when the captain-moderation branch is still applied.
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_attribute WHERE attrelid = 'race'::regclass
                  AND attname = 'sport' AND NOT attisdropped
            ) THEN
                ALTER TABLE race DROP COLUMN IF EXISTS elevation_gain_m;
            END IF;
        END $$;
        ALTER TABLE race DROP COLUMN series, DROP COLUMN season,
            DROP COLUMN source_url, DROP COLUMN sport_type, DROP COLUMN source_discipline;
        ALTER TABLE competition DROP COLUMN collection_canonical, DROP COLUMN primary_protocol_url;
    """)

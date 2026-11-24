"""Persist collection batches and approval state separately from published protocols."""

from alembic import op

revision = "20261125_14"
down_revision = "20261124_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE bulk_batch (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            publication_status text NOT NULL DEFAULT 'pending',
            publication_error text
        );

        CREATE TABLE bulk_source (
            batch_id bigint NOT NULL REFERENCES bulk_batch(id) ON DELETE CASCADE,
            source_id integer NOT NULL REFERENCES source(id),
            status text NOT NULL CHECK (status IN ('queued','running','completed','failed','unsupported','disabled')),
            error text,
            is_automatic boolean NOT NULL,
            scan_until timestamptz,
            catalog jsonb,
            PRIMARY KEY (batch_id, source_id)
        );

        CREATE TABLE bulk_draft (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            batch_id bigint NOT NULL,
            source_id integer NOT NULL,
            event_code text NOT NULL,
            status text NOT NULL CHECK (status IN ('queued','running','ready','failed','approved','unchanged')),
            error text,
            payload jsonb,
            payload_hash text,
            summary jsonb,
            approved_at timestamptz,
            resolved_races jsonb NOT NULL DEFAULT '{}'::jsonb,
            FOREIGN KEY (batch_id, source_id) REFERENCES bulk_source(batch_id, source_id) ON DELETE CASCADE,
            UNIQUE (batch_id, source_id, event_code)
        );
        CREATE INDEX bulk_draft_previous_idx ON bulk_draft (source_id, event_code, id DESC)
            WHERE status IN ('ready','approved');

        CREATE TABLE bulk_watermark (
            source_id integer PRIMARY KEY REFERENCES source(id),
            scanned_until timestamptz NOT NULL,
            catalog jsonb NOT NULL
        );

        CREATE TABLE bulk_approval (
            batch_id bigint NOT NULL REFERENCES bulk_batch(id) ON DELETE CASCADE,
            request_key text NOT NULL,
            result jsonb NOT NULL,
            PRIMARY KEY (batch_id, request_key)
        );

        ALTER TABLE race ADD COLUMN superseded_by_race_id integer REFERENCES race(id) ON DELETE SET NULL;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE race DROP COLUMN superseded_by_race_id;
        DROP TABLE bulk_approval, bulk_watermark, bulk_draft, bulk_source, bulk_batch;
    """)

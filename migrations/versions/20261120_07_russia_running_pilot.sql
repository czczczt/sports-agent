CREATE TABLE pilot_run (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id integer NOT NULL REFERENCES source(id),
    event_code text NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    phase text NOT NULL DEFAULT 'queued',
    processed_distances integer NOT NULL DEFAULT 0 CHECK (processed_distances >= 0),
    error text,
    rating_version_id bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX pilot_one_active_run ON pilot_run(source_id) WHERE status IN ('queued', 'running');
CREATE TABLE rating_version (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL UNIQUE REFERENCES pilot_run(id),
    formula_version text NOT NULL,
    period_start text NOT NULL,
    period_end text NOT NULL,
    athlete_count integer NOT NULL CHECK (athlete_count > 0),
    published_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE pilot_run ADD CONSTRAINT pilot_run_rating_version_fk FOREIGN KEY (rating_version_id) REFERENCES rating_version(id);
CREATE TABLE rating_version_row (
    version_id bigint NOT NULL REFERENCES rating_version(id),
    athlete_id bigint NOT NULL,
    display_name text NOT NULL,
    birth_year integer,
    gender text,
    name_key text NOT NULL,
    points double precision NOT NULL,
    best_points double precision,
    starts_count integer NOT NULL,
    rank integer NOT NULL,
    PRIMARY KEY (version_id, athlete_id)
);
CREATE TABLE rating_publication (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    version_id bigint REFERENCES rating_version(id)
);

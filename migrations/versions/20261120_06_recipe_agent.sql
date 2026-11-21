CREATE TABLE recipe (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id integer NOT NULL UNIQUE REFERENCES source(id),
    UNIQUE (id, source_id)
);

CREATE TABLE recipe_repair (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recipe_id bigint NOT NULL,
    source_id integer NOT NULL,
    issue_id integer REFERENCES issue(id) ON DELETE SET NULL,
    samples jsonb NOT NULL,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'waiting', 'activated', 'unchanged', 'rejected', 'stale')),
    requested_by text NOT NULL,
    review jsonb,
    state jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (recipe_id, source_id) REFERENCES recipe(id, source_id)
);

CREATE UNIQUE INDEX recipe_one_open_repair ON recipe_repair (source_id)
    WHERE status IN ('running', 'waiting');

CREATE TABLE recipe_version (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recipe_id bigint NOT NULL,
    source_id integer NOT NULL,
    repair_id bigint NOT NULL UNIQUE REFERENCES recipe_repair(id),
    version integer NOT NULL CHECK (version > 0),
    body jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'active', 'retired', 'rejected')),
    golden_score integer NOT NULL,
    tokens_used integer NOT NULL,
    activated_at timestamptz,
    FOREIGN KEY (recipe_id, source_id) REFERENCES recipe(id, source_id),
    UNIQUE (recipe_id, version)
);

CREATE UNIQUE INDEX recipe_one_active_version ON recipe_version(source_id)
    WHERE status = 'active';

CREATE TABLE golden_case (
    source_id integer NOT NULL REFERENCES source(id),
    raw_id bigint NOT NULL REFERENCES raw(id),
    place_by text NOT NULL CHECK (place_by IN ('chip', 'gun')),
    expected_count integer NOT NULL CHECK (expected_count > 0),
    expected_digest text NOT NULL CHECK (length(expected_digest) = 64),
    PRIMARY KEY (source_id, raw_id)
);

ALTER TABLE result ADD COLUMN recipe_id bigint REFERENCES recipe_version(id);
CREATE INDEX result_recipe ON result(recipe_id) WHERE recipe_id IS NOT NULL;


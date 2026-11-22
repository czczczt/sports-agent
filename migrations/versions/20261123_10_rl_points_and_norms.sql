-- 1. Таблица очков Russialoppet (SPEC v1.3 §5, §9.2)
CREATE TABLE IF NOT EXISTS rl_points (
    athlete_id INTEGER NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    rl_season TEXT NOT NULL,
    points DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (athlete_id, rl_season)
);
CREATE INDEX IF NOT EXISTS idx_rl_points_athlete_id ON rl_points(athlete_id);
CREATE INDEX IF NOT EXISTS idx_rl_points_season ON rl_points(rl_season);

-- 2. Таблица нормативов бега по годам (SPEC v1.3 §5 RunNorm)
CREATE TABLE IF NOT EXISTS run_norm (
    year INTEGER NOT NULL,
    distance_class TEXT NOT NULL,
    gender TEXT NOT NULL CHECK (gender IN ('M', 'F')),
    value DOUBLE PRECISION NOT NULL CHECK (value > 0),
    unit TEXT NOT NULL CHECK (unit IN ('s', 'km')),
    PRIMARY KEY (year, distance_class, gender)
);
CREATE INDEX IF NOT EXISTS idx_run_norm_year_class ON run_norm(year, distance_class);


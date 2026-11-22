-- 1. Таблица агрегированного рейтинга по видам спорта и периодам (SPEC v1.3 §5 RatingEntry)
CREATE TABLE IF NOT EXISTS rating_entry (
    sport TEXT NOT NULL,
    period_type TEXT NOT NULL DEFAULT 'rolling',
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    athlete_id INTEGER NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    formula_version TEXT NOT NULL,
    points DOUBLE PRECISION NOT NULL,
    best_points DOUBLE PRECISION NOT NULL,
    starts_count INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    PRIMARY KEY (sport, period_type, period_start, period_end, athlete_id)
);
CREATE INDEX IF NOT EXISTS idx_rating_entry_lookup
    ON rating_entry(sport, period_type, period_end, rank);
CREATE INDEX IF NOT EXISTS idx_rating_entry_athlete
    ON rating_entry(athlete_id);

-- 2. Таблица снимков рейтинга для динамики места ▲▼ (SPEC v1.3 §5 RatingSnapshot)
CREATE TABLE IF NOT EXISTS rating_snapshot (
    sport TEXT NOT NULL,
    taken_on DATE NOT NULL,
    athlete_id INTEGER NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    points DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (sport, taken_on, athlete_id)
);
CREATE INDEX IF NOT EXISTS idx_rating_snapshot_lookup
    ON rating_snapshot(sport, taken_on, athlete_id);

-- 3. Синхронизация данных из running_athlete_rating в rating_entry
INSERT INTO rating_entry (
    sport, period_type, period_start, period_end,
    athlete_id, formula_version, points, best_points, starts_count, rank
)
SELECT
    'run', 'rolling', period_start, period_end,
    athlete_id, formula_version, points, best_points, starts_count, rank
FROM running_athlete_rating
ON CONFLICT (sport, period_type, period_start, period_end, athlete_id) DO UPDATE SET
    points = EXCLUDED.points,
    best_points = EXCLUDED.best_points,
    starts_count = EXCLUDED.starts_count,
    rank = EXCLUDED.rank;

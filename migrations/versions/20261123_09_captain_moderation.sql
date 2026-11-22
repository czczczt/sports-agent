-- 1. Таблица привязки видов спорта к капитану (SPEC v1.3 §2, §5)
CREATE TABLE IF NOT EXISTS captain_sport (
    user_id integer NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    sport text NOT NULL,
    PRIMARY KEY (user_id, sport)
);
CREATE INDEX IF NOT EXISTS idx_captain_sport_user_id ON captain_sport(user_id);

-- 2. Модерационные поля дистанции/старта (SPEC v1.3 §5, §8.5, §9)
ALTER TABLE race
    ADD COLUMN IF NOT EXISTS sport text,
    ADD COLUMN IF NOT EXISTS scoring_class text,
    ADD COLUMN IF NOT EXISTS elevation_gain_m double precision,
    ADD COLUMN IF NOT EXISTS is_rl_series boolean DEFAULT false,
    ADD COLUMN IF NOT EXISTS special text DEFAULT 'regular';

CREATE INDEX IF NOT EXISTS idx_race_sport ON race(sport);
CREATE INDEX IF NOT EXISTS idx_race_scoring_class ON race(scoring_class);

-- 3. Таблица системных настроек (SPEC v1.3 §5, §11)
CREATE TABLE IF NOT EXISTS setting (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz DEFAULT now(),
    updated_by integer REFERENCES app_user(id) ON DELETE SET NULL
);

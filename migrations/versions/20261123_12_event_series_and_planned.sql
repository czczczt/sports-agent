-- 1. Таблица серий соревнований (SPEC v1.3 §5 EventSeries)
CREATE TABLE IF NOT EXISTS event_series (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    name_norm TEXT NOT NULL,
    city TEXT,
    sport TEXT NOT NULL DEFAULT 'run',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_event_series_norm ON event_series(name_norm, city, sport);

-- 2. Модификация таблицы competition для поддержки статусов и серий
ALTER TABLE competition
    ADD COLUMN IF NOT EXISTS series_id INTEGER REFERENCES event_series(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'done' CHECK (status IN ('planned', 'done', 'cancelled')),
    ADD COLUMN IF NOT EXISTS planned_date_start DATE,
    ADD COLUMN IF NOT EXISTS planned_date_end DATE,
    ADD COLUMN IF NOT EXISTS planned_note TEXT,
    ADD COLUMN IF NOT EXISTS sport TEXT DEFAULT 'run',
    ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES app_user(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS possible_duplicate_id INTEGER REFERENCES competition(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_competition_series_id ON competition(series_id);
CREATE INDEX IF NOT EXISTS idx_competition_status ON competition(status);
CREATE INDEX IF NOT EXISTS idx_competition_duplicate_id ON competition(possible_duplicate_id);

-- 3. Обновление представления web_event
DROP VIEW IF EXISTS web_event;
CREATE VIEW web_event AS
SELECT c.id, c.source_id, c.name AS title, c.date_begin::text, c.date_end::text,
       c.location AS place, c.address,
       COALESCE(c.status, 'done') AS status,
       COALESCE(c.sport, 'run') AS sport,
       c.series_id,
       es.name AS series_name,
       c.possible_duplicate_id
FROM competition c
LEFT JOIN event_series es ON es.id = c.series_id;

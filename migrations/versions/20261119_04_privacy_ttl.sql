ALTER TABLE result ADD COLUMN IF NOT EXISTS is_anonymized boolean DEFAULT false;
ALTER TABLE raw ADD COLUMN IF NOT EXISTS purged_at timestamptz;
CREATE INDEX IF NOT EXISTS idx_raw_fetched_at ON raw(fetched_at);
CREATE INDEX IF NOT EXISTS idx_raw_purged_at ON raw(purged_at);
CREATE INDEX IF NOT EXISTS idx_result_is_anonymized ON result(is_anonymized);

CREATE OR REPLACE VIEW web_result AS
SELECT r.id, r.id AS result_id, r.race_id, l.athlete_id, r.bib, r.full_name_raw, r.gender, r.age, r.birth_year, r.club_raw,
       r.position AS place_abs, r.position_gender AS place_gender, r.chip_time_s, r.gun_time_s,
       r.status, r.duplicate_of, r.is_anonymized
FROM result r
LEFT JOIN result_athlete l ON l.result_id = r.id;

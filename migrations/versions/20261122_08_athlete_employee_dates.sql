ALTER TABLE athlete
    ADD COLUMN IF NOT EXISTS employee_since date,
    ADD COLUMN IF NOT EXISTS employee_until date;

CREATE INDEX IF NOT EXISTS idx_athlete_employee_dates
    ON athlete (employee_since, employee_until);

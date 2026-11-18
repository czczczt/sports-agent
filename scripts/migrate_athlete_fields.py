"""Скрипт миграции схемы базы данных под SPEC v1.3:
1. Добавляет в таблицу athlete поля:
   - first_name, last_name, middle_name (раздельное ФИО)
   - birth_date (точная дата рождения)
   - employee_status (presumed, confirmed, not_employee; по умолчанию presumed)
   - is_hidden (скрытие спортсмена из выдачи)
2. Заполняет first_name, last_name, middle_name из display_name.
3. Создаёт таблицу report (заявки пользователей: not_me, add_start, hide_me и др.).
"""
import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/sports_agent")

def run_migration():
    print(f"Connecting to database: {DATABASE_URL}")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            print("1. Adding columns to athlete table...")
            cur.execute("""
                ALTER TABLE athlete 
                ADD COLUMN IF NOT EXISTS first_name TEXT,
                ADD COLUMN IF NOT EXISTS last_name TEXT,
                ADD COLUMN IF NOT EXISTS middle_name TEXT,
                ADD COLUMN IF NOT EXISTS birth_date TEXT,
                ADD COLUMN IF NOT EXISTS employee_status VARCHAR(20) DEFAULT 'presumed',
                ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT FALSE;
            """)

            print("2. Populating first_name, last_name, middle_name from display_name...")
            cur.execute("""
                UPDATE athlete
                SET 
                    last_name = split_part(regexp_replace(trim(display_name), '\\s+', ' ', 'g'), ' ', 1),
                    first_name = split_part(regexp_replace(trim(display_name), '\\s+', ' ', 'g'), ' ', 2),
                    middle_name = NULLIF(trim(substring(regexp_replace(trim(display_name), '\\s+', ' ', 'g') from '^\\S+\\s+\\S+\\s+(.*)$')), ''),
                    employee_status = COALESCE(employee_status, 'presumed'),
                    is_hidden = COALESCE(is_hidden, FALSE)
                WHERE last_name IS NULL OR first_name IS NULL;
            """)
            print(f"   Updated {cur.rowcount} athlete rows.")

            print("3. Creating indexes...")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_athlete_last_name ON athlete(last_name);
                CREATE INDEX IF NOT EXISTS idx_athlete_first_name ON athlete(first_name);
                CREATE INDEX IF NOT EXISTS idx_athlete_employee_status ON athlete(employee_status);
                CREATE INDEX IF NOT EXISTS idx_athlete_is_hidden ON athlete(is_hidden);
            """)

            print("4. Creating report table for user tickets...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS report (
                    id SERIAL PRIMARY KEY,
                    kind VARCHAR(50) NOT NULL,
                    user_id INT,
                    athlete_id INT,
                    result_id INT,
                    event_id INT,
                    url TEXT,
                    message TEXT,
                    status VARCHAR(20) DEFAULT 'new',
                    decided_by TEXT,
                    decided_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_report_status ON report(status);
                CREATE INDEX IF NOT EXISTS idx_report_kind ON report(kind);
            """)

            conn.commit()
            print("Migration completed successfully!")

if __name__ == "__main__":
    run_migration()

"""Миграция БД: расширение полей app_user, report и создание audit_log по SPEC v1.3 §5, §8.4, §8.6."""
import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/sports_agent")


def migrate():
    print("Running migration for requests schema...")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # 1. Расширение таблицы app_user
            print("1. Upgrading app_user table...")
            cur.execute("""
                ALTER TABLE app_user 
                    ADD COLUMN IF NOT EXISTS first_name VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS last_name VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS middle_name VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS birth_date DATE,
                    ADD COLUMN IF NOT EXISTS city VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS consent_at TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS consent_version VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS approved_by INT REFERENCES app_user(id) ON DELETE SET NULL,
                    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS failed_logins INT DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

                CREATE INDEX IF NOT EXISTS idx_app_user_status ON app_user(status);
                CREATE INDEX IF NOT EXISTS idx_app_user_role ON app_user(role);
            """)

            # 2. Доработка таблицы report
            print("2. Upgrading report table...")
            cur.execute("""
                ALTER TABLE report 
                    ADD COLUMN IF NOT EXISTS moderator_comment TEXT,
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

                CREATE INDEX IF NOT EXISTS idx_report_status ON report(status);
                CREATE INDEX IF NOT EXISTS idx_report_kind ON report(kind);
                CREATE INDEX IF NOT EXISTS idx_report_user_id ON report(user_id);
                CREATE INDEX IF NOT EXISTS idx_report_athlete_id ON report(athlete_id);
            """)

            # Безопасное добавление внешних ключей к report, если ещё не добавлены
            try:
                cur.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'fk_report_user'
                        ) THEN
                            ALTER TABLE report ADD CONSTRAINT fk_report_user FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE SET NULL;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'fk_report_athlete'
                        ) THEN
                            ALTER TABLE report ADD CONSTRAINT fk_report_athlete FOREIGN KEY (athlete_id) REFERENCES athlete(id) ON DELETE SET NULL;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'fk_report_result'
                        ) THEN
                            ALTER TABLE report ADD CONSTRAINT fk_report_result FOREIGN KEY (result_id) REFERENCES result(id) ON DELETE SET NULL;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'fk_report_event'
                        ) THEN
                            ALTER TABLE report ADD CONSTRAINT fk_report_event FOREIGN KEY (event_id) REFERENCES event(id) ON DELETE SET NULL;
                        END IF;
                    END $$;
                """)
            except Exception as e:
                print(f"Notice on constraints: {e}")

            # 3. Создание audit_log (SPEC v1.3 §5, line 356)
            print("3. Creating audit_log table...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    user_id INT REFERENCES app_user(id) ON DELETE SET NULL,
                    action VARCHAR(100) NOT NULL,
                    entity VARCHAR(50) NOT NULL,
                    entity_id INT,
                    diff JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity, entity_id);
                CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
            """)

            conn.commit()
            print("Migration completed successfully!")


if __name__ == "__main__":
    migrate()

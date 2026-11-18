"""Создание таблицы app_user и сидирование учетных записей user и admin с хэшированием argon2."""
import os
import psycopg
from argon2 import PasswordHasher

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/sports_agent")

def init_users():
    ph = PasswordHasher()
    print("Hashing passwords with Argon2...")
    user_hash = ph.hash("user")
    admin_hash = ph.hash("admin")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            print("Creating app_user table...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_user (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE,
                    password_hash TEXT NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'user',
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    display_name TEXT,
                    athlete_id INT REFERENCES athlete(id) ON DELETE SET NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_app_user_username ON app_user(username);
                CREATE INDEX IF NOT EXISTS idx_app_user_status ON app_user(status);
            """)

            print("Seeding user and admin accounts...")
            cur.execute("""
                INSERT INTO app_user (username, email, password_hash, role, status, display_name)
                VALUES 
                    ('user', 'user@sberbank.ru', %s, 'user', 'active', 'Пользователь'),
                    ('admin', 'admin@sberbank.ru', %s, 'admin', 'active', 'Администратор')
                ON CONFLICT (username) DO UPDATE 
                SET password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role,
                    status = EXCLUDED.status,
                    display_name = EXCLUDED.display_name;
            """, (user_hash, admin_hash))

            conn.commit()
            print("Users seeded successfully!")

if __name__ == "__main__":
    init_users()

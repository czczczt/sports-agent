import psycopg
from argon2 import PasswordHasher

from app.config import DATABASE_URL

hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)


def seed():
    with psycopg.connect(DATABASE_URL) as connection:
        for username, role, display in (
            ("admin", "admin", "Администратор"),
            ("user", "user", "Пользователь"),
            ("captain", "captain", "Капитан"),
        ):
            connection.execute(
                """
                INSERT INTO app_user(username, email, password_hash, role, status, display_name)
                VALUES (%s, %s, %s, %s, 'active', %s)
                ON CONFLICT (username) DO NOTHING
                """,
                (
                    username,
                    f"{username}@example.test",
                    hasher.hash(username),
                    role,
                    display,
                ),
            )
        connection.commit()


if __name__ == "__main__":
    seed()

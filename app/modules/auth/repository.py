from app.core.repository import ReadRepository


class AuthRepository(ReadRepository):
    async def user_by_username(self, username):
        return await self.row(
            """
            SELECT id, username, role, status, display_name, athlete_id
            FROM app_user
            WHERE username = :username
        """,
            {"username": username},
        )

    async def athlete_employee_status(self, athlete_id):
        return await self.scalar(
            "SELECT employee_status FROM athlete WHERE id = :athlete_id",
            {"athlete_id": athlete_id},
        )

    async def block_user(self, user_id):
        return await self.execute(
            "UPDATE app_user SET status = 'blocked' WHERE id = :user_id",
            {"user_id": user_id},
        )

    async def login_user(self, username, email):
        return await self.row(
            """
            SELECT id, username, password_hash, role, status, display_name, athlete_id
            FROM app_user
            WHERE username = :username OR email = :email
        """,
            {"username": username, "email": email},
        )

    async def login_employee_status(self, athlete_id):
        return await self.scalar(
            "SELECT employee_status FROM athlete WHERE id = :athlete_id",
            {"athlete_id": athlete_id},
        )

    async def block_login_user(self, user_id):
        return await self.execute(
            "UPDATE app_user SET status = 'blocked' WHERE id = :user_id",
            {"user_id": user_id},
        )

    async def registration_exists(self, username, email):
        return await self.row(
            "SELECT id FROM app_user WHERE username = :username OR email = :email",
            {"username": username, "email": email},
        )

    async def create_registration(
        self,
        username,
        email,
        password_hash,
        display_name,
        first_name,
        last_name,
        middle_name,
        birth_date,
        city,
        consent_version,
    ):
        return await self.row(
            """
            INSERT INTO app_user (
                username, email, password_hash, role, status, display_name,
                first_name, last_name, middle_name, birth_date, city,
                consent_at, consent_version
            )
            VALUES (:username, :email, :password_hash, 'user', 'pending', :display_name, :first_name, :last_name, :middle_name, :birth_date, :city, NOW(), :consent_version)
            RETURNING id, username, email, role, status, display_name, created_at
        """,
            {
                "username": username,
                "email": email,
                "password_hash": password_hash,
                "display_name": display_name,
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "birth_date": birth_date,
                "city": city,
                "consent_version": consent_version,
            },
        )

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
            SELECT id, username, email, password_hash, role, status, display_name, athlete_id,
                   failed_logins, locked_until
            FROM app_user
            WHERE username = :username OR email = :email
        """,
            {"username": username, "email": email},
        )

    async def record_failed_login(self, user_id, max_attempts=5, lockout_minutes=15):
        return await self.row(
            """
            UPDATE app_user
            SET failed_logins = COALESCE(failed_logins, 0) + 1,
                locked_until = CASE
                    WHEN COALESCE(failed_logins, 0) + 1 >= :max_attempts
                    THEN NOW() + (:lockout_minutes || ' minutes')::interval
                    ELSE locked_until
                END
            WHERE id = :user_id
            RETURNING failed_logins, locked_until
        """,
            {
                "user_id": user_id,
                "max_attempts": max_attempts,
                "lockout_minutes": str(lockout_minutes),
            },
        )

    async def reset_failed_logins(self, user_id):
        await self.execute(
            """
            UPDATE app_user
            SET failed_logins = 0, locked_until = NULL
            WHERE id = :user_id
        """,
            {"user_id": user_id},
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

    async def is_token_revoked(self, token_hash: str) -> bool:
        val = await self.scalar(
            "SELECT 1 FROM revoked_token WHERE token_hash = :token_hash AND expires_at > NOW()",
            {"token_hash": token_hash},
        )
        return val is not None

    async def revoke_token(self, token_hash: str, expires_at):
        await self.execute(
            """
            INSERT INTO revoked_token (token_hash, expires_at)
            VALUES (:token_hash, :expires_at)
            ON CONFLICT (token_hash) DO NOTHING
        """,
            {"token_hash": token_hash, "expires_at": expires_at},
        )

    async def user_by_email(self, email: str):
        return await self.row(
            "SELECT id, username, email, status FROM app_user WHERE email = :email",
            {"email": email},
        )

    async def create_password_reset_token(
        self, user_id: int, token_hash: str, expires_at
    ):
        await self.execute(
            """
            INSERT INTO password_reset_token (user_id, token_hash, expires_at)
            VALUES (:user_id, :token_hash, :expires_at)
        """,
            {"user_id": user_id, "token_hash": token_hash, "expires_at": expires_at},
        )

    async def get_valid_reset_token(self, token_hash: str):
        return await self.row(
            """
            SELECT id, user_id, expires_at, used_at
            FROM password_reset_token
            WHERE token_hash = :token_hash
              AND used_at IS NULL
              AND expires_at > NOW()
        """,
            {"token_hash": token_hash},
        )

    async def mark_reset_token_used(self, token_id: int):
        await self.execute(
            "UPDATE password_reset_token SET used_at = NOW() WHERE id = :token_id",
            {"token_id": token_id},
        )

    async def update_user_password(self, user_id: int, password_hash: str):
        await self.execute(
            """
            UPDATE app_user
            SET password_hash = :password_hash,
                failed_logins = 0,
                locked_until = NULL,
                updated_at = NOW()
            WHERE id = :user_id
        """,
            {"user_id": user_id, "password_hash": password_hash},
        )

    async def log_audit(
        self,
        user_id: int | None,
        action: str,
        entity: str,
        entity_id: int | None = None,
        diff: str | None = None,
    ):
        await self.execute(
            """
            INSERT INTO audit_log (user_id, action, entity, entity_id, diff, created_at)
            VALUES (:user_id, :action, :entity, :entity_id, CAST(:diff AS jsonb), NOW())
        """,
            {
                "user_id": user_id,
                "action": action,
                "entity": entity,
                "entity_id": entity_id,
                "diff": diff or "{}",
            },
        )

class AuthService:
    def __init__(self, repository):
        self.repository = repository

    async def commit(self):
        await self.repository.session.commit()

    async def user_by_username(self, username):
        return await self.repository.user_by_username(username)

    async def athlete_employee_status(self, athlete_id):
        return await self.repository.athlete_employee_status(athlete_id)

    async def block_user(self, user_id):
        return await self.repository.block_user(user_id)

    async def login_user(self, username, email):
        return await self.repository.login_user(username, email)

    async def record_failed_login(self, user_id, max_attempts=5, lockout_minutes=15):
        return await self.repository.record_failed_login(
            user_id, max_attempts, lockout_minutes
        )

    async def reset_failed_logins(self, user_id):
        return await self.repository.reset_failed_logins(user_id)

    async def login_employee_status(self, athlete_id):
        return await self.repository.login_employee_status(athlete_id)

    async def block_login_user(self, user_id):
        return await self.repository.block_login_user(user_id)

    async def registration_exists(self, username, email):
        return await self.repository.registration_exists(username, email)

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
        return await self.repository.create_registration(
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
        )

    async def is_token_revoked(self, token_hash: str) -> bool:
        return await self.repository.is_token_revoked(token_hash)

    async def revoke_token(self, token_hash: str, expires_at):
        return await self.repository.revoke_token(token_hash, expires_at)

    async def user_by_email(self, email: str):
        return await self.repository.user_by_email(email)

    async def create_password_reset_token(
        self, user_id: int, token_hash: str, expires_at
    ):
        return await self.repository.create_password_reset_token(
            user_id, token_hash, expires_at
        )

    async def get_valid_reset_token(self, token_hash: str):
        return await self.repository.get_valid_reset_token(token_hash)

    async def mark_reset_token_used(self, token_id: int):
        return await self.repository.mark_reset_token_used(token_id)

    async def update_user_password(self, user_id: int, password_hash: str):
        return await self.repository.update_user_password(user_id, password_hash)

    async def log_audit(
        self,
        user_id: int | None,
        action: str,
        entity: str,
        entity_id: int | None = None,
        diff: str | None = None,
    ):
        return await self.repository.log_audit(user_id, action, entity, entity_id, diff)

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

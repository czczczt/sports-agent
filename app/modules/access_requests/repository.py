from app.core.repository import ReadRepository


class AccessRequestsRepository(ReadRepository):
    async def list_by_status(self, status):
        return await self.rows(
            """
            SELECT id, username, email, role, status, first_name, last_name, middle_name,
                   birth_date, city, athlete_id, created_at
            FROM app_user
            WHERE status = :status
            ORDER BY id ASC
        """,
            {"status": status},
        )

    async def list_all(self):
        return await self.rows(
            """
            SELECT id, username, email, role, status, first_name, last_name, middle_name,
                   birth_date, city, athlete_id, created_at
            FROM app_user
            ORDER BY id ASC
        """,
            {},
        )

    async def get_linked_athlete(self, athlete_id):
        return await self.row(
            "SELECT id, display_name FROM athlete WHERE id = :athlete_id",
            {"athlete_id": athlete_id},
        )

    async def match_athlete_year(self, pattern, year_from, year_to):
        return await self.row(
            """
            SELECT id, display_name
            FROM athlete
            WHERE name_key LIKE :pattern
              AND birth_year BETWEEN :year_from - 1 AND :year_to + 1
            ORDER BY starts_count DESC
            LIMIT 1
        """,
            {"pattern": pattern, "year_from": year_from, "year_to": year_to},
        )

    async def match_athlete(self, pattern):
        return await self.row(
            """
            SELECT id, display_name
            FROM athlete
            WHERE name_key LIKE :pattern
            ORDER BY starts_count DESC
            LIMIT 1
        """,
            {"pattern": pattern},
        )

    async def get_user(self, user_id):
        return await self.row(
            "SELECT * FROM app_user WHERE id = :user_id", {"user_id": user_id}
        )

    async def update_decision(self, status, athlete_id, moderator_id, user_id):
        return await self.row(
            """
            UPDATE app_user
            SET status = :status,
                athlete_id = COALESCE(:athlete_id, athlete_id),
                approved_by = :moderator_id,
                approved_at = NOW(),
                updated_at = NOW()
            WHERE id = :user_id
            RETURNING id, username, email, role, status, first_name, last_name, middle_name,
                      birth_date, city, athlete_id, created_at
        """,
            {
                "status": status,
                "athlete_id": athlete_id,
                "moderator_id": moderator_id,
                "user_id": user_id,
            },
        )

    async def audit_decision(self, user_id, action, entity_id, diff):
        return await self.execute(
            """
            INSERT INTO audit_log (user_id, action, entity, entity_id, diff)
            VALUES (:user_id, :action, 'app_user', :entity_id, :diff)
        """,
            {
                "user_id": user_id,
                "action": action,
                "entity_id": entity_id,
                "diff": diff,
            },
        )

    async def get_athlete(self, athlete_id):
        return await self.row(
            "SELECT id, employee_status FROM athlete WHERE id = :athlete_id",
            {"athlete_id": athlete_id},
        )

    async def mark_presumed(self, athlete_id):
        return await self.execute(
            "UPDATE athlete SET employee_status = 'presumed' WHERE id = :athlete_id",
            {"athlete_id": athlete_id},
        )

    async def create_athlete_from_user(self, user_row) -> int:
        first = (user_row["first_name"] or "").strip()
        last = (user_row["last_name"] or "").strip()
        middle = (user_row["middle_name"] or "").strip() or None
        display = f"{last} {first}".strip() or user_row["username"]
        import re

        tokens = sorted(re.findall(r"[a-zа-я0-9]+", display.lower().replace("ё", "е")))
        name_key = " ".join(tokens)
        birth_year = user_row["birth_date"].year if user_row["birth_date"] else None

        row = await self.row(
            """
            INSERT INTO athlete (display_name, first_name, last_name, middle_name, birth_date, birth_year, city, employee_status, is_hidden, name_key)
            VALUES (:display_name, :first_name, :last_name, :middle_name, :birth_date, :birth_year, :city, 'presumed', FALSE, :name_key)
            RETURNING id
            """,
            {
                "display_name": display,
                "first_name": first or None,
                "last_name": last or None,
                "middle_name": middle,
                "birth_date": user_row["birth_date"],
                "birth_year": birth_year,
                "city": user_row["city"],
                "name_key": name_key,
            },
        )
        return row["id"]

    async def candidates(self, ids, patterns):
        return await self.rows(
            """
            SELECT id, display_name, name_key, birth_year, starts_count FROM athlete
            WHERE id = ANY(CAST(:ids AS bigint[]))
               OR name_key LIKE ANY(CAST(:patterns AS text[]))
            ORDER BY starts_count DESC, id
        """,
            {"ids": ids, "patterns": patterns},
        )

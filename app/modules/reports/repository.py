from app.core.repository import ReadRepository


class ReportsRepository(ReadRepository):
    async def find_pending_link_claim(self, user_id):
        return await self.row(
            """
            SELECT id, athlete_id
            FROM report
            WHERE kind = 'link_me'
              AND user_id = :user_id
              AND status NOT IN ('accepted', 'resolved', 'rejected')
            LIMIT 1
        """,
            {"user_id": user_id},
        )

    async def create(
        self, kind, user_id, athlete_id, result_id, event_id, url, message
    ):
        return await self.row(
            """
            INSERT INTO report (kind, user_id, athlete_id, result_id, event_id, url, message, status)
            VALUES (:kind, :user_id, :athlete_id, :result_id, :event_id, :url, :message, 'new')
            RETURNING id, kind, user_id, athlete_id, result_id, event_id, url, message, status, decided_by, decided_at, moderator_comment, created_at, updated_at
        """,
            {
                "kind": kind,
                "user_id": user_id,
                "athlete_id": athlete_id,
                "result_id": result_id,
                "event_id": event_id,
                "url": url,
                "message": message,
            },
        )

    async def list_by_status(self, status):
        return await self.rows(
            """
            SELECT id, kind, user_id, athlete_id, result_id, event_id, url, message,
                   status, decided_by, decided_at, moderator_comment, created_at, updated_at
            FROM report
            WHERE status = :status
            ORDER BY id DESC
        """,
            {"status": status},
        )

    async def list_all(self):
        return await self.rows(
            """
            SELECT id, kind, user_id, athlete_id, result_id, event_id, url, message,
                   status, decided_by, decided_at, moderator_comment, created_at, updated_at
            FROM report
            ORDER BY id DESC
        """,
            {},
        )

    async def list_by_user(self, user_id):
        return await self.rows(
            """
            SELECT id, kind, user_id, athlete_id, result_id, event_id, url, message,
                   status, decided_by, decided_at, moderator_comment, created_at, updated_at
            FROM report
            WHERE user_id = :user_id
            ORDER BY id DESC
        """,
            {"user_id": user_id},
        )

    async def get_report(self, report_id):
        return await self.row(
            "SELECT * FROM report WHERE id = :report_id", {"report_id": report_id}
        )

    async def update_decision(self, decision, moderator_id, comment, report_id):
        return await self.row(
            """
            UPDATE report
            SET status = :decision,
                decided_by = :moderator_id,
                decided_at = NOW(),
                moderator_comment = :comment,
                updated_at = NOW()
            WHERE id = :report_id
            RETURNING id, kind, user_id, athlete_id, result_id, event_id, url, message,
                      status, decided_by, decided_at, moderator_comment, created_at, updated_at
        """,
            {
                "decision": decision,
                "moderator_id": moderator_id,
                "comment": comment,
                "report_id": report_id,
            },
        )

    async def audit_decision(self, user_id, report_id, diff):
        return await self.execute(
            """
            INSERT INTO audit_log (user_id, action, entity, entity_id, diff)
            VALUES (:user_id, 'report_decision', 'report', :report_id, :diff)
        """,
            {"user_id": user_id, "report_id": report_id, "diff": diff},
        )

    async def hide_athlete(self, athlete_id):
        return await self.execute(
            "UPDATE athlete SET is_hidden = TRUE WHERE id = :athlete_id",
            {"athlete_id": athlete_id},
        )

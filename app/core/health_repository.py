from app.core.repository import ReadRepository


class HealthRepository(ReadRepository):
    async def ready(self) -> bool:
        row = await self.row("""
            SELECT to_regclass('competition') IS NOT NULL
               AND to_regclass('race') IS NOT NULL
               AND to_regclass('result') IS NOT NULL
               AND to_regclass('result_athlete') IS NOT NULL
               AND to_regclass('web_result') IS NOT NULL
               AND to_regclass('web_event') IS NOT NULL
               AND to_regclass('web_race') IS NOT NULL
               AND to_regclass('running_athlete_rating') IS NOT NULL
               AND to_regclass('app_user') IS NOT NULL
               AND to_regclass('report') IS NOT NULL
               AND to_regclass('audit_log') IS NOT NULL
               AND (SELECT count(*) = 2 FROM information_schema.columns
                    WHERE table_schema = current_schema() AND table_name = 'athlete'
                      AND column_name IN ('employee_status', 'is_hidden')) AS ready
        """)
        return bool(row and row["ready"])

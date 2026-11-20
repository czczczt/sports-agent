"""Synchronous PostgreSQL operations for transactional rating publication."""


class RatingPublicationRepository:
    def __init__(self, connection):
        self.connection = connection

    def prepare(self, run_id):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO rating_publication(singleton) VALUES (true) ON CONFLICT DO NOTHING"
            )
            cursor.execute("SELECT version_id FROM rating_publication WHERE singleton FOR UPDATE")
            previous_id = cursor.fetchone()[0]
            cursor.execute("SELECT id FROM rating_version WHERE run_id = %s", (run_id,))
            existing = cursor.fetchone()
            cursor.execute(
                """SELECT period_start, period_end, COUNT(*) FROM running_athlete_rating
                   WHERE formula_version = 'run-v1' GROUP BY period_start, period_end
                   ORDER BY period_end DESC LIMIT 1"""
            )
            return previous_id, existing[0] if existing else None, cursor.fetchone()

    def comparable_count(self, previous_id, summary):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT athlete_count FROM rating_version
                   WHERE id = %s AND formula_version = %s AND period_start = %s AND period_end = %s""",
                (previous_id, summary["formula_version"], summary["period_start"], summary["period_end"]),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def publish(self, run_id, summary):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO rating_version (run_id, formula_version, period_start, period_end, athlete_count)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (run_id, summary["formula_version"], summary["period_start"], summary["period_end"],
                 summary["athletes_rated"]),
            )
            version_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO rating_version_row
                   (version_id, athlete_id, display_name, birth_year, gender, name_key,
                    points, best_points, starts_count, rank)
                   SELECT %s, a.id, a.display_name, a.birth_year, a.gender, a.name_key,
                          ar.points, ar.best_points, ar.starts_count, ar.rank
                   FROM running_athlete_rating ar JOIN athlete a ON a.id = ar.athlete_id
                   WHERE ar.formula_version = %s AND ar.period_start = %s AND ar.period_end = %s""",
                (version_id, summary["formula_version"], summary["period_start"], summary["period_end"]),
            )
            cursor.execute("UPDATE rating_publication SET version_id = %s WHERE singleton", (version_id,))
            return version_id

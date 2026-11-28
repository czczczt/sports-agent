from sqlalchemy import text

from app.core.repository import ReadRepository


class AthletesWebRepository(ReadRepository):
    async def search_candidates(self, name, year, limit):
        words = [w for w in name.split() if w]
        if not words:
            return []
        clauses = [
            "starts_count > 0",
            "is_hidden = FALSE",
            "(employee_status IS NULL OR employee_status != 'not_employee')",
        ]
        params = {"year": year, "limit": limit}
        if len(words) == 1:
            # Поиск только по фамилии: первое слово display_name (Фамилия) или совпадение с префиксом/подстрокой фамилии
            # Исключаем поиск по личному имени (например, "Максим" не должен находить "Тихонов Максим")
            clauses.append(
                "strpos(lower(replace(split_part(trim(display_name), ' ', 1), 'ё', 'е')), :last_name) > 0"
            )
            params["last_name"] = words[0]
        else:
            # Введены фамилия + имя (в любом порядке): оба слова должны входить в спортсмена
            for idx, word in enumerate(words):
                param_name = f"word_{idx}"
                clauses.append(f"strpos(name_key, :{param_name}) > 0")
                params[param_name] = word

        if year is not None:
            clauses.append("birth_year = :year")
        where = " AND ".join(clauses)
        return await self.rows(
            f"""
            SELECT id, display_name, first_name, last_name, middle_name,
                   birth_date::text, birth_year, gender, city, region, club,
                   employee_status, is_hidden, starts_count, results_count
            FROM athlete WHERE {where}
            ORDER BY starts_count DESC, results_count DESC, id LIMIT :limit
        """,
            params,
        )

    async def cached_assessment(self, athlete_id):
        return await self.row(
            "SELECT * FROM athlete_assessment_cache WHERE athlete_id=:id",
            {"id": athlete_id},
        )

    async def save_assessment(self, athlete_id, assessment_text, metrics_json, model):
        await self.session.execute(
            text("""
            INSERT INTO athlete_assessment_cache(athlete_id, assessment_text, metrics_json, model)
            VALUES (:id, :assessment, :metrics, :model)
            ON CONFLICT (athlete_id) DO UPDATE SET assessment_text=excluded.assessment_text,
                metrics_json=excluded.metrics_json, model=excluded.model, created_at=now()
        """),
            {
                "id": athlete_id,
                "assessment": assessment_text,
                "metrics": metrics_json,
                "model": model,
            },
        )

    async def finisher_counts(self, race_ids: list[int]) -> dict[int, int]:
        rows = await self.rows(
            """
            SELECT race_id, count(*) AS total
            FROM web_result
            WHERE race_id = ANY(CAST(:race_ids AS integer[]))
              AND status = 'FIN' AND duplicate_of IS NULL
            GROUP BY race_id
        """,
            {"race_ids": race_ids},
        )
        return {row["race_id"]: row["total"] for row in rows}

    async def athlete(self, athlete_id):
        return await self.row(
            """
            SELECT id, display_name, first_name, last_name, middle_name, birth_date::text, birth_year, gender, city, region, club, employee_status, is_hidden, starts_count, results_count
            FROM athlete
            WHERE id = :athlete_id
        """,
            {"athlete_id": athlete_id},
        )

    async def results(self, athlete_id):
        return await self.rows(
            """
            WITH race_stats AS (
                SELECT race_id, max(place_abs) AS max_fin_place,
                       count(*) AS race_participants_count
                FROM web_result
                WHERE duplicate_of IS NULL AND race_id IN (
                    SELECT race_id FROM web_result WHERE athlete_id = :athlete_id
                )
                GROUP BY race_id
            )
            SELECT
                r.id AS result_id,
                e.id AS event_id,
                e.title AS event_title,
                e.date_begin AS event_date,
                s.name AS source_name,
                ra.id AS race_id,
                ra.name_raw AS distance_name,
                ra.norm_distance,
                ra.distance_m,
                ra.total_count AS race_total_count,
                r.place_abs,
                r.place_gender,
                r.chip_time_s,
                r.gun_time_s,
                rs.points AS rating_points,
                rs.reason AS rating_reason,
                rs.breakdown_json AS rating_breakdown_json,
                r.status,
                r.bib,
                stats.max_fin_place,
                stats.race_participants_count
            FROM web_result r
            JOIN web_race ra ON ra.id = r.race_id
            JOIN web_event e ON e.id = ra.event_id
            JOIN source s ON s.id = e.source_id
            LEFT JOIN race_stats stats ON stats.race_id = r.race_id
            LEFT JOIN web_rating_score rs
              ON rs.result_id = r.id AND rs.formula_version = 'run-v1'
            WHERE r.athlete_id = :athlete_id
              AND r.status = 'FIN'
              AND r.duplicate_of IS NULL
            ORDER BY e.date_begin DESC, r.id DESC
        """,
            {"athlete_id": athlete_id},
        )

    async def published_rating(self, athlete_id):
        return await self.row(
            """
            SELECT points, rank, starts_count, period_start, period_end
            FROM web_athlete_rating
            WHERE athlete_id = :athlete_id AND formula_version = 'run-v1'
            ORDER BY period_end DESC
            LIMIT 1
        """,
            {"athlete_id": athlete_id},
        )

    async def cached_assessment_exists(self, athlete_id):
        return await self.row(
            """
            SELECT 1 FROM athlete_assessment_cache WHERE athlete_id = :athlete_id
        """,
            {"athlete_id": athlete_id},
        )

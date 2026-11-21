import re

from app.core.repository import ReadRepository


class EventsWebRepository(ReadRepository):
    async def list_events(self, query, date_from, date_to, city, source, limit, offset):
        clauses, params = [], {"limit": limit, "offset": offset}
        for index, word in enumerate(
            re.findall(r"\w+", (query or "").lower().replace("ё", "е"))
        ):
            key = f"word{index}"
            clauses.append(f"""(strpos(search_text(e.title), :{key}) > 0 OR EXISTS
                (SELECT 1 FROM web_race ra WHERE ra.event_id=e.id
                 AND strpos(search_text(ra.name_raw), :{key}) > 0))""")
            params[key] = word
        if date_from:
            clauses.append("e.date_begin >= :date_from")
            params["date_from"] = date_from.strip()[:10]
        if date_to:
            clauses.append("e.date_begin <= :date_to")
            params["date_to"] = date_to.strip()[:10]
        if source:
            clauses.append("s.name=:source")
            params["source"] = source.lower()
        if city:
            words = re.findall(r"\w+", city.lower().replace("ё", "е"))
            words = [
                w
                for w in words
                if w not in ("г", "город", "обл", "область", "край", "р", "рн", "район")
            ] or words
            for index, word in enumerate(words):
                stem = word[:-1] if len(word) >= 4 and word[-1] in "аяеиыуюо" else word
                stem = stem if len(stem) >= 3 else word
                key = f"city{index}"
                clauses.append(
                    f"search_text(concat_ws(' ', e.place, e.address)) ~ :{key}"
                )
                params[key] = r"(^|[^a-zа-я0-9_])" + re.escape(stem)
        where = " AND ".join(clauses) or "true"
        return await self.rows(
            f"""
            SELECT e.*, s.name AS source_name FROM web_event e JOIN source s ON s.id=e.source_id
            WHERE {where} ORDER BY e.date_begin DESC NULLS LAST, e.id DESC LIMIT :limit OFFSET :offset
        """,
            params,
        )

    async def protocol(
        self,
        race_id: int,
        search: str | None = None,
        limit: int = 300,
        offset: int = 0,
        employees_only: bool = False,
    ):
        clauses = ["r.race_id=:id", "r.duplicate_of IS NULL"]
        params = {"id": race_id, "limit": limit, "offset": offset}
        if employees_only:
            clauses.append(
                "a.id IS NOT NULL AND (a.employee_status IS NULL OR a.employee_status != 'not_employee')"
            )
        if search:
            number = re.sub(r"^[№#\s]+", "", search.strip()).lower().replace("ё", "е")
            params["bib"] = number
            name_clauses = []
            for index, word in enumerate(re.findall(r"[a-zа-я0-9]+", number)):
                key = f"word{index}"
                name_clauses.append(
                    f"(strpos(a.name_key,:{key})>0 OR (a.id IS NOT NULL AND (a.employee_status IS NULL OR a.employee_status != 'not_employee') AND strpos(search_text(r.full_name_raw),:{key})>0))"
                )
                params[key] = word
            name_match = " AND ".join(name_clauses) or "false"
            clauses.append(
                f"((a.id IS NOT NULL AND (a.employee_status IS NULL OR a.employee_status != 'not_employee') AND search_text(r.bib)=:bib) OR ({name_match}))"
            )
        where = " AND ".join(clauses)
        return await self.rows(
            f"""
            SELECT r.id AS result_id,
                   CASE
                       WHEN a.id IS NOT NULL AND (a.employee_status IS NULL OR a.employee_status != 'not_employee') THEN r.athlete_id
                       ELSE NULL
                   END AS athlete_id,
                   CASE
                       WHEN a.id IS NOT NULL AND (a.employee_status IS NULL OR a.employee_status != 'not_employee') THEN r.bib
                       ELSE NULL
                   END AS bib,
                   CASE
                       WHEN a.id IS NOT NULL AND (a.employee_status IS NULL OR a.employee_status != 'not_employee') THEN COALESCE(r.full_name_raw, 'Участник')
                       ELSE 'Участник'
                   END AS full_name_raw,
                   r.gender, r.age, r.birth_year,
                   CASE
                       WHEN a.id IS NOT NULL AND (a.employee_status IS NULL OR a.employee_status != 'not_employee') THEN r.club_raw
                       ELSE NULL
                   END AS club_raw,
                   r.place_abs, r.place_gender, r.chip_time_s, r.gun_time_s, r.status,
                   CASE
                       WHEN a.id IS NOT NULL AND (a.employee_status IS NULL OR a.employee_status != 'not_employee') THEN sc.points
                       ELSE NULL
                   END AS points
            FROM web_result r
            LEFT JOIN athlete a ON a.id=r.athlete_id
            LEFT JOIN web_rating_score sc ON sc.result_id=r.id AND sc.formula_version='run-v1'
            WHERE {where}
            ORDER BY CASE WHEN r.status='FIN' THEN 0 ELSE 1 END, r.place_abs NULLS LAST,
                     r.chip_time_s NULLS LAST, r.id LIMIT :limit OFFSET :offset
        """,
            params,
        )

    async def sber_finishers_count(self, race_id: int) -> int:
        row = await self.row(
            """
            SELECT COUNT(DISTINCT r.id) AS cnt
            FROM web_result r
            JOIN athlete a ON a.id = r.athlete_id
            WHERE r.race_id = :race_id
              AND r.duplicate_of IS NULL
              AND (a.employee_status IS NULL OR a.employee_status != 'not_employee')
            """,
            {"race_id": race_id},
        )
        return row["cnt"] if row else 0

    async def event(self, event_id):
        return await self.row(
            """
            SELECT
                e.id, e.source_id, s.name AS source_name, e.title,
                e.date_begin, e.date_end, e.place, e.address
            FROM web_event e
            JOIN source s ON s.id = e.source_id
            WHERE e.id = :event_id
        """,
            {"event_id": event_id},
        )

    async def event_races(self, event_id):
        return await self.rows(
            """
            SELECT id, event_id, name_raw, norm_distance, distance_m, distance_km_raw, total_count
            FROM web_race
            WHERE event_id = :event_id
            ORDER BY distance_m ASC, id ASC
        """,
            {"event_id": event_id},
        )

    async def race_distance(self, race_id):
        return await self.row(
            """
            SELECT distance_m FROM web_race WHERE id = :race_id
        """,
            {"race_id": race_id},
        )

    async def athlete_result(self, race_id, athlete_id):
        return await self.row(
            """
            SELECT
                r.id AS result_id,
                r.athlete_id,
                r.bib,
                r.full_name_raw,
                r.gender,
                r.age,
                r.birth_year,
                r.club_raw,
                r.place_abs,
                r.place_gender,
                r.chip_time_s,
                r.gun_time_s,
                r.status
            FROM web_result r
            WHERE r.race_id = :race_id AND r.athlete_id = :athlete_id AND r.duplicate_of IS NULL
            LIMIT 1
        """,
            {"race_id": race_id, "athlete_id": athlete_id},
        )

    async def rating_leaders(self, race_id, limit):
        return await self.rows(
            """
            SELECT ar.rank AS rating_rank, ar.points AS rating_points,
                   ar.starts_count AS rating_starts,
                   r.athlete_id, r.id AS result_id, COALESCE(r.full_name_raw, 'Участник') AS full_name_raw,
                   r.place_abs, r.chip_time_s, r.gun_time_s
            FROM web_result r
            JOIN web_athlete_rating ar ON ar.athlete_id = r.athlete_id
            WHERE r.race_id = :race_id
              AND r.status = 'FIN'
              AND r.duplicate_of IS NULL
              AND ar.formula_version = 'run-v1'
              AND ar.period_end = (
                  SELECT MAX(period_end)
                  FROM web_athlete_rating
                  WHERE formula_version = 'run-v1'
              )
            ORDER BY ar.points DESC, ar.best_points DESC, ar.starts_count DESC,
                     ar.rank ASC
            LIMIT :limit
        """,
            {"race_id": race_id, "limit": limit},
        )

    async def race(self, race_id):
        return await self.row(
            """
            SELECT id, event_id, name_raw, norm_distance, distance_m
            FROM web_race
            WHERE id = :race_id
        """,
            {"race_id": race_id},
        )

    async def finishers(self, race_id):
        return await self.rows(
            """
            SELECT r.id, r.chip_time_s, r.gun_time_s, r.place_abs, r.athlete_id
            FROM web_result r
            WHERE r.race_id = :race_id
              AND r.status = 'FIN'
              AND r.duplicate_of IS NULL
        """,
            {"race_id": race_id},
        )

    async def athlete_status(self, race_id, athlete_id):
        return await self.row(
            """
            SELECT r.id, r.status, r.place_abs, r.chip_time_s, r.gun_time_s
            FROM web_result r
            WHERE r.race_id = :race_id AND r.athlete_id = :athlete_id AND r.duplicate_of IS NULL
            LIMIT 1
        """,
            {"race_id": race_id, "athlete_id": athlete_id},
        )

    async def races_for_events(self, ids):
        rows = await self.rows(
            """
            SELECT id,event_id,name_raw,norm_distance,distance_m,distance_km_raw,total_count
            FROM web_race WHERE event_id=ANY(CAST(:ids AS integer[]))
            ORDER BY distance_m NULLS FIRST,id
        """,
            {"ids": ids},
        )
        grouped = {}
        for row in rows:
            grouped.setdefault(row["event_id"], []).append(row)
        return grouped

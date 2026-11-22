from typing import Any

from sqlalchemy import text

from app.core.repository import ReadRepository
from app.modules.rating.calculator import RATING_PERIOD_DAYS

FORMULA_VERSION = "run-v1"


class RatingRepository(ReadRepository):
    async def _query(self, query, args):
        parts = query.split("?")
        if len(parts) - 1 != len(args):
            raise ValueError("SQL bind count mismatch")
        sql = "".join(
            part + (f":p{i}" if i < len(args) else "") for i, part in enumerate(parts)
        )
        return await self.session.execute(
            text(sql), {f"p{i}": v for i, v in enumerate(args)}
        )

    async def fetch(self, query, *args):
        return (await self._query(query, args)).mappings().all()

    async def fetchrow(self, query, *args):
        return (await self._query(query, args)).mappings().first()

    async def fetchval(self, query, *args):
        return (await self._query(query, args)).scalar()

    async def _published_version(self):
        if not hasattr(self, "_version"):
            self._version = await self.fetchrow(
                """SELECT v.id AS version_id, v.period_start, v.period_end, v.published_at
                   FROM rating_publication p JOIN rating_version v ON v.id = p.version_id
                   WHERE p.singleton"""
            )
        return self._version

    async def _published_rows(
        self, version, gender=None, search=None, athlete_id=None, limit=100
    ):
        conditions = [
            "v.version_id = ?",
            "a.is_hidden = FALSE",
            "a.employee_status != 'not_employee'",
        ]
        args = [version["version_id"]]
        if gender:
            conditions.append("v.gender = ?")
            args.append(gender)
        ranked = f"""SELECT ROW_NUMBER() OVER (ORDER BY v.points DESC, v.best_points DESC,
                     v.starts_count DESC, v.athlete_id) AS rank, v.athlete_id, v.display_name,
                     v.birth_year, v.gender, v.points, v.best_points, v.starts_count, v.name_key
                     FROM rating_version_row v JOIN athlete a ON a.id = v.athlete_id
                     WHERE {' AND '.join(conditions)}"""
        filters = []
        if search:
            filters.append("name_key LIKE ?")
            args.append(f"%{search.lower().replace('\u0451', '\u0435')}%")
        if athlete_id is not None:
            filters.append("athlete_id = ?")
            args.append(athlete_id)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        query = f"WITH ranked AS ({ranked}) SELECT * FROM ranked{where}"
        rows = await self.fetch(query + " ORDER BY rank LIMIT ?", *args, limit)
        total = await self.fetchval(
            f"WITH ranked AS ({ranked}) SELECT COUNT(*) FROM ranked{where}", *args
        )
        return [
            {key: value for key, value in row.items() if key != "name_key"}
            for row in rows
        ], total

    async def get_rating_page(
        self,
        *,
        sport: str = "run",
        as_of: Any = None,
        gender: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Возвращает сохранённый рейтинг или динамический срез на дату (SPEC v1.3 §9.6)."""
        from datetime import date, timedelta

        # 1. Срез на дату для капитана / админа (расчёт на лету, не меняет снимки)
        if as_of is not None:
            end_date = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of)[:10])
            start_date = end_date - timedelta(days=RATING_PERIOD_DAYS)
            start_str = start_date.isoformat()
            end_str = end_date.isoformat()

            sport_clause = (
                "(ra.sport = 'run' OR ra.sport IS NULL)"
                if sport == "run"
                else ("ra.sport IN ('ski', 'biathlon')" if sport == "ski" else "ra.sport = ?")
            )
            query_args: list[Any] = [start_date, end_date]
            if sport not in ("run", "ski"):
                query_args.append(sport)

            cut_rows = await self.fetch(
                f"""
                SELECT a.id AS athlete_id, a.display_name, a.birth_year, a.gender,
                       SUM(s.points) AS points, MAX(s.points) AS best_points,
                       COUNT(*) AS starts_count
                FROM athlete a
                JOIN result_athlete link ON link.athlete_id = a.id
                JOIN rating_score s ON s.result_id = link.result_id
                JOIN result r ON r.id = s.result_id
                JOIN race ra ON ra.id = r.race_id
                JOIN competition c ON c.id = ra.competition_id
                WHERE s.points IS NOT NULL
                  AND c.date_begin BETWEEN ? AND ?
                  AND {sport_clause}
                  AND a.is_hidden = FALSE
                  AND a.employee_status != 'not_employee'
                GROUP BY a.id, a.display_name, a.birth_year, a.gender
                ORDER BY points DESC, best_points DESC, starts_count DESC, a.id ASC
                """,
                *query_args,
            )

            # Для лыж учитываем очки RL
            if sport == "ski":
                try:
                    rl_rows = await self.fetch("SELECT athlete_id, points FROM rl_points")
                    rl_map = {r["athlete_id"]: float(r["points"]) for r in rl_rows}
                except Exception:
                    rl_map = {}
            else:
                rl_map = {}

            processed = []
            for r in cut_rows:
                aid = r["athlete_id"]
                pts = float(r["points"])
                if sport == "ski" and aid in rl_map:
                    pts += rl_map[aid] / 7.0
                processed.append({
                    "athlete_id": aid,
                    "display_name": r["display_name"],
                    "birth_year": r["birth_year"],
                    "gender": r["gender"],
                    "points": pts,
                    "best_points": float(r["best_points"]),
                    "starts_count": int(r["starts_count"]),
                })

            processed.sort(
                key=lambda x: (x["points"], x["best_points"], x["starts_count"], -x["athlete_id"]),
                reverse=True,
            )

            # Фильтрация по полу и поиску
            if gender in ("M", "F"):
                processed = [p for p in processed if p["gender"] == gender]
            if search:
                s_lower = search.lower().replace("ё", "е")
                processed = [p for p in processed if s_lower in p["display_name"].lower().replace("ё", "е")]

            # Определение rank_delta по снимку за предыдущий месяц (~30 дней)
            target_snap_date = end_date - timedelta(days=30)
            snap_map: dict[int, int] = {}
            try:
                prev_snaps = await self.fetch(
                    """
                    SELECT athlete_id, rank
                    FROM rating_snapshot
                    WHERE sport = ?
                      AND taken_on = (
                          SELECT MAX(taken_on) FROM rating_snapshot
                          WHERE sport = ? AND taken_on <= ?
                      )
                    """,
                    sport, sport, target_snap_date,
                )
                snap_map = {s["athlete_id"]: int(s["rank"]) for s in prev_snaps}
            except Exception:
                pass

            total_count = len(processed)
            ranked_rows = []
            for idx, item in enumerate(processed[:limit], 1):
                prev_rank = snap_map.get(item["athlete_id"])
                delta = (prev_rank - idx) if prev_rank is not None else None
                ranked_rows.append({
                    "rank": idx,
                    "athlete_id": item["athlete_id"],
                    "display_name": item["display_name"],
                    "birth_year": item["birth_year"],
                    "gender": item["gender"],
                    "points": item["points"],
                    "best_points": item["best_points"],
                    "starts_count": item["starts_count"],
                    "rank_delta": delta,
                })

            return {
                "sport": sport,
                "as_of": end_str,
                "period_start": start_str,
                "period_end": end_str,
                "rows": ranked_rows,
                "total": total_count,
            }

        # 2. Обычный режим (rolling 365 дней)
        # Проверяем published_version (только для бега)
        if sport == "run":
            version = await self._published_version()
            if version:
                rows, total = await self._published_rows(version, gender, search, limit=limit)
                return {**dict(version), "sport": sport, "rows": rows, "total": total}

        # Ищем период в rating_entry или fallback на running_athlete_rating
        period = await self.fetchrow(
            """
            SELECT period_start, period_end
            FROM rating_entry
            WHERE sport = ? AND period_type = 'rolling'
            ORDER BY period_end DESC
            LIMIT 1
            """,
            sport,
        )
        if not period and sport == "run":
            period = await self.fetchrow(
                """
                SELECT period_start, period_end
                FROM running_athlete_rating
                WHERE formula_version = ?
                ORDER BY period_end DESC
                LIMIT 1
                """,
                FORMULA_VERSION,
            )

        if not period:
            return {"sport": sport, "period_start": None, "period_end": None, "rows": [], "total": 0}

        # Загрузка строк из rating_entry или fallback
        conditions = [
            "a.is_hidden = FALSE",
            "a.employee_status != 'not_employee'",
        ]

        try:
            # Пробуем rating_entry
            conditions_re = [
                "re.sport = ?",
                "re.period_type = 'rolling'",
                "re.period_start = ?",
                "re.period_end = ?",
            ] + conditions
            params_re: list[Any] = [sport, period["period_start"], period["period_end"]]
            if gender in ("M", "F"):
                conditions_re.append("a.gender = ?")
                params_re.append(gender)
            if search:
                conditions_re.append("a.name_key LIKE ?")
                params_re.append(f"%{search.lower().replace('ё', 'е')}%")

            where_re = " AND ".join(conditions_re)
            raw_rows = await self.fetch(
                f"""
                SELECT re.rank, a.id AS athlete_id, a.display_name, a.birth_year,
                       a.gender, re.points, re.best_points, re.starts_count
                FROM rating_entry re
                JOIN athlete a ON a.id = re.athlete_id
                WHERE {where_re}
                ORDER BY re.points DESC, re.best_points DESC, re.starts_count DESC, re.athlete_id
                LIMIT ?
                """,
                *params_re,
                limit,
            )
            total = await self.fetchval(
                f"""
                SELECT COUNT(*)
                FROM rating_entry re
                JOIN athlete a ON a.id = re.athlete_id
                WHERE {where_re}
                """,
                *params_re,
            )
        except Exception:
            raw_rows = []
            total = 0

        if not raw_rows and sport == "run":
            conditions_rar = [
                "ar.formula_version = ?",
                "ar.period_start = ?",
                "ar.period_end = ?",
            ] + conditions
            params_rar: list[Any] = [FORMULA_VERSION, period["period_start"], period["period_end"]]
            if gender in ("M", "F"):
                conditions_rar.append("a.gender = ?")
                params_rar.append(gender)
            if search:
                conditions_rar.append("a.name_key LIKE ?")
                params_rar.append(f"%{search.lower().replace('ё', 'е')}%")

            where_rar = " AND ".join(conditions_rar)
            raw_rows = await self.fetch(
                f"""
                SELECT ar.rank, a.id AS athlete_id, a.display_name, a.birth_year,
                       a.gender, ar.points, ar.best_points, ar.starts_count
                FROM running_athlete_rating ar
                JOIN athlete a ON a.id = ar.athlete_id
                WHERE {where_rar}
                ORDER BY ar.points DESC, ar.best_points DESC, ar.starts_count DESC, ar.athlete_id
                LIMIT ?
                """,
                *params_rar,
                limit,
            )
            total = await self.fetchval(
                f"""
                SELECT COUNT(*)
                FROM running_athlete_rating ar
                JOIN athlete a ON a.id = ar.athlete_id
                WHERE {where_rar}
                """,
                *params_rar,
            )

        # Вычисляем rank_delta по rating_snapshot за прошлый месяц
        snap_map = {}
        try:
            p_end_date = date.fromisoformat(str(period["period_end"])[:10])
            prev_snaps = await self.fetch(
                """
                SELECT athlete_id, rank
                FROM rating_snapshot
                WHERE sport = ?
                  AND taken_on = (
                      SELECT MAX(taken_on) FROM rating_snapshot
                      WHERE sport = ? AND taken_on <= ?
                  )
                """,
                sport, sport, p_end_date - timedelta(days=30),
            )
            snap_map = {s["athlete_id"]: int(s["rank"]) for s in prev_snaps}
        except Exception:
            pass

        rows = [
            {
                "rank": index,
                "athlete_id": row["athlete_id"],
                "display_name": row["display_name"],
                "birth_year": row["birth_year"],
                "gender": row["gender"],
                "points": row["points"],
                "best_points": row["best_points"],
                "starts_count": row["starts_count"],
                "rank_delta": (snap_map.get(row["athlete_id"]) - index) if row["athlete_id"] in snap_map else None,
            }
            for index, row in enumerate(raw_rows, 1)
        ]
        return {
            "sport": sport,
            "period_start": period["period_start"],
            "period_end": period["period_end"],
            "rows": rows,
            "total": total or 0,
        }

    async def get_rating_me_row(
        self,
        athlete_id: int,
        gender: str | None = None,
        sport: str = "run",
        as_of: Any = None,
    ) -> dict[str, Any] | None:
        """Строка «это вы» для страницы рейтинга.

        Если выбран фильтр по полу, место пересчитывается среди спортсменов этого пола
        (с теми же тай-брейками, что и общий рейтинг). Спортсмен другого пола скрывается.
        """
        page = await self.get_rating_page(sport=sport, as_of=as_of, gender=gender, limit=1000)
        for row in page.get("rows", []):
            if row["athlete_id"] == athlete_id:
                return row
        return None

    async def get_rating_norms(self, year: int = 2026) -> dict[str, Any]:
        """Нормативы года и период действующего рейтинга — для страницы «Как посчитано»."""
        norms = await self.fetch(
            """
            SELECT distance_class, gender, value, unit
            FROM rating_norm
            WHERE year = ?
            ORDER BY CASE distance_class
                WHEN '60m' THEN 1 WHEN '100m' THEN 2 WHEN '200m' THEN 3
                WHEN '400m' THEN 4 WHEN '800m' THEN 5 WHEN '1000m' THEN 6
                WHEN '1500m' THEN 7 WHEN '1mile' THEN 8 WHEN '3000m' THEN 9
                WHEN '5000m' THEN 10 WHEN '10000m' THEN 11
                WHEN 'half_marathon' THEN 12 WHEN 'marathon' THEN 13
                WHEN '100km' THEN 14 WHEN '24h' THEN 15 ELSE 99 END,
                gender
            """,
            year,
        )
        period = await self._published_version()
        if not period:
            period = await self.fetchrow(
                """
                SELECT period_start, period_end FROM running_athlete_rating
                WHERE formula_version = ? ORDER BY period_end DESC LIMIT 1
                """,
                FORMULA_VERSION,
            )
        return {
            "year": year,
            "norms": [dict(row) for row in norms],
            "period_start": period["period_start"] if period else None,
            "period_end": period["period_end"] if period else None,
        }

    async def recalculate_rating(
        self,
        *,
        as_of: Any = None,
        formula_version: str = FORMULA_VERSION,
    ) -> dict[str, Any]:
        """Пересчитывает баллы результатов и агрегированный 365-дневный рейтинг бега в PostgreSQL."""
        import json
        import statistics
        from datetime import date, timedelta

        from app.modules.rating.calculator import (
            RATING_PERIOD_DAYS,
            _calculate_score,
        )

        end_date = as_of or date.today()
        start_date = end_date - timedelta(days=RATING_PERIOD_DAYS)
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('collection:publication', 0))"))
        await self.session.execute(text("""
            DELETE FROM rating_score s USING result r, race ra, competition c
            WHERE s.result_id=r.id AND r.race_id=ra.id AND ra.competition_id=c.id
              AND s.formula_version = :formula_version
              AND (r.collection_review OR COALESCE(ra.sport_type, c.sport_type, 'run') <> 'run'
                   OR ra.race_type = 'relay')
        """), {"formula_version": formula_version})

        norm_rows = await self.fetch("SELECT distance_class, gender, value, unit, year FROM rating_norm")
        norms = {
            (row["distance_class"], row["gender"]): row
            for row in norm_rows
        }

        result_rows = await self.fetch(
            """
            SELECT r.id, r.race_id, r.status, r.duplicate_of, r.gender, r.chip_time_s,
                   r.gun_time_s, r.distance_km, r.position, r.position_gender,
                   ra.distance_type, ra.discipline, ra.sport, ra.scoring_class,
                   ra.elevation_gain_m, ra.is_rl_series, ra.special,
                   c.date_begin, a.id AS athlete_id
            FROM result r
            JOIN race ra ON ra.id = r.race_id
            JOIN competition c ON c.id = ra.competition_id
            LEFT JOIN result_athlete link ON link.result_id = r.id
            LEFT JOIN athlete a ON a.id = link.athlete_id
            WHERE COALESCE(ra.sport_type, c.sport_type, 'run') = 'run'
              AND NOT r.collection_review AND ra.race_type IS DISTINCT FROM 'relay'
            """
        )

        # Precompute race statistics per (race_id, gender) for multi-sport calculations
        race_stats: dict[tuple[Any, Any], dict[str, Any]] = {}
        for row in result_rows:
            rid_key = (row.get("race_id"), row.get("gender"))
            if rid_key not in race_stats:
                race_stats[rid_key] = {"times": [], "count": 0}
            if row.get("status") == "FIN":
                race_stats[rid_key]["count"] += 1
                t_val = row.get("chip_time_s") if row.get("chip_time_s") is not None else row.get("gun_time_s")
                if isinstance(t_val, (int, float)) and t_val > 0:
                    race_stats[rid_key]["times"].append(float(t_val))

        for stats in race_stats.values():
            times = stats["times"]
            stats["leader_time_s"] = min(times) if times else None
            stats["median_time_s"] = statistics.median(times) if times else None
            stats["finishers_count"] = stats["count"]

        scored_count = 0
        for row in result_rows:
            rid_key = (row.get("race_id"), row.get("gender"))
            stats = race_stats.get(rid_key, {})
            sport = row.get("sport") or "run"
            dist_class = (
                row.get("scoring_class")
                or row.get("distance_type")
                or (f"{int(row['distance_km'])}km" if row.get("distance_km") else None)
            )
            norm = norms.get((dist_class, row.get("gender")))

            place = row.get("position_gender") or row.get("position")
            finishers_count = stats.get("finishers_count")
            leader_time_s = stats.get("leader_time_s")
            median_time_s = stats.get("median_time_s")

            points, reason, breakdown = _calculate_score(
                status=row.get("status"),
                duplicate_of=row.get("duplicate_of"),
                gender=row.get("gender"),
                distance_class=dist_class,
                event_date=str(row["date_begin"]) if row.get("date_begin") else None,
                chip_time_s=row.get("chip_time_s"),
                gun_time_s=row.get("gun_time_s"),
                distance_km=row.get("distance_km"),
                norm_value=norm["value"] if norm else None,
                norm_unit=norm["unit"] if norm else None,
                norm_year=norm["year"] if norm else None,
                sport=sport,
                finishers_count=finishers_count,
                place=place,
                leader_time_s=leader_time_s,
                median_time_s=median_time_s,
                elevation_gain_m=row.get("elevation_gain_m"),
                special=row.get("special") or "regular",
                is_rl_series=bool(row.get("is_rl_series", False)),
                discipline=row.get("discipline"),
                formula_version=formula_version if sport == "run" else None,
            )
            f_ver = breakdown.get("formula_version") or formula_version
            breakdown_json = json.dumps(breakdown, ensure_ascii=False, allow_nan=False)
            await self.session.execute(
                text(
                    """
                    INSERT INTO rating_score (result_id, formula_version, points, reason, breakdown_json)
                    VALUES (:res_id, :ver, :pts, :rsn, :bd)
                    ON CONFLICT (result_id, formula_version) DO UPDATE SET
                        points = EXCLUDED.points,
                        reason = EXCLUDED.reason,
                        breakdown_json = EXCLUDED.breakdown_json
                    """
                ),
                {
                    "res_id": row["id"],
                    "ver": f_ver,
                    "pts": points,
                    "rsn": reason,
                    "bd": breakdown_json,
                },
            )
            if points is not None:
                scored_count += 1

        # Multi-sport aggregation for rating_entry and rating_snapshot (SPEC v1.3 §5, §9)
        sport_definitions = [
            ("run", "run-v1", "(ra.sport = 'run' OR ra.sport IS NULL)"),
            ("ski", "ski-v1", "ra.sport IN ('ski', 'biathlon')"),
            ("triathlon", "triathlon-v1", "ra.sport = 'triathlon'"),
            ("trail", "trail-v1", "ra.sport = 'trail'"),
        ]

        rl_map: dict[int, float] = {}
        try:
            rl_rows = await self.fetch("SELECT athlete_id, points FROM rl_points")
            rl_map = {r["athlete_id"]: float(r["points"]) for r in rl_rows}
        except Exception:
            pass

        run_aggregates: list[dict[str, Any]] = []

        for sp, f_ver, sp_where in sport_definitions:
            aggs = await self.fetch(
                f"""
                SELECT a.id AS athlete_id, SUM(s.points) AS points,
                       MAX(s.points) AS best_points, COUNT(*) AS starts_count
                FROM athlete a
                JOIN result_athlete link ON link.athlete_id = a.id
                JOIN rating_score s ON s.result_id = link.result_id
                JOIN result r ON r.id = s.result_id
                JOIN race ra ON ra.id = r.race_id
                JOIN competition c ON c.id = ra.competition_id
                WHERE s.points IS NOT NULL
                  AND c.date_begin BETWEEN ? AND ?
                  AND {sp_where}
                GROUP BY a.id
                ORDER BY points DESC, best_points DESC, starts_count DESC, a.id ASC
                """,
                start_date,
                end_date,
            )

            processed_aggs = []
            for agg in aggs:
                aid = agg["athlete_id"]
                pts = float(agg["points"])
                best_pts = float(agg["best_points"])
                starts = int(agg["starts_count"])
                if sp == "ski" and aid in rl_map:
                    pts += rl_map[aid] / 7.0
                processed_aggs.append({
                    "athlete_id": aid,
                    "points": pts,
                    "best_points": best_pts,
                    "starts_count": starts,
                })

            processed_aggs.sort(
                key=lambda x: (x["points"], x["best_points"], x["starts_count"], -x["athlete_id"]),
                reverse=True,
            )

            if sp == "run":
                run_aggregates = processed_aggs

            # Clean and insert rating_entry and rating_snapshot
            try:
                await self.session.execute(
                    text(
                        """
                        DELETE FROM rating_entry
                        WHERE sport = :sp AND period_type = 'rolling'
                          AND period_start = :p_start AND period_end = :p_end
                        """
                    ),
                    {"sp": sp, "p_start": start_str, "p_end": end_str},
                )
                for rank, item in enumerate(processed_aggs, 1):
                    await self.session.execute(
                        text(
                            """
                            INSERT INTO rating_entry (
                                sport, period_type, period_start, period_end,
                                athlete_id, formula_version, points, best_points, starts_count, rank
                            ) VALUES (
                                :sport, 'rolling', :period_start, :period_end,
                                :athlete_id, :formula_version, :points, :best_points, :starts_count, :rank
                            )
                            ON CONFLICT (sport, period_type, period_start, period_end, athlete_id) DO UPDATE SET
                                points = EXCLUDED.points,
                                best_points = EXCLUDED.best_points,
                                starts_count = EXCLUDED.starts_count,
                                rank = EXCLUDED.rank
                            """
                        ),
                        {
                            "sport": sp,
                            "period_start": start_str,
                            "period_end": end_str,
                            "athlete_id": item["athlete_id"],
                            "formula_version": f_ver,
                            "points": item["points"],
                            "best_points": item["best_points"],
                            "starts_count": item["starts_count"],
                            "rank": rank,
                        },
                    )

                # Snapshot for ▲▼ dynamics
                await self.session.execute(
                    text(
                        """
                        DELETE FROM rating_snapshot
                        WHERE sport = :sp AND taken_on = :t_on
                        """
                    ),
                    {"sp": sp, "t_on": end_date},
                )
                for rank, item in enumerate(processed_aggs, 1):
                    await self.session.execute(
                        text(
                            """
                            INSERT INTO rating_snapshot (
                                sport, taken_on, athlete_id, rank, points
                            ) VALUES (
                                :sport, :taken_on, :athlete_id, :rank, :points
                            )
                            ON CONFLICT (sport, taken_on, athlete_id) DO UPDATE SET
                                rank = EXCLUDED.rank,
                                points = EXCLUDED.points
                            """
                        ),
                        {
                            "sport": sp,
                            "taken_on": end_date,
                            "athlete_id": item["athlete_id"],
                            "rank": rank,
                            "points": item["points"],
                        },
                    )
            except Exception:
                pass

        # Legacy running_athlete_rating synchronization
        await self.session.execute(
            text(
                """
                DELETE FROM running_athlete_rating
                WHERE formula_version = :ver AND period_start = :p_start AND period_end = :p_end
                """
            ),
            {"ver": formula_version, "p_start": start_str, "p_end": end_str},
        )

        for rank, agg in enumerate(run_aggregates, 1):
            await self.session.execute(
                text(
                    """
                    INSERT INTO running_athlete_rating (
                        athlete_id, formula_version, period_start, period_end,
                        points, best_points, starts_count, rank
                    ) VALUES (
                        :athlete_id, :formula_version, :period_start, :period_end,
                        :points, :best_points, :starts_count, :rank
                    )
                    """
                ),
                {
                    "athlete_id": agg["athlete_id"],
                    "formula_version": formula_version,
                    "period_start": start_str,
                    "period_end": end_str,
                    "points": agg["points"],
                    "best_points": agg["best_points"],
                    "starts_count": agg["starts_count"],
                    "rank": rank,
                },
            )

        await self.session.commit()
        return {
            "formula_version": formula_version,
            "period_start": start_str,
            "period_end": end_str,
            "results_scored": scored_count,
            "athletes_rated": len(run_aggregates),
        }


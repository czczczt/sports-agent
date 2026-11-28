"""Роутер администрирования карточек спортсменов (SPEC v1.3 §5, §8.5, §8.7, §10.4).

Доступен капитанам и администраторам:
- Просмотр и детальная карточка спортсмена со всеми ПДн и статусами;
- Ручное создание спортсмена;
- Редактирование карточки спортсмена (ФИО, ДР, статус сотрудника, hidden, даты работы);
- При переводе в not_employee: установка employee_until и авто-блокировка связанной учётки;
- Импорт спортсменов из CSV / XLSX списков с сопоставлением.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.api.auth import CaptainOrAdminDep
from app.core.postgres import SessionDep
from app.core.repository import ReadRepository
from app.models import (
    AdminAthleteCreate,
    AdminAthleteDetail,
    AdminAthleteUpdate,
    RosterImportResult,
)
from parser_running.normalize import format_display_name

router = APIRouter(prefix="/admin/athletes", tags=["admin-athletes"])


def norm_name(name: str | None) -> str:
    if not name:
        return ""
    s = name.lower().replace("ё", "е")
    tokens = sorted(re.findall(r"[a-zа-я0-9]+", s))
    return " ".join(tokens)


class AdminAthletesRepository(ReadRepository):
    async def list_athletes(
        self,
        query: str | None = None,
        employee_status: str | None = None,
        is_hidden: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if query:
            nk = norm_name(query)
            clauses.append("(strpos(a.name_key, :q) > 0 OR strpos(lower(a.display_name), :raw_q) > 0)")
            params["q"] = nk
            params["raw_q"] = query.strip().lower()

        if employee_status:
            clauses.append("a.employee_status = :emp_status")
            params["emp_status"] = employee_status

        if is_hidden is not None:
            clauses.append("a.is_hidden = :is_hidden")
            params["is_hidden"] = is_hidden

        where_sql = " AND ".join(clauses)
        sql = f"""
            SELECT a.id, a.display_name, a.first_name, a.last_name, a.middle_name,
                   a.birth_date::text AS birth_date, a.birth_year, a.gender,
                   a.city, a.club, a.employee_status,
                   a.employee_since::text AS employee_since,
                   a.employee_until::text AS employee_until,
                   a.is_hidden, a.starts_count, a.results_count,
                   u.id AS linked_user_id, u.username AS linked_username
            FROM athlete a
            LEFT JOIN app_user u ON u.athlete_id = a.id
            WHERE {where_sql}
            ORDER BY a.starts_count DESC, a.id DESC
            LIMIT :limit OFFSET :offset
        """
        return await self.rows(sql, params)

    async def get_athlete_detail(self, athlete_id: int) -> dict[str, Any] | None:
        sql = """
            SELECT a.id, a.display_name, a.first_name, a.last_name, a.middle_name,
                   a.birth_date::text AS birth_date, a.birth_year, a.gender,
                   a.city, a.club, a.employee_status,
                   a.employee_since::text AS employee_since,
                   a.employee_until::text AS employee_until,
                   a.is_hidden, a.starts_count, a.results_count,
                   u.id AS linked_user_id, u.username AS linked_username
            FROM athlete a
            LEFT JOIN app_user u ON u.athlete_id = a.id
            WHERE a.id = :athlete_id
        """
        return await self.row(sql, {"athlete_id": athlete_id})

    async def create_athlete(self, data: AdminAthleteCreate) -> int:
        first = format_display_name(data.first_name)
        last = format_display_name(data.last_name)
        middle = format_display_name(data.middle_name) or None
        display = format_display_name(f"{last} {first}".strip())
        name_key = norm_name(display)

        parsed_bdate = None
        birth_year = data.birth_year
        if data.birth_date:
            try:
                parsed_bdate = date.fromisoformat(data.birth_date)
                if not birth_year:
                    birth_year = parsed_bdate.year
            except ValueError:
                parsed_bdate = None

        parsed_since = date.fromisoformat(data.employee_since) if data.employee_since else None
        parsed_until = date.fromisoformat(data.employee_until) if data.employee_until else None

        row = await self.row(
            """
            INSERT INTO athlete (
                display_name, first_name, last_name, middle_name,
                birth_date, birth_year, gender, city, club,
                employee_status, employee_since, employee_until,
                is_hidden, name_key, created_at
            )
            VALUES (
                :display_name, :first_name, :last_name, :middle_name,
                :birth_date, :birth_year, :gender, :city, :club,
                :employee_status, :employee_since, :employee_until,
                :is_hidden, :name_key, NOW()
            )
            RETURNING id
            """,
            {
                "display_name": display,
                "first_name": first,
                "last_name": last,
                "middle_name": middle,
                "birth_date": parsed_bdate,
                "birth_year": birth_year,
                "gender": data.gender,
                "city": data.city,
                "club": data.club,
                "employee_status": data.employee_status or "presumed",
                "employee_since": parsed_since,
                "employee_until": parsed_until,
                "is_hidden": data.is_hidden,
                "name_key": name_key,
            },
        )
        return row["id"]

    async def update_athlete(self, athlete_id: int, updates: dict[str, Any]) -> None:
        set_clauses = []
        params: dict[str, Any] = {"athlete_id": athlete_id}
        for k, v in updates.items():
            set_clauses.append(f"{k} = :{k}")
            params[k] = v

        if not set_clauses:
            return

        sql = f"UPDATE athlete SET {', '.join(set_clauses)} WHERE id = :athlete_id"
        await self.execute(sql, params)

    async def get_linked_users(self, athlete_id: int) -> list[dict[str, Any]]:
        return await self.rows(
            "SELECT id, username, status FROM app_user WHERE athlete_id = :athlete_id",
            {"athlete_id": athlete_id},
        )

    async def get_athlete_sports(self, athlete_id: int) -> list[str]:
        rows = await self.rows(
            """
            SELECT DISTINCT COALESCE(ra.sport, c.sport_type, 'run') AS sport
            FROM result r
            JOIN race ra ON ra.id = r.race_id
            LEFT JOIN competition c ON c.id = ra.competition_id
            WHERE r.athlete_id = :athlete_id
            """,
            {"athlete_id": athlete_id},
        )
        return [r["sport"] for r in rows if r["sport"]]

    async def block_user(self, user_id: int) -> None:
        await self.execute(
            "UPDATE app_user SET status = 'blocked', updated_at = NOW() WHERE id = :user_id",
            {"user_id": user_id},
        )

    async def log_audit(self, user_id: int, action: str, entity: str, entity_id: int, diff: dict) -> None:
        await self.execute(
            """
            INSERT INTO audit_log (user_id, action, entity, entity_id, diff, created_at)
            VALUES (:user_id, :action, :entity, :entity_id, CAST(:diff AS jsonb), NOW())
            """,
            {"user_id": user_id, "action": action, "entity": entity, "entity_id": entity_id, "diff": json.dumps(diff, ensure_ascii=False)},
        )

    async def match_existing_athlete(
        self, name_key: str, birth_year: int | None, gender: str | None
    ) -> dict[str, Any] | None:
        clauses = ["strpos(name_key, :nk) > 0"]
        params: dict[str, Any] = {"nk": name_key}
        if birth_year:
            clauses.append("(birth_year = :by OR birth_year IS NULL)")
            params["by"] = birth_year
        if gender:
            clauses.append("(gender = :gender OR gender IS NULL)")
            params["gender"] = gender

        sql = f"SELECT * FROM athlete WHERE {' AND '.join(clauses)} ORDER BY starts_count DESC LIMIT 1"
        return await self.row(sql, params)


@router.get("", response_model=list[AdminAthleteDetail])
async def list_admin_athletes(
    current_user: CaptainOrAdminDep,
    session: SessionDep,
    query: str | None = Query(None, description="Поиск по ФИО"),
    employee_status: str | None = Query(None, description="Фильтр по статусу сотрудника (presumed, confirmed, not_employee)"),
    is_hidden: bool | None = Query(None, description="Фильтр по флагу скрытия"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Список карточек спортсменов для администрирования (SPEC v1.3 §8.5, §10.4)."""
    repo = AdminAthletesRepository(session)
    rows = await repo.list_athletes(
        query=query,
        employee_status=employee_status,
        is_hidden=is_hidden,
        limit=limit,
        offset=offset,
    )
    return [AdminAthleteDetail(**r) for r in rows]


@router.get("/{athlete_id}", response_model=AdminAthleteDetail)
async def get_admin_athlete(
    athlete_id: int,
    current_user: CaptainOrAdminDep,
    session: SessionDep,
):
    """Детальная карточка спортсмена со всеми ПДн и связками (SPEC v1.3 §8.5)."""
    repo = AdminAthletesRepository(session)
    row = await repo.get_athlete_detail(athlete_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Спортсмен не найден")
    return AdminAthleteDetail(**row)


@router.post("", response_model=AdminAthleteDetail, status_code=status.HTTP_201_CREATED)
async def create_admin_athlete(
    data: AdminAthleteCreate,
    current_user: CaptainOrAdminDep,
    session: SessionDep,
):
    """Ручное создание карточки спортсмена (SPEC v1.3 §8.5)."""
    repo = AdminAthletesRepository(session)
    athlete_id = await repo.create_athlete(data)

    await repo.log_audit(
        user_id=current_user.id,
        action="create_athlete_manual",
        entity="athlete",
        entity_id=athlete_id,
        diff=data.model_dump(),
    )
    await session.commit()

    created = await repo.get_athlete_detail(athlete_id)
    return AdminAthleteDetail(**created)


@router.patch("/{athlete_id}", response_model=AdminAthleteDetail)
async def update_admin_athlete(
    athlete_id: int,
    data: AdminAthleteUpdate,
    current_user: CaptainOrAdminDep,
    session: SessionDep,
):
    """Редактирование карточки спортсмена капитаном или админом (SPEC v1.3 §5, §8.5, §8.7)."""
    repo = AdminAthletesRepository(session)
    existing = await repo.get_athlete_detail(athlete_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Спортсмен не найден")

    # Проверка скоупа капитана по видам спорта (SPEC v1.3 §2, §3.2)
    if current_user.role == "captain":
        athlete_sports = await repo.get_athlete_sports(athlete_id)
        if athlete_sports and not any(
            s.lower() in [cs.lower() for cs in current_user.captain_sports]
            for s in athlete_sports
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступ запрещён: спортсмен не относится к видам спорта капитана",
            )

    updates: dict[str, Any] = {}
    raw_data = data.model_dump(exclude_unset=True)

    if "first_name" in raw_data or "last_name" in raw_data:
        first = raw_data.get("first_name", existing["first_name"]) or ""
        last = raw_data.get("last_name", existing["last_name"]) or ""
        updates["first_name"] = raw_data.get("first_name")
        updates["last_name"] = raw_data.get("last_name")
        display = f"{last} {first}".strip()
        updates["display_name"] = display
        updates["name_key"] = norm_name(display)

    if "middle_name" in raw_data:
        updates["middle_name"] = raw_data["middle_name"]

    if "birth_date" in raw_data:
        bdate_val = raw_data["birth_date"]
        if bdate_val:
            try:
                parsed_bdate = date.fromisoformat(bdate_val)
                updates["birth_date"] = parsed_bdate
                if "birth_year" not in raw_data:
                    updates["birth_year"] = parsed_bdate.year
            except ValueError:
                updates["birth_date"] = None
        else:
            updates["birth_date"] = None

    if "birth_year" in raw_data:
        updates["birth_year"] = raw_data["birth_year"]

    if "gender" in raw_data:
        updates["gender"] = raw_data["gender"]

    if "city" in raw_data:
        updates["city"] = raw_data["city"]

    if "club" in raw_data:
        updates["club"] = raw_data["club"]

    if "is_hidden" in raw_data:
        updates["is_hidden"] = raw_data["is_hidden"]

    if "employee_since" in raw_data:
        updates["employee_since"] = (
            date.fromisoformat(raw_data["employee_since"]) if raw_data["employee_since"] else None
        )

    if "employee_until" in raw_data:
        updates["employee_until"] = (
            date.fromisoformat(raw_data["employee_until"]) if raw_data["employee_until"] else None
        )

    old_status = existing["employee_status"]
    new_status = raw_data.get("employee_status")
    if new_status:
        updates["employee_status"] = new_status
        # При переводе в not_employee по СПЕКЕ §5: ставим employee_until = today, если не задано
        if new_status == "not_employee":
            if not updates.get("employee_until") and not existing.get("employee_until"):
                updates["employee_until"] = datetime.now(UTC).date()

    if updates:
        await repo.update_athlete(athlete_id, updates)

    # При переводе в not_employee: автоматически блокируем связанную учётку (SPEC §5, §8.7)
    if new_status == "not_employee" and old_status != "not_employee":
        if current_user.role == "captain":
            await repo.log_audit(
                user_id=current_user.id,
                action="captain_set_not_employee",
                entity="athlete",
                entity_id=athlete_id,
                diff={
                    "athlete_name": existing["display_name"],
                    "old_status": old_status,
                    "new_status": "not_employee",
                    "moderator": current_user.username,
                    "moderator_role": "captain",
                    "comment": raw_data.get("comment"),
                },
            )

        linked_users = await repo.get_linked_users(athlete_id)
        for u in linked_users:
            if u["status"] != "blocked":
                await repo.block_user(u["id"])
                await repo.log_audit(
                    user_id=current_user.id,
                    action="auto_block_not_employee",
                    entity="app_user",
                    entity_id=u["id"],
                    diff={"reason": "athlete_updated_not_employee", "athlete_id": athlete_id},
                )

    await repo.log_audit(
        user_id=current_user.id,
        action="update_athlete",
        entity="athlete",
        entity_id=athlete_id,
        diff={"updates": raw_data, "old": {k: existing.get(k) for k in raw_data}},
    )
    await session.commit()

    updated = await repo.get_athlete_detail(athlete_id)
    return AdminAthleteDetail(**updated)


@router.post("/import", response_model=RosterImportResult)
async def import_athletes_roster(
    current_user: CaptainOrAdminDep,
    session: SessionDep,
    file: UploadFile = File(...),
):
    """Импорт списка спортсменов из CSV или XLSX файла (SPEC v1.3 §8.5)."""
    repo = AdminAthletesRepository(session)
    content = await file.read()
    filename = file.filename or ""

    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    if filename.lower().endswith(".csv") or file.content_type == "text/csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("cp1251")
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="Не удалось определить кодировку CSV (ожидается UTF-8 или CP1251)")
        reader = csv.DictReader(io.StringIO(text))
        for idx, row in enumerate(reader, start=2):
            rows.append({"_line": idx, **row})
    elif filename.lower().endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            sheet = wb.active
            header: list[str] = []
            for cell in next(sheet.iter_rows(values_only=True)):
                header.append(str(cell or "").strip())
            for idx, row_vals in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if any(row_vals):
                    row_dict = {header[i]: row_vals[i] for i in range(min(len(header), len(row_vals)))}
                    rows.append({"_line": idx, **row_dict})
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Ошибка чтения Excel-файла: {exc}")
    else:
        raise HTTPException(status_code=400, detail="Поддерживаются только форматы CSV (.csv) и Excel (.xlsx)")

    total = len(rows)
    created_count = 0
    updated_count = 0

    for r in rows:
        line_num = r.pop("_line", 0)
        # Определение колонок
        first_name = ""
        last_name = ""
        middle_name = ""
        birth_val = None
        gender_val = None
        city_val = None
        club_val = None
        emp_status = "presumed"

        for k, v in r.items():
            if not k or v is None:
                continue
            kl = str(k).strip().lower()
            vs = str(v).strip()
            if kl in ("фамилия", "last_name", "lastname"):
                last_name = vs
            elif kl in ("имя", "first_name", "firstname"):
                first_name = vs
            elif kl in ("отчество", "middle_name", "patronymic"):
                middle_name = vs
            elif kl in ("фио", "full_name", "имя фамилия"):
                parts = vs.split()
                if len(parts) >= 2:
                    last_name = parts[0]
                    first_name = parts[1]
                    if len(parts) >= 3:
                        middle_name = " ".join(parts[2:])
                elif len(parts) == 1:
                    last_name = parts[0]
            elif kl in ("дата рождения", "др", "birth_date", "birthdate"):
                birth_val = vs
            elif kl in ("год рождения", "год", "birth_year"):
                try:
                    birth_val = int(vs)
                except ValueError:
                    pass
            elif kl in ("пол", "gender", "sex"):
                if vs.lower().startswith("ж") or vs.lower().startswith("f"):
                    gender_val = "F"
                elif vs.lower().startswith("м") or vs.lower().startswith("m"):
                    gender_val = "M"
            elif kl in ("город", "city"):
                city_val = vs
            elif kl in ("клуб", "club"):
                club_val = vs
            elif kl in ("статус", "employee_status"):
                if vs in ("presumed", "confirmed", "not_employee"):
                    emp_status = vs

        if not last_name or not first_name:
            errors.append(f"Строка {line_num}: Не указаны фамилия или имя")
            continue

        display = f"{last_name} {first_name}".strip()
        nk = norm_name(display)

        parsed_bdate = None
        birth_year = None
        if isinstance(birth_val, int):
            birth_year = birth_val
        elif isinstance(birth_val, str) and birth_val:
            try:
                # Попытка парсинга DD.MM.YYYY или YYYY-MM-DD
                if "." in birth_val:
                    d, m, y = birth_val.split(".")[:3]
                    parsed_bdate = date(int(y), int(m), int(d))
                else:
                    parsed_bdate = date.fromisoformat(birth_val[:10])
                birth_year = parsed_bdate.year
            except Exception:
                try:
                    birth_year = int(re.search(r"\b(19\d\d|20\d\d)\b", birth_val).group(1))
                except Exception:
                    pass

        # Поиск совпадений со существующим спортсменом (§8.2, §8.5)
        matched = await repo.match_existing_athlete(nk, birth_year, gender_val)
        if matched:
            upd: dict[str, Any] = {}
            if middle_name and not matched["middle_name"]:
                upd["middle_name"] = middle_name
            if parsed_bdate and not matched["birth_date"]:
                upd["birth_date"] = parsed_bdate
            if birth_year and not matched["birth_year"]:
                upd["birth_year"] = birth_year
            if city_val and not matched["city"]:
                upd["city"] = city_val
            if gender_val and not matched["gender"]:
                upd["gender"] = gender_val
            if emp_status == "confirmed" and matched["employee_status"] != "confirmed":
                upd["employee_status"] = "confirmed"

            if upd:
                await repo.update_athlete(matched["id"], upd)
            updated_count += 1
        else:
            create_dto = AdminAthleteCreate(
                first_name=first_name,
                last_name=last_name,
                middle_name=middle_name or None,
                birth_date=str(parsed_bdate) if parsed_bdate else None,
                birth_year=birth_year,
                gender=gender_val,
                city=city_val,
                club=club_val,
                employee_status=emp_status,
                is_hidden=False,
            )
            await repo.create_athlete(create_dto)
            created_count += 1

    await repo.log_audit(
        user_id=current_user.id,
        action="import_athletes_roster",
        entity="athlete",
        entity_id=0,
        diff={"filename": filename, "total": total, "created": created_count, "updated": updated_count, "errors_count": len(errors)},
    )
    await session.commit()

    return RosterImportResult(
        total=total,
        created=created_count,
        updated=updated_count,
        errors=errors,
    )

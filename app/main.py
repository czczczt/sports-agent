import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import SQLITE_DB_PATH, APP_HOST, APP_PORT
from app.db import get_db, get_db_connection
from app.api.athletes import router as athletes_router
from app.api.events import router as events_router
from app.api.races import router as races_router
from app.agent_review import router as agent_review_router
from app.services.athlete_service import (
    search_athletes, get_athlete_summary, get_athlete_results
)
from app.services.events_service import (
    list_events, get_event_by_id, get_race_results, get_race_competition,
    get_athlete_race_result, get_race_rating_leaders
)
from app.services.rating_service import recalculate as recalculate_rating, get_rating_page
from init_athletes import setup_schema, populate_athletes


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения: проверка БД при старте."""
    conn = get_db_connection()
    setup_schema(conn)
    # Если таблица athlete не заполнена, запускаем наполнение
    count = conn.execute("SELECT count(*) FROM athlete").fetchone()[0]
    conn.close()
    if count == 0:
        print("[Startup] Таблица athlete пуста. Запуск инициализации...")
        populate_athletes(SQLITE_DB_PATH)
    else:
        print(f"[Startup] База данных готова. Спортсменов в индексе: {count}")
    rating_conn = get_db_connection()
    rating_report = recalculate_rating(rating_conn)
    rating_conn.close()
    print(
        "[Startup] Рейтинг бега пересчитан: "
        f"{rating_report['athletes_rated']} спортсменов, "
        f"{rating_report['results_scored']} результатов"
    )
    yield


app = FastAPI(
    title="СберСпорт: Платформа бегового рейтинга (MVP)",
    description="MVP бэкенда для сбора результатов, поиска спортсменов, протоколов и ИИ-агента оценки.",
    version="1.0.0",
    lifespan=lifespan
)

# Подключение статических файлов (если понадобятся локальные ассеты)
static_dir = BASE_DIR / "static"
if not static_dir.exists():
    static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Подключение REST API роутеров
app.include_router(athletes_router)
app.include_router(events_router)
app.include_router(races_router)
app.include_router(agent_review_router)   # экран подтверждения правок агента


# =====================================================================
# ВЕБ-МАРШРУТЫ ДЛЯ ДЕМОНСТРАЦИОННОГО ИНТЕРФЕЙСА (ЧЕРНОВОЙ UI)
# =====================================================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home_search_view(
    request: Request,
    last_name: Optional[str] = Query(None),
    birth_year: Optional[str] = Query(None),
    db=Depends(get_db)
):
    """Главная страница: поиск спортсмена и выбор кандидата."""
    candidates = []
    missing_birth_year = False
    clean_last_name = (last_name or "").strip()

    parsed_birth_year: Optional[int] = None
    if birth_year and birth_year.strip().isdigit():
        try:
            parsed_birth_year = int(birth_year.strip())
        except ValueError:
            parsed_birth_year = None

    if clean_last_name:
        if not parsed_birth_year:
            missing_birth_year = True
        else:
            candidates = search_athletes(db, last_name=clean_last_name, birth_year=parsed_birth_year, limit=50)

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "query_last_name": clean_last_name,
            "query_birth_year": parsed_birth_year,
            "candidates": candidates,
            "missing_birth_year": missing_birth_year
        }
    )


@app.get("/rating-view", response_class=HTMLResponse, include_in_schema=False)
async def rating_view(
    request: Request,
    gender: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    athlete_id: Optional[int] = Query(None),
    db=Depends(get_db),
):
    """Страница сохранённого рейтинга бегунов за последние 365 дней."""
    clean_gender = gender if gender in ("M", "F") else None
    clean_search = (search or "").strip()
    rating = get_rating_page(
        db,
        gender=clean_gender,
        search=clean_search or None,
        limit=100,
    )
    me_row = None
    if athlete_id:
        ar = db.execute(
            """
            SELECT a.id AS athlete_id, a.display_name, a.birth_year, a.gender,
                   ar.points, ar.best_points, ar.starts_count, ar.rank AS overall_rank
            FROM athlete a
            LEFT JOIN running_athlete_rating ar
              ON ar.athlete_id = a.id AND ar.formula_version = 'run-v1'
            WHERE a.id = ?
            ORDER BY ar.period_end DESC
            LIMIT 1
            """,
            (athlete_id,)
        ).fetchone()

        if ar and ar["points"] is not None:
            athlete_gender = ar["gender"]
            # Если выбран фильтр по полу, и спортсмен другого пола — скрываем его
            if clean_gender and athlete_gender != clean_gender:
                me_row = None
            else:
                if clean_gender:
                    # Пересчитываем место именно среди участников данного пола
                    rank = db.execute(
                        """
                        SELECT COUNT(*) + 1 AS rank
                        FROM running_athlete_rating rar
                        JOIN athlete a ON a.id = rar.athlete_id
                        WHERE rar.formula_version = 'run-v1'
                          AND a.gender = ?
                          AND (
                              rar.points > ?
                              OR (rar.points = ? AND rar.best_points > ?)
                              OR (rar.points = ? AND rar.best_points = ? AND rar.starts_count > ?)
                              OR (rar.points = ? AND rar.best_points = ? AND rar.starts_count = ? AND rar.athlete_id < ?)
                          )
                        """,
                        (clean_gender, ar["points"], ar["points"], ar["best_points"],
                         ar["points"], ar["best_points"], ar["starts_count"],
                         ar["points"], ar["best_points"], ar["starts_count"], ar["athlete_id"])
                    ).fetchone()[0]
                else:
                    rank = ar["overall_rank"]

                me_row = {
                    "rank": rank,
                    "athlete_id": ar["athlete_id"],
                    "display_name": ar["display_name"],
                    "birth_year": ar["birth_year"],
                    "gender": ar["gender"],
                    "points": ar["points"],
                    "best_points": ar["best_points"],
                    "starts_count": ar["starts_count"],
                }

    return templates.TemplateResponse(
        request=request,
        name="rating.html",
        context={
            "rating": rating,
            "gender": clean_gender,
            "search_query": clean_search,
            "athlete_id": athlete_id,
            "me_row": me_row,
        },
    )


@app.get("/rating-formula", response_class=HTMLResponse, include_in_schema=False)
async def rating_formula_view(
    request: Request,
    db=Depends(get_db),
):
    """Пояснение действующей формулы бегового рейтинга."""
    norms = db.execute(
        """
        SELECT distance_class, gender, value, unit
        FROM rating_norm
        WHERE year = 2026
        ORDER BY CASE distance_class
            WHEN '60m' THEN 1 WHEN '100m' THEN 2 WHEN '200m' THEN 3
            WHEN '400m' THEN 4 WHEN '800m' THEN 5 WHEN '1000m' THEN 6
            WHEN '1500m' THEN 7 WHEN '1mile' THEN 8 WHEN '3000m' THEN 9
            WHEN '5000m' THEN 10 WHEN '10000m' THEN 11
            WHEN 'half_marathon' THEN 12 WHEN 'marathon' THEN 13
            WHEN '100km' THEN 14 WHEN '24h' THEN 15 ELSE 99 END,
            gender
        """
    ).fetchall()
    period = db.execute(
        """
        SELECT period_start, period_end
        FROM running_athlete_rating
        WHERE formula_version = 'run-v1'
        ORDER BY period_end DESC LIMIT 1
        """
    ).fetchone()
    return templates.TemplateResponse(
        request=request,
        name="rating_formula.html",
        context={"norms": norms, "period": period},
    )
@app.get("/athletes-view/{athlete_id}", response_class=HTMLResponse, include_in_schema=False)
async def athlete_profile_view(
    request: Request,
    athlete_id: int,
    db=Depends(get_db)
):
    """Страница профиля спортсмена: результаты, PB, динамика, рейтинг и агент."""
    summary = get_athlete_summary(db, athlete_id=athlete_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    results = get_athlete_results(db, athlete_id=athlete_id)
    import json
    dynamics_json = json.dumps([d.model_dump() for d in summary.dynamics], ensure_ascii=False)
    return templates.TemplateResponse(
        request=request,
        name="athlete_profile.html",
        context={
            "summary": summary,
            "results": results,
            "dynamics_json": dynamics_json,
            "selected_sport": "Бег"
        }
    )


@app.get("/events-view", response_class=HTMLResponse, include_in_schema=False)
async def events_catalog_view(
    request: Request,
    query: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    db=Depends(get_db)
):
    """Каталог стартов с фильтрами по названию забега, дате, городу и источнику."""
    search_query = query or title
    events = list_events(
        db, query=search_query, date_from=date_from, date_to=date_to, city=city,
        source=source, limit=60, offset=0
    )
    return templates.TemplateResponse(
        request=request,
        name="events_catalog.html",
        context={
            "events": events,
            "filters": {
                "query": search_query,
                "title": search_query,
                "date_from": date_from,
                "date_to": date_to,
                "city": city,
                "source": source
            }
        }
    )


@app.get("/events-view/{event_id}", response_class=HTMLResponse, include_in_schema=False)
async def event_detail_view(
    request: Request,
    event_id: int,
    db=Depends(get_db)
):
    """Карточка старта со списком дистанций."""
    event = get_event_by_id(db, event_id=event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Старт не найден")
    return templates.TemplateResponse(
        request=request,
        name="event_detail.html",
        context={
            "event": event
        }
    )


@app.get("/races-view/{race_id}", response_class=HTMLResponse, include_in_schema=False)
async def race_detail_view(
    request: Request,
    race_id: int,
    search: Optional[str] = Query(None),
    athlete_id: Optional[int] = Query(None),
    db=Depends(get_db)
):
    """Карточка дистанции: протокол забега и блок 'Конкуренция' (гистограмма)."""
    # Получаем старт и дистанцию
    cur = db.cursor()
    race_row = cur.execute("SELECT id, event_id, name_raw, norm_distance, distance_m FROM race WHERE id = ?", (race_id,)).fetchone()
    if not race_row:
        raise HTTPException(status_code=404, detail="Дистанция не найдена")

    event = get_event_by_id(db, event_id=race_row["event_id"])
    results = get_race_results(db, race_id=race_id, search_query=search, limit=300, offset=0)

    pinned_athlete_result = None
    show_gap = False

    # Если передан athlete_id и поиск не активен:
    # Если спортсмен занял место > 100 (или не финишировал DNS/DNF):
    # выносим его наверх таблицы с разделителем точек, исключая дублирование в основном списке
    if athlete_id and not search:
        athlete_item = get_athlete_race_result(db, race_id=race_id, athlete_id=athlete_id)
        if athlete_item:
            # Проверяем место: если место > 100 или места нет (DNS/DNF/DSQ)
            is_over_100 = (athlete_item.place_abs is None) or (isinstance(athlete_item.place_abs, int) and athlete_item.place_abs > 100)
            if is_over_100:
                pinned_athlete_result = athlete_item
                show_gap = True
                # Убираем спортсмена из основного списка, чтобы не дублировать
                results = [r for r in results if r.athlete_id != athlete_id]

    competition = get_race_competition(db, race_id=race_id, athlete_id=athlete_id)
    rating_leaders = get_race_rating_leaders(db, race_id=race_id)

    return templates.TemplateResponse(
        request=request,
        name="race_detail.html",
        context={
            "event": event,
            "race": race_row,
            "results": results,
            "pinned_athlete_result": pinned_athlete_result,
            "show_gap": show_gap,
            "competition": competition,
            "rating_leaders": rating_leaders,
            "search_query": search or "",
            "athlete_id": athlete_id
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=True)

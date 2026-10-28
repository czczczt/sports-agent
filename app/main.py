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
from app.services.athlete_service import (
    search_athletes, get_athlete_summary, get_athlete_results
)
from app.services.events_service import (
    list_events, get_event_by_id, get_race_results, get_race_competition
)
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


# =====================================================================
# ВЕБ-МАРШРУТЫ ДЛЯ ДЕМОНСТРАЦИОННОГО ИНТЕРФЕЙСА (ЧЕРНОВОЙ UI)
# =====================================================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home_search_view(
    request: Request,
    last_name: Optional[str] = Query(None),
    birth_year: Optional[int] = Query(None),
    db=Depends(get_db)
):
    """Главная страница: поиск спортсмена и выбор кандидата."""
    candidates = []
    if last_name:
        candidates = search_athletes(db, last_name=last_name, birth_year=birth_year, limit=50)

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "query_last_name": last_name or "",
            "query_birth_year": birth_year,
            "candidates": candidates
        }
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
            "dynamics_json": dynamics_json
        }
    )


@app.get("/events-view", response_class=HTMLResponse, include_in_schema=False)
async def events_catalog_view(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    db=Depends(get_db)
):
    """Каталог стартов с фильтрами по дате, городу и источнику."""
    events = list_events(
        db, date_from=date_from, date_to=date_to, city=city,
        source=source, limit=60, offset=0
    )
    return templates.TemplateResponse(
        request=request,
        name="events_catalog.html",
        context={
            "events": events,
            "filters": {
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
    results = get_race_results(db, race_id=race_id, search_query=search, limit=200, offset=0)
    competition = get_race_competition(db, race_id=race_id, athlete_id=athlete_id)

    return templates.TemplateResponse(
        request=request,
        name="race_detail.html",
        context={
            "event": event,
            "race": race_row,
            "results": results,
            "competition": competition,
            "search_query": search or "",
            "athlete_id": athlete_id
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=True)

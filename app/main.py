from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.config import SQLITE_DB_PATH, APP_HOST, APP_PORT
from app.db import get_db_connection
from app.api.athletes import router as athletes_router
from app.api.events import router as events_router
from app.api.races import router as races_router
from app.api.rating import router as rating_router
from app.agent_review import router as agent_review_router
from app.frontend import mount_frontend
from app.services.rating_service import recalculate as recalculate_rating
from init_athletes import setup_schema, populate_athletes


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

# REST API. Интерфейс (frontend/) ходит только в /api/...; старые адреса без префикса
# (/athletes, /events, /races) оставлены для совместимости и скрыты из Swagger.
api = APIRouter(prefix="/api")
for domain_router in (athletes_router, events_router, races_router, rating_router):
    api.include_router(domain_router)
app.include_router(api)
for legacy_router in (athletes_router, events_router, races_router):
    app.include_router(legacy_router, include_in_schema=False)
app.include_router(agent_review_router)   # /api/agent-review/... — экран подтверждения правок агента

# React-интерфейс (frontend/dist) и SPA-fallback. Строго последним: перехватывает все прочие GET.
mount_frontend(app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=True)

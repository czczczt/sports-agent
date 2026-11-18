from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from app.config import APP_HOST, APP_PORT
from app.db import get_db_pool, close_db_pool
from app.api.athletes import router as athletes_router
from app.api.auth import router as auth_router, get_current_user
from app.api.events import router as events_router
from app.api.races import router as races_router
from app.api.rating import router as rating_router
from app.api.reports import router as reports_router
from app.agent_review import router as agent_review_router
from app.frontend import mount_frontend


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения: инициализация пула PostgreSQL при старте."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        athlete_count = await conn.fetchval("SELECT count(*) FROM athlete")
        rating_count = await conn.fetchval("SELECT count(*) FROM running_athlete_rating")
        print(
            f"[Startup] PostgreSQL подключен. Спортсменов в базе: {athlete_count}, "
            f"записей в рейтинге: {rating_count}"
        )
    try:
        yield
    finally:
        await close_db_pool()
        print("[Shutdown] Пул PostgreSQL закрыт.")


app = FastAPI(
    title="СберСпорт: Платформа бегового рейтинга (MVP)",
    description="MVP бэкенда для сбора результатов, поиска спортсменов, протоколов и ИИ-агента оценки.",
    version="1.0.0",
    lifespan=lifespan
)

# REST API. Сервис для внутреннего пользования: все доменные эндпоинты требуют авторизации.
# /api/auth открыт для входа по логину и паролю.
api = APIRouter(prefix="/api")
api.include_router(auth_router)

protected_api = APIRouter(dependencies=[Depends(get_current_user)])
for domain_router in (athletes_router, events_router, races_router, rating_router, reports_router):
    protected_api.include_router(domain_router)
api.include_router(protected_api)
app.include_router(api)

for legacy_router in (athletes_router, events_router, races_router):
    app.include_router(legacy_router, dependencies=[Depends(get_current_user)], include_in_schema=False)
app.include_router(agent_review_router, dependencies=[Depends(get_current_user)])

# React-интерфейс (frontend/dist) и SPA-fallback. Строго последним: перехватывает все прочие GET.
mount_frontend(app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=True)

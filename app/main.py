from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent_review import router as agent_review_router
from app.api.access_requests import router as access_requests_router
from app.api.athletes import router as athletes_router
from app.api.auth import get_current_user
from app.api.auth import router as auth_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.races import router as races_router
from app.api.rating import router as rating_router
from app.api.reports import router as reports_router
from app.api.runs import router as runs_router
from app.api.status import router as status_router
from app.config import APP_HOST, APP_PORT, DATABASE_URL
from app.core.database import async_postgres_url
from app.frontend import mount_frontend
from app.modules.athletes.exceptions import AthleteNotFound
from app.recipe_agent.api import router as recipe_review_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения: инициализация пула PostgreSQL при старте."""
    engine = create_async_engine(
        async_postgres_url(DATABASE_URL),
        pool_pre_ping=True,
        isolation_level="REPEATABLE READ",
    )
    app.state.postgres_sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield
    finally:
        del app.state.postgres_sessions
        await engine.dispose()


app = FastAPI(
    title="СберСпорт: Платформа бегового рейтинга (MVP)",
    description="MVP бэкенда для сбора результатов, поиска спортсменов, протоколов и ИИ-агента оценки.",
    version="1.0.0",
    lifespan=lifespan,
)

# REST API. Сервис для внутреннего пользования: все доменные эндпоинты требуют авторизации.
# /api/auth открыт для входа по логину и паролю.
api = APIRouter(prefix="/api")
api.include_router(auth_router)

protected_api = APIRouter(dependencies=[Depends(get_current_user)])
for domain_router in (
    athletes_router,
    events_router,
    races_router,
    rating_router,
    reports_router,
    access_requests_router,
    status_router,
    runs_router,
):
    protected_api.include_router(domain_router)
api.include_router(protected_api)
app.include_router(api)

for legacy_router in (athletes_router, events_router, races_router):
    app.include_router(
        legacy_router, dependencies=[Depends(get_current_user)], include_in_schema=False
    )
app.include_router(agent_review_router, dependencies=[Depends(get_current_user)])
app.include_router(recipe_review_router)


@app.exception_handler(AthleteNotFound)
async def athlete_not_found(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


# React-интерфейс (frontend/dist) и SPA-fallback. Строго последним: перехватывает все прочие GET.
app.include_router(health_router)
mount_frontend(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=APP_HOST,
        port=APP_PORT,
        loop="app.core.database:postgres_event_loop_factory",
        reload=True,
    )

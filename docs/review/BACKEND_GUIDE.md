# Гид по бэкенду на FastAPI

Свод правил и практик бэкенд-разработки для разработчиков и AI-агентов. Стек: FastAPI, Pydantic v2 (+pydantic-settings), SQLAlchemy 2.0 async, asyncpg, Alembic, uv, ruff, mypy, pytest. Примеры доменные (спорт), правила не привязаны к проекту.

Формат каждого раздела: правило, почему, пример «плохо / хорошо». Код в примерах без комментариев-пересказов.

## Оглавление

1. Принципы и структура проекта
2. FastAPI: best practices
3. Pydantic: схемы и настройки
4. Async и event loop
5. База данных: сессии, транзакции, запросы
6. Alembic: миграции
7. Фоновые задачи
8. Конфиг, логирование, ошибки, healthcheck
9. Тестирование
10. Docker
11. Чек-лист PR и правила для AI-агента

---

## 1. Принципы и структура проекта

### 1.1 Слои

```
router (HTTP)  ->  service (правила, транзакция)  ->  repository (SQL)  ->  models (таблицы)
```

| Слой | Знает про | Не знает про | Что делает |
|---|---|---|---|
| `router.py` | FastAPI, schemas, service | SQLAlchemy, `Session`, SQL | Разбор HTTP, вызов сервиса, статус-коды |
| `service.py` | repository, schemas, exceptions | `Request`, `HTTPException`, `Response` | Бизнес-правила, оркестрация, граница транзакции |
| `repository.py` | `AsyncSession`, models | schemas ответа, HTTP | Запросы к БД, возвращает ORM-объекты или простые типы |
| `models.py` | SQLAlchemy | всё остальное | Таблицы, связи, индексы |

Правила импортов (одно направление, снизу вверх запрещено):

- `router` импортирует `service`, `schemas`, `dependencies`. Не импортирует `repository` и `models`.
- `service` импортирует `repository`, `schemas`, `exceptions`, соседние сервисы через публичный интерфейс. Не импортирует `fastapi`.
- `repository` импортирует `models` и `sqlalchemy`. Не импортирует `service`, `router`, `fastapi`.
- Модуль домена А не лезет в `repository`/`models` модуля Б; только в его `service`.
- Скрипты и парсеры не импортируются из `app/`, и `app/` не делает `sys.path.insert`.

Запрещено: SQL в роутере, `HTTPException` в сервисе, бизнес-логика в модели, `session.commit()` в репозитории, глобальное соединение с БД, `print`.

### 1.2 Модульность по доменам

Дерево каталогов:

```
.
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── migrations/
│   ├── env.py
│   └── versions/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   └── pagination.py
│   ├── modules/
│   │   ├── athletes/
│   │   │   ├── router.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   ├── dependencies.py
│   │   │   └── exceptions.py
│   │   ├── races/
│   │   └── rating/
│   ├── workers/
│   │   ├── settings.py
│   │   └── tasks.py
│   └── api_v1.py
└── tests/
    ├── conftest.py
    ├── factories.py
    └── modules/
```

`core/` содержит только то, что нужно всем и не знает про домены. `api_v1.py` собирает роутеры доменов. `main.py` только создаёт приложение.

Размер: файл больше 300 строк это сигнал к разделению; функция больше 40 строк тоже.

---

## 2. FastAPI: best practices

### 2.1 Lifespan вместо on_event

Правило: ресурсы приложения (engine, httpx-клиент) создаются и закрываются в `lifespan`.
Почему: `on_event` устарел; lifespan гарантирует закрытие ресурсов; нет тяжёлых операций до старта.

Плохо:

```python
@app.on_event("startup")
def startup() -> None:
    recalculate_rating(sqlite3.connect("running.db"))
```

Хорошо:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings)
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0))
    try:
        yield
    finally:
        await app.state.http.aclose()
        await engine.dispose()
```

Тяжёлые операции (пересчёт рейтинга, наполнение справочников) не делаются в lifespan: это отдельная команда или задача воркера.

### 2.2 APIRouter, версионирование, response_model, статус-коды

```python
router = APIRouter(prefix="/athletes", tags=["athletes"])


@router.get("/{athlete_id}", response_model=AthleteOut)
async def get_athlete(athlete_id: int, service: AthleteServiceDep) -> AthleteOut:
    return await service.get(athlete_id)


@router.post("", response_model=AthleteOut, status_code=status.HTTP_201_CREATED)
async def create_athlete(body: AthleteIn, service: AthleteServiceDep) -> AthleteOut:
    return await service.create(body)


@router.delete("/{athlete_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_athlete(athlete_id: int, service: AthleteServiceDep) -> None:
    await service.delete(athlete_id)
```

```python
api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(athletes_router)
api_v1.include_router(races_router)
app.include_router(api_v1)
```

Правила:

- Все маршруты под `/api/v1`. Дубли «для совместимости» без префикса не заводить.
- У каждого эндпоинта `response_model` (или аннотация возврата) и осмысленный статус: 201 создание, 204 удаление, 202 «принято в очередь», 404/409/422 для ошибок.
- Возвращать `dict` из роутера нельзя: контракт пропадает из OpenAPI.

### 2.3 Depends и Annotated-алиасы

Правило: зависимости объявляются один раз как `Annotated`-алиас и подключаются по имени.
Почему: единая точка подмены в тестах, нет копипасты `Depends(...)` в каждой сигнатуре.

```python
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_athlete_service(session: SessionDep) -> AthleteService:
    return AthleteService(AthleteRepository(session))


AthleteServiceDep = Annotated[AthleteService, Depends(get_athlete_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
```

Auth: защита вешается на роутер (`dependencies=[Depends(require_admin)]`), а не на отдельные функции. Опасные операции (удаление, применение правок, запуск пересчёта) всегда за ролью.

### 2.4 Исключения: домен в HTTP

Правило: сервис бросает доменное исключение, HTTP-код выбирает обработчик.

```python
class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class AthleteNotFound(NotFoundError):
    def __init__(self, athlete_id: int) -> None:
        super().__init__(f"Спортсмен {athlete_id} не найден")
```

```python
@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
```

Плохо: `raise HTTPException(404)` внутри сервиса; `return None` с проверкой в каждом роутере.

### 2.5 Пагинация

Правило: любой список ограничен. `limit` с верхней границей, `offset` или keyset-курсор, ответ содержит `total`.

```python
class PageParams(BaseModel):
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


PageDep = Annotated[PageParams, Depends()]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
```

Для больших таблиц вместо `offset` используем keyset (`WHERE id < :last_id ORDER BY id DESC LIMIT n`).

---

## 3. Pydantic: схемы и настройки

### 3.1 Набор схем

Правило: отдельные схемы для входа, обновления и выхода. Одна «универсальная» схема на всё запрещена.

```python
class AthleteBase(BaseModel):
    last_name: str = Field(min_length=1, max_length=100)
    birth_year: int | None = Field(None, ge=1900, le=2100)
    gender: Literal["M", "F"] | None = None


class AthleteIn(AthleteBase):
    pass


class AthleteUpdate(BaseModel):
    last_name: str | None = Field(None, min_length=1, max_length=100)
    birth_year: int | None = Field(None, ge=1900, le=2100)


class AthleteOut(AthleteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
```

Правила:

- `from_attributes=True` только в `Out`-схемах. Роутер возвращает ORM-объект или схему; Pydantic сам сериализует.
- PATCH: `body.model_dump(exclude_unset=True)`.
- Типы современные: `X | None`, `list[X]`, не `Optional`/`List`.
- Закрытые наборы значений: `Literal` или `StrEnum`, не голый `str`.
- Даты и числа в Query как `date`/`int`, не как `str`.
- `Dict[str, Any]` в ответе запрещён: опишите вложенную модель.

Плохо:

```python
class DecisionIn(BaseModel):
    decision: str
    author: str
```

Хорошо:

```python
class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    author: str = Field(min_length=1, max_length=100)
    comment: str = ""
```

### 3.2 Настройки

Правило: конфиг один раз в `BaseSettings`, из env, с валидацией при старте. Секреты только в env.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: PostgresDsn
    db_pool_size: int = 10
    gigachat_credentials: SecretStr
    gigachat_verify_ssl: bool = True
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Плохо:

```python
GIGACHAT_VERIFY_SSL = os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() in ("true", "1")
DB = os.environ.get("DATABASE_URL", "postgresql://agent:change-me@127.0.0.1:5432/db")
```

Дефолты безопасные (`verify=True`), дефолтов-паролей нет, `.env` в `.gitignore`, пример в `.env.example`.

---

## 4. Async и event loop

### 4.1 Что блокирует loop

Один поток исполняет все `async def`. Любой блокирующий вызов в корутине останавливает всех клиентов.

Блокируют: `requests`, `time.sleep`, `sqlite3`, `psycopg` (sync), `open().read()` на больших файлах, `subprocess.run`, парсинг больших HTML/JSON, `bcrypt`, pandas/numpy-расчёты.

| Задача | Как |
|---|---|
| I/O, есть async-библиотека (asyncpg, httpx) | `async def` + `await` |
| I/O, только sync-библиотека | `def` эндпоинт (FastAPI запустит в threadpool) или `await asyncio.to_thread(fn, ...)` |
| CPU-bound, короткий (до 100 мс) | `asyncio.to_thread` |
| CPU-bound, долгий | процесс/воркер (раздел 7) |
| Запуск внешней команды | `asyncio.create_subprocess_exec` в воркере, не в запросе |

Плохо:

```python
@router.post("/athletes/{athlete_id}/assessment")
async def assess(athlete_id: int, db: sqlite3.Connection = Depends(get_db)):
    metrics = db.execute("SELECT ...").fetchall()
    time.sleep(1)
    return requests.post(URL, json=metrics).json()
```

Хорошо:

```python
@router.post("/{athlete_id}/assessment", response_model=AssessmentOut)
async def assess(athlete_id: int, service: AssessmentServiceDep) -> AssessmentOut:
    return await service.get_or_generate(athlete_id)
```

Не смешивать: `def` эндпоинт с sync-БД допустим, но внутри него нельзя `async`-код; `async def` эндпоинт нельзя соединять с sync-соединением.

### 4.2 httpx.AsyncClient один на приложение

Правило: клиент создаётся в lifespan, передаётся через `Depends`, у каждого вызова есть таймаут.

```python
def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


HttpDep = Annotated[httpx.AsyncClient, Depends(get_http)]
```

Плохо:

```python
async def call(token: str, payload: dict) -> dict:
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(URL, json=payload)
        return resp.json()
```

Хорошо:

```python
class LlmClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        self._semaphore = asyncio.Semaphore(4)

    async def complete(self, prompt: str) -> str:
        async with self._semaphore:
            resp = await self._http.post(
                self._settings.llm_url,
                json={"prompt": prompt},
                timeout=httpx.Timeout(30.0, connect=3.0),
            )
        resp.raise_for_status()
        return resp.json()["text"]
```

Правила: явные таймауты (connect/read), семафор на внешний API, кэш токена с `expires_at` и `asyncio.Lock`, ретраи с backoff только для идемпотентных вызовов.

### 4.3 Параллельная работа

```python
async def load_profile(athlete_id: int) -> Profile:
    results, records = await asyncio.gather(
        results_repo.list_for(athlete_id),
        records_repo.personal_bests(athlete_id),
    )
    return Profile(results=results, records=records)
```

Внимание: одну `AsyncSession` нельзя использовать в двух корутинах одновременно. Для `gather` каждому запросу нужна своя сессия, либо выполнять последовательно.

---

## 5. База данных

### 5.1 Engine и sessionmaker

```python
def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        str(settings.database_url).replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=settings.db_pool_size,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
```

```python
sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
```

- Один engine на процесс, создаётся в lifespan.
- `expire_on_commit=False`: после commit объекты остаются читаемыми (иначе ленивая подгрузка в async даёт `MissingGreenlet`).
- Размер пула согласовать: `pool_size * число воркеров uvicorn` не больше `max_connections` PostgreSQL.
- Ленивые связи в async запрещены: загружать явно (`selectinload`).

### 5.2 Короткие сессии

Правило: сессия живёт только на время работы с БД. Во время сетевых вызовов (LLM, внешний API, парсинг сайта) сессии и транзакции нет.

Почему: открытая транзакция держит соединение из пула; при 10 запросах с LLM по 30 секунд пул кончается, API встаёт.

Сессия на запрос:

```python
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session
```

Сессия на единицу работы в фоне:

```python
async def refresh_assessment(ctx: dict, athlete_id: int) -> None:
    sessionmaker = ctx["sessionmaker"]
    llm = ctx["llm"]

    async with sessionmaker() as session:
        metrics = await MetricsRepository(session).for_athlete(athlete_id)

    text = await llm.complete(render_prompt(metrics))

    async with sessionmaker() as session, session.begin():
        await AssessmentRepository(session).upsert(athlete_id, text)
```

Плохо:

```python
async def get_or_generate(self, athlete_id: int) -> AssessmentOut:
    cached = await self.repo.get(athlete_id)
    if cached:
        return cached
    text = await self.llm.complete(...)
    await self.repo.save(athlete_id, text)
    await self.session.commit()
```

Здесь сессия (и соединение) удерживается на всё время `llm.complete`. Нужно: прочитать, отпустить, сходить в сеть, открыть новую сессию, записать через upsert.

### 5.3 Транзакции и Unit of Work

Правило: границу транзакции задаёт сервис (один бизнес-сценарий = одна транзакция). Репозиторий не коммитит.

```python
class AthleteService:
    def __init__(self, session: AsyncSession, athletes: AthleteRepository, results: ResultRepository) -> None:
        self._session = session
        self._athletes = athletes
        self._results = results

    async def merge(self, source_id: int, target_id: int) -> None:
        async with self._session.begin():
            await self._results.reassign(source_id, target_id)
            await self._athletes.delete(source_id)
```

Если сессия уже начала транзакцию автоматически (чтением в `Depends`), используйте один стиль на проект: либо `async with session.begin()` в сервисе на запись, либо `await session.commit()` в конце сценария. Одновременно оба не использовать.

Читающие эндпоинты не коммитят. Исключение из сервиса откатывает транзакцию автоматически при выходе из `begin()`.

### 5.4 Репозиторий

Правило: репозиторий обязателен для каждого домена, даже для простого CRUD. Сервис не работает с `AsyncSession` запросами напрямую.

Почему: SQL в одном месте, сервис тестируется с фейковым репозиторием, ревью проще.

```python
class AthleteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, athlete_id: int) -> Athlete | None:
        return await self._session.get(Athlete, athlete_id)

    async def search(self, last_name: str, birth_year: int | None, page: PageParams) -> list[Athlete]:
        conds = [Athlete.name_key.ilike(f"{last_name}%")]
        if birth_year is not None:
            conds.append(Athlete.birth_year.between(birth_year - 1, birth_year + 1))
        stmt = select(Athlete).where(*conds).order_by(Athlete.id).limit(page.limit).offset(page.offset)
        return list((await self._session.scalars(stmt)).all())
```

Правила:

- Никаких f-строк в SQL. Динамические условия собираются списком выражений `where(*conds)`.
- Если нужен сырой SQL: `text("... WHERE id = :id")` и параметры словарём.
- Репозиторий возвращает ORM или простые типы, схемы ответа собирает сервис/роутер.

Плохо:

```python
cur.execute(f"SELECT * FROM athlete WHERE {where_clause} LIMIT ?", params)
```

### 5.5 N+1

Плохо:

```python
events = (await session.scalars(select(Event).limit(50))).all()
for event in events:
    event.races
```

Хорошо:

```python
stmt = select(Event).options(selectinload(Event.races)).order_by(Event.date.desc()).limit(50)
events = (await session.scalars(stmt)).all()
```

Для «один ко многим» предпочтителен `selectinload`, для «многие к одному» `joinedload`. Проверять число запросов в тесте (счётчик через event `before_cursor_execute`).

### 5.6 Bulk upsert

```python
async def upsert_results(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    stmt = insert(Result).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Result.race_id, Result.bib],
        set_={"place": stmt.excluded.place, "chip_time_s": stmt.excluded.chip_time_s},
    )
    await session.execute(stmt)
```

- Пачками (например, по 1000 строк): у asyncpg лимит 32767 параметров на запрос.
- Уникальный индекс под `ON CONFLICT` обязателен.
- Кэш «посчитано LLM» это тоже upsert по `athlete_id`, а не `SELECT` + `INSERT`: так два параллельных запроса не дублируют работу.

### 5.7 Индексы и ограничения

- Индекс на каждый внешний ключ и на поля, по которым ищем и сортируем.
- Поиск по тексту: `pg_trgm` GIN или нормализованное поле (`name_key`) при записи; не функции в `WHERE` без функционального индекса.
- Ограничения в БД, не только в коде: `UNIQUE`, `CHECK`, `NOT NULL`, FK с `ondelete`.
- Время хранить как `timestamptz`; деньги и точные величины `Numeric`.

---

## 6. Alembic

### 6.1 Async env.py

```python
def run_migrations_online() -> None:
    connectable = create_async_engine(get_settings().sqlalchemy_url, poolclass=pool.NullPool)

    async def run() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    asyncio.run(run())


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()
```

### 6.2 Naming convention

```python
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
```

Без naming convention автогенерация создаёт безымянные ограничения, которые нельзя надёжно удалить.

### 6.3 Правила миграций

- Схему меняют только миграциями. `CREATE TABLE IF NOT EXISTS` в коде приложения запрещён.
- `alembic revision --autogenerate -m "..."`, затем ручная проверка: автогенерация не видит переименований и часть изменений.
- Применённую (в main/на любом общем стенде) миграцию не править; новая правка = новая ревизия.
- Структурные и data-миграции раздельно: перенос данных в своей ревизии.
- Каждая миграция имеет рабочий `downgrade`, либо явно помечена необратимой.
- Опасные операции на больших таблицах: добавить nullable-колонку, заполнить, потом `NOT NULL`; индекс `CONCURRENTLY`.
- Одна «голова» (`alembic heads`), проверять в CI; `alembic upgrade head` на чистой БД и на дампе.
- Миграции запускаются отдельным шагом (job/entrypoint), не в lifespan.
- Миграции не импортируют код приложения (модели меняются, миграции должны остаться прежними).

---

## 7. Фоновые задачи

Правило: `BackgroundTasks` только для коротких (до секунд) дел, потерю которых не жалко: отправить письмо, записать аудит. Всё остальное идёт в воркер.

Почему: `BackgroundTasks` работает в том же процессе; рестарт теряет задачу; нет повторов, статуса и ограничения параллелизма.

| Признак | Решение |
|---|---|
| До 1-2 секунд, потеря допустима | `BackgroundTasks` |
| Минуты, LLM, парсинг, git, пересчёт рейтинга | воркер с очередью |
| По расписанию | периодические задачи воркера (cron arq / `periodic` procrastinate) |

Паттерн для долгих задач:

1. `POST /api/v1/jobs/...` создаёт запись `job(status=queued)` и кладёт id в очередь, отвечает `202` + `job_id`.
2. Воркер берёт задачу, обновляет `status`, пишет результат.
3. `GET /api/v1/jobs/{id}` возвращает статус и результат.
4. Идемпотентность: повторный запуск той же задачи не ломает данные (upsert, ключ идемпотентности).

Выбор очереди:

| Ситуация | Очередь | Почему |
|---|---|---|
| Redis в стеке нет | procrastinate | Очередь в том же Postgres: retry, periodic, блокировки, без лишнего сервиса |
| Redis уже есть (кэш, pub/sub) | arq | Async, минимум кода, cron и retry из коробки |

Celery не брать: sync-модель, тяжёлая конфигурация, для async-стека избыточен. Своя очередь на `SELECT ... FOR UPDATE SKIP LOCKED` допустима, если задача одна и простая.

Плохо:

```python
@router.post("/{issue_id}/apply")
def apply(issue_id: int):
    subprocess.run(["git", "push", ...], timeout=300)
```

Хорошо:

```python
@router.post("/{issue_id}/apply", status_code=status.HTTP_202_ACCEPTED, response_model=JobOut)
async def apply(issue_id: int, jobs: JobServiceDep, _: AdminDep) -> JobOut:
    return await jobs.enqueue("apply_issue", issue_id=issue_id)
```

---

## 8. Конфиг, логирование, ошибки, healthcheck

### 8.1 Логирование

Правила: `print` запрещён. Логгер на модуль; формат JSON в проде; исключения логируются с трейсом; секреты и персональные данные не логируются.

```python
logger = structlog.get_logger(__name__)


async def refresh(athlete_id: int) -> None:
    try:
        text = await llm.complete(prompt)
    except httpx.HTTPError:
        logger.exception("llm_failed", athlete_id=athlete_id)
        raise
    logger.info("assessment_saved", athlete_id=athlete_id, chars=len(text))
```

Плохо:

```python
except Exception:
    assessment = fallback(metrics)
```

Правило: `except Exception` без логирования и без повторного `raise` запрещён. Ловить узкие типы.

Конфигурация логов в одном месте (`core/logging.py`), вызывается из `lifespan`/точки входа воркера. Добавляйте `request_id` через middleware.

### 8.2 Обработка ошибок

- Доменные ошибки: раздел 2.4.
- Валидация: 422 от FastAPI, не ловить.
- Неожиданные: обработчик `Exception` возвращает 500 без деталей и логирует трейс.
- Внешние сервисы: ловить `httpx.HTTPError` и превращать в доменную ошибку (502/503) с понятным кодом.
- Fallback-результат нельзя записывать в кэш под видом настоящего.

### 8.3 Healthcheck

```python
@router.get("/health/live", include_in_schema=False)
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
async def ready(session: SessionDep) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
```

`live` не ходит в БД (процесс жив), `ready` проверяет зависимости. Compose/оркестратор используют их в healthcheck.

---

## 9. Тестирование

### 9.1 Фикстуры

```python
@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(conn, expire_on_commit=False, join_transaction_mode="create_savepoint") as s:
            yield s
        await trans.rollback()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app.dependency_overrides[get_session] = lambda: session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 9.2 Правила

- Тестовая БД это отдельная PostgreSQL (testcontainers или сервис в CI), не файл разработчика и не боевая база. SQLite вместо PostgreSQL не использовать: поведение отличается.
- Каждый тест изолирован откатом транзакции; порядок тестов не важен.
- Внешние вызовы (LLM, сайты) подменяются через `dependency_overrides` или фейк-клиент; в тестах сети нет.
- Данные через фабрики (`factory-boy` или простые функции), не через общий дамп.
- Слои: юнит-тесты сервисов (с фейковым репозиторием), интеграционные для репозиториев (реальная БД), API-тесты на основные сценарии и ошибки (404, 409, 422).
- Чистые функции (расчёт баллов) тестируются таблично `pytest.mark.parametrize`.
- Тест на каждый исправленный баг.
- Не писать тесты, привязанные к времени/порядку/текущему наполнению БД.

---

## 10. Docker

### 10.1 Multi-stage Dockerfile на uv

```dockerfile
# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.5.11

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /bin/bash --uid 1000 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/app /app/app
COPY --chown=appuser:appuser alembic.ini ./alembic.ini
COPY --chown=appuser:appuser migrations ./migrations
USER appuser
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

| Приём | Зачем |
|---|---|
| uv из готового образа `ghcr.io/astral-sh/uv:<версия>` с зафиксированной версией | Быстро, без pip, воспроизводимо |
| Зависимости отдельным слоем (`pyproject.toml` + `uv.lock`, `--no-install-project`), код потом | Слой зависимостей кэшируется, пока не изменился lock |
| `--mount=type=cache,target=/root/.cache/uv` | Кэш пакетов между сборками |
| `uv sync --locked --no-dev` | Сборка падает при рассинхроне lock, dev-пакетов в образе нет |
| `UV_COMPILE_BYTECODE=1`, `UV_LINK_MODE=copy` | Быстрый старт, venv переносится между stage |
| Runtime-stage без uv и компиляторов, копируется только `.venv` | Маленький образ |
| Пользователь `appuser`, `--chown` при `COPY` | Не root |

`PYTHONOPTIMIZE=1` отключает `assert` в рантайме: не полагаться на `assert` для проверок.

### 10.2 .dockerignore

Белый список: впускаем только нужное, секреты и данные не попадут в образ случайно.

```
*
!pyproject.toml
!uv.lock
!alembic.ini
!migrations/
!app/
**/__pycache__/
**/*.pyc
```

Файлы данных (`*.db`, дампы, `data/`) и `.env` в образ не попадают никогда.

### 10.3 docker-compose

Пример с arq + Redis; с procrastinate сервис `redis` не нужен, воркер запускается `procrastinate --app=app.workers.app worker`.

```yaml
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "50m"
    max-file: "3"

services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-app}
      POSTGRES_USER: ${POSTGRES_USER:-app}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?задайте POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-app} -d ${POSTGRES_DB:-app}"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped
    logging: *default-logging

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 10
    restart: unless-stopped

  migrate:
    build: .
    image: myproject/app
    command: ["alembic", "upgrade", "head"]
    env_file: [.env]
    depends_on:
      db:
        condition: service_healthy
    restart: "no"

  app:
    image: myproject/app
    env_file: [.env]
    ports: ["127.0.0.1:${APP_PORT:-8000}:8000"]
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
      interval: 10s
      timeout: 3s
      retries: 5
    mem_limit: 1g
    restart: unless-stopped
    logging: *default-logging

  worker:
    image: myproject/app
    command: ["arq", "app.workers.settings.WorkerSettings"]
    env_file: [.env]
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "grep -qa arq /proc/1/cmdline"]
      interval: 10s
      timeout: 3s
      retries: 5
    mem_limit: 1g
    restart: unless-stopped
    logging: *default-logging

volumes:
  pgdata:
```

Ключевые приёмы:

- `x-logging` с ротацией json-file: диск не забивается логами.
- `depends_on` с `service_healthy` / `service_completed_successfully`: порядок запуска по готовности, а не по старту контейнера.
- Миграции отдельным one-shot сервисом `migrate`, а не в entrypoint: при нескольких репликах два `alembic upgrade` гоняются.
- Один образ на `migrate`, `app` и `worker`: собирается один раз.
- `${VAR:?сообщение}`: compose падает с понятной ошибкой, если обязательная переменная не задана.
- `mem_limit`, `restart: unless-stopped`, healthcheck у каждого сервиса.
- Порты привязаны к `127.0.0.1`, наружу публикует только reverse-proxy.
- Данные в именованных volumes; секреты только через `.env`/secrets, не через образ.

### 10.4 pyproject.toml

```toml
[project]
name = "app"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0.35",
    "asyncpg>=0.30",
    "alembic>=1.13",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "httpx>=0.27",
    "structlog>=24.4",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "factory-boy>=3.3",
    "ruff>=0.7",
    "mypy>=1.12",
    "testcontainers>=4.8",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "RUF", "ASYNC", "S", "T20"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`ASYNC` ловит блокирующие вызовы в корутинах, `S` — проблемы безопасности, `T20` запрещает `print`. mypy `strict` с pydantic-плагином. Lock-файл `uv.lock` лежит в репозитории.

---

## 11. Чек-лист PR и правила для AI-агента

### 11.1 Чек-лист PR

- [ ] Импорты только вниз по слоям; SQL только в repository; `HTTPException` только в роутере.
- [ ] У эндпоинта `response_model`, статус-код, маршрут под `/api/v1`; списки с `limit`.
- [ ] Нет блокирующих вызовов в `async def`; сессия не держится во время сетевых вызовов.
- [ ] Нет N+1 и f-строк в SQL; массовые записи через upsert.
- [ ] Изменение схемы идёт с Alembic-миграцией и индексами.
- [ ] Долгие операции в воркере; у внешних вызовов таймауты.
- [ ] Нет голых `except`, `print`, секретов в коде; конфиг через `Settings`.
- [ ] Тесты на новое поведение и ошибки (404/409/422).
- [ ] `ruff`, `mypy`, `pytest` зелёные; `docker compose up` поднимает стек.

### 11.2 Правила для AI-агента

1. Читай этот гид до написания кода; при конфликте с существующим кодом следуй гиду и отметь расхождение в PR.
2. Один домен = `app/modules/<domain>/` (router, schemas, service, repository, models, dependencies, exceptions).
3. Роутер тонкий, сервис бросает доменные исключения, SQL только в repository.
4. Всё I/O асинхронное: никаких `requests`, `time.sleep`, sync-драйверов и `subprocess` в `async def`.
5. Не держи `AsyncSession` во время LLM/HTTP-вызовов: прочитал, закрыл, вызвал, открыл новую, записал.
6. Схему меняй только миграцией; применённые миграции не правь.
7. Долгие задачи (LLM, парсинг, git, пересчёты) ставь в очередь и отвечай 202.
8. Конфиг только через `Settings`, без дефолтов для секретов; `verify=True`.
9. Логгер вместо `print`, исключения не глуши.
10. Тест на каждое изменение поведения; перед завершением `ruff check`, `ruff format`, `mypy`, `pytest` должны быть зелёными.
11. Комментарии в коде: ноль, кроме `# почему: ...`, прагм и `TODO` с конкретикой.

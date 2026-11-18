# Аудит бэкенда sport-raiting-dashboard

Дата: 2026-11-14. Объём: `app/`, `parser_running/` (db/store/run/agent_queue), корневые скрипты, `tests/`, конфиги. Код проекта не менялся.

## 1. Карта текущей архитектуры

```
frontend/ (React, dist раздаётся FastAPI)  ──►  /api/...
                                                   │
app/main.py (FastAPI, sync-lifespan)               │
 ├─ api/{athletes,events,races,rating}.py          │  sync def, Depends(get_db) -> sqlite3.Connection
 │     └─ services/*.py  (голый SQL на sqlite3, dict-ы, часть бизнес-логики и DDL внутри)
 │            └─ SQLite файл running.db (SQLITE_DB_PATH)   <-- ЗАМОРОЖЕННЫЙ снимок данных
 │     └─ services/agent_service.py (async + sync sqlite внутри, GigaChat через httpx)
 ├─ agent_review.py (/api/agent-review/*, sync def)
 │     └─ sys.path.insert(parser_running) -> agent_queue.py, db.py   (psycopg, PostgreSQL)
 │            └─ PostgreSQL (DATABASE_URL, docker-compose db)         <-- ЖИВЫЕ данные парсеров
 ├─ mcp_agent/ (заготовка; пишет в SQLite и в PostgreSQL одновременно)
 └─ frontend.py (SPA-fallback)

parser_running/ (CLI: run.py, runc.py, grom.py, rr_platform.py) -> psycopg -> PostgreSQL
parser_biathlon/ (отдельный набор скриптов, свой requirements.txt)
init_athletes.py / parse_url.py / test_*.py в корне (скрипты, импортируются из app/main.py)
```

Ключевое: в проекте две БД с разными ролями. API читает SQLite, парсеры пишут в PostgreSQL (`parser_running/migrate_sqlite.py` описывает перенос SQLite -> PG как уже случившийся). Экран `/agent-review` ходит в PostgreSQL, остальной сайт в SQLite. Синхронизации между ними нет.

## 2. Сводка по вопросам задания

| Вопрос | Факт |
|---|---|
| sync vs async | Почти все эндпоинты `def` (корректно: уходят в threadpool), но единственный `async def` с БД блокирует loop: `app/api/athletes.py:57` + `agent_service.py:181-241` (sqlite внутри корутины). lifespan делает тяжёлый sync-пересчёт до старта (`main.py:21-43`). |
| Какая БД у API | SQLite (`db.py:36`, `config.py:9`). У `agent_review` и `mcp_agent` частично PostgreSQL. |
| Одна БД или две | Две, рассинхрон: парсеры пишут в PG, API читает файл `running.db` (в `.gitignore`, `*.db`). Новые данные парсера на сайте не появятся. |
| SQL vs ORM | Голый SQL везде, ORM нет. Значения параметризованы (`?` / `%s`), но WHERE собирается f-строкой. |
| Соединения | SQLite: соединение на запрос (`db.py:49-55`), закрывается в `finally`. PG: `_con()` на каждый вызов (`agent_review.py:45`), закрывается, но пула нет и на каждый запрос выполняется `ensure_schema` (DDL). |
| Pydantic | Схемы ответов есть для 4 доменных роутеров (`models.py`), у `agent_review` их нет, `response_model` отсутствует. |
| Конфиг | `os.getenv` + `load_dotenv` на уровне модуля (`config.py`), без валидации. |
| Логи | `print` в lifespan (`main.py:31-43`); `logging` только в `mcp_agent`; парсер: `print` повсюду. |
| Миграции | Нет Alembic. DDL разбросан: `init_athletes.setup_schema`, `rating_service.initialize` (`:69`), `parser_running/db.py`, `agent_queue.ensure_schema`. |
| Тесты | `unittest` + `test_mvp.py` в корне на реальной `running.db`; в `tests/` — scoring-юнит-тесты. Нет изолированной тестовой БД, CI нет. |
| Docker | Нет Dockerfile для app/парсеров. compose содержит только `db` (postgres:16). |

## 3. Таблица проблем

Severity: **C** critical, **H** high, **M** medium, **L** low.

| # | Sev | Где | Что | Почему плохо | Как правильно |
|---|---|---|---|---|---|
| 1 | C | `agent_review.py:185-202`, `:205-219`, `:110-137`, `:222-235` | Деструктивные эндпоинты (`DELETE /clear-all`, `DELETE /{id}`, `reset-demo`, `apply`) без аутентификации; `_cleanup_issue_files` (`:141-182`) удаляет `.py` файлы с диска проекта по именам из БД | Любой, кто видит порт, стирает очередь задач и файлы парсеров; `apply` запускает git push/gh. Данные из БД управляют удалением файлов | Auth (хотя бы API-ключ/роль admin) на весь роутер; убрать файловую чистку из API; демо-ручки только в dev; soft-delete |
| 2 | H | `main.py:21-43`, `rating_service.py:165` | `recalculate` рейтинга и `populate_athletes` синхронно в lifespan при каждом старте | Долгий старт, блокировка loop, гонка при нескольких воркерах (запись в SQLite), `print` вместо логов | Пересчёт — отдельная команда/воркер по расписанию; lifespan только создаёт ресурсы (engine, http-клиент) |
| 3 | H | `config.py:9`, `db.py:36`, `agent_review.py:7,45`, `mcp_agent/orchestrator.py:11,28-31` | Две БД (SQLite для API, PostgreSQL для парсеров и review), нет единого источника правды | Сайт показывает устаревшие данные; код `mcp_agent` пишет в обе БД в одном вызове без транзакционной связи | Одна БД (PostgreSQL), одна модель данных, API читает то, что пишет парсер |
| 4 | H | `api/athletes.py:57`, `agent_service.py:181-241` | `async def` эндпоинт делает sync `sqlite3` в loop; между чтением кэша и записью идёт сетевой вызов GigaChat (до 45 с) с открытым соединением | Блокирует весь event loop; два параллельных запроса оба идут в LLM (нет блокировки/уникальности); соединение держится на время сети | Async-драйвер или `def`; сессия на короткую единицу работы: прочитать, закрыть, сходить в LLM, открыть, записать (upsert) |
| 5 | H | `agent_service.py:226-233,235-241` | `except Exception` без лога, и результат fallback кэшируется навсегда | Временный сбой GigaChat навсегда закрепляет локальный шаблон под видом оценки; причина ошибки теряется | Логировать исключение; не кэшировать fallback (или кэшировать с TTL/пометкой); узкие типы исключений |
| 6 | H | `agent_review.py:23-28`, `:248`, `parser_running/agent_queue.py:566-581,631+` | `sys.path.insert` + импорт CLI-модуля парсера в API-процесс; `apply_approved` делает `git worktree add`, перезапуск парсера (`run_child`, таймаут 300 с `agent_queue.py:38`), `git push`, `gh pr create` внутри HTTP-запроса | Запрос висит минутами, занимает поток; изменение репозитория с сервера; нет повторной защиты от двойного клика | Вынести в воркер/очередь: API создаёт задачу и отдаёт `202` + статус; общая логика — в отдельном пакете, а не через `sys.path` |
| 7 | H | `events_service.py:53,59,215,233`; `rating_service.py:336-352` | SQL собирается f-строкой с `{where_clause}` | Сейчас фрагменты константны и значения идут через `?`, инъекции нет, но паттерн хрупкий: следующий правщик подставит пользовательскую строку | SQLAlchemy Core/ORM с динамическими условиями `and_(*conds)` |
| 8 | H | `agent_review.py:45-48` | `_con()` на каждый запрос: новое TCP-соединение PG + `ensure_schema` (DDL) | Накладные расходы, DDL под нагрузкой, нет пула, `connect_timeout` склеивается строкой | Пул (async engine), схема только миграциями |
| 9 | H | `config.py:16` | `GIGACHAT_VERIFY_SSL` по умолчанию `false` | TLS-проверка отключена в продакшене по умолчанию | Дефолт `true`, отключение только явным флагом в dev; CA сертификат НУЦ Минцифры подкладывать в образ |
| 10 | H | `mcp_agent/orchestrator.py:27,44-57` | Захардкожен DSN `postgresql://agent:change-me@...` и фейковый patch, который пишется в рабочую таблицу `issue` | Демо-данные в боевой очереди, секрет в коде | Конфиг из env, демо-фикстуры вынести в seed/тесты |
| 11 | M | `events_service.py:67-76` | N+1: на каждое событие отдельный запрос `race` | Время растёт линейно с `limit` | Один запрос `WHERE event_id IN (...)` или `selectinload` |
| 12 | M | `main.py:7-12,50-56` | Роутеры импортируются плоско; импорт из корневого скрипта `init_athletes` в `app`; легаси-дубли роутеров без префикса | Нарушение слоёв (приложение зависит от скрипта), удвоенный набор маршрутов | Один префикс `/api/v1`, инициализация данных — CLI-команда/миграция |
| 13 | M | `config.py:1-17` | `os.getenv` + `load_dotenv` на уровне модуля, нет типов и валидации, `int(...)` падает при импорте | Ошибки конфига видны поздно, нет единого объекта настроек, сложно подменять в тестах | `pydantic-settings` `BaseSettings`, `@lru_cache get_settings()`, `Depends(get_settings)` |
| 14 | M | `services/events_service.py` (480 строк), `rating_service.py` (471), `athlete_service.py` (351), `parser_running/agent_queue.py` (784), `parse_url.py` (314) | God-файлы: SQL + бизнес-логика + форматирование ответа в одном модуле; `agent_queue.py` совмещает библиотеку, CLI и `print` | Нельзя тестировать части, сложно ревьюить | Разбить на `repository` (SQL) и `service` (правила), CLI вынести отдельно |
| 15 | M | `services/*.py`, `api/*.py` | Сервисы возвращают `dict`/`None`, роутер решает 404; ошибок домена нет | Логика ошибок размазана, одно и то же `HTTPException(404)` в каждом роуте | Доменные исключения + глобальные обработчики |
| 16 | M | `models.py` | Все схемы в одном файле, `Optional`/`List`/`Union[int,str]`, нет `from_attributes`, `Dict[str, Any]` для breakdown | Слабая типизация контракта, `place_abs: int \| str` скрывает данные плохого качества | Схемы по доменам, `X \| None`, типизированные вложенные модели |
| 17 | M | `agent_review.py:51-59,62-77` | Request/response без `response_model`, `decision: str` вместо `Literal["approve","reject"]`, ответ — сырой `dict`/`jsonable_encoder`; `except (RuntimeError, Exception)` (`:69`) | OpenAPI не описывает контракт, любая ошибка превращается в `db_error` | Pydantic-схемы, `Literal`, узкие исключения |
| 18 | M | `agent_service.py:61,85` | Новый `httpx.AsyncClient` на каждый вызов; OAuth-токен GigaChat запрашивается на каждый запрос оценки | Лишние TLS-хендшейки и запросы, токен живёт ~30 мин | Один клиент в lifespan, кэш токена с `expires_at` и блокировкой |
| 19 | M | `events.py:14-15`, `events_service.py:36-43` | `date_from`/`date_to` — произвольные `str`, обрезаются `[:10]` | Мусор не даёт 422, сравнение строк работает случайно | Тип `date` в Query |
| 20 | M | `db.py:7-33,36-44` | Бизнес-функция `match_city` и регистрация SQL-функций в слое доступа; `PRAGMA journal_mode=WAL` на каждый connect | Логика поиска привязана к SQLite UDF; не переносится на PG | В PostgreSQL: `unaccent`/`pg_trgm`, нормализация при записи (`name_key`) |
| 21 | M | `requirements.txt`, `parser_running/` | Нет `psycopg`, `requests`, `bs4` в requirements (корневой), у `parser_running` нет собственного файла, версии `>=` без lock; ruff/mypy/pytest не установлены | Окружение не воспроизводимо, «у меня работает» | `pyproject.toml` + `uv.lock`, группа `dev` |
| 22 | M | repo | Нет Dockerfile, `.dockerignore`, сервисов `app`/`worker` в compose, CI | Нельзя запустить стек одной командой, нет единообразной среды | См. раздел 10 гайда: multi-stage uv, non-root, compose app+db+worker |
| 23 | M | `init_athletes.py:76-183`, `rating_service.py:69-82`, `agent_queue.py:405` | DDL в коде (`CREATE TABLE IF NOT EXISTS` при старте) | Нет истории схемы, невозможно откатить, расхождение окружений | Alembic, autogenerate, миграции в CI |
| 24 | M | `test_mvp.py`, `test_mcp_agent.py` (корень) | Тесты ходят в реальную `running.db`, зависят от наполнения | Нестабильные, нельзя запускать в CI | Тестовая БД, `dependency_overrides`, фабрики |
| 25 | L | `main.py:64`, `config.py` | `reload=True` захардкожен в `__main__`, `APP_HOST=0.0.0.0` по умолчанию | Dev-режим в запуске по умолчанию | Запуск через uvicorn CLI/compose, флаги из окружения |
| 26 | L | `env.example` | `GIGACHAT_CREDENTIALS==` (двойной `=`), одновременно `DATABASE_URL` и `SQLITE_DB_PATH` | Опечатка ломает ключ, вводит в заблуждение о БД | Привести к одной БД, проверить пример |
| 27 | L | `parser_running/run.py`, `rr_platform.py`, `http_cache.py` | `requests` (sync) + `print` в парсерах | Для CLI допустимо, но не годится для вызова из API-процесса | Сохранить sync в воркере/CLI; из API только ставить задачу в очередь |
| 28 | L | `frontend.py:44-57` | `def spa` читает файлы синхронно (FileResponse), `HEAD`/`GET` — ок | Не проблема, но лучше раздавать статику через nginx/CDN в проде | В проде фронт отдельно, API без SPA-fallback |

## 4. Запуск агента и парсера из API (кратко)

- Агент оценки спортсмена (`POST /athletes/{id}/assessment`): запрос ждёт GigaChat в рамках HTTP (до 15 + 30 с), внутри `async def` с sync SQLite. Поток не блокируется на subprocess, но блокируется event loop на SQLite-вызовах и держит соединение на время сети.
- Применение правок агента (`POST /api/agent-review/{id}/apply`): sync `def`, внутри `subprocess.run` для `git worktree/push/gh` и повторного запуска парсера с таймаутом 300 с. Блокирует поток из threadpool (около 40 по умолчанию), без очереди и статуса.
- Парсеры (`run.py`) из API не запускаются, только CLI; `mcp_agent` пишет «предложения» в PG напрямую.
- Детали и целевую схему (очередь, воркер, статусы задач) описывает отдельный документ про агента.

## 5. Что нужно для контейнеризации

1. `pyproject.toml` + `uv.lock` вместо `requirements.txt` (включить `psycopg`/`asyncpg`, `requests`, `bs4`).
2. Один образ app (uvicorn) и один образ worker (парсеры/агент) из одного multi-stage Dockerfile; `frontend` собирается отдельным stage (node) или отдельным контейнером.
3. Конфиг только из env (`pydantic-settings`), `.env` не копируется в образ.
4. Миграции Alembic запускаются отдельной командой/entrypoint, не в lifespan.
5. compose: `db` (есть) + `app` + `worker`, healthchecks, `depends_on: condition: service_healthy`.
6. Убрать запись в рабочий каталог из кода (`data/`, git worktree) или вынести в именованный volume.

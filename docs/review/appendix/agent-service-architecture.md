# Целевая архитектура: фоновый сбор с нескольких площадок и «последний готовый рейтинг»

Задача студентов: площадки обновляются в фоне, сайт показывает последнюю **готовую** версию рейтинга, пока идут сбор и пересчёт.
Исходное состояние и номера строк — [agent-audit.md](agent-audit.md). Принцип документа: минимум движущихся частей, всё,
что можно сделать одной таблицей в уже имеющемся PostgreSQL, делается ей.

## 0. Решения одним списком

| Вопрос | Решение | Почему |
|---|---|---|
| Единая БД | PostgreSQL для всего, SQLite сайта выводим | Иначе нечем атомарно публиковать версии; сейчас рейтинг сайта не связан со сбором (аудит, п. 0.1) |
| Очередь | **procrastinate** (очередь в самом Postgres) | Не нужен Redis; уже названа в SPEC (`docs/agent-queue.md:117`); есть повторы, периодические задачи, блокировки |
| Расписание | `@app.periodic` в том же воркере | Отдельный контейнер-планировщик не нужен |
| Публикация рейтинга | **Версии-снимки**: `rating_version` + `rating_entry` + указатель `rating_current` | Один короткий UPDATE как «переключатель», история и откат бесплатно |
| Параллелизм | `asyncio` + `httpx.AsyncClient`, лимитер на домен; CPU — отдельный процесс | Узкое место — сетевое ожидание и вежливые паузы, не CPU |
| Защита от двух запусков | частичный уникальный индекс + `pg_try_advisory_lock` + `FOR UPDATE` на дистанции | Три дешёвых слоя, каждый закрывает свою дыру |
| API | `POST /api/runs` -> 202 + `run_id`; `GET /api/runs/{id}`; `/api/rating` читает только `ready` | API никогда не ходит в сеть площадок и не считает рейтинг |

## 1. Вынос в отдельный процесс: варианты

| | (a1) procrastinate (Postgres) | (a2) arq / taskiq (Redis) | (b) APScheduler / cron-контейнер | (c) Celery |
|---|---|---|---|---|
| Новые сервисы | 0 (уже есть Postgres) | +Redis | 0 | +Redis или RabbitMQ |
| Постановка из API | `defer_async` или `INSERT` в той же БД | `enqueue_job` в Redis | **нет очереди**: только по расписанию, «запусти сейчас» надо городить | да |
| Статус/прогресс | таблицы `procrastinate_*` + своя `scrape_run` | Redis + своя таблица | своя таблица | Redis + `AsyncResult`, обычно тоже своя таблица |
| Повторы, backoff | `RetryStrategy` | arq: `Retry`; taskiq: middleware | вручную | `autoretry_for`, `retry_backoff` |
| Периодические | `@app.periodic` | cron в arq; `taskiq-scheduler` | основное назначение | `celery beat` (отдельный процесс) |
| Одна задача на 10+ минут | подходит (долгая корутина) | arq: `job_timeout` надо поднимать; подходит | подходит, но без изоляции от API | prefork, надо `acks_late` и `visibility_timeout` |
| Async-нативность | да | arq да; taskiq да | да (AsyncIOScheduler) | нет (prefork, sync) |
| Сложность для студентов | низкая-средняя | низкая | самая низкая, но не решает «по кнопке» | высокая |
| Риск | меньше туториалов; следить за версией API | потеря задач при падении Redis без AOF | двойной запуск при 2 репликах API | вес, конфигурация |

**Рекомендация: procrastinate.** Задач мало (несколько площадок + пересчёт + агент), нагрузка — единицы задач в минуту, а не тысячи. Брокер на Redis ради этого — лишняя инфраструктура и лишнее место, где состояние расходится с БД. Постановка задачи и запись `scrape_run` живут в одной базе и могут быть одной транзакцией. Если procrastinate окажется тяжёлой, откат — собственный цикл `SELECT ... FOR UPDATE SKIP LOCKED` по `scrape_run` (около 40 строк, ничего не ставить); схема таблиц ниже уже годится для него.

Что **не** делаем: Celery (избыточен), cron-контейнер как единственный механизм (нет «обновить сейчас» и статуса), Kafka/RabbitMQ.

### Контракт API

```
POST /api/runs        {"kind": "scrape", "source": "runc", "events": 30}   -> 202 {"run_id": 17, "status": "queued"}
                      409 {"detail": "уже идёт", "run_id": 15}              (активный запуск этой площадки)
GET  /api/runs/{id}   -> {"id": 17, "status": "running", "progress": {...}, "stats": {...}, "error": null, "started_at": ...}
GET  /api/runs?limit=20
GET  /api/rating      -> {..., "version_id": 42, "published_at": "...", "refresh": {"running": true, "run_id": 17}}
```

`kind`: `scrape` (одна площадка), `rebuild` (только пересчёт), `full` (все включённые площадки + пересчёт). Админ-эндпоинты закрываем простым токеном из окружения (сегодня у сайта нет входа, `docs/agent-queue.md:106-110`).

Фронтенду достаточно: плашка «данные на {published_at}», индикатор «идёт обновление» из `refresh`, опрос `GET /api/runs/{id}` раз в 3-5 с.

```python
@router.post("/runs", status_code=202)
async def create_run(body: RunIn, pool: AsyncConnectionPool = Depends(get_pool)) -> RunQueued:
    async with pool.connection() as con:
        try:
            row = await (await con.execute(
                "INSERT INTO scrape_run(kind, source_id, params, trigger) "
                "VALUES (%s, (SELECT id FROM source WHERE name = %s), %s, 'manual') RETURNING id",
                (body.kind, body.source, Jsonb(body.params())))).fetchone()
        except UniqueViolation:
            active = await active_run_id(con, body.source)
            raise HTTPException(409, {"detail": "уже идёт", "run_id": active})
    await tasks.scrape_source.defer_async(run_id=row[0])
    return RunQueued(run_id=row[0], status="queued")
```

Если процесс API упал между `INSERT` и `defer_async`, запуск останется в `queued` без задачи; периодическая задача-«санитар» (п. 5) переставит такие записи старше двух минут.

## 2. Параллелизм внутри воркера

### 2.1. Схема

```
worker (1 процесс, asyncio loop)
 ├─ задача scrape_source(run_id)   x до WORKER_CONCURRENCY одновременно  -> площадки параллельно
 │    └─ Semaphore(4) на соревнования
 │         └─ дистанции стартa: последовательно (или Semaphore(2))
 │              fetch (httpx, без БД)  ->  parse (чистая функция)  ->  короткая транзакция записи
 ├─ задача rebuild_rating(run_id)  (queue=rebuild, concurrency 1)
 └─ задача process_issue(id)       (queue=agent, concurrency 1; sync-задача в потоке)
```

Площадки параллельны потому, что каждая — отдельная задача procrastinate (`-c 4`). Соревнования одной площадки — `asyncio.Semaphore(4)`. Внутри старта дистанции идут по очереди: страницы одного протокола уже запрашиваются последовательно (пагинация), этого хватает.

### 2.2. Вежливый rate-limit на домен

Один лимитер на хост на весь процесс (не на площадку: РФ-площадки RR работают на нескольких доменах, а `russiarunning`/`timerman` — разные хосты, но один коннектор):

```python
class DomainLimiter:
    def __init__(self, concurrency: int, min_interval_s: float) -> None:
        self._sem = asyncio.Semaphore(concurrency)
        self._interval = min_interval_s
        self._lock = asyncio.Lock()
        self._next = 0.0

    @asynccontextmanager
    async def slot(self):
        async with self._sem:
            async with self._lock:
                now = time.monotonic()
                wait = max(0.0, self._next - now)
                self._next = max(now, self._next) + self._interval
            if wait:
                await asyncio.sleep(wait)
            yield

LIMITS = {"results.runc.run": (1, 1.0), "grom.place": (1, 1.5), "results.russiarunning.com": (3, 0.4), "timerman.org": (2, 0.5)}
```

`почему: runc и grom медленные (E23, E29), ограничиваем жёстче; значения вынести в конфиг и подбирать по `scrape_run.stats` (доля 429/таймаутов)`. Сегодняшний `DELAY_S = 0.5` (`http_cache.py:12`) становится `min_interval_s` по хосту.

### 2.3. Fetcher: кеш, повторы, контекст

```python
async def fetch_text(self, url: str, *, max_age: timedelta | None) -> Fetched:
    path = self.cache_path(url)
    if path.exists() and (max_age is None or age(path) < max_age):
        return Fetched(path.read_text("utf-8"), url=url, path=path, from_cache=True)
    async for attempt in retrying(max_attempts=4, base=2.0, cap=60.0):
        async with attempt, self.limiter(url).slot():
            r = await self.client.get(url, timeout=60)
            if r.status_code in RETRYABLE:
                raise Retryable(r)
            r.raise_for_status()
    path.write_text(r.text, "utf-8")
    return Fetched(r.text, url=url, path=path, from_cache=False)
```

Правила повторов (заменяют `http_cache.py:32-41`, `rr_platform.py:41-49`):
- повторяем: `httpx.TimeoutException`, `httpx.TransportError`, статусы 429, 502, 503, 504;
- пауза `min(cap, base * 2**n) * random(0.5..1.5)`, при `Retry-After` — не меньше него;
- не повторяем: 4xx, кроме 408/429; `404` — штатная ветка «нет протокола» (E13), как сейчас в `run.py:104-107`;
- `max_age`: `None` (вечно) для протоколов стартов старше 30 дней, `6h` для свежих, `1h` для списков; `isFinalProtocol = false` — всегда короткий TTL.

`Fetched` возвращается **значением**; глобальный `FETCH_LOG` (`http_cache.py:16`) убираем: коннектор собирает `fetches` в локальный список и отдаёт вместе с результатом. Без этого параллельные корутины перемешают журналы.

### 2.4. Коннекторы: что менять

Минимальный путь, не переписывая разбор: сохранить `races()`/`results()` как есть, но сделать их `async def` и заменить `http_cache.get(...)` на `await self.http.fetch_text(...)`. Функции, которые только разбирают текст (`_row`, `parse_country_group`, `normalize.*`), остаются синхронными и чистыми — их легко тестировать на фикстурах (это уже делает `parser_running/evals/`). Затронуто три файла (~375 строк). Вспомогательная явная схема контракта:

```python
class Connector(Protocol):
    name: str
    async def competitions(self, http: Fetcher, limit: int, skip: int = 0) -> list[Competition]: ...
    async def races(self, http: Fetcher, comp: Competition) -> list[Race]: ...
    async def results(self, http: Fetcher, comp: Competition, race: Race) -> ParsedProtocol: ...
```

`ParsedProtocol(rows, total, fetches)` вместо мутации `race`/`comp` на месте (аудит, п. 3). Это же станет входом для гибкого LLM-парсера: один и тот же `Protocol`, один и тот же набор проверок `store.checks`.

### 2.5. Что оставить синхронным

| Работа | Где выполнять |
|---|---|
| Разбор HTML/JSON страницы (`bs4`+`lxml`, десятки мс) | прямо в корутине; для страниц > ~1 МБ — `asyncio.to_thread` |
| OCR (`tesseract`, подпроцесс на картинку), `parse_pdf` | `ProcessPoolExecutor(max_workers=os.cpu_count())` через `loop.run_in_executor`; отдельная очередь `ocr` |
| `dedup`, `scoring.recalculate`, сопоставление спортсменов | отдельная задача `rebuild_rating` в процессе (не в event loop сбора), потоковое чтение курсором уже есть (`scoring.py:169-176`) |
| GigaChat-агент (`requests`, подпроцессы песочницы) | sync-задача очереди `agent` с `concurrency 1`; код агента не переписываем |

`почему: bs4/lxml держат GIL, но на 100-1000 строк это миллисекунды; настоящий CPU-расход — OCR и пересчёт, их выносим в процессы, а не усложняем сбор.`

Исключения одной дистанции не должны отменять соседние: использовать `asyncio.gather(..., return_exceptions=True)` или `try/except` внутри задачи, а не `TaskGroup` с отменой при первой ошибке.

## 3. «Показывать последнюю готовую версию, пока идёт сбор»

### 3.1. Три паттерна

| | Версии-снимки (рекомендуем) | Staging + атомарный swap | MATERIALIZED VIEW + `REFRESH ... CONCURRENTLY` |
|---|---|---|---|
| Идея | Каждый пересчёт пишет строки с `version_id`; API читает версию из указателя | Строим `rating_new`, в транзакции `RENAME` | Рейтинг — вью над `score`/`athlete`; обновляем командой |
| Читатели во время пересчёта | не блокируются | кратко блокируются на `ACCESS EXCLUSIVE` при `RENAME` | не блокируются (CONCURRENTLY) |
| История, откат | есть: переключить указатель назад | нет | нет |
| Статус сборки, статистика | колонки `rating_version` | отдельно | нет |
| Согласованность страниц/пагинации | да: `version_id` фиксируется на запрос | да | да, но между двумя запросами вью может обновиться |
| Расчёт в Python (сопоставление спортсменов, `scoring.calculate`) | да, без ограничений | да | нет: вью — только SQL; нужен уникальный индекс |
| Сложность | средняя: 3 таблицы | средняя + DDL в рантайме, миграции ломаются | самая низкая, если весь рейтинг выразим в SQL |
| Хранение | N версий (чистим) | 2 копии | 1 копия + временная при refresh |

Рейтинг здесь включает Python-шаги (сопоставление спортсменов, нормализация, `scoring.calculate` с классификатором), поэтому matview не подходит как основной механизм. Swap даёт короткий lock и теряет историю. **Снимки** — единственный вариант, где API ничего не знает о сборке, а сбой пересчёта ничего не портит: просто нет новой `ready`-версии.

### 3.2. DDL

Расширение существующей схемы `parser_running/db.py` (новые таблицы; существующие не меняем).

```sql
CREATE TABLE scrape_run (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind             text NOT NULL CHECK (kind IN ('scrape', 'rebuild', 'full')),
    source_id        integer REFERENCES source(id),
    params           jsonb NOT NULL DEFAULT '{}',
    trigger          text NOT NULL CHECK (trigger IN ('manual', 'schedule', 'chain')),
    status           text NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    queued_at        timestamptz NOT NULL DEFAULT now(),
    started_at       timestamptz,
    finished_at      timestamptz,
    heartbeat_at     timestamptz,
    progress         jsonb NOT NULL DEFAULT '{}',
    stats            jsonb NOT NULL DEFAULT '{}',
    error            text,
    parent_run_id    bigint REFERENCES scrape_run(id),
    rating_version_id bigint
);

CREATE UNIQUE INDEX scrape_run_one_active_per_source
    ON scrape_run (source_id)
    WHERE kind = 'scrape' AND status IN ('queued', 'running');

CREATE UNIQUE INDEX scrape_run_one_active_rebuild
    ON scrape_run (kind)
    WHERE kind = 'rebuild' AND status IN ('queued', 'running');

CREATE INDEX scrape_run_recent ON scrape_run (queued_at DESC);

ALTER TABLE source ADD COLUMN last_success_at timestamptz;
ALTER TABLE source ADD COLUMN schedule_interval interval;

CREATE TABLE rating_version (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status           text NOT NULL DEFAULT 'building' CHECK (status IN ('building', 'ready', 'failed')),
    formula_version  text NOT NULL,
    period_start     date NOT NULL,
    period_end       date NOT NULL,
    run_id           bigint REFERENCES scrape_run(id),
    results_total    integer,
    athletes_rated   integer,
    stats            jsonb NOT NULL DEFAULT '{}',
    error            text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    published_at     timestamptz
);

CREATE TABLE rating_entry (
    version_id    bigint NOT NULL REFERENCES rating_version(id) ON DELETE CASCADE,
    athlete_id    bigint NOT NULL,
    display_name  text NOT NULL,
    gender        text NOT NULL CHECK (gender IN ('M', 'F')),
    birth_year    integer,
    points        double precision NOT NULL,
    best_points   double precision NOT NULL,
    starts_count  integer NOT NULL,
    rank          integer NOT NULL,
    rank_gender   integer NOT NULL,
    PRIMARY KEY (version_id, athlete_id)
);
CREATE INDEX rating_entry_rank ON rating_entry (version_id, rank);
CREATE INDEX rating_entry_gender_rank ON rating_entry (version_id, gender, rank_gender);

CREATE TABLE rating_current (
    singleton   boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    version_id  bigint NOT NULL REFERENCES rating_version(id)
);
```

`rating_entry` хранит `display_name`, `gender`, `birth_year` **копией**: версия не зависит от последующих правок таблицы `athlete`, а API читает рейтинг без `JOIN` с живыми таблицами. Места по полу (`rank_gender`) считаются при сборке, а не запросом `COUNT` на лету (как в `rating_service.py:405-423`). Сырые факты (`result`, `race`, `raw`) в версии не копируются — они меняются инкрементально и не участвуют в чтении рейтинга.

### 3.3. Чтение

```sql
WITH cur AS (SELECT version_id FROM rating_current)
SELECT e.rank, e.athlete_id, e.display_name, e.birth_year, e.gender, e.points, e.best_points, e.starts_count,
       count(*) OVER () AS total, v.published_at, v.period_start, v.period_end, v.id AS version_id
FROM cur
JOIN rating_entry e ON e.version_id = cur.version_id
JOIN rating_version v ON v.id = cur.version_id
WHERE (%(gender)s::text IS NULL OR e.gender = %(gender)s)
ORDER BY e.rank
LIMIT %(limit)s;
```

Это один запрос: `rows`, `total` и метаданные версии из одного снимка — «разъезда» `rows`/`total`/`me_row` (аудит, п. 1.5) не бывает. Для последующих запросов страницы клиент передаёт `version_id`, API использует его вместо указателя (версии неизменяемы). Если версии нет (первый запуск) — пустой ответ с `version_id = null`.

### 3.4. Последовательность шагов

```
1. SCRAPE   (параллельно по площадкам)   пишет raw / competition / race / result короткими транзакциями
            └─ рейтинг не затрагивается; сайт показывает версию N
2. REBUILD  (после успешного scrape или по расписанию; единственный за раз)
   2.1  создать rating_version(status='building')                       
   2.2  dedup                 (пересчёт duplicate_of, пачки по датам, commit на пачку)
   2.3  сопоставление спортсменов (только новые result без athlete_id) (commit на пачку)
   2.4  scoring.recalculate() (уже одна транзакция, MVCC, scoring.py:164)
   2.5  в одной REPEATABLE READ транзакции: INSERT INTO rating_entry SELECT ... агрегат по последним 365 дням с rank/rank_gender
   2.6  проверки версии: athletes_rated > 0, не меньше 80 % предыдущей версии, нет NaN
3. PUBLISH  (одна короткая транзакция)
4. CLEANUP  (следующий шаг той же задачи)
```

Публикация:

```sql
BEGIN;
UPDATE rating_version SET status = 'ready', published_at = now() WHERE id = %(id)s AND status = 'building';
INSERT INTO rating_current (version_id) VALUES (%(id)s)
ON CONFLICT (singleton) DO UPDATE SET version_id = excluded.version_id;
COMMIT;
```

Очистка:

```sql
DELETE FROM rating_version
WHERE id NOT IN (SELECT version_id FROM rating_current)
  AND id NOT IN (SELECT id FROM rating_version WHERE status = 'ready' ORDER BY published_at DESC LIMIT 3)
  AND created_at < now() - interval '1 day';
```

(`ON DELETE CASCADE` удаляет строки `rating_entry`; `failed` и зависшие `building` уходят тем же условием.)

Проверка 2.6 — предохранитель от публикации мусора после «площадка поменяла формат» (то, что сейчас превращается в `zero_rows`, `run.py:134-139`). Не прошла — версия `failed`, указатель остаётся, сайт жив на старом снимке, в `scrape_run.error` причина.

Нюанс блокировок: `dedup`/сопоставление обновляют `result` пачками и коммитят — не обнуляют всю таблицу одним `UPDATE`, как `dedup.py:81-82`. Запись сбора, упёршаяся в блокировку строк пересчёта, ждёт не дольше `lock_timeout = 30s` и повторяется целиком (идемпотентно). `rebuild` не стартует, пока для каких-либо площадок есть `running` запуски (проверка в начале + перепостановка через 60 с), так что взаимные блокировки возможны только при ручном `scrape` во время пересчёта.

### 3.5. Данные, которые остаются «живыми»

Страницы `GET /api/athletes/{id}/results`, `/events`, `/races` читают живые `result`/`race`: они могут опережать рейтинг на один цикл обновления. Для рейтинга это не страшно; на страницах спортсмена показываем место из `rating_entry` текущей версии и подпись «рейтинг на {published_at}».

## 4. Схема таблиц целиком

| Таблица | Роль | Ключ |
|---|---|---|
| `source` | площадки, `enabled`, `schedule_interval`, `last_success_at` | `name` |
| `scrape_run` | запуски: статус, прогресс, статистика, ошибка | `id`; частичные уникальные индексы активных запусков |
| `competition`, `race` | как сейчас | `(source_id, external_id)`, `(competition_id, external_id)` |
| `raw` | как сейчас; тело — файлом в томе | `(source_id, request_key, content_hash)` |
| `result` | сырые результаты, upsert по дистанции под `FOR UPDATE` | `id`; добавить `UNIQUE (race_id, row_no)` — см. ниже |
| `score` | как сейчас, по `formula_version` | `(result_id, formula_version)` |
| `athlete`, `result_athlete` | порт `init_athletes.py` в PG | `athlete.id`, `result_id` |
| `rating_version`, `rating_entry`, `rating_current` | снимки | см. DDL |
| `issue`, `agent_run`, `agent_review` | как сейчас | `fingerprint` |

Сырые результаты — upsert по естественному ключу. Протокол уже перезаписывается целиком в пределах дистанции (`store.py:74`), и это правильно (строки исчезают/меняются при пересчёте площадки). Чтобы операция была безопасна при гонке, достаточно взять блокировку дистанции перед `DELETE`:

```python
await con.execute("SELECT id FROM race WHERE id = %s FOR UPDATE", (race_id,))
await con.execute("DELETE FROM result WHERE race_id = %s", (race_id,))
```

Второй процесс на ту же дистанцию ждёт на `FOR UPDATE`, а его `DELETE` стартует уже после коммита первого и видит его строки — дублей нет (в отличие от текущего кода, аудит п. 4). Уникальный ключ `(race_id, row_no)` (порядковый номер строки протокола, который добавляет `save_results`) страхует от остатков.

## 5. Идемпотентность, повторы, блокировки, сессии БД, наблюдаемость

### 5.1. Идемпотентность и возобновление

- Любая задача может быть выполнена повторно: upsert по естественным ключам, `result` — перезапись дистанции под блокировкой, `raw` — по хешу, `issue` — по fingerprint.
- Повтор запуска стоит дёшево за счёт файлового кеша (п. 2.3): уже скачанные протоколы свежее TTL не запрашиваются повторно.
- Задача procrastinate: `RetryStrategy(max_attempts=3, exponential_wait=60)` на уровне всего `scrape_source`; внутри — повторы отдельных HTTP-запросов (п. 2.3). Различаем: падение запроса -> повтор запроса; падение дистанции -> `issue` и продолжаем (как сейчас `run.py:100-125`); падение всей задачи (БД, OOM) -> повтор задачи.
- Статус в `scrape_run` меняется только вперёд: `queued -> running -> succeeded|failed|cancelled`.

### 5.2. Блокировки от двойного запуска

Три слоя:
1. **Постановка**: частичные уникальные индексы `scrape_run_one_active_*` — второй `POST /runs` на ту же площадку получает `409` и `run_id` активного.
2. **Выполнение**: `pg_try_advisory_lock` на выделенном соединении `autocommit`, которое живёт всё время задачи:

```python
async with pool.connection() as lock_con:
    await lock_con.set_autocommit(True)
    got = await (await lock_con.execute("SELECT pg_try_advisory_lock(%s)", (lock_key("scrape", source_id),))).fetchone()
    if not got[0]:
        raise AlreadyRunning(source_id)
    ...
```

`почему: advisory lock живёт на сессии, а не в транзакции — при падении воркера соединение закрывается и блокировка снимается сама; это страхует от «осиротевшего» running`. `lock_key` — стабильный `hashtext`/crc32 от строки, не `hash()` Python (он случаен между процессами).
3. **Запись**: `FOR UPDATE` на дистанции (п. 4).

Санитар — периодическая задача раз в минуту: `running` с `heartbeat_at < now() - interval '5 minutes'` -> `failed` («воркер пропал»); `queued` старше 2 минут без активной задачи procrastinate -> повторный `defer`.

### 5.3. Короткие сессии БД

Правила для воркера:
- Транзакция живёт только вокруг записи одной дистанции: `fetch` и `parse` идут **до** `BEGIN`.
- Не держим транзакцию и во время вызова LLM (агент: `claim` уже коммитится сразу, `agent_queue.py:277-283`; `finish` — отдельный короткий commit).
- Соединения — из `psycopg_pool.AsyncConnectionPool` (`min_size=2, max_size=8`), на задачу не больше двух; соединение под advisory lock — отдельное, вне пула транзакций.
- `statement_timeout`/`lock_timeout` на сессию записи (`SET lock_timeout = '30s'`), `idle_in_transaction_session_timeout = '2min'` на уровне БД как страховка от забытых транзакций.
- `db.connect()` больше не гоняет DDL на каждое подключение (`db.py:185-189`): схема применяется один раз сервисом `init` при деплое.

```python
async def save_protocol(pool: AsyncConnectionPool, src: int, comp: Competition, race: Race, parsed: ParsedProtocol) -> None:
    async with pool.connection() as con:
        async with con.transaction():
            await con.execute("SET LOCAL lock_timeout = '30s'")
            event_id = await save_competition(con, src, comp)
            race_id = await save_race(con, event_id, race)
            raw_ids = await save_raw(con, src, parsed.fetches, event_id, race_id)
            await save_results(con, race_id, parsed.rows, raw_ids)
```

### 5.4. Прогресс, логи, метрики

- Прогресс: каждые N дистанций (или раз в 5 с) короткий `UPDATE scrape_run SET progress = %s, heartbeat_at = now()` в autocommit. Формат: `{"competitions_total": 30, "competitions_done": 12, "races_done": 61, "current": "runc/ETNORAN"}`.
- Итоговая `stats` — то же, что сегодня собирает `run.py` в `Counter` (`stats["races_ok"]`, `races_empty`, ...), плюс `http_requests`, `http_retries`, `http_429`, `cache_hits`, `duration_s`, `bytes`.
- Логи: стандартный `logging` в JSON, контекст через `contextvars` (`run_id`, `source`, `competition`, `race`); `print` заменяется логами. Отчёт `data/report_<площадка>.json` (`run.py:167-169`) перестаёт быть единственным следом запуска — он остаётся как артефакт, но канонический итог лежит в `scrape_run.stats`.
- Метрики: пока не вводим Prometheus; достаточно `GET /api/runs` и запросов к `scrape_run`. Добавить `/metrics` стоит, когда появится мониторинг на стороне заказчика.

### 5.5. Расписание

Периодическая задача раз в час проверяет `source` и ставит `scrape` для площадок, где `now() - last_success_at >= schedule_interval`; по завершении всех поставленных в этом цикле запусков ставится один `rebuild` (триггер `chain`, `parent_run_id` — запуск, который его вызвал). Стартовые значения: RR (`russiarunning`, `timerman`) — раз в 6 часов, `runc`, `grom` — раз в сутки ночью (они медленные и хрупкие, E23, E29), `rebuild` — после каждого цикла и принудительно раз в сутки (период рейтинга «последние 365 дней» сдвигается). Эти числа — предложение, подтвердить с заказчиком.

```python
@app.periodic(cron="*/30 * * * *")
@app.task(queue="scrape", queueing_lock="schedule-tick")
async def schedule_tick(timestamp: int) -> None:
    await enqueue_due_sources()
```

`почему: queueing_lock не даёт накопиться нескольким тик-задачам, если воркер был выключен`. Точный API `periodic`/`RetryStrategy` проверить по установленной версии procrastinate.

### 5.6. Агент в очереди

Агент-ремонтник и применение правок переходят в очередь `agent` (`concurrency 1`, чтобы уложиться в лимиты GigaChat и не гонять много песочниц):
- `process_issue(issue_id)` — sync-задача, внутри существующий `cmd_process`; идемпотентность уже есть в `claim` (`agent_queue.py:277-283`);
- `apply_approved` — тоже задача; `POST /api/agent-review/{id}/apply` ставит её и возвращает 202, статус читается из `agent_review.applied_result`;
- `retry` в `decide` (`agent_queue.py:500-522`) вместо «вернуть в new и ждать CLI» ставит `process_issue`;
- автотриаж: после `scrape` для задач `new` + `agent` ставится не более N `process_issue` за цикл (бюджет токенов в конфиге);
- кеш OAuth-токена GigaChat в `agent_service` вынести на уровень процесса (сейчас токен берётся на каждый запрос, аудит п. 1.4), эндпоинт оценки спортсмена после перехода на PG — на `psycopg` async или обычный `def`.

## 6. docker-compose

Один образ, разные команды (Dockerfile — по BACKEND_GUIDE: multi-stage, непривилегированный пользователь, `uv`/`pip` из lock-файла; в этом документе не дублируется).

```yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: sports_agent
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?задайте POSTGRES_PASSWORD в .env}
    command: ["postgres", "-c", "idle_in_transaction_session_timeout=120000"]
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agent -d sports_agent"]
      interval: 5s
      retries: 10

  init:
    build: .
    command: ["python", "-m", "app.cli", "init"]
    environment: &app_env
      DATABASE_URL: postgresql://agent:${POSTGRES_PASSWORD}@db:5432/sports_agent
      GIGACHAT_CREDENTIALS: ${GIGACHAT_CREDENTIALS:-}
      ADMIN_TOKEN: ${ADMIN_TOKEN:?задайте ADMIN_TOKEN в .env}
    depends_on:
      db: {condition: service_healthy}
    restart: "no"

  api:
    build: .
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    environment: *app_env
    ports:
      - "8000:8000"
    depends_on:
      init: {condition: service_completed_successfully}

  worker:
    build: .
    command: ["procrastinate", "--app=app.worker.app", "worker", "--queues", "scrape,rebuild,ocr", "--concurrency", "4"]
    environment: *app_env
    volumes:
      - rawdata:/app/parser_running/data
    depends_on:
      init: {condition: service_completed_successfully}
    restart: unless-stopped

  agent-worker:
    build: .
    command: ["procrastinate", "--app=app.worker.app", "worker", "--queues", "agent", "--concurrency", "1"]
    environment: *app_env
    volumes:
      - rawdata:/app/parser_running/data
    depends_on:
      init: {condition: service_completed_successfully}
    restart: unless-stopped

volumes:
  pgdata:
  rawdata:
```

- **Redis не нужен.** **Отдельного scheduler-контейнера нет:** периодические задачи исполняет `worker`; несколько реплик воркера безопасны — procrastinate ставит периодическую задачу один раз на отметку времени.
- `init` — разовое применение схемы (`CREATE TABLE IF NOT EXISTS` из `db.py`, DDL scoring/classification, схема procrastinate, новые таблицы); заменяет DDL при каждом `connect()`.
- `agent-worker` отделён, потому что ему нужны `git`/`gh` и том с репозиторием для `apply`; если применение остаётся CLI-only (`docs/agent-queue.md`, вопрос 3), контейнер можно не поднимать.
- Том `rawdata` — кеш ответов площадок (`data/raw`), общий для воркеров; в API не монтируется.

## 7. План миграции (каждая итерация оставляет рабочее состояние)

Сложность: S — до 1 дня, M — 2-3 дня, L — 4-6 дней для студента.

| # | Итерация | Состояние в конце | Сложность |
|---|---|---|---|
| 0 | **Одна база.** Портировать `init_athletes.py` и `rating_service.py` на PG (`athlete`, `result_athlete`), переключить сервисы API (`athlete_service`, `events_service`, `analytics_service`, `agent_service`) на `psycopg`; `ru_lower`/`match_city` (`app/db.py:41-42`) -> SQL (`lower`+`translate`, при необходимости `pg_trgm`). Данные — повторным прогоном из `data/raw` (`migrate_sqlite.py` как образец) | Сайт читает PG; поведение то же | L |
| 1 | **Снимки рейтинга.** DDL `rating_version/entry/current`, команда `rebuild` (CLI), `/api/rating` читает указатель, `me_row` из `rank_gender`. Убрать пересчёт из `lifespan` (`app/main.py:30-37`) | Сайт показывает `ready`-версию; пересчёт руками, публикация атомарна. Первый заметный результат для заказчика | M |
| 2 | **Воркер и запуски.** procrastinate + `scrape_run`, `POST/GET /api/runs`, контейнеры `worker`/`init`. Внутри задачи пока старый синхронный `run.run()` в потоке. Заодно: коммит на дистанцию (не на старт), `FOR UPDATE` на `race`, индексы активных запусков, advisory lock, `rollback` при ошибке | Парсер запускается кнопкой/`curl`, статус виден, двойной запуск невозможен, API не блокируется | M |
| 3 | **Цепочка и расписание.** `scrape` -> `rebuild` -> публикация, `@app.periodic`, санитар, heartbeat, плашка «данные на ...» и индикатор обновления на фронте | Сайт сам обновляется по расписанию | M |
| 4 | **Async-сеть.** `Fetcher` на `httpx`: лимитер по домену, повторы с backoff и `Retry-After`, TTL кеша, возврат `fetches` значением; коннекторы -> `async`; тесты на фикстурах (оффлайн-режим `run.py:33-41` заменить заменой транспорта в тестах) | Сбор на asyncio, но последовательный; тот же результат, что в итерации 3 | L |
| 5 | **Параллелизм и наблюдаемость.** Площадки/старты параллельно, прогресс и `stats`, JSON-логи, замер времени «до/после» | Сбор в разы быстрее; видно, что происходит | M |
| 6 | **Агент в очереди.** `process_issue`/`apply` как задачи, `retry` ставит задачу, бюджет токенов, кеш токена GigaChat; `ocr` через `ProcessPool`; решение по заглушке `app/mcp_agent/` (удалить или довести — `sync_postgres_issue` пишет вымышленные предложения, аудит п. 2.3) | Ремонт и применение не блокируют API | M |
| 7 | **Биатлон в общий конвейер** (по необходимости): `parser_biathlon` -> `store.py`/PG вместо CSV | Один конвейер на все виды спорта | M-L |

Критический путь к цели студентов («сайт показывает последнюю готовую версию, пока идёт сбор»): итерации 0-2. Итерация 3 делает это автоматическим. 4-5 — ускорение, их можно делать позже и независимо. Итого порядка 4 недель одного студента, меньше при двух.

Безопасный порядок внутри итерации 0, если её хочется разбить: сначала `athlete` + рейтинг в PG рядом со старой SQLite (сайт читает ещё SQLite), затем переключение чтения по одному роутеру (`rating` -> `athletes` -> `events/races`).

## 8. Открытые вопросы

1. Остаётся ли SQLite у сайта — если да (итерация 0 вырезается), единственный вариант публикации — отдельный файл `rating-<версия>.db` и атомарная замена `os.replace` указателя; это работает, но два хранилища и ручной экспорт останутся навсегда. Рекомендуем итерацию 0.
2. Расписание и частота опроса площадок (п. 5.5) — подтвердить с заказчиком; для RR можно ли чаще без риска блокировки.
3. Кто может нажимать «обновить»: общий токен из окружения на старте; нормальная авторизация — отдельная задача (см. `docs/agent-queue.md`, вопрос 2).
4. Допустим ли «хвост» живых данных на страницах спортсмена (п. 3.5), или нужен снимок и для них.
5. Судьба `app/mcp_agent/` и `parse_url.py` — зависит от результатов исследования гибкого LLM-парсера (внешняя работа): единый `Connector`-протокол из п. 2.4 — точка стыковки.

# Руководство по запуску проекта на новом компьютере

Пошаговая инструкция в хронологическом порядке: установка PostgreSQL → установка библиотек Python → перенос БД из дампа → настройка `.env` → сборка фронтенда → запуск.

---

## Шаг 1. Скачать и установить PostgreSQL

1. Скачайте и установите **PostgreSQL** (версии 16, 17 или 18) с официального сайта:  
   👉 [https://www.postgresql.org/download/windows/](https://www.postgresql.org/download/windows/)
2. При установке оставьте порт `5432` и запомните пароль суперпользователя `postgres`.
3. Добавьте путь к папке `bin` (например, `C:\Program Files\PostgreSQL\17\bin`) в системную переменную `PATH`.
4. Откройте PowerShell, подключитесь к PostgreSQL и создайте пользователя и пустую базу:
   ```powershell
   psql -U postgres -h 127.0.0.1
   ```
   Внутри `psql` выполните:
   ```sql
   CREATE USER agent WITH PASSWORD 'change-me';
   CREATE DATABASE sports_agent OWNER agent;
   GRANT ALL PRIVILEGES ON DATABASE sports_agent TO agent;
   \q
   ```

---

## Шаг 2. Скачать проект и установить библиотеки Python

1. Убедитесь, что установлен **Python 3.12+**.
2. Клонируйте репозиторий (или скопируйте папку проекта) и перейдите в неё:
   ```powershell
   git clone <URL_РЕПОЗИТОРИЯ>
   cd sports-agent
   ```
3. Если PowerShell запрещает активацию `.venv`, выполните один раз:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```
4. В корне проекта (`sports-agent`) создайте виртуальное окружение и установите зависимости:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## Шаг 3. Перенести базу данных из дампа

1. Положите файл `sports_agent_dump.dump` в корень проекта (`sports-agent/`).
2. В PowerShell из корня проекта восстановите базу командой:
   ```powershell
   $env:PGPASSWORD="change-me"
   pg_restore -h 127.0.0.1 -p 5432 -U agent -d sports_agent --clean --if-exists --no-owner "sports_agent_dump.dump"
   ```
   *(Если `pg_restore` не найден в `PATH`, используйте полный путь, например `& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" ...`. Предупреждения `role "postgres"` / `does not exist` при первом импорте можно игнорировать.)*

---

## Шаг 4. Создать и настроить файл `.env`

Файл `.env` не хранится в Git, поэтому его нужно создать вручную в корне проекта (`sports-agent/.env`).

### Вариант А — создать файл через PowerShell одной командой:
```powershell
@'
# Local running database (SQLite)
RUNNING_DB_PATH=running.db

# PostgreSQL
DATABASE_URL=postgresql://agent:change-me@127.0.0.1:5432/sports_agent

# Default author for agent review decisions
DEFAULT_AUTHOR=cz

# GigaChat API
GIGACHAT_CREDENTIALS=<ВСТАВЬТЕ_КЛЮЧ_ИЗ_ЛОКАЛЬНОГО_.env>
GIGACHAT_MODEL=GigaChat-2-Pro
GIGACHAT_VERIFY_SSL=false

# Пауза на ревью в «Правках агента» перед активацией нового рецепта
AUTO_APPLY_SAFE_REPAIRS=false
'@ | Set-Content -Encoding UTF8 .env
```

### Вариант Б — создать файл `.env` вручную и вставить содержимое:
```env
RUNNING_DB_PATH=running.db
DATABASE_URL=postgresql://agent:change-me@127.0.0.1:5432/sports_agent
DEFAULT_AUTHOR=cz
GIGACHAT_CREDENTIALS=<ВСТАВЬТЕ_КЛЮЧ_ИЗ_ЛОКАЛЬНОГО_.env>
GIGACHAT_MODEL=GigaChat-2-Pro
GIGACHAT_VERIFY_SSL=false
AUTO_APPLY_SAFE_REPAIRS=false
```

> **Пояснение переменных:**
> - `DATABASE_URL` — строка подключения к PostgreSQL (пользователь `agent`, пароль `change-me`, база `sports_agent`). Если задавали свой логин/пароль/порт — поменяйте здесь.
> - `RUNNING_DB_PATH` — путь к локальной SQLite для старых скриптов миграции (сайту для работы не требуется, вся работа идёт через PostgreSQL).
> - `GIGACHAT_CREDENTIALS` / `GIGACHAT_MODEL` — ключ доступа и модель GigaChat (`GigaChat-2-Pro`).
> - `GIGACHAT_VERIFY_SSL=false` — отключает ошибку проверки самоподписанного SSL-сертификата на Windows.
> - `AUTO_APPLY_SAFE_REPAIRS=false` — включает обязательную паузу на подтверждение рецептов в «Правках агента».

---

## Шаг 5. Собрать фронтенд

*(Нужно, если папка `frontend/dist` отсутствует — например, при клонировании через Git. Требуется **Node.js 20+**.)*

```powershell
cd frontend
npm.cmd install
npm.cmd run build
cd ..
```

---

## Шаг 6. Запуск сайта

### Терминал 1 — Веб-сервер:
```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --loop app.core.database:postgres_event_loop_factory
```
*(Либо просто `python -m app.main` — флаг `--loop app.core.database:postgres_event_loop_factory` обязателен на Windows для работы асинхронного `psycopg`.)*

Сайт откроется по адресу: [http://127.0.0.1:8000](http://127.0.0.1:8000)

Учётные записи в базе:
- `admin` / `admin` (администратор)
- `captain` / `captain` (капитан)
- `user` / `user` (сотрудник)

### Терминал 2 — Фоновый воркер (опционально, для фонового сбора и ИИ-ремонта):
```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="."
python -m procrastinate --app=app.worker.procrastinate_app worker
```

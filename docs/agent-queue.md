# Агент-ремонтник в бою: очередь, решения людей, применение, экран

Ветка `feature/repair-agent` (в неё влита `feature/running-fixes-issues-clubcode` с дизайном сайта).
Закрывает задачи из [agent-spec.md §9](agent-spec.md): воспроизведение задачи в песочнице, сквозной прогон,
решение человека из командной строки, применение подтверждённого предложения, экран подтверждения.
Сам агент (модель GigaChat, цикл, промпт) описан в
[parser_running/evals/agents/GIGACHAT_AGENT.md](../parser_running/evals/agents/GIGACHAT_AGENT.md).

## Как всё связано

```
run.py (парсер) ── проверки упали ──► issue (new, agent)        сохранённые ответы площадки → таблица raw
                                         │
   agent_queue.py process <id> ─────────►│ agent_working
      песочница: копия *.py парсера + ответы этой дистанции из data/raw, без сети
      агент (evals/agents/<имя>.solve) ─► предложение ─► проверяющий модуль + перезапуск коннектора
                                         │
                       ┌─────────────────┼──────────────────────────────┐
                    proposed      new / human (не справился)     blocked / infra (сеть)
                       │                 каждая попытка — строка в agent_run
   человек: CLI decide / страница /agent-review
          ├─ reject (+ комментарий) ─► rejected, или new/agent с --retry: агент видит комментарий
          └─ approve ─► approved ─► apply
                ├─ patch: ветка agent/issue-N-run-M в отдельной копии репо (git worktree), перезапуск,
                │         коммит, push, PR  ─► resolved      (правка не легла, но проверки проходят ─► already_fixed / resolved)
                ├─ known_exception: строка в known_exception, если не ловит соседние дистанции ─► known
                └─ заготовка кейса для стенда: evals/cases/drafts/issue_N.py
```

## Файлы

| Файл | Что это |
|---|---|
| `parser_running/agent_queue.py` | Вся логика: песочница, прогон агента, решения, применение. Командная строка + функции для сайта |
| `app/agent_review.py` | Роутер FastAPI `/agent-review`: HTML-страница и JSON API. Логику не дублирует, вызывает функции `agent_queue` |
| `app/templates/agent_review.html` | Шаблон страницы на классах `theme.css` и макросах `_ui.html` (ADR-0001); цвета только через токены, тёмная тема работает |
| `app/main.py` | +2 строки: импорт и `app.include_router(agent_review_router)` |
| `app/templates/base.html` | +1 пункт «Правки агента» в верхней навигации, раздел `agent` для подсветки. В нижнюю мобильную панель не добавлен: она свёрстана на 2 пункта, а экран по SPEC десктопный (админка) |

Файлы коллег, кроме этих трёх строк, не менялись. `db.py` парсера не менялся.

## База данных

**Важно:** страница работает с **PostgreSQL парсера** (`DATABASE_URL` из `.env`, `parser_running/db.py`),
а не с SQLite сайта (`running.db`). Это две разные базы — нужно решить, какая будет общей.

| Таблица | Кто пишет | Что |
|---|---|---|
| `issue` | парсер, `agent_queue` | Очередь задач. `agent_queue` меняет `status` и `assignee` |
| `raw` | парсер | Какой сохранённый ответ площадки к какому старту/дистанции относится (`raw.object_ref = issue.object_ref`) |
| `agent_run` | `agent_queue` | Каждая попытка агента: модель, токены (in/out), действие, результат, предложение (JSON в `patch`), отчёт проверок, время |
| `known_exception` | `agent_queue apply` | Новые правила-исключения, `journal_ref = issue-N` |
| **`agent_review`** (новая) | `agent_queue decide/apply` | Решение человека: `decision`, `author`, `comment`, `decided_at`, итог применения, ссылка на PR. Создаётся автоматически (`CREATE TABLE IF NOT EXISTS`) при запуске `agent_queue.py` или страницы |

Статусы задачи: `new → agent_working → proposed → approved | rejected → resolved | known`; плюс `blocked`.
Результаты попытки в `agent_run.result`: `proposed`, `escalated`, `not_reproducible`, `unsafe`, `bad_patch`,
`not_fixed`, `regression`, `repeat_rejected`, `error`. Итог применения в `agent_review.applied_result`:
`pr_created`, `branch_created`, `already_fixed`, `patch_conflict`, `rerun_failed`, `known_exception_added`, `ke_too_broad`.

## Командная строка

Из `parser_running/` (нужны `.env` с `DATABASE_URL`, запущенный `docker compose up -d db`; на Windows `$env:PYTHONUTF8 = "1"`):

```bash
python agent_queue.py list                                   # задачи new для агента
python agent_queue.py reproduce 36 [--keep]                  # воспроизвести: упадёт ли та же проверка
python agent_queue.py process 38 --agent gigachat_agent      # агент разбирает задачу (по умолчанию --agent template)
python agent_queue.py runs [38]                              # попытки из agent_run
python agent_queue.py review [38] [--status proposed] [--source runc]
python agent_queue.py decide 38 approve [--comment "…"] [--author Имя]
python agent_queue.py decide 38 reject --comment "что не так" [--retry]
python agent_queue.py apply 38 [--no-push]
```

## Страница и API

| Метод | Путь | Что |
|---|---|---|
| GET | `/agent-review?status=proposed&source=runc` | Страница: фильтры, дифф, отчёт, обоснование, кнопки |
| GET | `/agent-review/api/items?status=&source=` | То же в JSON |
| POST | `/agent-review/api/{issue_id}/decide` | `{"decision": "approve"\|"reject", "author", "comment", "retry"}` |
| POST | `/agent-review/api/{issue_id}/apply` | `{"push": false}` |

Ошибки решения (не тот статус, нет комментария при отклонении) — `400` с текстом в `detail`.

Запуск:
- в составе сайта — роутер уже подключён в `app/main.py`, страница `/agent-review`;
- отдельно, без SQLite сайта: из корня `python -m uvicorn app.agent_review:standalone --port 8001`.

## Что проверено

- Стенд evals: `gigachat_agent` на GigaChat-2-Max — 6/8, 0 нарушений, 0 регрессий.
- На реальных задачах из прогона runc (ошибка E20 возвращалась в код временно):
  воспроизведение (задача 36), шаблонный агент (37 → передан человеку), GigaChat (38 → `proposed`,
  41/42 → честно переданы человеку), повторно взять задачу в работу нельзя, задачи без сохранённых ответов
  (журнал) → `not_reproducible` с понятной причиной.
- `review` из командной строки, страница: отображение, решение `approve`.
- `apply` с созданием ветки, `known_exception` (узкое добавляется, широкое отклоняется), заготовка кейса,
  `already_fixed` — проверены на тестовой базе с настоящим git и перезапуском коннектора.
- **Не проверено вживую:** создание настоящего PR (нужна живая поломка в закоммиченном коде) и `reject --retry`
  с повторным прогоном агента.

## Открытые вопросы к бэкенду

1. **Какая база общая** — PostgreSQL парсера или SQLite сайта. Сейчас страница ходит в PostgreSQL.
2. **Кто автор решения.** Сейчас автор — поле на форме (по умолчанию `git config user.name`). Когда появится
   вход в админку, автора надо брать из сессии, а страницу закрыть для всех, кроме администратора.
3. **`apply` с сервера.** Применение делает `git worktree`, коммит и push из папки, где запущен сайт. На сервере
   нужен доступ к репозиторию на запись и, по желанию, `gh` для автоматического PR (без него выдаётся ссылка
   на создание PR). Возможно, применение лучше оставить только в командной строке.
4. **`resolved` до слияния PR.** Задача закрывается, когда правка в PR и перезапуск на сохранённых ответах прошёл,
   не дожидаясь слияния. Если нужно «закрывать после слияния» — нужен отдельный шаг или вебхук GitHub.
5. Применение и прогон агента идут синхронно в запросе (секунды–минуты). Для очереди задач нужен фоновый
   обработчик (`procrastinate` по SPEC).

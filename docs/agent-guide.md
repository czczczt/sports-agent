# Путеводитель для разработчика агента сбора данных

Практическое руководство для разработчика модуля агента: окружение, зависимости, архитектура рецептов, запуск генерации и тестирование ремонта.
Спецификация логики агента — в [agent-spec.md](agent-spec.md).

---

## 1. Стек и ключевые зависимости

Модуль агента строится на современных библиотеках декларативного извлечения данных:

| Библиотека | Назначение | Документация |
|---|---|---|
| **Crawl4AI** | Декларативное извлечение данных по CSS-схемам (`JsonCssExtractionStrategy`), генерация схем по HTML-образцам | [docs.crawl4ai.com](https://docs.crawl4ai.com/extraction/no-llm-strategies/) |
| **Pydantic AI** | Управление циклом валидации, типизация вывода, механизм `ModelRetry` при ремонте схемы | [ai.pydantic.dev](https://ai.pydantic.dev/) |
| **Pydantic v2** | Строгая схема данных `ResultRow`, контракты входных и выходных параметров | [docs.pydantic.dev](https://docs.pydantic.dev/) |
| **GigaChat / OpenAI** | Языковая модель для синтеза CSS-селекторов (подключается через OpenAI-совместимый endpoint) | [Сбер GigaChat API](https://developers.sber.ru/docs/ru/gigachat/guides/compatible-openai) |

Установка зависимостей:
```bash
pip install crawl4ai pydantic-ai pydantic beautifulsoup4 selectolax httpx
```

---

## 2. Структура файлов агента

```
sports-agent/
├── docs/
│   ├── agent-spec.md            ← Спецификация агента и правила безопасности
│   ├── agent-guide.md           ← Этот документ
│   ├── agent-queue.md           ← Очередь задач ремонта и модерация
│   └── review/
│       ├── PARSER_AGENT_SPEC.md ← Полная архитектурная спека сбора и агента
│       └── PIPELINE_ARCHITECTURE.md
├── app/
│   ├── services/
│   │   ├── agent_service.py     ← Сервис вызова агента и оркестрации
│   │   └── recipe_service.py    ← Управление версиями рецептов в БД
│   └── api/
│       └── agent.py             ← API админки для подтверждения рецептов
├── parser_running/
│   ├── recipes/                 ← Локальные JSON-рецепты по умолчанию
│   │   ├── runc.json
│   │   ├── grom.json
│   │   └── results_zone.json
│   ├── golden_sets/             ← Сохранённые HTML-образцы и эталонный вывод
│   │   ├── runc/
│   │   └── grom/
│   └── runner.py                ← Детерминированный сборщик без LLM (0 токенов)
```

---

## 3. Как устроен рецепт (CSS-схема Crawl4AI)

Рецепт описывает правила поиска строк протокола и извлечения отдельных колонок без единой строчки императивного Python-кода:

```json
{
  "source_code": "results_zone",
  "version": 1,
  "base_selector": "table.protocol-table tbody tr.row",
  "fields": [
    {"name": "place", "selector": "td.rank", "type": "text"},
    {"name": "bib", "selector": "td.bib", "type": "text"},
    {"name": "full_name", "selector": "td.athlete-name a", "type": "text"},
    {"name": "gender", "selector": "td.gender", "type": "text"},
    {"name": "birth_year", "selector": "td.year", "type": "text"},
    {"name": "club", "selector": "td.club", "type": "text"},
    {"name": "chip_time", "selector": "td.time-chip", "type": "text"},
    {"name": "gun_time", "selector": "td.time-gun", "type": "text"},
    {"name": "status", "selector": "td.status", "type": "text"}
  ],
  "transforms": {
    "gender": {"М": "m", "Ж": "f", "M": "m", "F": "f"},
    "status": {"ФИНИШ": "finished", "DNF": "dnf", "DNS": "dns", "DSQ": "dsq"}
  }
}
```

### Исполнение рецепта воркером (0 токенов):
```python
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

strategy = JsonCssExtractionStrategy(schema=recipe["fields"], base_selector=recipe["base_selector"])
# Быстрое извлечение данных напрямую из HTML без вызова нейросети
extracted_rows = strategy.extract(html_content)
```

---

## 4. Запуск генерации и ремонта рецепта

### Генерация нового рецепта (при подключении площадки):
1. Сохраните 1–2 страницы HTML с протоколами соревнований в `golden_sets/<source>/`.
2. Запустите скрипт генерации:
```python
from app.services.agent_service import generate_recipe_from_samples

recipe = await generate_recipe_from_samples(
    source_code="my_new_source",
    html_samples=["golden_sets/my_new_source/sample1.html"]
)
print("Сгенерированный рецепт:", recipe)
```
3. Проверьте превью первых 20 извлечённых строк. При корректности подтвердите сохранение версии в БД.

### Ремонт существующего рецепта:
Если воркер регулярного сбора зафиксировал сбой (например, изменился селектор `td.athlete-name` на `td.name-link`), задача автоматически поступает в обработчик:
```python
from app.services.agent_service import repair_recipe

repaired_recipe = await repair_recipe(
    source_code="runc",
    current_recipe=existing_recipe,
    failed_html="data/cache/failed_page.html",
    validation_error="Field 'full_name' extracted 0 non-empty values across 150 rows"
)
```
Агент:
- анализирует разницу в DOM;
- обновляет селектор;
- прогоняет извлечение на сохранённом образце;
- проверяет отсутствие регрессии на эталонах `golden_sets/runc/`;
- при успехе публикует новую версию рецепта (`version += 1`).

---

## 5. Тестирование без внешних запросов (Golden-Set)

Любые изменения в логике агента и рецептов тестируются **строго изолированно**, без сетевых запросов к реальным сайтам:
- Для каждого источника поддерживается набор из 3–5 сохранённых фикстур протоколов (`sample.html`) и эталонный JSON с ожидаемыми результатами.
- Запуск тестов регрессии:
```bash
pytest tests/test_recipes.py
```
Критерий успешности: 100% совпадение ключевых полей (чистое время, занятое место) и полное отсутствие исключений при парсинге.

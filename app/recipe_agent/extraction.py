import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

import regex
from bs4 import BeautifulSoup
from pydantic import ValidationError
from soupsieve import SelectorSyntaxError
from soupsieve import compile as compile_selector

from app.recipe_agent.contracts import PlaceBy, RecipeProposal, ResultRow
from parser_running.normalize import to_seconds

MAX_ROWS = 30000
MAX_HTML_BYTES = 8 * 1024 * 1024
PROMPT_SAMPLE_LENGTH = 6000
GENDERS = {"M": "M", "F": "F", "М": "M", "Ж": "F", "MALE": "M", "FEMALE": "F"}
TIME_FIELDS = ("chip_time_s", "gun_time_s")
EMPTY_CELLS = {"", "-", "—"}


class InvalidProtocol(ValueError):
    """A recipe failed to extract a valid protocol."""


@dataclass(frozen=True)
class Sample:
    raw_id: int
    html: str
    place_by: PlaceBy
    total: int | None


@dataclass(frozen=True)
class GoldenCase:
    sample: Sample
    digest: str


def compact_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for element in soup.find_all(["script", "style", "svg", "iframe", "noscript"]):
        element.decompose()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[5:]:
            if row.parent is not None:
                row.decompose()
    return str(soup.body or soup)[:PROMPT_SAMPLE_LENGTH]


def extract(recipe: RecipeProposal, html: str) -> list[ResultRow]:
    # Crawl4AI imports LiteLLM even for CSS-only extraction.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from crawl4ai import JsonCssExtractionStrategy

    css = []
    patterns: dict[str, regex.Pattern[str]] = {}
    try:
        compile_selector(recipe.baseSelector)
        for field in recipe.fields:
            compile_selector(field.selector)
            spec = field.model_dump(exclude_none=True, exclude={"pattern"})
            if field.pattern is not None:
                patterns[field.name] = regex.compile(field.pattern)
                spec["type"] = "text"
            css.append(spec)
    except (SelectorSyntaxError, regex.error) as exc:
        raise InvalidProtocol(
            "Недопустимый CSS-селектор или регулярное выражение"
        ) from exc

    strategy = JsonCssExtractionStrategy(
        {"baseSelector": recipe.baseSelector, "fields": css}
    )
    rows = strategy.extract("about:blank", html)
    if not 1 <= len(rows) <= MAX_ROWS:
        raise InvalidProtocol("Рецепт вернул пустой протокол или превысил лимит строк")
    try:
        for row in rows:
            for name, pattern in patterns.items():
                value = str(row.get(name, ""))[:4096]
                match = pattern.search(value, timeout=0.025)
                row[name] = (
                    (match.group(1) if pattern.groups else match.group())
                    if match
                    else None
                )
    except TimeoutError as exc:
        raise InvalidProtocol("Истекло время применения регулярного выражения") from exc
    return [_normalize(row, number) for number, row in enumerate(rows, start=1)]


def _normalize(raw: dict[str, Any], number: int) -> ResultRow:
    row = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in raw.items()
    }
    row = {
        key: value
        for key, value in row.items()
        if value is not None and value not in EMPTY_CELLS
    }
    if "gender" in row:
        gender = row["gender"].upper()
        row["gender"] = GENDERS.get(gender, gender)
    if "status" in row:
        row["status"] = row["status"].upper()
    for field in TIME_FIELDS:
        if field in row:
            raw_time = row[field]
            seconds = to_seconds(raw_time)
            if seconds is None or any(
                float(part.replace(",", ".")) >= 60 for part in raw_time.split(":")[1:]
            ):
                raise InvalidProtocol(f"Строка {number}: неверный формат {field}")
            row[field] = seconds
    try:
        return ResultRow.model_validate(row)
    except ValidationError as exc:
        fields = ", ".join(
            str(error["loc"][0]) for error in exc.errors(include_input=False)
        )
        raise InvalidProtocol(f"Строка {number}: неверные поля {fields}") from exc


def validate_protocol(
    rows: list[ResultRow], place_by: PlaceBy, total: int | None
) -> None:
    if total is not None and len(rows) != total:
        raise InvalidProtocol(f"Ожидалось строк: {total}, извлечено: {len(rows)}")
    finishers = [row for row in rows if row.status == "FIN"]
    if not finishers:
        raise InvalidProtocol("В протоколе нет финишёров")
    places = [row.place_abs for row in finishers]
    if any(place is None for place in places) or places != sorted(
        place for place in places if place is not None
    ):
        raise InvalidProtocol("У финишёров отсутствуют места или нарушен порядок мест")
    times = [
        row.chip_time_s if place_by == "chip" else row.gun_time_s for row in finishers
    ]
    if any(time is None for time in times) or times != sorted(
        time for time in times if time is not None
    ):
        raise InvalidProtocol(
            f"Отсутствует время по шкале {place_by} или нарушен его порядок"
        )


def protocol_digest(rows: list[ResultRow]) -> str:
    values = [row.model_dump(mode="json") for row in rows]
    canonical = json.dumps(
        values, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

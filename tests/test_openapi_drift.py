"""Тест проверки дрейфа контрактов OpenAPI <-> TypeScript (frontend-audit.md, SPEC v1.3 §4.1).

Проверяет, что FastAPI backend (app.openapi()) синхронизирован с frontend/openapi.json,
и не произошло незафиксированного дрейфа контрактов API.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

ROOT_DIR = Path(__file__).resolve().parent.parent
OPENAPI_JSON = ROOT_DIR / "frontend" / "openapi.json"


def test_openapi_contract_no_drift():
    """Проверяет отсутствие дрейфа между FastAPI OpenAPI и frontend/openapi.json."""
    assert OPENAPI_JSON.exists(), f"frontend/openapi.json не найден по пути {OPENAPI_JSON}"

    generated_spec = app.openapi()
    saved_spec = json.loads(OPENAPI_JSON.read_text(encoding="utf-8"))

    # Сверяем пути (эндпоинты)
    gen_paths = set(generated_spec.get("paths", {}).keys())
    saved_paths = set(saved_spec.get("paths", {}).keys())

    missing_in_frontend = gen_paths - saved_paths
    extra_in_frontend = saved_paths - gen_paths

    assert not missing_in_frontend, (
        f"В backend появились новые эндпоинты, отсутствующие в frontend/openapi.json: {missing_in_frontend}. "
        "Запустите `python scripts/generate_types.py` или `npm --prefix frontend run gen:api`."
    )
    assert not extra_in_frontend, (
        f"В frontend/openapi.json присутствуют удалённые эндпоинты: {extra_in_frontend}. "
        "Запустите `python scripts/generate_types.py` или `npm --prefix frontend run gen:api`."
    )

    # Сверяем компоненты схем
    gen_schemas = set(generated_spec.get("components", {}).get("schemas", {}).keys())
    saved_schemas = set(saved_spec.get("components", {}).get("schemas", {}).keys())

    missing_schemas = gen_schemas - saved_schemas
    extra_schemas = saved_schemas - gen_schemas

    assert not missing_schemas, (
        f"В backend добавлены схемы моделей, отсутствующие в frontend/openapi.json: {missing_schemas}. "
        "Запустите `python scripts/generate_types.py`."
    )
    assert not extra_schemas, (
        f"В frontend/openapi.json присутствуют удалённые схемы моделей: {extra_schemas}. "
        "Запустите `python scripts/generate_types.py`."
    )

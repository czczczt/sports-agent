import importlib
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.database import async_postgres_url
from app.main import app
from app.pipeline.import_sqlite import migrate

try:
    from fastapi.routing import iter_route_contexts
except ImportError:  # FastAPI versions that eagerly flatten included routers.
    def iter_route_contexts(routes):
        return iter(routes)


def headers(client):
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user"}
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_every_domain_route_requires_auth():
    with TestClient(app) as client:
        routes = [
            route
            for route in iter_route_contexts(app.routes)
            if isinstance(getattr(route, "original_route", route), APIRoute)
            and (
                route.path.startswith("/api/")
                or route.path.startswith(("/athletes", "/events", "/races"))
            )
            and not route.path.startswith("/api/auth")
        ]
        assert routes
        for route in routes:
            path = re.sub(r"\{[^}]+\}", "1", route.path)
            for method in route.methods:
                response = client.request(method, path)
                assert response.status_code == 401, (method, path, response.text)


def test_empty_startup_and_health(empty_client):
    client = empty_client
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    auth = headers(client)
    assert client.get("/api/athletes/search?last_name=test", headers=auth).json() == []
    assert client.get("/api/events", headers=auth).json() == []
    rating = client.get("/api/rating", headers=auth)
    assert rating.status_code == 200, rating.text
    assert rating.json()["rows"] == []
    assert client.get("/api/athletes/999/summary", headers=auth).status_code == 404
    assert client.get("/api/races/999", headers=auth).status_code == 404


def test_login_profiles_events_protocol_and_rating(client, migrated_url, sqlite_source):
    migrate(sqlite_source, migrated_url)
    auth = headers(client)
    admin_response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    )
    auth = {"Authorization": "Bearer " + admin_response.json()["access_token"]}
    for spelling in ("федоров", "ФЁДОРОВ"):
        response = client.get(
            "/api/athletes/search", params={"last_name": spelling}, headers=auth
        )
        assert response.status_code == 200, response.text
        assert [row["id"] for row in response.json()] == [1]
    expectations = {
        "/api/athletes/1/summary": {"athlete", "personal_bests", "dynamics", "rating"},
        "/api/events/1": {"id", "races"},
        "/api/races/1": {"race", "event", "results", "competition", "rating_leaders"},
        "/api/rating": {"rows", "total", "period_start", "period_end", "me_row"},
        "/api/rating/formula": {"norms"},
    }
    for path, keys in expectations.items():
        response = client.get(path, headers=auth)
        assert response.status_code == 200, (path, response.text)
        assert keys <= response.json().keys(), (path, response.json())
    response = client.get("/api/athletes/1/results", headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()[0]["result_id"] == 1
    response = client.get("/api/races/1/results", headers=auth)
    assert response.status_code == 200, response.text
    assert [row["bib"] for row in response.json()] == ["A-7", None, "003"]
    found = client.get("/api/races/1/results", params={"search": "A-7"}, headers=auth)
    assert len(found.json()) == 1
    rating = client.get("/api/rating?athlete_id=1", headers=auth).json()
    assert rating["me_row"]["points"] == 123.456
    assert {row["athlete_id"]: row["points"] for row in rating["rows"]} == {
        1: 123.456,
        2: 87.125,
    }


def test_assessment_uses_cache_without_real_llm(
    client, migrated_url, sqlite_source, monkeypatch
):
    migrate(sqlite_source, migrated_url)
    agent = importlib.import_module("app.services.agent_service")
    monkeypatch.setattr(agent, "GIGACHAT_CREDENTIALS", "test-credentials")
    calls = []

    async def token(*args):
        calls.append("token")
        return "fake-token"

    async def completion(*args):
        calls.append("completion")
        return "Synthetic assessment"

    monkeypatch.setattr(agent, "get_gigachat_token", token)
    monkeypatch.setattr(agent, "call_gigachat_chat", completion)
    auth = headers(client)
    first = client.post("/api/athletes/1/assessment", headers=auth)
    assert first.status_code == 200, first.text
    assert first.json()["cached"] is False
    second = client.post("/api/athletes/1/assessment", headers=auth)
    assert second.status_code == 200, second.text
    assert second.json()["cached"] is True
    assert second.json()["assessment_text"] == "Synthetic assessment"
    assert calls == ["token", "completion"]


def test_sqlite_runtime_is_rejected():
    for url in ("sqlite:///running.db", "sqlite+aiosqlite:///running.db"):
        with pytest.raises(ValueError, match="PostgreSQL"):
            async_postgres_url(url)

"""Synthetic PostgreSQL MVP contracts live in tests/stage0/test_api.py.

This file retains the historical smoke-test entry point without depending on a
local running.db or sending requests to an actual LLM provider.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_frontend_and_unknown_api():
    with TestClient(app) as client:
        for path in (
            "/",
            "/events-view",
            "/athletes-view/1",
            "/rating-view",
            "/agent-review",
        ):
            response = client.get(path)
            assert response.status_code in (200, 503)
            assert "text/html" in response.headers["content-type"]
        assert client.get("/api/no-such-endpoint").status_code == 404

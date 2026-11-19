"""Privacy and roles retain dev behavior using deterministic synthetic records."""

import pytest


@pytest.mark.parametrize(
    "username,role", [("user", "user"), ("admin", "admin"), ("captain", "captain")]
)
def test_db_auth_user_and_admin(client, auth_headers, username, role):
    response = client.get("/api/auth/me", headers=auth_headers(username))
    assert response.status_code == 200
    assert response.json()["role"] == role


def test_privacy_sanitization_for_regular_and_admin(client, auth_headers):
    assert client.get("/api/athletes/search?last_name=федоров").status_code == 401
    user = auth_headers()
    response = client.get("/api/athletes/search?last_name=федоров", headers=user)
    assert response.status_code == 200, response.text
    athlete = response.json()[0]
    for field in ("city", "club", "middle_name", "birth_date"):
        assert athlete[field] is None
    summary = client.get("/api/athletes/1/summary", headers=user)
    assert summary.status_code == 200, summary.text
    for field in ("city", "club", "middle_name", "birth_date"):
        assert summary.json()["athlete"][field] is None
    admin = client.get("/api/athletes/1/summary", headers=auth_headers("admin"))
    assert admin.status_code == 200, admin.text
    assert admin.json()["athlete"]["city"] == "city"
    assert admin.json()["athlete"]["middle_name"] == "Иванович"
    assert admin.json()["athlete"]["birth_date"] == "1990-05-15"


def test_blocked_or_not_employee_access(client):
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "wrongpassword"}
    )
    assert response.status_code == 401

"""Auth contracts against isolated PostgreSQL accounts, never developer accounts."""

import psycopg
import pytest


@pytest.mark.parametrize(
    "username,role,display",
    [
        ("user", "user", "Пользователь"),
        ("admin", "admin", "Администратор"),
    ],
)
def test_login_success(client, username, role, display):
    response = client.post(
        "/api/auth/login", json={"username": username, "password": username}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == username
    assert data["user"]["role"] == role
    assert data["user"]["display_name"] == display
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    me = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer " + data["access_token"]}
    )
    assert me.status_code == 200
    assert me.json()["username"] == username


def test_login_invalid_credentials(client):
    for username, password in [("user", "wrongpassword"), ("hacker", "user")]:
        response = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 401


def test_me_unauthorized(client):
    assert client.get("/api/auth/me").status_code == 401


def test_logout(client, auth_headers):
    auth = auth_headers()
    assert client.post("/api/auth/logout", headers=auth).status_code == 200
    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_protected_endpoints_require_auth(client, auth_headers):
    assert client.get("/api/athletes/search?last_name=федоров").status_code == 401
    assert (
        client.get(
            "/api/athletes/search?last_name=федоров", headers=auth_headers()
        ).status_code
        == 200
    )


def test_not_employee_block_is_persisted(client, imported_url, auth_headers):
    auth = auth_headers()
    with psycopg.connect(imported_url) as connection:
        connection.execute("UPDATE app_user SET athlete_id=1 WHERE username='user'")
        connection.execute(
            "UPDATE athlete SET employee_status='not_employee' WHERE id=1"
        )
    assert client.get("/api/auth/me", headers=auth).status_code == 403
    with psycopg.connect(imported_url) as connection:
        assert (
            connection.execute(
                "SELECT status FROM app_user WHERE username='user'"
            ).fetchone()[0]
            == "blocked"
        )
    assert (
        client.post(
            "/api/auth/login", json={"username": "user", "password": "user"}
        ).status_code
        == 403
    )


def test_blocked_account_login(client, imported_url):
    with psycopg.connect(imported_url) as connection:
        connection.execute("UPDATE app_user SET status='blocked' WHERE username='user'")
    assert (
        client.post(
            "/api/auth/login", json={"username": "user", "password": "user"}
        ).status_code
        == 403
    )


def test_login_failed_attempts_lockout(client):
    for _ in range(4):
        resp = client.post(
            "/api/auth/login", json={"username": "user", "password": "wrong_pwd"}
        )
        assert resp.status_code == 401, resp.text

    resp = client.post(
        "/api/auth/login", json={"username": "user", "password": "wrong_pwd"}
    )
    assert resp.status_code == 403
    assert "заблокирован" in resp.json()["detail"].lower()

    resp_correct = client.post(
        "/api/auth/login", json={"username": "user", "password": "user"}
    )
    assert resp_correct.status_code == 403


def test_registration_consent_required(client):
    payload_no_consent = {
        "username": "no_consent_user",
        "email": "noconsent@example.test",
        "password": "secret_password_123",
        "first_name": "Иван",
        "last_name": "Тестов",
        "consent": False,
    }
    resp = client.post("/api/auth/register", json=payload_no_consent)
    assert resp.status_code == 422

    del payload_no_consent["consent"]
    resp2 = client.post("/api/auth/register", json=payload_no_consent)
    assert resp2.status_code == 422


def test_password_reset_flow(client):
    from app.core.email import SENT_EMAILS

    SENT_EMAILS.clear()

    req_resp = client.post(
        "/api/auth/password-reset-request", json={"email": "user@example.test"}
    )
    assert req_resp.status_code == 200
    assert len(SENT_EMAILS) == 1
    token = SENT_EMAILS[0]["token"]
    assert token

    confirm_resp = client.post(
        "/api/auth/password-reset",
        json={"token": token, "new_password": "brand_new_password_456"},
    )
    assert confirm_resp.status_code == 200

    assert (
        client.post(
            "/api/auth/login", json={"username": "user", "password": "user"}
        ).status_code
        == 401
    )

    login_resp = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "brand_new_password_456"},
    )
    assert login_resp.status_code == 200

    reuse_resp = client.post(
        "/api/auth/password-reset",
        json={"token": token, "new_password": "another_new_password_789"},
    )
    assert reuse_resp.status_code == 400

import pytest
from fastapi.testclient import TestClient
from app.main import app


def test_db_auth_user_and_admin():
    client = TestClient(app)
    # Login as user
    resp = client.post("/api/auth/login", json={"username": "user", "password": "user"})
    assert resp.status_code == 200, resp.text
    user_data = resp.json()
    assert user_data["user"]["role"] == "user"
    assert "access_token" in user_data

    # Login as admin
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200, resp.text
    admin_data = resp.json()
    assert admin_data["user"]["role"] == "admin"
    assert "access_token" in admin_data


def test_privacy_sanitization_for_regular_and_admin():
    # 1. Unauthenticated guest: blocked by protected_api (401)
    guest_client = TestClient(app)
    resp_guest = guest_client.get("/api/athletes/search?last_name=Иванов")
    assert resp_guest.status_code == 401

    # 2. Regular user client
    user_client = TestClient(app)
    login_user = user_client.post("/api/auth/login", json={"username": "user", "password": "user"})
    assert login_user.status_code == 200

    resp_user = user_client.get("/api/athletes/search?last_name=Иванов")
    assert resp_user.status_code == 200
    user_results = resp_user.json()
    assert len(user_results) > 0
    first = user_results[0]
    # Sensitive PII must be redacted for regular users
    assert first["city"] is None
    assert first["club"] is None
    assert first["middle_name"] is None
    assert first["birth_date"] is None
    assert first["birth_year"] is not None or first["last_name"] is not None

    athlete_id = first["id"]

    # Summary as regular user
    resp_sum_user = user_client.get(f"/api/athletes/{athlete_id}/summary")
    assert resp_sum_user.status_code == 200
    ath = resp_sum_user.json()["athlete"]
    assert ath["city"] is None
    assert ath["club"] is None
    assert ath["middle_name"] is None
    assert ath["birth_date"] is None

    # 3. Admin client
    admin_client = TestClient(app)
    login_admin = admin_client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login_admin.status_code == 200

    resp_sum_admin = admin_client.get(f"/api/athletes/{athlete_id}/summary")
    assert resp_sum_admin.status_code == 200
    ath_admin = resp_sum_admin.json()["athlete"]
    # Admin can see fields if populated in DB (not forced None)
    # The record with id athlete_id in DB has city='Казань'
    assert ath_admin["city"] == "Казань"


def test_blocked_or_not_employee_access():
    client = TestClient(app)
    # Wrong credentials
    resp = client.post("/api/auth/login", json={"username": "user", "password": "wrongpassword"})
    assert resp.status_code == 401

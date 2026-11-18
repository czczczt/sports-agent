"""Тесты для новых полей спортсмена и заявок (SPEC v1.3)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def get_auth_headers():
    """Авторизуемся под admin и user для тестов."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    admin_token = resp.json()["access_token"]

    resp = client.post("/api/auth/login", json={"username": "user", "password": "user"})
    assert resp.status_code == 200
    user_token = resp.json()["access_token"]

    return {
        "admin": {"Authorization": f"Bearer {admin_token}"},
        "user": {"Authorization": f"Bearer {user_token}"},
    }


def test_athlete_fields_returned():
    """Проверяем, что эндпоинт спортсмена возвращает first_name, last_name, employee_status."""
    headers = get_auth_headers()
    resp = client.get("/api/athletes/search?last_name=Андреев", headers=headers["user"])
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    athlete = data[0]
    assert "last_name" in athlete
    assert athlete["last_name"] == "Андреев"
    assert "first_name" in athlete
    assert "middle_name" in athlete
    assert "employee_status" in athlete
    assert athlete["employee_status"] == "presumed"
    assert "is_hidden" in athlete
    assert athlete["is_hidden"] is False


def test_create_report_authenticated():
    """Пользователь может отправить заявку."""
    headers = get_auth_headers()
    payload = {
        "kind": "not_me",
        "athlete_id": 1,
        "message": "Это результат моего тёзки, отвяжите пожалуйста",
    }
    resp = client.post("/api/reports", json=payload, headers=headers["user"])
    assert resp.status_code == 201
    created = resp.json()
    assert created["kind"] == "not_me"
    assert created["status"] == "new"
    assert created["message"] == payload["message"]


def test_create_report_invalid_kind():
    """Заявка с невалидным типом отклоняется."""
    headers = get_auth_headers()
    payload = {
        "kind": "unknown_action",
        "message": "Тест",
    }
    resp = client.post("/api/reports", json=payload, headers=headers["user"])
    assert resp.status_code == 400


def test_list_reports_admin_only():
    """Просмотр списка заявок доступен только админу."""
    headers = get_auth_headers()
    # Обычный пользователь получает 403
    resp_user = client.get("/api/reports", headers=headers["user"])
    assert resp_user.status_code == 403

    # Админ видит список
    resp_admin = client.get("/api/reports", headers=headers["admin"])
    assert resp_admin.status_code == 200
    reports = resp_admin.json()
    assert isinstance(reports, list)
    assert len(reports) > 0

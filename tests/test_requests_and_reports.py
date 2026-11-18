import pytest
from fastapi.testclient import TestClient
from app.main import app


def test_user_report_lifecycle():
    admin_client = TestClient(app)
    admin_login = admin_client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert admin_login.status_code == 200

    user_client = TestClient(app)
    user_login = user_client.post("/api/auth/login", json={"username": "user", "password": "user"})
    assert user_login.status_code == 200

    # 1. User submits report with kind 'hide_me'
    report_payload = {
        "kind": "hide_me",
        "athlete_id": 1,
        "message": "Прошу скрыть мои данные из публичного рейтинга по 152-ФЗ",
    }
    resp = user_client.post("/api/reports", json=report_payload)
    assert resp.status_code == 201, resp.text
    created_report = resp.json()
    assert created_report["kind"] == "hide_me"
    assert created_report["status"] == "new"
    report_id = created_report["id"]

    # 2. Regular user views reports - gets 403 on general list, 200 on /my
    resp_user_forbidden = user_client.get("/api/reports")
    assert resp_user_forbidden.status_code == 403

    resp_user_my = user_client.get("/api/reports/my")
    assert resp_user_my.status_code == 200
    user_reports = resp_user_my.json()
    assert any(r["id"] == report_id for r in user_reports)

    # 3. Admin views reports
    resp_admin_list = admin_client.get("/api/reports?status_filter=new")
    assert resp_admin_list.status_code == 200
    admin_reports = resp_admin_list.json()
    assert any(r["id"] == report_id for r in admin_reports)

    # 4. Admin decides on report
    decision_payload = {
        "decision": "accepted",
        "moderator_comment": "Профиль скрыт по обращению пользователя",
    }
    resp_decide = admin_client.post(f"/api/reports/{report_id}/decision", json=decision_payload)
    assert resp_decide.status_code == 200, resp_decide.text
    decided_report = resp_decide.json()
    assert decided_report["status"] == "accepted"
    assert decided_report["moderator_comment"] == "Профиль скрыт по обращению пользователя"


def test_access_request_registration_lifecycle():
    admin_client = TestClient(app)
    admin_login = admin_client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert admin_login.status_code == 200

    # 1. New user registers
    guest_client = TestClient(app)
    reg_username = "new_runner_test"
    reg_payload = {
        "username": reg_username,
        "email": "runner@sberbank.ru",
        "password": "strongpassword123",
        "first_name": "Иван",
        "last_name": "Иванов",
        "birth_date": "1990-05-15",
        "city": "Москва",
        "consent": True,
        "consent_version": "v1.0",
    }
    # Clean up if existed from previous run
    reg_resp = guest_client.post("/api/auth/register", json=reg_payload)
    if reg_resp.status_code == 400:
        # User already exists, use timestamped username
        import time
        reg_username = f"runner_{int(time.time())}"
        reg_payload["username"] = reg_username
        reg_payload["email"] = f"{reg_username}@sberbank.ru"
        reg_resp = guest_client.post("/api/auth/register", json=reg_payload)

    assert reg_resp.status_code == 201, reg_resp.text
    reg_data = reg_resp.json()
    assert reg_data["status"] == "pending"
    new_user_id = reg_data["user_id"]

    # 2. Trying to login while pending fails with 403
    login_attempt = guest_client.post("/api/auth/login", json={"username": reg_username, "password": "strongpassword123"})
    assert login_attempt.status_code == 403
    assert "на рассмотрении" in login_attempt.text

    # 3. Admin lists access requests
    reqs_resp = admin_client.get("/api/admin/access-requests?status_filter=pending")
    assert reqs_resp.status_code == 200
    reqs = reqs_resp.json()
    target_req = next((r for r in reqs if r["id"] == new_user_id), None)
    assert target_req is not None
    assert target_req["first_name"] == "Иван"

    # 4. Admin approves access request
    approve_resp = admin_client.post(
        f"/api/admin/access-requests/{new_user_id}/decision",
        json={"decision": "approve", "comment": "Сотрудник подтверждён"},
    )
    assert approve_resp.status_code == 200, approve_resp.text
    approved_data = approve_resp.json()
    assert approved_data["status"] == "active"

    # 5. User can now successfully login!
    login_success = guest_client.post("/api/auth/login", json={"username": reg_username, "password": "strongpassword123"})
    assert login_success.status_code == 200
    assert login_success.json()["user"]["status"] == "active"

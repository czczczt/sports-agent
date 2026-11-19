"""Dev athlete fields and report checks on synthetic PostgreSQL data."""


def test_athlete_fields_returned(client, auth_headers):
    response = client.get(
        "/api/athletes/search?last_name=федоров", headers=auth_headers("admin")
    )
    assert response.status_code == 200, response.text
    athlete = response.json()[0]
    assert athlete["first_name"] == "Иван"
    assert athlete["last_name"] == "Фёдоров"
    assert athlete["middle_name"] == "Иванович"
    assert athlete["birth_date"] == "1990-05-15"
    assert athlete["employee_status"] == "presumed"
    assert athlete["is_hidden"] is False


def test_create_report_authenticated(client, auth_headers):
    payload = {
        "kind": "not_me",
        "athlete_id": 1,
        "message": "Synthetic mismatch report",
    }
    response = client.post("/api/reports", json=payload, headers=auth_headers())
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "not_me"
    assert response.json()["status"] == "new"
    assert response.json()["message"] == payload["message"]


def test_create_report_invalid_kind(client, auth_headers):
    response = client.post(
        "/api/reports",
        json={"kind": "unknown_action", "message": "test"},
        headers=auth_headers(),
    )
    assert response.status_code == 400


def test_list_reports_admin_only(client, auth_headers):
    user = auth_headers()
    response = client.post(
        "/api/reports", json={"kind": "other", "message": "test"}, headers=user
    )
    assert response.status_code == 201
    assert client.get("/api/reports", headers=user).status_code == 403
    response = client.get("/api/reports", headers=auth_headers("admin"))
    assert response.status_code == 200
    assert len(response.json()) == 1

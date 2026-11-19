"""Request lifecycle and atomicity checks on disposable PostgreSQL databases."""

import psycopg


def test_user_report_lifecycle(client, auth_headers, imported_url):
    admin = auth_headers("admin")
    user = auth_headers()
    response = client.post(
        "/api/reports",
        json={"kind": "hide_me", "athlete_id": 1, "message": "Hide profile"},
        headers=user,
    )
    assert response.status_code == 201, response.text
    report_id = response.json()["id"]
    assert client.get("/api/reports", headers=user).status_code == 403
    assert any(
        row["id"] == report_id
        for row in client.get("/api/reports/my", headers=user).json()
    )
    assert any(
        row["id"] == report_id
        for row in client.get("/api/reports?status_filter=new", headers=admin).json()
    )
    response = client.post(
        f"/api/reports/{report_id}/decision",
        json={"decision": "accepted", "moderator_comment": "done"},
        headers=admin,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "accepted"
    assert response.json()["moderator_comment"] == "done"
    with psycopg.connect(imported_url) as connection:
        assert (
            connection.execute("SELECT is_hidden FROM athlete WHERE id=1").fetchone()[0]
            is True
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM audit_log WHERE action='report_decision' AND entity_id=%s",
                (report_id,),
            ).fetchone()[0]
            == 1
        )


def test_access_request_registration_lifecycle(client, auth_headers, imported_url):
    admin = auth_headers("admin")
    payload = {
        "username": "new_runner",
        "email": "new@example.test",
        "password": "strongpassword123",
        "first_name": "Иван",
        "last_name": "Фёдоров",
        "birth_date": "1990-05-15",
        "city": "Москва",
        "consent": True,
        "consent_version": "v1.0",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    new_id = response.json()["user_id"]
    credentials = {"username": payload["username"], "password": payload["password"]}
    assert client.post("/api/auth/login", json=credentials).status_code == 403
    queue = client.get(
        "/api/admin/access-requests?status_filter=pending", headers=admin
    )
    assert queue.status_code == 200, queue.text
    request = next(row for row in queue.json() if row["id"] == new_id)
    assert request["first_name"] == "Иван"
    response = client.post(
        f"/api/admin/access-requests/{new_id}/decision",
        json={"decision": "approve", "athlete_id": 1, "comment": "confirmed"},
        headers=admin,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    with psycopg.connect(imported_url) as connection:
        row = connection.execute(
            "SELECT password_hash,athlete_id,consent_at,approved_by FROM app_user WHERE id=%s",
            (new_id,),
        ).fetchone()
        assert row[0].startswith("$argon2")
        assert row[1:] == (1, row[2], 2)
        assert row[2] is not None
        assert (
            connection.execute(
                "SELECT count(*) FROM audit_log WHERE entity_id=%s", (new_id,)
            ).fetchone()[0]
            >= 1
        )


def test_report_decision_rolls_back_when_audit_fails(
    client, auth_headers, imported_url
):
    admin = auth_headers("admin")
    response = client.post(
        "/api/reports",
        json={"kind": "hide_me", "athlete_id": 1, "message": "Atomic failure test"},
        headers=auth_headers(),
    )
    assert response.status_code == 201, response.text
    report_id = response.json()["id"]
    with psycopg.connect(imported_url) as connection:
        connection.execute(
            "ALTER TABLE audit_log ADD CONSTRAINT fail_test_audit CHECK (action <> 'report_decision')"
        )
    original = client._transport.raise_server_exceptions
    client._transport.raise_server_exceptions = False
    try:
        response = client.post(
            f"/api/reports/{report_id}/decision",
            json={"decision": "accepted"},
            headers=admin,
        )
        assert response.status_code == 500, response.text
    finally:
        client._transport.raise_server_exceptions = original
    with psycopg.connect(imported_url) as connection:
        assert (
            connection.execute(
                "SELECT status FROM report WHERE id=%s", (report_id,)
            ).fetchone()[0]
            == "new"
        )
        assert (
            connection.execute("SELECT is_hidden FROM athlete WHERE id=1").fetchone()[0]
            is False
        )

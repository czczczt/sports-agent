import io


def test_hidden_athlete_privacy(client, auth_headers):
    admin_auth = auth_headers("admin")
    user_auth = auth_headers("user")

    # Скрываем спортсмена #2
    hide_resp = client.patch(
        "/api/admin/athletes/2",
        json={"is_hidden": True},
        headers=admin_auth,
    )
    assert hide_resp.status_code == 200, hide_resp.text
    assert hide_resp.json()["is_hidden"] is True

    # Обычный пользователь получает 404 при попытке открыть профиль или результаты
    resp_user_summary = client.get("/api/athletes/2/summary", headers=user_auth)
    assert resp_user_summary.status_code == 404

    resp_user_results = client.get("/api/athletes/2/results", headers=user_auth)
    assert resp_user_results.status_code == 404

    # Администратор может видеть карточку
    resp_admin_summary = client.get("/api/athletes/2/summary", headers=admin_auth)
    assert resp_admin_summary.status_code == 200

    # Возвращаем флаг обратно
    client.patch("/api/admin/athletes/2", json={"is_hidden": False}, headers=admin_auth)


def test_create_and_update_athlete_admin(client, auth_headers):
    admin_auth = auth_headers("admin")
    user_auth = auth_headers("user")

    # Обычный пользователь не имеет доступа к админке спортсменов
    assert client.get("/api/admin/athletes", headers=user_auth).status_code == 403

    # Создание спортсмена админом
    new_athlete = {
        "first_name": "Пётр",
        "last_name": "Сидоров",
        "middle_name": "Алексеевич",
        "birth_date": "1992-04-12",
        "gender": "M",
        "city": "Екатеринбург",
        "club": "Сбер",
        "employee_status": "presumed",
        "employee_since": "2023-01-10",
    }
    create_resp = client.post("/api/admin/athletes", json=new_athlete, headers=admin_auth)
    assert create_resp.status_code == 201, create_resp.text
    data = create_resp.json()
    ath_id = data["id"]
    assert data["display_name"] == "Сидоров Пётр"
    assert data["employee_since"] == "2023-01-10"

    # Редактирование спортсмена: перевод в not_employee
    patch_resp = client.patch(
        f"/api/admin/athletes/{ath_id}",
        json={"employee_status": "not_employee"},
        headers=admin_auth,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    patched = patch_resp.json()
    assert patched["employee_status"] == "not_employee"
    assert patched["employee_until"] is not None  # Auto-set to today


def test_import_athletes_csv(client, auth_headers):
    admin_auth = auth_headers("admin")

    csv_content = """Фамилия,Имя,Отчество,Дата рождения,Пол,Город,Клуб,Статус
Иванов,Алексей,Сергеевич,15.06.1988,М,Москва,Сбер,confirmed
Смирнова,Ольга,Николаевна,22.09.1995,Ж,Санкт-Петербург,SberTeam,presumed
"""
    files = {"file": ("athletes.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp = client.post("/api/admin/athletes/import", files=files, headers=admin_auth)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["total"] == 2
    assert result["created"] >= 1
    assert len(result["errors"]) == 0

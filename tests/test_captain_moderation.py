"""Тесты для проверки роли капитана, скоупа по видам спорта и модерации (SPEC v1.3 §2, §3.2, §3.5, §5).

Приёмка:
- Капитан меняет класс, D+, RL-статус старта только по своему виду (иначе 403);
- Ручная загрузка только по своему виду (иначе 403);
- Капитан не может менять настройки, источники, роли, удалять протоколы (403);
- not_employee от капитана попадает в сводку админу;
- Все действия пишутся в AuditLog.
"""

import json

import psycopg
import pytest


def auth_headers(username: str, role: str = "captain", display_name: str = "Капитан") -> dict[str, str]:
    from app.api.auth import _create_token
    token = _create_token(username, role, display_name)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def captain_run_headers():
    return auth_headers("captain", "captain", "Капитан Бега")


@pytest.fixture
def admin_headers():
    return auth_headers("admin", "admin", "Администратор")


@pytest.fixture
def user_headers():
    return auth_headers("user", "user", "Пользователь")


def test_check_captain_sport_scope_unit():
    from fastapi import HTTPException

    from app.api.auth import check_captain_sport_scope
    from app.models import UserOut

    admin = UserOut(
        username="admin",
        role="admin",
        display_name="Admin",
        captain_sports=["run", "ski"],
    )
    # Admin is allowed any sport
    check_captain_sport_scope(admin, "run")
    check_captain_sport_scope(admin, "triathlon")

    captain_run = UserOut(
        username="cap",
        role="captain",
        display_name="Captain",
        captain_sports=["run"],
    )
    # Captain can access run
    check_captain_sport_scope(captain_run, "run")
    check_captain_sport_scope(captain_run, "RUN")

    # Captain cannot access ski
    with pytest.raises(HTTPException) as exc_info:
        check_captain_sport_scope(captain_run, "ski", "редактирование")
    assert exc_info.value.status_code == 403

    # Ordinary user is always 403
    user = UserOut(username="usr", role="user", display_name="User")
    with pytest.raises(HTTPException) as exc_info:
        check_captain_sport_scope(user, "run")
    assert exc_info.value.status_code == 403



def test_captain_can_update_race_in_own_sport(client, imported_url, captain_run_headers):
    # Убеждаемся, что race 1 привязан к competition со sport_type = 'run'
    with psycopg.connect(imported_url) as conn:
        conn.execute("UPDATE competition SET sport_type = 'run' WHERE id = 1")
        conn.execute("UPDATE race SET sport = 'run' WHERE id = 1")

    # Капитан бега обновляет класс дистанции, D+, RL-статус
    payload = {
        "scoring_class": "10k",
        "elevation_gain_m": 120.5,
        "is_rl_series": True,
        "special": "regular",
    }
    resp = client.patch("/api/admin/races/1", json=payload, headers=captain_run_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["scoring_class"] == "10k"
    assert data["elevation_gain_m"] == 120.5
    assert data["is_rl_series"] is True

    # Проверяем запись в audit_log
    with psycopg.connect(imported_url) as conn:
        row = conn.execute(
            "SELECT action, entity, entity_id, diff FROM audit_log WHERE entity = 'race' AND entity_id = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "update_race"
        diff = row[3] if isinstance(row[3], dict) else json.loads(row[3])
        assert diff["updates"]["scoring_class"] == "10k"


def test_captain_forbidden_to_update_race_in_foreign_sport(client, imported_url, captain_run_headers):
    # Создаём лыжную дистанцию
    with psycopg.connect(imported_url) as conn:
        conn.execute(
            "INSERT INTO competition (id, source_id, external_id, name, sport_type) VALUES (99, 1, 'comp_ski', 'Лыжный марафон', 'ski') ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO race (id, competition_id, external_id, name, sport) VALUES (99, 99, 'race_ski', 'Лыжи 50км', 'ski') ON CONFLICT DO NOTHING"
        )

    # Капитан бега пытается изменить лыжную дистанцию -> 403 Forbidden
    payload = {"scoring_class": "ski_50k", "elevation_gain_m": 300.0}
    resp = client.patch("/api/admin/races/99", json=payload, headers=captain_run_headers)
    assert resp.status_code == 403, resp.text
    assert "видов спорта капитана" in resp.json()["detail"]


def test_captain_forbidden_to_change_sport_to_foreign(client, imported_url, captain_run_headers):
    # Дистанция беговая, капитан пытается сменить sport на 'triathlon'
    payload = {"sport": "triathlon"}
    resp = client.patch("/api/admin/races/1", json=payload, headers=captain_run_headers)
    assert resp.status_code == 403, resp.text
    assert "видов спорта капитана" in resp.json()["detail"]


def test_captain_manual_protocol_upload_scope(client, imported_url, captain_run_headers):
    # Беговая дистанция -> капитан бега может грузить протокол
    rows = [
        {
            "bib": "101",
            "full_name_raw": "Сергеев Сергей",
            "gender": "M",
            "birth_year": 1995,
            "status": "FIN",
            "place_abs": 1,
            "chip_time_s": 2100.0,
            "gun_time_s": 2105.0,
        }
    ]
    resp = client.post("/api/admin/races/1/manual-upload", json={"rows": rows}, headers=captain_run_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported_count"] == 1

    # Проверяем audit_log
    with psycopg.connect(imported_url) as conn:
        row = conn.execute(
            "SELECT action FROM audit_log WHERE action = 'manual_protocol_upload' AND entity_id = 1"
        ).fetchone()
        assert row is not None

    # Попытка загрузить на лыжную дистанцию 99 -> 403 Forbidden
    with psycopg.connect(imported_url) as conn:
        conn.execute(
            "INSERT INTO competition (id, source_id, external_id, name, sport_type) VALUES (99, 1, 'comp_ski', 'Лыжный марафон', 'ski') ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO race (id, competition_id, external_id, name, sport) VALUES (99, 99, 'race_ski', 'Лыжи 50км', 'ski') ON CONFLICT DO NOTHING"
        )
    resp_ski = client.post("/api/admin/races/99/manual-upload", json={"rows": rows}, headers=captain_run_headers)
    assert resp_ski.status_code == 403, resp_ski.text


def test_captain_forbidden_to_delete_protocol(client, imported_url, captain_run_headers, admin_headers):
    # Капитану удаление протокола ЗАПРЕЩЕНО -> 403
    resp_captain = client.delete("/api/admin/races/1/protocol", headers=captain_run_headers)
    assert resp_captain.status_code == 403, resp_captain.text

    # Администратору разрешено -> 200
    resp_admin = client.delete("/api/admin/races/1/protocol", headers=admin_headers)
    assert resp_admin.status_code == 200, resp_admin.text
    assert resp_admin.json()["success"] is True

    # Проверяем audit_log
    with psycopg.connect(imported_url) as conn:
        row = conn.execute(
            "SELECT action FROM audit_log WHERE action = 'delete_protocol' AND entity_id = 1"
        ).fetchone()
        assert row is not None


def test_captain_forbidden_settings_sources_roles(client, captain_run_headers):
    # Настройки -> 403
    resp_settings = client.patch("/api/admin/settings", json={"key": "top_n_verify", "value": 15}, headers=captain_run_headers)
    assert resp_settings.status_code == 403

    # Источники -> 403
    resp_sources = client.patch("/api/admin/sources/1", json={"enabled": False}, headers=captain_run_headers)
    assert resp_sources.status_code == 403

    # Роли -> 403
    resp_roles = client.patch("/api/admin/users/1", json={"role": "admin"}, headers=captain_run_headers)
    assert resp_roles.status_code == 403


def test_captain_not_employee_in_admin_summary(client, imported_url, captain_run_headers, admin_headers):
    # Убеждаемся, что спортсмен 1 относится к 'run'
    with psycopg.connect(imported_url) as conn:
        conn.execute("UPDATE competition SET sport_type = 'run' WHERE id = 1")
        conn.execute("UPDATE race SET sport = 'run' WHERE id = 1")

    # Капитан переводит спортсмена в not_employee
    patch_payload = {
        "employee_status": "not_employee",
    }
    resp = client.patch("/api/admin/athletes/1", json=patch_payload, headers=captain_run_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["employee_status"] == "not_employee"

    # Проверяем audit_log
    with psycopg.connect(imported_url) as conn:
        row = conn.execute(
            "SELECT action FROM audit_log WHERE action = 'captain_set_not_employee' AND entity_id = 1"
        ).fetchone()
        assert row is not None

    # Администратор запрашивает сводку -> перевод виден в captain_not_employee_changes
    resp_summary = client.get("/api/admin/summary", headers=admin_headers)
    assert resp_summary.status_code == 200, resp_summary.text
    summary = resp_summary.json()
    assert len(summary["captain_not_employee_changes"]) >= 1
    item = summary["captain_not_employee_changes"][0]
    assert item["athlete_id"] == 1
    assert item["new_status"] == "not_employee"
    assert item["moderator_username"] == "captain"

    # Капитан запрашивает сводку админа -> 403
    resp_cap_sum = client.get("/api/admin/summary", headers=captain_run_headers)
    assert resp_cap_sum.status_code == 403


def test_captain_forbidden_to_edit_athlete_of_foreign_sport(client, imported_url, captain_run_headers):
    # Создаём спортсмена 99, у которого результат только в лыжах (race 99, competition 99)
    with psycopg.connect(imported_url) as conn:
        conn.execute(
            "INSERT INTO athlete (id, display_name, name_key, employee_status) VALUES (99, 'Лыжник Пётр', 'лыжник петр', 'presumed') ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO competition (id, source_id, external_id, name, sport_type) VALUES (99, 1, 'comp_ski', 'Лыжи', 'ski') ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO race (id, competition_id, external_id, name, sport) VALUES (99, 99, 'race_ski', 'Лыжи 50км', 'ski') ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO result (id, race_id, athlete_id, full_name_raw, status) VALUES (99, 99, 99, 'Лыжник Пётр', 'FIN') ON CONFLICT DO NOTHING"
        )

    # Капитан бега пытается отредактировать лыжника -> 403 Forbidden!
    resp = client.patch(
        "/api/admin/athletes/99",
        json={"employee_status": "confirmed"},
        headers=captain_run_headers,
    )
    assert resp.status_code == 403, resp.text
    assert "видам спорта капитана" in resp.json()["detail"]

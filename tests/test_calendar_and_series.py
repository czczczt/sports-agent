"""Тесты для Блока 8: Календарь, планируемые старты, EventSeries и агрегаты прошлых выпусков.

SPEC v1.3 §3.4, §3.5, §5, §8:
1. Planned-старт создаётся админом/капитаном (капитан только по своему виду, иначе 403; обычный юзер 403);
2. Автоподсказка серии по названию+город+сезон требует подтверждения (suggest -> attach);
3. Planned и фактический старт помечаются «возможный дубль», доступен merge;
4. Экран показывает число сотрудников прошлого выпуска и по дистанциям, БЕЗ списков людей
   (строгий тест на отсутствие ФИО и персональных данных в ответе).
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
def captain_ski_headers(imported_url):
    with psycopg.connect(imported_url) as conn:
        conn.execute(
            """
            INSERT INTO app_user (username, email, password_hash, role, status, display_name)
            VALUES ('captain_ski', 'ski@test.ru', 'hash', 'captain', 'active', 'Капитан Лыж')
            ON CONFLICT (username) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO captain_sport (user_id, sport)
            SELECT id, 'ski' FROM app_user WHERE username = 'captain_ski'
            ON CONFLICT DO NOTHING
            """
        )
    return auth_headers("captain_ski", "captain", "Капитан Лыж")


@pytest.fixture
def admin_headers():
    return auth_headers("admin", "admin", "Администратор")


@pytest.fixture
def user_headers():
    return auth_headers("user", "user", "Обычный пользователь")


def test_planned_event_creation_and_permissions(client, imported_url, captain_run_headers, captain_ski_headers, admin_headers, user_headers):
    # 1. Обычный пользователь получает 403
    payload_run = {
        "title": "Зимний пробег 2026",
        "sport": "run",
        "planned_date_start": "2026-12-15",
        "city": "Москва",
        "races": [{"name": "10 км", "distance_km": 10.0}],
    }
    resp = client.post("/api/admin/events/planned", json=payload_run, headers=user_headers)
    assert resp.status_code == 403

    # 2. Капитан лыж пытается создать беговой старт -> 403
    resp = client.post("/api/admin/events/planned", json=payload_run, headers=captain_ski_headers)
    assert resp.status_code == 403
    assert "видов спорта капитана" in resp.json()["detail"]

    # 3. Капитан бега успешно создаёт беговой старт -> 200
    resp = client.post("/api/admin/events/planned", json=payload_run, headers=captain_run_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["title"] == "Зимний пробег 2026"
    assert data["status"] == "planned"
    assert data["sport"] == "run"
    assert len(data["races"]) == 1
    assert data["races"][0]["name_raw"] == "10 км"
    created_id = data["id"]

    # Проверяем запись в audit_log
    with psycopg.connect(imported_url) as conn:
        row = conn.execute(
            "SELECT action, entity, entity_id FROM audit_log WHERE entity = 'competition' AND entity_id = %s ORDER BY id DESC LIMIT 1",
            (created_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "create_planned_event"

    # 4. Администратор может создать старт по любому виду (например, лыжи)
    payload_ski = {
        "title": "Лыжня России 2027",
        "sport": "ski",
        "planned_date_start": "2027-02-10",
        "city": "Яхрома",
        "races": [{"name": "50 км", "distance_km": 50.0}],
    }
    resp = client.post("/api/admin/events/planned", json=payload_ski, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["sport"] == "ski"
    assert resp.json()["status"] == "planned"


def test_series_suggest_and_confirm(client, imported_url, captain_run_headers, captain_ski_headers):
    with psycopg.connect(imported_url) as conn:
        # Создаём серию соревнований
        conn.execute(
            """
            INSERT INTO event_series (id, name, name_norm, city, sport)
            VALUES (101, 'Белые Ночи', 'белые ночи', 'Санкт-Петербург', 'run')
            ON CONFLICT (id) DO NOTHING
            """
        )
        # Создаём старт без серии
        conn.execute(
            """
            INSERT INTO competition (id, source_id, external_id, name, location, sport, status)
            VALUES (201, 1, 'comp_wn_2026', 'Марафон Белые Ночи 2026', 'Санкт-Петербург', 'run', 'planned')
            ON CONFLICT (id) DO NOTHING
            """
        )

    # 1. Автоподсказка серии
    resp = client.get("/api/admin/events/series/suggest?event_id=201", headers=captain_run_headers)
    assert resp.status_code == 200, resp.text
    suggestions = resp.json()
    assert len(suggestions) > 0
    assert any(s["series_id"] == 101 and s["series_name"] == "Белые Ночи" for s in suggestions)

    # До подтверждения серия НЕ привязана
    with psycopg.connect(imported_url) as conn:
        row = conn.execute("SELECT series_id FROM competition WHERE id = 201").fetchone()
        assert row[0] is None

    # 2. Капитан другого вида спорта не может подтвердить привязку -> 403
    attach_payload = {"series_id": 101}
    resp = client.post("/api/admin/events/201/series", json=attach_payload, headers=captain_ski_headers)
    assert resp.status_code == 403

    # 3. Капитан бега подтверждает привязку -> 200
    resp = client.post("/api/admin/events/201/series", json=attach_payload, headers=captain_run_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert resp.json()["series_id"] == 101

    # Проверяем, что в БД series_id теперь проставлен и записан audit_log
    with psycopg.connect(imported_url) as conn:
        row = conn.execute("SELECT series_id FROM competition WHERE id = 201").fetchone()
        assert row[0] == 101

        log_row = conn.execute(
            "SELECT action, entity, entity_id FROM audit_log WHERE entity = 'competition' AND entity_id = 201 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert log_row is not None
        assert log_row[0] == "attach_series"


def test_duplicate_detection_and_merge(client, imported_url, captain_run_headers):
    # Создаём фактический проведённый старт 'done'
    with psycopg.connect(imported_url) as conn:
        conn.execute(
            """
            INSERT INTO competition (id, source_id, external_id, name, location, sport, status, date_begin)
            VALUES (301, 1, 'comp_kazan_done', 'Казанский Марафон 2026', 'Казань', 'run', 'done', '2026-05-10')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, location = EXCLUDED.location, status = 'done'
            """
        )

    # Создаём planned старт с тем же городом и названием
    payload = {
        "title": "Казанский Марафон",
        "sport": "run",
        "planned_date_start": "2026-05-10",
        "city": "Казань",
        "races": [{"name": "42.2 км", "distance_km": 42.2}],
    }
    resp = client.post("/api/admin/events/planned", json=payload, headers=captain_run_headers)
    assert resp.status_code == 200, resp.text
    planned_data = resp.json()
    planned_id = planned_data["id"]

    # Оба старта должны быть помечены как возможные дубли друг друга
    assert planned_data["possible_duplicate_id"] == 301
    with psycopg.connect(imported_url) as conn:
        act_row = conn.execute("SELECT possible_duplicate_id FROM competition WHERE id = 301").fetchone()
        assert act_row[0] == planned_id

    # Запрос кандидатов на дубликат
    resp = client.get(f"/api/admin/events/{planned_id}/duplicates", headers=captain_run_headers)
    assert resp.status_code == 200
    dups = resp.json()
    assert len(dups) == 1
    assert dups[0]["event_id"] == 301

    # Выполняем склейку
    merge_payload = {
        "planned_event_id": planned_id,
        "actual_event_id": 301,
    }
    resp = client.post("/api/admin/events/merge", json=merge_payload, headers=captain_run_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    # После склейки possible_duplicate_id сброшен
    with psycopg.connect(imported_url) as conn:
        p_row = conn.execute("SELECT possible_duplicate_id, status FROM competition WHERE id = %s", (planned_id,)).fetchone()
        a_row = conn.execute("SELECT possible_duplicate_id, status FROM competition WHERE id = 301").fetchone()
        assert p_row[0] is None
        assert a_row[0] is None

        # Проверяем audit_log
        log_row = conn.execute(
            "SELECT action, entity, entity_id FROM audit_log WHERE entity = 'competition' AND entity_id = 301 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert log_row[0] == "merge_events"


def test_past_edition_aggregates_without_athlete_names_or_fio(client, imported_url, captain_run_headers):
    """Экран показывает число сотрудников прошлого выпуска и по дистанциям, без списков людей (тест на отсутствие ФИО)."""
    with psycopg.connect(imported_url) as conn:
        # Серия
        conn.execute(
            """
            INSERT INTO event_series (id, name, name_norm, city, sport)
            VALUES (401, 'Космический полумарафон', 'космический полумарафон', 'Королёв', 'run')
            ON CONFLICT (id) DO NOTHING
            """
        )
        # Прошлый выпуск: 2025 год
        conn.execute(
            """
            INSERT INTO competition (id, source_id, external_id, name, location, sport, status, date_begin, series_id)
            VALUES (501, 1, 'comp_space_2025', 'Космический полумарафон 2025', 'Королёв', 'run', 'done', '2025-04-12', 401)
            ON CONFLICT (id) DO NOTHING
            """
        )
        # Дистанции прошлого выпуска: 21.1 км и 10 км
        conn.execute(
            """
            INSERT INTO race (id, competition_id, external_id, name, sport)
            VALUES (601, 501, 'race_space_21k', '21.1 км', 'run'),
                   (602, 501, 'race_space_10k', '10 км', 'run')
            ON CONFLICT (id) DO NOTHING
            """
        )
        # Атлеты: 2 подтверждённых сотрудника, 1 не сотрудник
        conn.execute(
            """
            INSERT INTO athlete (id, display_name, name_key, first_name, last_name, employee_status)
            VALUES (701, 'Иван Иванов', 'иван иванов', 'Иван', 'Иванов', 'confirmed'),
                   (702, 'Петр Петров', 'петр петров', 'Петр', 'Петров', 'presumed'),
                   (703, 'Сидор Сидоров', 'сидор сидоров', 'Сидор', 'Сидоров', 'not_employee')
            ON CONFLICT (id) DO UPDATE SET employee_status = EXCLUDED.employee_status
            """
        )
        # Результаты прошлого выпуска
        conn.execute(
            """
            INSERT INTO result (id, race_id, bib, full_name_raw, status)
            VALUES (801, 601, '101', 'Иванов Иван', 'FIN'),
                   (802, 601, '102', 'Петров Петр', 'FIN'),
                   (803, 602, '103', 'Иванов Иван', 'FIN'),
                   (804, 602, '104', 'Сидоров Сидор', 'FIN')
            ON CONFLICT (id) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO result_athlete (result_id, athlete_id)
            VALUES (801, 701), (802, 702), (803, 701), (804, 703)
            ON CONFLICT DO NOTHING
            """
        )

        # Новый старт 2026 года в той же серии
        conn.execute(
            """
            INSERT INTO competition (id, source_id, external_id, name, location, sport, status, date_begin, series_id)
            VALUES (502, 1, 'comp_space_2026', 'Космический полумарафон 2026', 'Королёв', 'run', 'planned', '2026-04-12', 401)
            ON CONFLICT (id) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO race (id, competition_id, external_id, name, sport)
            VALUES (603, 502, 'race_space_2026_21k', '21.1 км', 'run')
            ON CONFLICT (id) DO NOTHING
            """
        )

    # 1. Запрашиваем новый старт через GET /api/events/{id}
    resp = client.get("/api/events/502", headers=captain_run_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    past_edition = data.get("past_edition")
    assert past_edition is not None, "Ожидаются агрегаты прошлого выпуска"
    assert past_edition["edition_year"] == 2025
    assert past_edition["edition_title"] == "Космический полумарафон 2025"
    # Всего 2 уникальных сотрудника (701 и 702), 703 не сотрудник и не входит
    assert past_edition["employees_total"] == 2

    # Проверяем разбивку по дистанциям
    dist_counts = {dc["distance_name"]: dc["count"] for dc in past_edition["distance_counts"]}
    assert dist_counts.get("21.1 км") == 2  # 701 и 702
    assert dist_counts.get("10 км") == 1    # только 701 (703 - not_employee)

    # СТРОГАЯ ПРОВЕРКА: Никаких ФИО, имен, списков спортсменов в объекте past_edition!
    past_edition_raw = json.dumps(past_edition, ensure_ascii=False).lower()
    for forbidden_text in ["иванов", "иван", "петров", "петр", "сидоров", "сидор", "athlete_id", "full_name", "first_name", "last_name", "athletes"]:
        assert forbidden_text not in past_edition_raw, f"Персональные данные или списки людей обнаружены в ответе: {forbidden_text}"

    # 2. Проверяем также выдачу в общем списке /api/events
    resp_list = client.get("/api/events?limit=100", headers=captain_run_headers)
    assert resp_list.status_code == 200
    events = resp_list.json()
    ev_502 = next((e for e in events if e["id"] == 502), None)
    assert ev_502 is not None
    assert ev_502.get("past_edition") is not None
    assert ev_502["past_edition"]["employees_total"] == 2

    past_edition_list_raw = json.dumps(ev_502["past_edition"], ensure_ascii=False).lower()
    for forbidden_text in ["иванов", "иван", "петров", "петр", "сидоров", "сидор"]:
        assert forbidden_text not in past_edition_list_raw

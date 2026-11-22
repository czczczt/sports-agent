"""Тесты очереди «не проверен» для топ-N рейтинга (SPEC v1.3 §3.5, §5, §10.4).

Проверяет:
1. Защиту роутеров: только captain и admin.
2. Получение очереди неподтверждённых спортсменов топ-N.
3. Подтверждение статуса сотрудника ('confirmed').
4. Перевод в 'not_employee' с автоматической блокировкой связанной учётки.
5. Запись действий в audit_log.
"""

from __future__ import annotations

import psycopg


def test_verify_queue_unauthorized_and_user_forbidden(client, auth_headers):
    # Неавторизованный запрос
    res = client.get("/api/admin/verify-queue")
    assert res.status_code == 401

    # Обычный пользователь (role: user)
    user_headers = auth_headers("user")
    res_user = client.get("/api/admin/verify-queue", headers=user_headers)
    assert res_user.status_code == 403


def test_verify_queue_list_and_decisions(client, imported_url, auth_headers):
    admin_headers = auth_headers("admin")

    with psycopg.connect(imported_url) as con:
        # Привязываем существующего спортсмена 1 к пользователю user
        con.execute("UPDATE app_user SET athlete_id = 1 WHERE username = 'user'")
        # Убедимся, что спортсмены 1 и 2 имеют статус presumed
        con.execute("UPDATE athlete SET employee_status = 'presumed' WHERE id IN (1, 2)")
        con.commit()

    # 1. Получаем список очереди топ-N
    res = client.get("/api/admin/verify-queue?top_n=10", headers=admin_headers)
    assert res.status_code == 200, res.text
    items = res.json()
    assert len(items) >= 2

    athlete_ids = [item["athlete_id"] for item in items]
    assert 1 in athlete_ids and 2 in athlete_ids

    # 2. Подтверждаем спортсмена 2 ('confirmed')
    res_confirm = client.post(
        "/api/admin/verify-queue/2/decision",
        json={"status": "confirmed", "comment": "Проверен по кадровой системе Пульс"},
        headers=admin_headers,
    )
    assert res_confirm.status_code == 200, res_confirm.text
    confirm_data = res_confirm.json()
    assert confirm_data["success"] is True
    assert confirm_data["new_status"] == "confirmed"

    # Проверяем, что подтверждение убирает спортсмена из очереди (СПЕКА §3.5)
    res_after_confirm = client.get("/api/admin/verify-queue?top_n=10", headers=admin_headers)
    assert res_after_confirm.status_code == 200
    ids_after_confirm = [it["athlete_id"] for it in res_after_confirm.json()]
    assert 2 not in ids_after_confirm, "Подтверждённый спортсмен должен исчезнуть из очереди"
    assert 1 in ids_after_confirm, "Неподтверждённый спортсмен 1 должен остаться в очереди"

    # Проверяем, что подтверждение НЕ убирает спортсмена из рейтинга (СПЕКА §3.5: из рейтинга никого не убираем)
    res_rating = client.get("/api/rating", headers=admin_headers)
    assert res_rating.status_code == 200
    rating_athlete_ids = [r["athlete_id"] for r in res_rating.json()["rows"]]
    assert 2 in rating_athlete_ids, "Подтверждённый спортсмен 2 должен оставаться в рейтинге"
    assert 1 in rating_athlete_ids, "Неподтверждённый спортсмен 1 (presumed) также должен быть в рейтинге"

    # Проверяем, что в БД обновился статус и записан аудит
    with psycopg.connect(imported_url) as con:
        status_row = con.execute("SELECT employee_status FROM athlete WHERE id = 2").fetchone()
        assert status_row[0] == "confirmed"

        audit_row = con.execute(
            "SELECT action, entity, entity_id FROM audit_log WHERE entity = 'athlete' AND entity_id = 2 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert audit_row is not None
        assert audit_row[0] == "verify_employee_status"

    # 3. Переводим спортсмена 1 в 'not_employee' (с проверкой авто-блокировки связанного пользователя)
    res_reject = client.post(
        "/api/admin/verify-queue/1/decision",
        json={"status": "not_employee", "comment": "Не найден в кадровой системе"},
        headers=admin_headers,
    )
    assert res_reject.status_code == 200, res_reject.text
    reject_data = res_reject.json()
    assert reject_data["success"] is True
    assert reject_data["new_status"] == "not_employee"
    assert reject_data["auto_blocked_user"] is True

    # Проверяем, что в БД спортсмен получил not_employee, а связанный пользователь user стал blocked
    with psycopg.connect(imported_url) as con:
        ath_status = con.execute("SELECT employee_status FROM athlete WHERE id = 1").fetchone()
        assert ath_status[0] == "not_employee"

        user_status = con.execute("SELECT status FROM app_user WHERE username = 'user'").fetchone()
        assert user_status[0] == "blocked"

        block_audit = con.execute(
            "SELECT action FROM audit_log WHERE entity = 'app_user' AND action = 'auto_block_not_employee' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert block_audit is not None


def test_verify_queue_top_n_change_and_setting(client, imported_url, auth_headers):
    """Смена N меняет очередь; дефолт берётся из настроек setting (SPEC v1.3 §3.5, §5)."""
    admin_headers = auth_headers("admin")

    # Создаём несколько спортсменов с местами с 1 по 15 в running_athlete_rating
    with psycopg.connect(imported_url) as con:
        # Узнаем текущий период рейтинга
        period = con.execute(
            "SELECT period_start, period_end FROM running_athlete_rating LIMIT 1"
        ).fetchone()
        p_start, p_end = period[0], period[1]

        for i in range(11, 26):
            con.execute(
                "INSERT INTO athlete (id, display_name, name_key, gender, employee_status, is_hidden) VALUES (%s, %s, %s, 'M', 'presumed', false) ON CONFLICT (id) DO UPDATE SET employee_status = 'presumed', gender = 'M'",
                (i, f"Спортсмен {i}", f"спортсмен {i}"),
            )
            con.execute(
                "INSERT INTO running_athlete_rating (athlete_id, formula_version, period_start, period_end, points, best_points, starts_count, rank) VALUES (%s, 'run-v1', %s, %s, %s, %s, 1, %s) ON CONFLICT (athlete_id, formula_version, period_start, period_end) DO UPDATE SET points = EXCLUDED.points, rank = EXCLUDED.rank",
                (i, p_start, p_end, 100 - (i - 10), 100 - (i - 10), i),
            )
        con.commit()

    # При N=10 спортсмен 22 (занимающий 13 место среди мужчин) НЕ попадает в очередь
    res_10 = client.get("/api/admin/verify-queue?top_n=10", headers=admin_headers)
    assert res_10.status_code == 200
    ids_10 = [it["athlete_id"] for it in res_10.json()]
    assert 22 not in ids_10, "Спортсмен на 13 месте не должен попадать в топ-10"

    # При смене N=15 спортсмен 22 ПОПАДАЕТ в очередь (смена N меняет очередь!)
    res_15 = client.get("/api/admin/verify-queue?top_n=15", headers=admin_headers)
    assert res_15.status_code == 200
    ids_15 = [it["athlete_id"] for it in res_15.json()]
    assert 22 in ids_15, "Спортсмен на 13 месте должен попасть в топ-15"

    # Меняем настройку top_n_verify на 20 в таблице setting
    client.patch("/api/admin/settings", json={"key": "top_n_verify", "value": 20}, headers=admin_headers)

    # Запрос без явного top_n теперь берёт 20 из настроек -> спортсмен 22 в очереди
    res_default = client.get("/api/admin/verify-queue", headers=admin_headers)
    assert res_default.status_code == 200
    ids_default = [it["athlete_id"] for it in res_default.json()]
    assert 22 in ids_default, "Без параметра top_n должно использоваться значение 20 из настроек"


def test_get_top_n_setting_fallback_unit():
    import asyncio

    from app.services.rating_service import get_top_n_setting

    class MockSession:
        async def execute(self, query):
            class MockResult:
                def scalar(self):
                    return None
            return MockResult()

    val = asyncio.run(get_top_n_setting(MockSession()))
    assert val == 10



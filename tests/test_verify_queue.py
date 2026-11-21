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

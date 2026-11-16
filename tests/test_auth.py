import unittest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestAuth(unittest.TestCase):
    def test_login_user_success(self):
        resp = client.post("/api/auth/login", json={"username": "user", "password": "user"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["user"]["username"], "user")
        self.assertEqual(data["user"]["role"], "user")
        self.assertEqual(data["user"]["display_name"], "Пользователь")

        # Проверяем получение данных пользователя через me
        token = data["access_token"]
        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 200)
        me_data = me_resp.json()
        self.assertEqual(me_data["username"], "user")
        self.assertEqual(me_data["role"], "user")

    def test_login_admin_success(self):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["username"], "admin")
        self.assertEqual(data["user"]["role"], "admin")
        self.assertEqual(data["user"]["display_name"], "Администратор")

        token = data["access_token"]
        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["role"], "admin")

    def test_login_invalid_credentials(self):
        # Неверный пароль
        resp = client.post("/api/auth/login", json={"username": "user", "password": "wrongpassword"})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Неверный логин или пароль", resp.json()["detail"])

        # Несуществующий пользователь
        resp2 = client.post("/api/auth/login", json={"username": "hacker", "password": "user"})
        self.assertEqual(resp2.status_code, 401)

    def test_me_unauthorized(self):
        resp = client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)

    def test_logout(self):
        login_resp = client.post("/api/auth/login", json={"username": "user", "password": "user"})
        self.assertEqual(login_resp.status_code, 200)
        token = login_resp.json()["access_token"]

        # Вызываем logout
        logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(logout_resp.status_code, 200)

        # Теперь старый токен должен быть отклонён
        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()

from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.main import app
from app.models import UserOut


def test_status_endpoint_unauthorized_returns_401():
    with TestClient(app) as client:
        response = client.get("/api/status")
        assert response.status_code == 401


def test_status_endpoint_authorized_returns_json():
    mock_user = UserOut(
        id=1,
        username="admin",
        role="admin",
        status="active",
        display_name="Администратор",
        athlete_id=None,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with TestClient(app) as client:
            response = client.get("/api/status")
            assert response.status_code == 200
            data = response.json()

            assert "status" in data
            assert "database" in data
            assert "queue" in data
            assert "adapters" in data
            assert "overview" in data
            assert data["database"]["engine"] == "PostgreSQL 16"
            assert isinstance(data["adapters"], list)
    finally:
        app.dependency_overrides.pop(get_current_user, None)

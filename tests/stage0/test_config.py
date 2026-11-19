import pytest
from psycopg.conninfo import conninfo_to_dict

from app.config import Settings, normalize_postgres_url


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
def test_postgres_url_compatible_with_sync_and_async_consumers(scheme):
    encoded = "user%40name:p%40ss%2Fword%25@127.0.0.1:5432/database?application_name=stage0%20test"
    url = f"{scheme}://{encoded}"
    config = Settings(_env_file=None, database_url=url)
    assert config.database_url == f"postgresql://{encoded}"
    parameters = conninfo_to_dict(config.database_url)
    assert parameters["user"] == "user@name"
    assert parameters["password"] == "p@ss/word%"
    assert parameters["application_name"] == "stage0 test"


def test_non_postgres_url_rejected():
    with pytest.raises(ValueError, match="must be a PostgreSQL URL"):
        normalize_postgres_url("sqlite:///running.db")


def test_standalone_parser_normalizes_environment_and_explicit_url(monkeypatch):
    from parser_running import db

    url = "postgresql+asyncpg://agent:p%40ss%2Fword@127.0.0.1/sports_agent"
    expected = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    monkeypatch.setenv("DATABASE_URL", url)
    assert db.database_url() == expected
    received = []
    monkeypatch.setattr(db.psycopg, "connect", lambda dsn: received.append(dsn))
    db.connect(url)
    assert received == [expected]


def test_auth_secret_reads_dotenv_without_exposing_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("AUTH_SECRET_KEY=dotenv-test-key\n", encoding="utf-8")
    config = Settings(_env_file=env_file, database_url="postgresql://localhost/test")
    assert config.auth_secret_key == "dotenv-test-key"
    assert "dotenv-test-key" not in repr(config)

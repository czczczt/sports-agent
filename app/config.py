from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parent.parent


def normalize_postgres_url(value: str) -> str:
    if make_url(value).drivername not in {
        "postgres",
        "postgresql",
        "postgresql+asyncpg",
    }:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL")
    return "postgresql:" + value.split(":", 1)[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = Field(min_length=1, repr=False)
    auth_secret_key: str = Field(default="", repr=False)
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    gigachat_credentials: str = Field(default="", repr=False)
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"
    gigachat_verify_ssl: bool = True

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: str) -> str:
        return normalize_postgres_url(value)


settings = Settings()
DATABASE_URL = settings.database_url
AUTH_SECRET_KEY = settings.auth_secret_key
APP_HOST = settings.app_host
APP_PORT = settings.app_port
GIGACHAT_CREDENTIALS = settings.gigachat_credentials
GIGACHAT_SCOPE = settings.gigachat_scope
GIGACHAT_MODEL = settings.gigachat_model
GIGACHAT_VERIFY_SSL = settings.gigachat_verify_ssl

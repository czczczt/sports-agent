import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные из .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://agent:change-me@127.0.0.1:5432/sports_agent")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# GigaChat
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
GIGACHAT_VERIFY_SSL = os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() in ("true", "1", "yes")

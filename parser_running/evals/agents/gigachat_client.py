"""Минимальный синхронный клиент GigaChat для агента-ремонтника.

Настройки берутся из .env в корне репозитория (sports-agent/.env):
    GIGACHAT_CREDENTIALS   ключ авторизации из личного кабинета (строка base64)
    GIGACHAT_SCOPE         GIGACHAT_API_PERS для физлиц
    GIGACHAT_MODEL         например GigaChat-2-Pro
    GIGACHAT_CA_BUNDLE     (необязательно) путь к корневому сертификату НУЦ Минцифры
    GIGACHAT_VERIFY_SSL    (необязательно) false — отключить проверку сертификата, только для отладки
    GIGACHAT_CACHE         (необязательно) 0 — не использовать кеш ответов

Ответы кешируются в parser_running/data/llm_cache/: одинаковый запрос второй раз не тратит токены,
а демо можно повторить без сети. Папка data/ в git не попадает.

Проверка ключа:
    python agents/gigachat_client.py
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]          # sports-agent/
CACHE_DIR = ROOT / "parser_running" / "data" / "llm_cache"
OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


def _load_env() -> None:
    """Читаем .env без внешних библиотек; уже заданные переменные окружения не перезаписываем."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class GigaChatError(RuntimeError):
    pass


class GigaChat:
    def __init__(self, model: str | None = None, temperature: float = 0.1, timeout: int = 120):
        _load_env()
        self.credentials = os.environ.get("GIGACHAT_CREDENTIALS", "").strip()
        if not self.credentials or self.credentials == "change-me":
            raise GigaChatError(f"Нет GIGACHAT_CREDENTIALS в {ROOT / '.env'}")
        self.scope = os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.model = model or os.environ.get("GIGACHAT_MODEL", "GigaChat-2-Pro")
        self.temperature = temperature
        self.timeout = timeout
        ca = os.environ.get("GIGACHAT_CA_BUNDLE", "").strip()
        self.verify = ca if ca else os.environ.get("GIGACHAT_VERIFY_SSL", "true").lower() != "false"
        self.use_cache = os.environ.get("GIGACHAT_CACHE", "1") != "0"
        self._token, self._token_expires = None, 0.0
        self.tokens_used = 0       # всего токенов за жизнь клиента (без учёта ответов из кеша)
        self.calls = 0             # реальных запросов к API
        self.prompt_tokens = 0     # входящие токены (запросы)
        self.completion_tokens = 0 # исходящие токены (ответы модели)

    # --- авторизация -------------------------------------------------------
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        r = self._post(OAUTH_URL,
                       headers={"Authorization": f"Basic {self.credentials}", "RqUID": str(uuid.uuid4()),
                                "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                       data={"scope": self.scope})
        body = r.json()
        self._token = body["access_token"]
        self._token_expires = body.get("expires_at", 0) / 1000 or time.time() + 25 * 60
        return self._token

    def _post(self, url: str, **kw) -> requests.Response:
        try:
            r = requests.post(url, verify=self.verify, timeout=self.timeout, **kw)
        except requests.exceptions.SSLError as ex:
            raise GigaChatError(
                "Ошибка сертификата. GigaChat использует сертификат НУЦ Минцифры. Варианты: "
                "указать путь к нему в GIGACHAT_CA_BUNDLE (правильно) или временно "
                "GIGACHAT_VERIFY_SSL=false (только для отладки).") from ex
        if r.status_code == 401:
            where = "получение токена (ключ или scope)" if url == OAUTH_URL else "запрос к модели (токен)"
            raise GigaChatError(f"401 на шаге «{where}». Ответ сервера: {r.text[:300]}")
        if r.status_code == 402:
            raise GigaChatError("402: закончились токены для этой модели")
        if r.status_code >= 400:
            raise GigaChatError(f"{r.status_code}: {r.text[:300]}")
        return r

    # --- запрос к модели ---------------------------------------------------
    def chat(self, messages: list[dict]) -> tuple[str, int]:
        """messages: [{"role": "system"|"user"|"assistant", "content": "..."}].
        Возвращает (текст ответа, токены этого запроса; 0 — ответ из кеша)."""
        payload = {"model": self.model, "messages": messages, "temperature": self.temperature}
        key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]
        cache_file = CACHE_DIR / f"{key}.json"
        if self.use_cache and cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))["content"], 0

        for attempt in range(3):
            try:
                r = self._post(CHAT_URL, json=payload,
                               headers={"Authorization": f"Bearer {self._get_token()}", "Accept": "application/json"})
                break
            except GigaChatError as ex:
                # 429 и 5xx — подождать и повторить; остальное сразу наверх
                if attempt == 2 or not str(ex)[:3] in {"429", "500", "502", "503", "504"}:
                    raise
                time.sleep(5 * (attempt + 1))
        body = r.json()
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        self.tokens_used += tokens
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        self.calls += 1
        if self.use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps({"model": self.model, "content": content, "tokens": tokens},
                                             ensure_ascii=False, indent=2), encoding="utf-8")
        return content, tokens


def _diagnose_key() -> None:
    """Проверяем форму ключа, не печатая сам секрет."""
    import base64
    key = os.environ.get("GIGACHAT_CREDENTIALS", "")
    print(f"Длина ключа: {len(key)} символов")
    if key != key.strip() or key.startswith(("'", '"')):
        print("  ВНИМАНИЕ: в ключе пробелы или кавычки по краям")
    if key.lower().startswith("basic"):
        print("  ВНИМАНИЕ: ключ начинается со слова Basic — уберите его, клиент добавляет сам")
    try:
        decoded = base64.b64decode(key.removeprefix("Basic ").strip(), validate=True).decode()
        parts = decoded.split(":")
        ok = len(parts) == 2 and all(len(p) >= 30 for p in parts)
        print(f"  base64: да; внутри «id:секрет»: {'да' if ok else 'НЕТ — похоже, вставлен не тот ключ'}")
    except Exception:  # noqa: BLE001
        print("  base64: НЕТ — похоже, вставлен Client ID или Client Secret, а нужен «Ключ авторизации»")
    proxies = {k: v for k, v in os.environ.items() if k.lower() in ("https_proxy", "http_proxy", "all_proxy")}
    print(f"Прокси в окружении: {proxies or 'нет'}")


if __name__ == "__main__":
    os.environ["GIGACHAT_CACHE"] = "0"   # проверка ключа всегда идёт в сеть
    _load_env()
    _diagnose_key()
    try:
        llm = GigaChat()
        print(f"Модель: {llm.model}, scope: {llm.scope}, проверка сертификата: {llm.verify}")
        text, tokens = llm.chat([{"role": "user", "content": "Ответь одним словом: сколько будет 2+2?"}])
        print(f"Ответ: {text!r}\nТокенов: {tokens}\nКлюч работает.")
    except GigaChatError as ex:
        print(f"Не получилось: {ex}")

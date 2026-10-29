"""GET с кешем на диске (raw-слой для HTML-площадок): data/raw/<source>/<sha1(url)>.html."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import requests

RAW = Path(__file__).parent / "data" / "raw"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
DELAY_S = 0.5

# Журнал обращений: какой ответ (файл кеша) использован. run.py переносит его в таблицу raw,
# чтобы по старту/дистанции и по задаче из очереди находились её сохранённые ответы.
FETCH_LOG: list[dict] = []


def log_fetch(source: str, request_key: str, url: str, path: Path, from_cache: bool) -> None:
    FETCH_LOG.append({"source": source, "request_key": request_key, "url": url, "path": path,
                      "from_cache": from_cache})

_session = requests.Session()
_session.headers.update(UA)


def get(source: str, url: str, cache: bool = True, timeout: int = 60) -> str:
    f = RAW / source / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".html")
    if cache and f.exists():
        log_fetch(source, url, url, f, True)
        return f.read_text(encoding="utf-8")
    for attempt in range(3):
        try:
            time.sleep(DELAY_S)
            r = _session.get(url, timeout=timeout)
            r.raise_for_status()
            break
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))  # E23: runc временами отвечает дольше минуты — даём серверу паузу
    if "charset" not in r.headers.get("Content-Type", "").lower():
        r.encoding = r.apparent_encoding  # без charset requests берёт latin-1 и ломает кириллицу
    if cache:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(r.text, encoding="utf-8")
        log_fetch(source, url, url, f, False)
    return r.text

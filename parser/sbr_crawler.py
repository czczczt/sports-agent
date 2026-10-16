"""Обход biathlonrus.com: сезон -> соревнования -> гонки -> PDF-протоколы.

Сайт отдаёт обычный HTML (Bitrix), JS/Selenium не нужен.
Все скачанные страницы и PDF кешируются в data/raw, повторный запуск сеть не трогает.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://biathlonrus.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (diploma research crawler)"}
DELAY_S = 1.0  # пауза между сетевыми запросами, чтобы не нагружать сайт
RAW = Path(__file__).parent / "data" / "raw"

_session = requests.Session()
_session.headers.update(HEADERS)


@dataclass
class RaceLink:
    race_id: str
    title: str          # текст ссылки на странице соревнования: "Спринт 10 км Мужчины"
    url: str
    competition_url: str


@dataclass
class ProtocolFile:
    race_id: str
    label: str          # "Итоговый протокол", "Стартовый протокол", ...
    url: str


def _cache_path(url: str, suffix: str) -> Path:
    return RAW / (hashlib.sha1(url.encode()).hexdigest()[:16] + suffix)


def fetch(url: str, binary: bool = False) -> bytes:
    path = _cache_path(url, ".bin" if binary else ".html")
    if path.exists():
        return path.read_bytes()
    time.sleep(DELAY_S)
    r = _session.get(url, timeout=60)
    r.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.content


def _soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch(url).decode("utf-8", errors="replace"), "lxml")


def list_competitions(season: str) -> list[str]:
    """URL всех российских соревнований сезона, напр. season='2025-2026'."""
    s = _soup(f"{BASE}/sorevnovaniya/rossiyskie/all/{season}/")
    out = set()
    for a in s.find_all("a", href=True):
        h = a["href"]
        # /sorevnovaniya/rossiyskie/<тип>/<сезон>[_N]/<slug>/ ; страницы-разделы (без slug) отбрасываем
        if re.fullmatch(r"/sorevnovaniya/rossiyskie/(?!all/)[^/]+/[^/]+/[^/]+/", h):
            out.add(urljoin(BASE, h))
    return sorted(out)


def list_races(competition_url: str) -> list[RaceLink]:
    s = _soup(competition_url)
    races = {}
    for a in s.find_all("a", href=True):
        m = re.fullmatch(r"/sorevnovaniya/races/(\d+)/", a["href"])
        if m:
            races[m.group(1)] = RaceLink(m.group(1), a.get_text(" ", strip=True),
                                         urljoin(BASE, a["href"]), competition_url)
    return list(races.values())


def list_protocols(race: RaceLink) -> list[ProtocolFile]:
    """Файлы на странице гонки. Тип определяем по подписи ссылки:
    в старых сезонах имена файлов — хеши, и по имени тип не понять."""
    s = _soup(race.url)
    files = {}
    for a in s.find_all("a", href=True):
        h = a["href"]
        if not h.lower().endswith((".pdf", ".xls", ".xlsx")):
            continue
        label = a.get_text(" ", strip=True)
        if label in ("Открыть", "Скачать"):   # дубли ссылки рядом с подписью
            continue
        files.setdefault(urljoin(BASE, h), label)
    return [ProtocolFile(race.race_id, lbl, url) for url, lbl in files.items()]


def final_protocol(files: list[ProtocolFile]) -> ProtocolFile | None:
    """Итоговый протокол гонки. Варианты вроде 'Итоговый протокол Альфа-Банк Кубка России'
    (зачёт кубка) пропускаем — берём ровно 'Итоговый протокол'."""
    exact = [f for f in files if f.label.strip().lower() == "итоговый протокол"]
    if exact:
        return exact[0]
    loose = [f for f in files if f.label.lower().startswith("итоговый протокол")]
    return loose[0] if loose else None

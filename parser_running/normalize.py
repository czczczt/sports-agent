"""Нормализация: время, дистанция -> зачётный норматив ТЗ, пол."""
from __future__ import annotations

import re

# Зачётные дистанции ТЗ (м). 24 часа — отдельно (результат в км, а не во времени).
NORM_DISTANCES_M = {
    "60m": 60, "100m": 100, "200m": 200, "400m": 400, "800m": 800, "1000m": 1000, "1500m": 1500,
    "1mile": 1609, "3000m": 3000, "5000m": 5000, "10000m": 10000,
    "half_marathon": 21097, "marathon": 42195, "100km": 100000,
}
# Допуск по длине: решение заказчика ещё не получено (вопрос 5 в ТЗ), пока ±2%.
DISTANCE_TOLERANCE = 0.02


def to_seconds(s: str | None) -> float | None:
    """'01:03:24' / '08:38' / '1:02:03.4' / '45.6' -> секунды. Пусто/мусор -> None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace(",", ".")
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}(\.\d+)?", s):
        return None
    total = 0.0
    for p in s.split(":"):
        total = total * 60 + float(p)
    return total


RU_MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
             "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}


def ru_date(text: str | None) -> str | None:
    """'26 сентября 2026, Москва' -> '2026-09-26'. Берём первую дату вида «день месяц год»."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", text.lower())
    if not m:
        return None
    # «ма» (мая) проверяем последним, чтобы не перехватить «март»
    month = next((n for stem, n in sorted(RU_MONTHS.items(), key=lambda kv: -len(kv[0]))
                  if m.group(2).startswith(stem)), None)
    return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}" if month else None


def km_from_name(name: str | None) -> float | None:
    """'10 км - любители' -> 10.0, '21,1 км' -> 21.1, '1.8km' -> 1.8; нет числа с км -> None."""
    if not name:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:км|km)\b", name.lower())
    return float(m.group(1).replace(",", ".")) if m else None


def infer_place_by(rows: list[dict]) -> str:
    """Для площадок, которые не сообщают, по какому времени места (runc, grom):
    берём то время, с которым порядок мест согласован; если ни одно — 'chip' (проверка 5 это покажет)."""
    fin = sorted((r for r in rows if r["status"] == "FIN" and r.get("place_abs")), key=lambda r: r["place_abs"])
    for key, label in (("chip_time_s", "chip"), ("gun_time_s", "gun")):
        t = [r.get(key) for r in fin]
        if t and None not in t and t == sorted(t):
            return label
    return "chip"


def norm_distance(distance_m: int | None) -> str | None:
    """Ближайшая зачётная дистанция в пределах допуска, иначе None (старт не зачётный)."""
    if not distance_m:
        return None
    best = min(NORM_DISTANCES_M.items(), key=lambda kv: abs(kv[1] - distance_m))
    return best[0] if abs(best[1] - distance_m) <= best[1] * DISTANCE_TOLERANCE else None


def km_to_m(km) -> int | None:
    try:
        v = float(km)
    except (TypeError, ValueError):
        return None
    return round(v * 1000) if v > 0 else None


GENDER_RR = {0: "M", 1: "F"}  # RR API: gender 0 = Мужчины, 1 = Женщины (проверяется в checks)
# RR API: enum из JS сайта {Finish:0, DNF:1, DSQ:2, DNS:3, NC:4, LAP:5}; NC — не уложился в лимит
STATUS_RR = {0: "FIN", 1: "DNF", 2: "DSQ", 3: "DNS", 4: "NC", 5: "LAP"}

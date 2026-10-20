"""Коннектор grom.place (серверный HTML + JSON во Vue-атрибутах). Разведка — SOURCES.md.

Список стартов: /?sort=past&page=N -> /results/<slug>
Старт:          <title> «Результаты по соревнованию<Название> | grom.place», дата в тексте,
                дисциплины: /results/<slug>/discipline/<имя>
Протокол:       атрибут :initial-rows — JSON всех строк (данные хронометража RaceResult).
                Колонки ColumnDataK меняются от гонки к гонке, ищем их по ColumnNameK.
"""
from __future__ import annotations

import html
import json
import re
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

import http_cache
from normalize import infer_place_by, km_from_name, ru_date, to_seconds

BASE = "https://grom.place"
NOT_RUN = re.compile(r"swim|bike|плав|велос|\bT1\b|\bT2\b", re.I)  # признаки триатлона/дуатлона в колонках


class GromConnector:
    name, base_url, platform, parse_method = "grom", BASE, "grom", "html"

    def competitions(self, limit: int, skip: int = 0) -> list[dict]:
        slugs, page = [], 1
        while len(slugs) < skip + limit:
            try:
                h = http_cache.get(self.name, f"{BASE}/?sort=past&page={page}")
            except requests.RequestException:  # E29: страница списка не ответила — работаем с тем, что собрали
                break
            found = [s for s in dict.fromkeys(re.findall(r'href="https://grom\.place/results/([^"/?#]+)"', h))
                     if s not in slugs]
            if not found:
                break
            slugs += found
            page += 1
        return [{"external_id": s, "code": s, "url": f"{BASE}/results/{s}"} for s in slugs[skip: skip + limit]]

    def races(self, comp: dict) -> list[dict]:
        h = http_cache.get(self.name, comp["url"])
        s = BeautifulSoup(h, "lxml")
        title = s.title.get_text(strip=True) if s.title else ""
        m = re.search(r"соревнованию\s*(.+?)\s*\|", title)
        comp.update(title=m.group(1) if m else comp["code"], date_begin=ru_date(s.get_text(" ", strip=True)),
                    sport="run")
        out = []
        for d in dict.fromkeys(re.findall(rf'href="{BASE}/results/{re.escape(comp["code"])}/discipline/([^"/]+)"', h)):
            name = unquote(d)
            out.append({"external_id": name, "name_raw": name, "distance_km": km_from_name(name),
                        "race_type": "individual", "place_by": "chip", "_path": d})
        return out

    def results(self, comp: dict, race: dict) -> tuple[list[dict], int | None]:
        h = http_cache.get(self.name, f"{comp['url']}/discipline/{race['_path']}")
        m = re.search(r':initial-rows="([^"]*)"', h)
        data = json.loads(html.unescape(m.group(1))) if m else []
        col_names = {v for r in data[:50] for k, v in r.items() if k.startswith("ColumnName") and isinstance(v, str)}
        race["sport"] = "triathlon" if any(NOT_RUN.search(n) for n in col_names) else "run"
        if any(r.get("Relay") == "Yes" for r in data):
            race["race_type"] = "relay"
        rows = [self._row(r) for r in data]
        race["place_by"] = infer_place_by(rows)
        race["is_final"] = None
        return rows, None  # площадка не заявляет число участников


    @staticmethod
    def _row(r: dict) -> dict:
        by_name = {r.get(f"ColumnName{i}"): r.get(f"ColumnData{i}") for i in range(1, 60) if f"ColumnName{i}" in r}
        chip = to_seconds(str(by_name.get("Chip Time") or r.get("Time") or "")) or None
        gun = to_seconds(str(by_name.get("Gun Time") or "")) or None
        finished = bool(r.get("Finished"))
        place = _rank(by_name.get("Место среди всех/всего"))
        dob = str(r.get("DateOfBirth") or "")
        gender = {"M": "M", "F": "F", "W": "F"}.get(str(r.get("Gender")).upper())
        if gender is None:  # E25: пол пустой — берём из возрастной группы «Male 25-29» / «Female …»
            ag = str(r.get("AgeGroup") or "").lower()
            gender = "F" if ag.startswith(("female", "жен", "ж")) else "M" if ag.startswith(("male", "муж", "м")) else None
        # E24: финишировал, но место «-1/-1» — вне зачёта
        status = ("FIN" if place else "NC") if finished else ("DNF" if chip or gun else "DNS")
        return {
            "external_participant_id": str(r.get("Bib")), "bib": r.get("Bib") if isinstance(r.get("Bib"), int) else None,
            # E26: «N.N.» с фамилией = номеру — чип без участника; место занимает, но человека нет
            "full_name_raw": None if r.get("Firstname") == "N.N." else
            " ".join(x for x in (r.get("Lastname"), r.get("Firstname")) if x) or None,
            "gender": gender,
            "birth_year": int(dob[:4]) if dob[:4].isdigit() else None,
            "club_raw": (r.get("Club") or "").strip() or None, "age_group": r.get("AgeGroup") or None,
            # не финишировал: есть хоть одно время — сошёл, нет ничего — не стартовал
            "status": status,
            "place_abs": place if status == "FIN" else None,
            "place_gender": _rank(by_name.get("Место по полу/всего")) if status == "FIN" else None,
            "chip_time_s": chip if finished else None, "gun_time_s": gun if finished else None,
        }


def _rank(v) -> int | None:
    """'1/1390' -> 1; '-1/-1' (вне зачёта) -> None."""
    m = re.match(r"\s*(\d+)\s*/", str(v or ""))
    return int(m.group(1)) if m else None

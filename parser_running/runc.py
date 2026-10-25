"""Коннектор results.runc.run (серверный HTML). Разведка — SOURCES.md.

Список стартов: /races/ -> /event/<код>/overview/
Старт:          h1 = название, .header-results-race__date = «26 сентября 2026, Москва»,
                дистанции = .results-distances-nav a (…/distance/<id>/)
Протокол:       /event/<код>/finishers/distance/<id>/page/<N>/page_size/1000/
                (вариант с `common/` — время от общего старта; по умолчанию — личное, места по нему)
В протоколе только финишёры; строка: место, ФИО, «Страна, М34», номер, темп, результат.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

import http_cache
from normalize import infer_place_by, km_from_name, ru_date, to_seconds

BASE = "https://results.runc.run"
PAGE = 1000
STATUS_WORDS = {"DNF": "DNF", "DNS": "DNS", "DSQ": "DSQ", "DQ": "DSQ", "СОШЕЛ": "DNF", "СОШЁЛ": "DNF", "ДИСКВ": "DSQ"}


class RuncConnector:
    name, base_url, platform, parse_method = "runc", BASE, "runc", "html"

    def _soup(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(http_cache.get(self.name, url), "lxml")

    def competitions(self, limit: int, skip: int = 0) -> list[dict]:
        s = self._soup(f"{BASE}/races/")
        codes = []
        for a in s.find_all("a", href=True):
            m = re.search(r"/event/([^/]+)/overview/", a["href"])
            if m and m.group(1) not in codes:
                codes.append(m.group(1))
        # список идёт по алфавиту; берём свежие — по году в конце кода
        year = lambda c: int(m.group(1)) if (m := re.search(r"(20\d\d)", c)) else 0
        codes.sort(key=year, reverse=True)
        return [{"external_id": c, "code": c, "sport": "run", "url": f"{BASE}/event/{c}/overview/"}
                for c in codes[skip: skip + limit]]

    def races(self, comp: dict) -> list[dict]:
        s = self._soup(comp["url"])
        h1 = s.select_one("h1")
        date_txt = s.select_one(".header-results-race__date")
        date_txt = date_txt.get_text(" ", strip=True) if date_txt else ""
        comp.update(title=h1.get_text(" ", strip=True) if h1 else comp["code"], date_begin=ru_date(date_txt),
                    place=date_txt.split(",", 1)[1].strip() if "," in date_txt else None)
        out = []
        for a in s.select(".results-distances-nav a[href]"):
            m = re.search(r"/distance/(\d+)/", a["href"])
            if m:
                name = a.get_text(" ", strip=True)
                out.append({"external_id": m.group(1), "name_raw": name, "distance_km": km_from_name(name),
                            "race_type": "relay" if "эстафет" in name.lower() else "individual",
                            "place_by": "chip", "sport": "run"})
        return out

    def results(self, comp: dict, race: dict) -> tuple[list[dict], int | None]:
        rows, total = self._pages(comp, race, common=False)
        # E22: у элиты места по времени от общего старта — берём его из вида `common/` и сверяем порядок
        gun = {r["external_participant_id"]: r["chip_time_s"] for r in self._pages(comp, race, common=True)[0]}
        for r in rows:
            r["gun_time_s"] = gun.get(r["external_participant_id"])
        race["place_by"] = infer_place_by(rows)
        race["is_final"] = None  # площадка не сообщает
        return rows, total

    def _pages(self, comp: dict, race: dict, common: bool) -> tuple[list[dict], int | None]:
        rows, total, page = [], None, 1
        while True:
            url = (f"{BASE}/event/{comp['code']}/finishers/distance/{race['external_id']}/"
                   f"{'common/' if common else ''}page/{page}/page_size/{PAGE}/")
            s = self._soup(url)
            if total is None:
                cnt = s.select_one(".results-top__heading-count")
                total = int(re.sub(r"\D", "", cnt.get_text())) if cnt and re.search(r"\d", cnt.get_text()) else None
            items = s.select("a.results-table__values")
            for it in items:
                txt = lambda cls: (e.get_text(" ", strip=True) if (e := it.select_one(cls)) else None)
                country, gender, age = parse_country_group(txt(".results-table__values-item-country"))
                result = txt(".results-table__col-result")
                # E20: в «финишёрах» в конце идут сошедшие: место «-», в колонке результата — статус
                status = "FIN" if to_seconds(result) is not None else STATUS_WORDS.get((result or "").upper(), "DNF")
                rows.append({
                    "external_participant_id": it.get("href"), "bib": _int(txt(".results-table__col-number")),
                    "full_name_raw": " ".join((txt(".results-table__values-item-name") or "").split()) or None,
                    "gender": gender, "age": age, "country": country, "status": status,
                    "place_abs": _int(txt(".results-table__values-item-place")) if status == "FIN" else None,
                    "chip_time_s": to_seconds(result),
                })
            if len(items) < PAGE:
                break
            page += 1
        return rows, total


def parse_country_group(s: str | None) -> tuple[str | None, str | None, int | None]:
    """'Россия, М34' -> ('Россия', 'M', 34); 'Кения, Ж29' -> ('Кения', 'F', 29)."""
    if not s:
        return None, None, None
    country, _, grp = s.rpartition(",")
    m = re.match(r"\s*([МЖMF])\s*(\d+)?", grp)
    if not m:
        return s.strip() or None, None, None
    gender = "M" if m.group(1) in "МM" else "F"
    return country.strip() or None, gender, int(m.group(2)) if m.group(2) else None


def _int(s: str | None) -> int | None:
    return int(s) if s and s.strip().isdigit() else None

"""Коннектор к платформе RussiaRunning (RR): russiarunning, timerman, legkovrace, pionercup.

JSON API, формат тел запросов — см. SOURCES.md. Ответы кешируются в data/raw/<source>/,
повторный прогон сеть не трогает.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import requests

if __package__:
    from .http_cache import log_fetch
    from .normalize import GENDER_RR, STATUS_RR, is_sber_club, to_seconds
    from .request_pacing import pace_request
else:
    from http_cache import log_fetch
    from normalize import GENDER_RR, STATUS_RR, is_sber_club, to_seconds
    from request_pacing import pace_request

SOURCES = {
    "russiarunning": "https://results.russiarunning.com/api",
    "timerman": "https://timerman.org/results/api",
    "legkovrace": "https://results.legkovrace.ru/api",
    "pionercup": "https://results.pionercup.ru/api",
}
RAW = Path(__file__).parent / "data" / "raw"
DELAY_S = 0.5
PAGE = 100  # максимум, который принимает API (Page.Take 1..100)


class RRClient:
    def __init__(self, name: str, *, cache: bool = True):
        self.name, self.base = name, SOURCES[name]
        self.cache = cache
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0 (diploma research crawler)"

    def _call(self, method: str, path: str, body: dict | None = None, params: dict | None = None,
              cache: bool = True):
        cache = cache and self.cache
        key = hashlib.sha1(json.dumps([method, path, body, params], sort_keys=True).encode()).hexdigest()[:20]
        f = RAW / self.name / f"{key}.json"
        req = json.dumps([method, path, body, params], sort_keys=True, ensure_ascii=False)
        if cache and f.exists():
            log_fetch(self.name, req, self.base + path, f, True)
            return json.loads(f.read_text(encoding="utf-8"))
        for attempt in range(3):  # E2: разовые таймауты
            try:
                pace_request(self.base, DELAY_S)
                r = self.s.request(method, self.base + path, json=body, params=params, timeout=60)
                r.raise_for_status()
                break
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise
        data = r.json()
        if cache:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            log_fetch(self.name, req, self.base + path, f, False)
        return data

    def list_events(self, skip: int, take: int) -> list[dict]:
        return self.event_catalog_page(skip, take)["list"]

    def event_catalog_page(self, skip: int, take: int) -> dict:
        # список меняется со временем — не кешируем
        return self._call("POST", "/events/list", {"page": {"skip": skip, "take": take}, "language": "ru"},
                          cache=False)

    def get_event(self, code: str) -> dict:
        return self._call("POST", "/events/get", {"eventCode": code, "language": "ru"})

    def race_options(self, race_id: str) -> dict:
        return self._call("GET", "/results/options/get", params={"RaceId": race_id, "Language": "ru"})

    def individual_results(self, event_id: str, race_id: str, club_code: str | None = None) -> tuple[list[dict], int]:
        """Все страницы протокола + totalCount, который заявляет площадка.
        club_code — фильтр по клубу (ключ `clubCode` из JS сайта): находит и тех, у кого в протоколе
        поле клуба пустое (E35)."""
        out, total, skip = [], None, 0
        flt = {"clubCode": club_code} if club_code else {}
        while total is None or skip < total:
            # E5: page = {skip, take<=100}, поле search не передаём
            j = self._call("POST", "/results/individual/get",
                           {"eventId": event_id, "raceId": race_id, "page": {"skip": skip, "take": PAGE},
                            "filter": flt, "isStagesOn": False, "language": "ru"})
            claimed = j["totalCount"]
            if isinstance(claimed, bool) or not isinstance(claimed, int) or claimed < 0:
                raise ValueError("Invalid RR totalCount")
            if total is not None and total != claimed:
                raise ValueError("RR totalCount changed during pagination")
            total = claimed
            if not isinstance(j["results"], list) or len(j["results"]) > PAGE:
                raise ValueError("Invalid RR protocol page")
            out += j["results"]
            if len(out) > total or (not j["results"] and len(out) < total):
                raise ValueError("Incomplete RR protocol")
            if not j["results"]:
                break
            skip += PAGE
        if len(out) != total:
            raise ValueError("Incomplete RR protocol")
        return out, total


class RRConnector:
    """Контракт коннектора (spec 3.2) поверх RRClient: отдаёт нормализованные словари для store.py."""
    platform, parse_method = "rr_api", "api"

    def __init__(self, name: str):
        self.name, self.base_url = name, SOURCES[name]
        self.cli = RRClient(name)

    def competitions(self, limit: int, skip: int = 0) -> list[dict]:
        out = []
        while len(out) < limit:
            batch = self.cli.list_events(skip, 50)
            if not batch:
                break
            out += [e for e in batch if e.get("disciplineCode") == "run"]
            skip += 50
        return [{"external_id": e["id"], "code": e["code"], "title": e["title"], "date_begin": e.get("beginDate"),
                 "date_end": e.get("endDate"), "place": e.get("place"), "address": e.get("address"), "sport": "run",
                 "url": f"{self.base_url.removesuffix('/api')}/event/{e['code']}/results"} for e in out[:limit]]

    def races(self, comp: dict, event: dict | None = None) -> list[dict]:
        ev = self.cli.get_event(comp["code"]) if event is None else event
        comp["_rr_event_id"] = ev["id"]
        return [{"external_id": r["id"], "name_raw": r.get("name"), "distance_km": r.get("distance"),
                 "race_type": "relay" if r.get("isRelay") else "individual",
                 # RR enum {Individual:0, Absolute:1}: места по чистому или по грязному времени (E12)
                 "place_by": "gun" if r.get("resultsCalculationMethod") == 1 else "chip",
                 "timing_type": r.get("timingType"), "sport": r.get("disciplineCode"),
                 # клубы Сбера на этой дистанции — из списка клубов забега (filters.raceClubs)
                 "_sber_clubs": [(c.get("code"), c.get("title")) for c in (r.get("filters") or {}).get("raceClubs") or []
                                 if is_sber_club(c.get("title"), c.get("code"))]}
                for r in ev["races"]]

    def results(self, comp: dict, race: dict, *, options: dict | None = None) -> tuple[list[dict], int]:
        """HTTPError 404 = протокола на платформе нет (E13) — пробрасываем, решает run.py."""
        if options is None:
            options = self.cli.race_options(race["external_id"])
        race["is_final"] = options.get("isFinalProtocol") is True
        rows, total = self.cli.individual_results(comp["_rr_event_id"], race["external_id"])
        out = []
        for r in rows:
            fin = r.get("status") == 0
            out.append({
                "external_participant_id": r.get("participantId"), "bib": r.get("number"),
                "full_name_raw": r.get("fullName"), "gender": GENDER_RR.get(r.get("gender")), "age": r.get("age"),
                "birth_year": r.get("birthYear"),
                "country": r.get("countryCode"), "region": r.get("region"), "city": r.get("city"),
                "club_raw": (r.get("raceClub") or "").strip() or None,
                "club_source": "protocol" if (r.get("raceClub") or "").strip() else None,
                "status": STATUS_RR.get(r.get("status"), f"RR_{r.get('status')}"),
                # E7: отрицательные позиции = скрыты; E10: у нефинишёров «место» — номер в списке
                "place_abs": r.get("position") if fin and (r.get("position") or 0) > 0 else None,
                "place_gender": next((r[k] for k in ("individualGenderPosition", "absoluteGenderPosition")
                                      if fin and (r.get(k) or 0) > 0), None),
                "age_group": r.get("genderAgeNominationName"),
                "place_age_group": next((r[k] for k in ("individualGenderAgePosition", "absoluteGenderAgePosition")
                                         if fin and (r.get(k) or 0) > 0), None),
                "chip_time_s": to_seconds(r.get("individualResult")), "gun_time_s": to_seconds(r.get("absoluteResult")),
                "official_time_s": (to_seconds(r.get("timeResult"))
                                    if race.get("sport") == "ski-biathlon" and fin else None),
            })
        self._mark_sber_by_filter(comp, race, out)
        return out, total

    def _mark_sber_by_filter(self, comp: dict, race: dict, rows: list[dict]) -> None:
        """E35: фильтр clubCode находит участников клуба, у которых в протоколе клуб не показан.
        Таким строкам ставим клуб из фильтра и помечаем club_source = 'filter'."""
        by_pid = {r["external_participant_id"]: r for r in rows}
        found = only_filter = 0
        for code, title in race.get("_sber_clubs", []):
            members, _ = self.cli.individual_results(comp["_rr_event_id"], race["external_id"], club_code=code)
            for m in members:
                row = by_pid.get(m.get("participantId"))
                if row is None:
                    continue
                found += 1
                if not row["club_raw"]:
                    row["club_raw"], row["club_source"] = title or code, "filter"
                    only_filter += 1
        race["_sber_found"], race["_sber_only_filter"] = found, only_filter

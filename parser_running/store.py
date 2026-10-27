"""Общая часть для всех площадок: запись в БД и проверки на нормализованных строках.

Коннектор площадки отдаёт три вида словарей (контракт — docs/parser-db-spec.md, 3.2):
  competition: external_id, code, title, date_begin, date_end, place, address, sport, url
  race:        external_id, name_raw, distance_km, race_type, place_by, timing_type, is_final, total_count
  row:         ключи RESULT_FIELDS (всё уже нормализовано: секунды, M/F, FIN/DNF/...)
"""
from __future__ import annotations

import sqlite3

from normalize import km_to_m, norm_distance

STATUSES = {"FIN", "DNF", "DSQ", "DNS", "NC", "LAP"}
RESULT_FIELDS = ("external_participant_id", "bib", "full_name_raw", "gender", "age", "birth_year", "country",
                 "region", "city", "club_raw", "club_source", "status", "place_abs", "place_gender", "age_group",
                 "chip_time_s", "gun_time_s")


def save_competition(con: sqlite3.Connection, src: int, c: dict) -> int:
    con.execute("""INSERT INTO event(source_id, external_id, code, title, date_begin, date_end, place, address,
                   sport, url) VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(source_id, external_id) DO UPDATE SET title=excluded.title,
                   date_begin=excluded.date_begin, place=excluded.place, url=excluded.url""",
                (src, c["external_id"], c.get("code"), c.get("title"), c.get("date_begin"), c.get("date_end"),
                 c.get("place"), c.get("address"), c.get("sport"), c.get("url")))
    return con.execute("SELECT id FROM event WHERE source_id=? AND external_id=?",
                       (src, c["external_id"])).fetchone()[0]


def save_race(con: sqlite3.Connection, event_id: int, r: dict) -> int:
    dist_m = km_to_m(r.get("distance_km"))
    # E21: не INSERT OR REPLACE — он удаляет строку, на которую уже ссылаются результаты (FK)
    con.execute("""INSERT INTO race(event_id, external_id, name_raw, distance_km_raw, distance_m,
                   norm_distance, race_type, place_by, is_final_protocol, total_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(event_id, external_id) DO UPDATE SET name_raw=excluded.name_raw,
                   distance_km_raw=excluded.distance_km_raw, distance_m=excluded.distance_m,
                   norm_distance=excluded.norm_distance, race_type=excluded.race_type, place_by=excluded.place_by,
                   is_final_protocol=excluded.is_final_protocol, total_count=excluded.total_count""",
                (event_id, r["external_id"], r.get("name_raw"), r.get("distance_km"), dist_m, norm_distance(dist_m),
                 r.get("race_type", "individual"), r["place_by"], int(bool(r.get("is_final"))), r.get("total_count")))
    return con.execute("SELECT id FROM race WHERE event_id=? AND external_id=?",
                       (event_id, r["external_id"])).fetchone()[0]


def save_results(con: sqlite3.Connection, race_id: int, rows: list[dict]) -> None:
    con.execute("DELETE FROM result WHERE race_id=?", (race_id,))  # протокол перезаписывается целиком
    for r in rows:  # откуда клуб: из протокола (по умолчанию) или из фильтра площадки (E35)
        r.setdefault("club_source", "protocol" if r.get("club_raw") else None)
    con.executemany(f"INSERT INTO result(race_id, {', '.join(RESULT_FIELDS)}) "
                    f"VALUES (?, {', '.join('?' * len(RESULT_FIELDS))})",
                    [(race_id, *(r.get(k) for k in RESULT_FIELDS)) for r in rows])


def checks(rows: list[dict], total: int | None, place_by: str) -> dict[str, bool]:
    """Инварианты протокола (spec, раздел 6). place_by — по какому времени площадка дала места."""
    fin = [r for r in rows if r["status"] == "FIN"]
    places = [r["place_abs"] for r in fin]
    times = [r["chip_time_s"] if place_by == "chip" else r["gun_time_s"] for r in fin]
    out = {
        "записей_как_заявлено": total is None or len(rows) == total,
        # анонимные строки (без ФИО, E26) пола не имеют — их не считаем
        "пол_известен": all(r["gender"] in ("M", "F") for r in rows if r.get("full_name_raw")),
        "у_финишёров_есть_время": bool(fin) and all(t is not None for t in times),
        "места_по_порядку": all(p is not None for p in places) and places == sorted(places),
        "статусы_известны": all(r["status"] in STATUSES for r in rows),
    }
    out["время_растёт_с_местом"] = out["у_финишёров_есть_время"] and out["места_по_порядку"] and \
        [t for _, t in sorted(zip(places, times))] == sorted(times)
    return out

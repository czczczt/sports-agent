"""Общая часть для всех площадок: запись в БД и проверки на нормализованных строках.

Коннектор площадки отдаёт три вида словарей (контракт — docs/parser-db-spec.md, 3.2):
  competition: external_id, code, title, date_begin, date_end, place, address, sport, url
  race:        external_id, name_raw, distance_km, race_type, place_by, timing_type, is_final, total_count
  row:         ключи RESULT_FIELDS (всё уже нормализовано: секунды, M/F, FIN/DNF/...)
Имена ключей коннектора и колонок БД различаются (title -> name, place_abs -> position и т. п.):
коннекторы не меняются, сопоставление — здесь.
"""
from __future__ import annotations

import hashlib
import re

import psycopg

from normalize import is_sber_club, km_to_m, norm_distance

STATUSES = {"FIN", "DNF", "DSQ", "DNS", "NC", "LAP"}
RESULT_FIELDS = ("external_participant_id", "bib", "full_name_raw", "gender", "age", "birth_year", "country",
                 "region", "city", "club_raw", "club_source", "status", "place_abs", "place_gender", "age_group",
                 "chip_time_s", "gun_time_s")
RESULT_COLUMNS = ("external_participant_id", "bib", "full_name_raw", "gender", "age", "birth_year", "country",
                  "region", "city", "club_raw", "club_source", "status", "position", "position_gender", "age_group",
                  "chip_time_s", "gun_time_s")


def to_date(s: str | None) -> str | None:
    """'2026-08-29T08:12:00' / '2026-08-29' -> '2026-08-29'; иначе None."""
    return s[:10] if s and re.match(r"\d{4}-\d\d-\d\d", s) else None


def save_competition(con: psycopg.Connection, src: int, c: dict) -> int:
    return con.execute("""INSERT INTO competition(source_id, external_id, code, name, date_begin, date_end, location,
                          address, sport_type, source_url) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                          ON CONFLICT (source_id, external_id) DO UPDATE SET name = excluded.name,
                          date_begin = excluded.date_begin, date_end = excluded.date_end, location = excluded.location,
                          source_url = excluded.source_url, fetched_at = now()
                          RETURNING id""",
                       (src, str(c["external_id"]), c.get("code"), c.get("title"), to_date(c.get("date_begin")),
                        to_date(c.get("date_end")), c.get("place"), c.get("address"), c.get("sport"),
                        c.get("url"))).fetchone()[0]


def save_race(con: psycopg.Connection, competition_id: int, r: dict) -> int:
    dist_m = km_to_m(r.get("distance_km"))
    # E21: не «удалить и вставить» — на дистанцию уже ссылаются результаты (FK)
    return con.execute("""INSERT INTO race(competition_id, external_id, name, distance_km_raw, distance_m,
                          distance_type, race_type, place_by, timing_type, is_final_protocol, total_count)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                          ON CONFLICT (competition_id, external_id) DO UPDATE SET name = excluded.name,
                          distance_km_raw = excluded.distance_km_raw, distance_m = excluded.distance_m,
                          distance_type = excluded.distance_type, race_type = excluded.race_type,
                          place_by = excluded.place_by, timing_type = excluded.timing_type,
                          is_final_protocol = excluded.is_final_protocol, total_count = excluded.total_count
                          RETURNING id""",
                       (competition_id, str(r["external_id"]), r.get("name_raw"), r.get("distance_km"), dist_m,
                        norm_distance(dist_m), r.get("race_type", "individual"), r["place_by"], r.get("timing_type"),
                        bool(r.get("is_final")), r.get("total_count"))).fetchone()[0]


def club_ids(con: psycopg.Connection, names: set[str]) -> dict[str, int]:
    """Справочник клубов: новые названия добавляются, признак Сбера ставит детектор (SPEC §8.1)."""
    if not names:
        return {}
    con.cursor().executemany(
        "INSERT INTO club(name_raw, name_normalized, is_sber) VALUES (%s, %s, %s) ON CONFLICT (name_raw) DO NOTHING",
        [(n, " ".join(n.lower().replace("ё", "е").split()), is_sber_club(n)) for n in sorted(names)])
    return dict(con.execute("SELECT name_raw, id FROM club WHERE name_raw = ANY(%s)", (list(names),)).fetchall())


def save_results(con: psycopg.Connection, race_id: int, rows: list[dict], raw_id: int | None = None) -> None:
    con.execute("DELETE FROM result WHERE race_id = %s", (race_id,))  # протокол перезаписывается целиком
    for r in rows:  # откуда клуб: из протокола (по умолчанию) или из фильтра площадки (E35)
        r.setdefault("club_source", "protocol" if r.get("club_raw") else None)
    clubs = club_ids(con, {r["club_raw"] for r in rows if r.get("club_raw")})
    cols = ("race_id", "raw_id", "club_id", *RESULT_COLUMNS)
    with con.cursor().copy(f"COPY result ({', '.join(cols)}) FROM STDIN") as cp:
        for r in rows:
            vals = [r.get(k) for k in RESULT_FIELDS]
            vals[1] = None if vals[1] is None else str(vals[1])            # bib — текст
            vals[0] = None if vals[0] is None else str(vals[0])            # external_participant_id
            cp.write_row((race_id, raw_id, clubs.get(r.get("club_raw")), *vals))


def save_raw(con: psycopg.Connection, src: int, fetches: list[dict], raw_root, object_ref: str | None,
             competition_id: int | None = None, race_id: int | None = None, parse_method: str | None = None) -> list[int]:
    """Сырые ответы, использованные для объекта (старт или дистанция), — в таблицу raw.
    Тело остаётся файлом в data/raw; повтор того же ответа строку не плодит."""
    ids = []
    for f in fetches:
        body = f["path"].read_bytes()
        ids.append(con.execute(
            """INSERT INTO raw(source_id, competition_id, race_id, object_ref, url, request_key, content_hash,
               storage_path, size_bytes, http_status, parse_method)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,200,%s)
               ON CONFLICT (source_id, request_key, content_hash) DO UPDATE SET
               competition_id = COALESCE(excluded.competition_id, raw.competition_id),
               race_id = COALESCE(excluded.race_id, raw.race_id),
               object_ref = COALESCE(excluded.object_ref, raw.object_ref)
               RETURNING id""",
            (src, competition_id, race_id, object_ref, f["url"], f["request_key"],
             hashlib.sha256(body).hexdigest(), f["path"].relative_to(raw_root).as_posix(), len(body),
             parse_method)).fetchone()[0])
    return ids


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

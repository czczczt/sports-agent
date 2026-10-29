"""Перенос прототипа SQLite -> PostgreSQL повторным прогоном из кеша и построчная сверка.

    docker compose up -d db
    python migrate_sqlite.py              # ОЧИЩАЕТ таблицы Postgres и собирает их заново
    python migrate_sqlite.py --compare    # только сверка уже собранной базы

Данные не копируются, а собираются заново тем же кодом: старты берутся из старой SQLite
(список стартов RR живой, с сайта пришёл бы другой), всё остальное — из data/raw при запрещённой сети.
Так проверяется сразу и перенос, и то, что повторный прогон даёт те же строки.
Отчёт — data/report_migration.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from collections import Counter

import db
import dedup
import run
import seed_journal
from normalize import is_sber_club

SQLITE = db.DATA_DIR / "running.db"
TABLES = "agent_run, result, raw, club, race, competition, issue, known_exception, source"


def r6(x):
    return None if x is None else round(float(x), 6)


def s(x):
    return None if x is None else str(x)


# ---------- естественные ключи: одинаковы в обеих базах, id — нет ----------
def old_rows(lt: sqlite3.Connection) -> dict:
    q = lambda sql: lt.execute(sql).fetchall()
    comps = {(src, s(ext)): (title, (d1 or "")[:10] or None, (d2 or "")[:10] or None, place, addr, sport, url)
             for src, ext, title, d1, d2, place, addr, sport, url in q(
                 """SELECT s.name, e.external_id, e.title, e.date_begin, e.date_end, e.place, e.address, e.sport, e.url
                    FROM event e JOIN source s ON s.id = e.source_id""")}
    races = {(src, s(ce), s(re_)): (name, r6(km), m, nd, rt, pb, bool(fin), tot)
             for src, ce, re_, name, km, m, nd, rt, pb, fin, tot in q(
                 """SELECT s.name, e.external_id, r.external_id, r.name_raw, r.distance_km_raw, r.distance_m,
                    r.norm_distance, r.race_type, r.place_by, r.is_final_protocol, r.total_count
                    FROM race r JOIN event e ON e.id = r.event_id JOIN source s ON s.id = e.source_id""")}
    res = q("""SELECT x.id, s.name, e.external_id, r.external_id, x.external_participant_id, x.bib, x.full_name_raw,
               x.gender, x.age, x.birth_year, x.country, x.region, x.city, x.club_raw, x.club_source, x.status,
               x.place_abs, x.place_gender, x.age_group, x.chip_time_s, x.gun_time_s, x.duplicate_of
               FROM result x JOIN race r ON r.id = x.race_id JOIN event e ON e.id = r.event_id
               JOIN source s ON s.id = e.source_id""")
    canon = {(a, s(b)): (c, s(d)) for a, b, c, d in q(
        """SELECT s.name, e.external_id, s2.name, e2.external_id FROM event e JOIN source s ON s.id = e.source_id
           JOIN event e2 ON e2.id = e.canonical_event_id JOIN source s2 ON s2.id = e2.source_id""")}
    issues = Counter((src, st, kd, ref, stat) for src, st, kd, ref, stat in q(
        """SELECT s.name, i.stage, i.kind, i.object_ref, i.status FROM issue i LEFT JOIN source s ON s.id = i.source_id
           WHERE i.fingerprint NOT LIKE 'journal|%'"""))
    return {"comps": comps, "races": races, "results": res, "canon": canon, "issues": issues}


def new_rows(pg) -> dict:
    q = lambda sql: pg.execute(sql).fetchall()
    comps = {(src, ext): (name, d1 and d1.isoformat(), d2 and d2.isoformat(), loc, addr, sport, url)
             for src, ext, name, d1, d2, loc, addr, sport, url in q(
                 """SELECT s.name, c.external_id, c.name, c.date_begin, c.date_end, c.location, c.address,
                    c.sport_type, c.source_url FROM competition c JOIN source s ON s.id = c.source_id""")}
    races = {(src, ce, re_): (name, r6(km), m, nd, rt, pb, fin, tot)
             for src, ce, re_, name, km, m, nd, rt, pb, fin, tot in q(
                 """SELECT s.name, c.external_id, r.external_id, r.name, r.distance_km_raw, r.distance_m,
                    r.distance_type, r.race_type, r.place_by, r.is_final_protocol, r.total_count
                    FROM race r JOIN competition c ON c.id = r.competition_id JOIN source s ON s.id = c.source_id""")}
    res = q("""SELECT x.id, s.name, c.external_id, r.external_id, x.external_participant_id, x.bib, x.full_name_raw,
               x.gender, x.age, x.birth_year, x.country, x.region, x.city, x.club_raw, x.club_source, x.status,
               x.position, x.position_gender, x.age_group, x.chip_time_s, x.gun_time_s, x.duplicate_of
               FROM result x JOIN race r ON r.id = x.race_id JOIN competition c ON c.id = r.competition_id
               JOIN source s ON s.id = c.source_id""")
    canon = {(a, b): (c, d) for a, b, c, d in q(
        """SELECT s.name, c.external_id, s2.name, c2.external_id FROM competition c JOIN source s ON s.id = c.source_id
           JOIN competition c2 ON c2.id = c.canonical_competition_id JOIN source s2 ON s2.id = c2.source_id""")}
    issues = Counter((src, st, kd, ref, stat) for src, st, kd, ref, stat in q(
        """SELECT s.name, i.stage, i.kind, i.object_ref, i.status FROM issue i LEFT JOIN source s ON s.id = i.source_id
           WHERE i.fingerprint NOT LIKE 'journal|%'"""))
    return {"comps": comps, "races": races, "results": res, "canon": canon, "issues": issues}


def result_key(r) -> tuple:
    """Строка протокола без id: площадка, старт, дистанция и все поля."""
    return (r[1], s(r[2]), s(r[3]), s(r[4]), s(r[5]), *r[6:19], r6(r[19]), r6(r[20]))


def dup_pairs(rows) -> Counter:
    by_id = {r[0]: result_key(r) for r in rows}
    return Counter((by_id[r[0]], by_id[r[21]]) for r in rows if r[21] is not None)


def sber(rows) -> dict:
    live = [r for r in rows if r[21] is None and r[13] and is_sber_club(r[13])]
    return {"результатов_сберовцев": len(live), "из_них_только_фильтром": sum(r[14] == "filter" for r in live)}


def diff_dict(a: dict, b: dict) -> dict:
    only_a, only_b = a.keys() - b.keys(), b.keys() - a.keys()
    changed = [k for k in a.keys() & b.keys() if a[k] != b[k]]
    return {"старая": len(a), "новая": len(b), "только_в_старой": len(only_a), "только_в_новой": len(only_b),
            "отличаются": len(changed),
            "примеры": [{"ключ": list(k), "старая": a.get(k), "новая": b.get(k)}
                        for k in (sorted(only_a, key=str)[:3] + sorted(only_b, key=str)[:3] + changed[:3])]}


def compare(pg) -> dict:
    lt = sqlite3.connect(SQLITE)
    old, new = old_rows(lt), new_rows(pg)
    ro, rn = Counter(map(result_key, old["results"])), Counter(map(result_key, new["results"]))
    do, dn = dup_pairs(old["results"]), dup_pairs(new["results"])
    per_source = lambda rows: dict(sorted(Counter(r[1] for r in rows).items()))
    rep = {
        "старты": diff_dict(old["comps"], new["comps"]),
        "дистанции": diff_dict(old["races"], new["races"]),
        "результаты": {"старая": sum(ro.values()), "новая": sum(rn.values()),
                       "только_в_старой": sum((ro - rn).values()), "только_в_новой": sum((rn - ro).values()),
                       "по_площадкам_старая": per_source(old["results"]),
                       "по_площадкам_новая": per_source(new["results"]),
                       "примеры": [list(k) for k in list((ro - rn))[:3] + list((rn - ro))[:3]]},
        "без_дублей": {"старая": sum(r[21] is None for r in old["results"]),
                       "новая": sum(r[21] is None for r in new["results"])},
        "склейки_результатов": {"старая": sum(do.values()), "новая": sum(dn.values()),
                                "совпадают": do == dn},
        "склейки_стартов": {"старая": len(old["canon"]), "новая": len(new["canon"]),
                            "совпадают": old["canon"] == new["canon"]},
        "сберовцы": {"старая": sber(old["results"]), "новая": sber(new["results"])},
        # в старой базе копились проблемы всех прошлых прогонов (в т. ч. до исправлений), в новой — только текущие
        "проблемы_прогона_по_статусам": {
            "старая": dict(Counter(k[4] for k in old["issues"].elements())),
            "новая": dict(Counter(k[4] for k in new["issues"].elements())),
            "только_в_новой": [list(k) for k in (new["issues"] - old["issues"])][:10]},
        "raw": dict(zip(("ответов", "привязано_к_дистанции", "МБ"), pg.execute(
            "SELECT count(*), count(race_id), round(sum(size_bytes) / 1e6) FROM raw").fetchone())),
        "клубы": dict(zip(("всего", "сбер_по_детектору"), pg.execute(
            "SELECT count(*), count(*) FILTER (WHERE is_sber) FROM club").fetchone())),
    }
    rep["итог_совпадает"] = all([
        rep["старты"]["только_в_старой"] == rep["старты"]["только_в_новой"] == rep["старты"]["отличаются"] == 0,
        rep["дистанции"]["только_в_старой"] == rep["дистанции"]["только_в_новой"] == rep["дистанции"]["отличаются"] == 0,
        rep["результаты"]["только_в_старой"] == rep["результаты"]["только_в_новой"] == 0,
        rep["склейки_результатов"]["совпадают"], rep["склейки_стартов"]["совпадают"],
        rep["сберовцы"]["старая"] == rep["сберовцы"]["новая"]])
    return rep


def rebuild(pg) -> dict:
    """Очистить Postgres и собрать заново: журнал -> площадки (старты из SQLite, данные из кеша) -> дедуп."""
    backup = db.DATA_DIR / "migration_before"
    backup.mkdir(exist_ok=True)
    for f in db.DATA_DIR.glob("report_*.json"):  # отчёты старой базы перезапишутся — сохраняем один раз
        if not (backup / f.name).exists():
            shutil.copy(f, backup / f.name)
    pg.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
    pg.commit()
    seed_journal.main()

    lt = sqlite3.connect(SQLITE)
    stats = {}
    for name, in lt.execute("SELECT name FROM source ORDER BY id").fetchall():
        comps = [{"external_id": ext, "code": code, "title": title, "date_begin": d1, "date_end": d2, "place": pl,
                  "address": ad, "sport": sp, "url": url}
                 for ext, code, title, d1, d2, pl, ad, sp, url in lt.execute(
                     """SELECT e.external_id, e.code, e.title, e.date_begin, e.date_end, e.place, e.address, e.sport,
                        e.url FROM event e JOIN source s ON s.id = e.source_id WHERE s.name = ? ORDER BY e.id""",
                     (name,)).fetchall()]
        conn = run.CONNECTORS[name]()
        run.take_fetches()
        summary = run.run(conn, pg, comps)
        before = json.loads((backup / f"report_{name}.json").read_text(encoding="utf-8"))
        got = dict(summary["stats"])
        # 404 «нет протокола» (E13) не кешируется: без сети такие дистанции видны как «нет в кеше»
        if "races_not_in_cache" in got and got["races_not_in_cache"] == before["stats"].get("races_no_protocol"):
            got["races_no_protocol"] = got.pop("races_not_in_cache")
        stats[name] = {"было": before["stats"], "стало": summary["stats"],
                       "совпадает": before["stats"] == got and before["statuses"] == summary["statuses"]}
        print(name, json.dumps(stats[name], ensure_ascii=False), flush=True)
    dedup.main()
    before = json.loads((backup / "report_dedup.json").read_text(encoding="utf-8"))
    after = json.loads((db.DATA_DIR / "report_dedup.json").read_text(encoding="utf-8"))
    keys = ("дубли_результатов", "оценка_на_participantId", "записей_всего", "записей_без_дублей")
    stats["дедуп"] = {"было": {k: before[k] for k in keys}, "стало": {k: after[k] for k in keys},
                      "совпадает": all(before[k] == after[k] for k in keys)}
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true", help="только сверка, без пересборки")
    args = ap.parse_args()
    pg = db.connect()
    out = {}
    if not args.compare:
        run.block_network()
        out["прогоны"] = rebuild(pg)
    out["сверка"] = compare(pg)
    (db.DATA_DIR / "report_migration.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str),
                                                       encoding="utf-8")
    print(json.dumps(out["сверка"], ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()

"""Прогон: площадка -> беговые старты -> протоколы -> PostgreSQL + отчёт о проверках.

    python run.py --source russiarunning --events 40
    python run.py --source runc --events 20
    python run.py --source runc --events 20 --offline   # только кеш data/raw, сеть запрещена
"""
from __future__ import annotations

import argparse
import json
import socket
from collections import Counter

import requests

import db
import http_cache
import store
from grom import GromConnector
from rr_platform import SOURCES as RR_SOURCES, RRConnector
from runc import RuncConnector

CONNECTORS = {**{n: (lambda n=n: RRConnector(n)) for n in RR_SOURCES},
              "runc": RuncConnector, "grom": GromConnector}
REPORT_DIR = db.DATA_DIR
RAW_ROOT = http_cache.RAW
PRIORITY = {"timerman": 2}  # дедуп: сайт организатора/хронометража — основной, зеркало timerman — дубль


OFFLINE = False


def block_network() -> None:
    """Режим --offline: любой сетевой запрос падает, данные берутся только из кеша."""
    global OFFLINE
    OFFLINE = True

    def refuse(*_a, **_k):
        raise ConnectionError("offline: ответа нет в кеше data/raw")
    socket.socket.connect = refuse
    socket.create_connection = refuse


def take_fetches() -> list[dict]:
    out = list(http_cache.FETCH_LOG)
    http_cache.FETCH_LOG.clear()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=CONNECTORS, default="russiarunning")
    ap.add_argument("--events", type=int, default=30, help="сколько стартов обработать")
    ap.add_argument("--skip", type=int, default=0, help="пропустить первые N стартов списка")
    ap.add_argument("--sber-only", action="store_true",
                    help="RR: протокол качать только у дистанций, где в списке клубов есть Сбер (стратегия SPEC)")
    ap.add_argument("--offline", action="store_true", help="без сети: только сохранённые ответы data/raw")
    args = ap.parse_args()
    if args.offline:
        block_network()

    conn = CONNECTORS[args.source]()
    con = db.connect()
    comps = conn.competitions(args.events, args.skip)
    take_fetches()  # списки стартов в raw не пишем: они не относятся к конкретному старту
    summary = run(conn, con, comps, sber_only=args.sber_only)
    print(json.dumps({"stats": summary["stats"], "statuses": summary["statuses"]}, ensure_ascii=False))


def run(conn, con, comps: list[dict], sber_only: bool = False) -> dict:
    """Старты -> дистанции -> протоколы -> БД. Пишет отчёт data/report_<площадка>.json и возвращает его."""
    src = db.source_id(con, conn.name, conn.base_url, conn.platform, getattr(conn, "parse_method", None),
                       PRIORITY.get(conn.name, 1))
    stats, statuses, report = Counter(), Counter(), []
    pm = getattr(conn, "parse_method", None)

    for comp in comps:
        take_fetches()
        try:
            races = conn.races(comp)
        except Exception as ex:  # noqa: BLE001 — фиксируем и идём дальше
            db.report_issue(con, src, "fetch", "fetch_failed", comp["code"], repr(ex)); stats["event_error"] += 1
            take_fetches()
            continue
        event_id = store.save_competition(con, src, comp)
        store.save_raw(con, src, take_fetches(), RAW_ROOT, comp["code"], competition_id=event_id, parse_method=pm)
        stats["events"] += 1
        for race in races:
            ref = f"{comp['code']}/{race['external_id']}"
            stats["races"] += 1
            if race.get("sport", "run") != "run":
                stats["races_not_run"] += 1
                continue
            if race["race_type"] == "relay":  # правил для эстафет в беге ТЗ не задаёт (E14)
                stats["races_relay_skipped"] += 1
                continue
            if sber_only and "_sber_clubs" in race and not race["_sber_clubs"]:
                stats["races_without_sber_skipped"] += 1
                continue
            try:
                rows, total = conn.results(comp, race)
            except requests.HTTPError as ex:
                store.save_raw(con, src, take_fetches(), RAW_ROOT, ref, competition_id=event_id, parse_method=pm)
                if ex.response is not None and ex.response.status_code == 404:  # E13: протокола нет
                    stats["races_no_protocol"] += 1
                    report.append({"race": ref, "name": race.get("name_raw"), "status": "нет протокола"})
                    continue
                db.report_issue(con, src, "fetch", "fetch_failed", ref, repr(ex)); stats["race_error"] += 1
                report.append({"race": ref, "status": f"ошибка: {ex!r}"[:300]})
                continue
            except requests.RequestException as ex:
                take_fetches()
                if OFFLINE:  # ответа нет в кеше (например, 404 «нет протокола» не кешируется) — не ошибка площадки
                    stats["races_not_in_cache"] += 1
                    report.append({"race": ref, "name": race.get("name_raw"), "status": "нет в кеше (offline)"})
                    continue
                # сеть, таймаут — проблема загрузки, а не разбора
                db.report_issue(con, src, "fetch", "fetch_failed", ref, repr(ex)); stats["race_error"] += 1
                report.append({"race": ref, "status": f"ошибка: {ex!r}"[:300]})
                continue
            except Exception as ex:  # noqa: BLE001
                store.save_raw(con, src, take_fetches(), RAW_ROOT, ref, competition_id=event_id, parse_method=pm)
                db.report_issue(con, src, "parse", "parse_failed", ref, repr(ex)); stats["race_error"] += 1
                report.append({"race": ref, "status": f"ошибка: {ex!r}"[:300]})
                continue
            fetches = take_fetches()
            # вид спорта и тип гонки у grom становятся известны только по протоколу
            if race.get("sport", "run") != "run":
                stats["races_not_run"] += 1
                continue
            if race["race_type"] == "relay":
                stats["races_relay_skipped"] += 1
                continue
            if not rows:  # частый признак того, что площадка поменяла формат — задача агенту
                store.save_raw(con, src, fetches, RAW_ROOT, ref, competition_id=event_id, parse_method=pm)
                stats["races_empty"] += 1
                db.report_issue(con, src, "parse", "zero_rows", ref, {"name": race.get("name_raw")})
                report.append({"race": ref, "name": race.get("name_raw"), "status": "пустой протокол"})
                continue
            race["total_count"] = total
            race_id = store.save_race(con, event_id, race)
            raw_ids = store.save_raw(con, src, fetches, RAW_ROOT, ref, competition_id=event_id, race_id=race_id,
                                     parse_method=pm)
            # строка -> её ответ площадки однозначна, только если протокол пришёл одним ответом
            store.save_results(con, race_id, rows, raw_ids[0] if len(raw_ids) == 1 else None)
            statuses.update(r["status"] for r in rows)
            c = store.checks(rows, total, race["place_by"])
            ok = all(c.values())
            stats["races_ok" if ok else "races_with_issues"] += 1
            stats["results"] += len(rows)
            stats["sber_by_filter"] += race.get("_sber_found", 0)
            stats["sber_only_via_filter"] += race.get("_sber_only_filter", 0)
            report.append({"race": ref, "name": race.get("name_raw"), "distance_km": race.get("distance_km"),
                           "n": len(rows), "total": total, "place_by": race["place_by"],
                           "sber_clubs": [t or c for c, t in race.get("_sber_clubs", [])],
                           "sber_by_filter": race.get("_sber_found"), "sber_only_via_filter": race.get("_sber_only_filter"),
                           "status": "ok" if ok else "есть проблемы", "checks": c})
            if not ok:
                st = db.report_issue(con, src, "check", "check_failed", ref,
                                     {"name": race.get("name_raw"), "failed": [k for k, v in c.items() if not v]})
                if st == "known":  # известная особенность данных (known_exception), а не ошибка парсера
                    stats["races_with_issues"] -= 1
                    stats["races_known_exception"] += 1
                    report[-1]["status"] = "известное исключение"
        con.commit()

    summary = {"stats": dict(stats), "statuses": dict(statuses), "races": report}
    (REPORT_DIR / f"report_{conn.name}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    main()

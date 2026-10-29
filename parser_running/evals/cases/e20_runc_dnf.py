"""E20: на runc в «финишёрах» в конце идут сошедшие: место «-», в колонке результата — статус."""
from fixtures_lib import runc_page, runc_url
from protocol import Task

META = {"id": "E20", "title": "runc: сошедшие записаны как финишёры", "expected": "fix"}
CODE = "autumn_run_2026"
ROWS = [(1, "Тестов Иван", "М30", 11, "0:35:10"), (2, "Пробный Пётр", "М41", 12, "0:36:02"),
        (3, "Образцова Анна", "Ж28", 13, "0:38:45"), ("-", "Модельный Олег", "М35", 14, "DNF"),
        ("-", "Шаблонова Вера", "Ж33", 15, "DQ")]
FIXTURES = {"chip.html": runc_page(CODE, ROWS), "gun.html": runc_page(CODE, ROWS)}
MUTATIONS = [{"file": "runc.py",
              "old": 'status = "FIN" if to_seconds(result) is not None else STATUS_WORDS.get((result or "").upper(), "DNF")',
              "new": 'status = "FIN"'}]
ORACLE = {"action": "patch", "reason": "статус берём из колонки результата, если там не время",
          "edits": [{"file": "runc.py", "old": 'status = "FIN"\n',
                     "new": 'status = "FIN" if to_seconds(result) is not None else '
                            'STATUS_WORDS.get((result or "").upper(), "DNF")\n'}]}


def task() -> Task:
    return Task("E20", "runc", "check", "check_failed", f"{CODE}/1",
                {"name": "10 км", "failed": ["у_финишёров_есть_время", "места_по_порядку", "время_растёт_с_местом"]},
                ["chip.html", "gun.html"])


def check(sb):
    import http_cache
    import runc
    import store
    pages = {runc_url(CODE, "1"): (sb / "fixtures/chip.html").read_text(encoding="utf-8"),
             runc_url(CODE, "1", common=True): (sb / "fixtures/gun.html").read_text(encoding="utf-8")}
    http_cache.get = lambda source, url, **k: pages[url]
    race = {"external_id": "1", "race_type": "individual", "place_by": "chip"}
    rows, total = runc.RuncConnector().results({"code": CODE}, race)
    c = store.checks(rows, total, race["place_by"])
    statuses = [r["status"] for r in rows]
    ok = all(c.values()) and statuses == ["FIN", "FIN", "FIN", "DNF", "DSQ"]
    return ok, f"проверки {c}, статусы {statuses}"

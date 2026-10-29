"""E22: у элиты места по времени от общего старта (грязному), а не по личному."""
from fixtures_lib import runc_page, runc_url
from protocol import Task

META = {"id": "E22", "title": "runc: элита ранжируется по грязному времени", "expected": "fix"}
CODE = "city_marathon_2026"
CHIP = [(1, "Бегунов Артём", "М29", 1, "2:26:32"), (2, "Скоров Илья", "М31", 2, "2:26:31"),
        (3, "Темпов Глеб", "М27", 3, "2:28:20"), (4, "Финишев Лев", "М33", 4, "2:30:00")]
GUN = [(1, "Бегунов Артём", "М29", 1, "2:26:35"), (2, "Скоров Илья", "М31", 2, "2:26:40"),
       (3, "Темпов Глеб", "М27", 3, "2:28:25"), (4, "Финишев Лев", "М33", 4, "2:30:10")]
FIXTURES = {"chip.html": runc_page(CODE, CHIP), "gun.html": runc_page(CODE, GUN)}
MUTATIONS = [{"file": "runc.py", "old": 'race["place_by"] = infer_place_by(rows)', "new": 'race["place_by"] = "chip"'}]
ORACLE = {"action": "patch", "reason": "по какому времени места — определяем по данным",
          "edits": [{"file": "runc.py", "old": 'race["place_by"] = "chip"',
                     "new": 'race["place_by"] = infer_place_by(rows)'}]}


def task() -> Task:
    return Task("E22", "runc", "check", "check_failed", f"{CODE}/7",
                {"name": "42,195 км - элитный кластер", "failed": ["время_растёт_с_местом"]},
                ["chip.html", "gun.html"])


def check(sb):
    import http_cache
    import runc
    import store
    pages = {runc_url(CODE, "7"): (sb / "fixtures/chip.html").read_text(encoding="utf-8"),
             runc_url(CODE, "7", common=True): (sb / "fixtures/gun.html").read_text(encoding="utf-8")}
    http_cache.get = lambda source, url, **k: pages[url]
    race = {"external_id": "7", "race_type": "individual", "place_by": "chip"}
    rows, total = runc.RuncConnector().results({"code": CODE}, race)
    c = store.checks(rows, total, race["place_by"])
    return all(c.values()) and race["place_by"] == "gun", f"проверки {c}, place_by={race['place_by']}"

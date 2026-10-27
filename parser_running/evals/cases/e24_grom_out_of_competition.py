"""E24: на grom финишёр с местом «-1/-1» — вне зачёта (NC), а не обычный финишёр."""
from fixtures_lib import grom_page, grom_row
from protocol import Task

META = {"id": "E24", "title": "grom: финишёр вне зачёта", "expected": "fix"}
URL = "https://grom.place/results/test-cross-2026"
ROWS = [grom_row(101, "Кроссов", "Иван", "M", "1/3", chip="0:40:00,00"),
        grom_row(102, "Лесная", "Ольга", "F", "2/3", chip="0:41:10,00", age_group="Female 30-34"),
        grom_row(103, "Полевой", "Пётр", "M", "3/3", chip="0:42:20,00"),
        grom_row(104, "Внезачётов", "Олег", "M", "-1/-1", chip="0:41:00,00")]
FIXTURES = {"disc.html": grom_page(ROWS)}
MUTATIONS = [{"file": "grom.py",
              "old": 'status = ("FIN" if place else "NC") if finished else ("DNF" if chip or gun else "DNS")',
              "new": 'status = "FIN" if finished else ("DNF" if chip or gun else "DNS")'}]
ORACLE = {"action": "patch", "reason": "место «-1/-1» = вне зачёта",
          "edits": [{"file": "grom.py",
                     "old": 'status = "FIN" if finished else ("DNF" if chip or gun else "DNS")',
                     "new": 'status = ("FIN" if place else "NC") if finished else ("DNF" if chip or gun else "DNS")'}]}


def task() -> Task:
    return Task("E24", "grom", "check", "check_failed", "test-cross-2026/12 км",
                {"name": "12 км", "failed": ["места_по_порядку", "время_растёт_с_местом"]}, ["disc.html"])


def check(sb):
    import grom
    import http_cache
    import store
    page = (sb / "fixtures/disc.html").read_text(encoding="utf-8")
    http_cache.get = lambda source, url, **k: page
    race = {"external_id": "12 км", "_path": "12%20км", "race_type": "individual", "place_by": "chip"}
    rows, total = grom.GromConnector().results({"url": URL}, race)
    c = store.checks(rows, total, race["place_by"])
    statuses = [r["status"] for r in rows]
    return all(c.values()) and statuses == ["FIN", "FIN", "FIN", "NC"], f"проверки {c}, статусы {statuses}"

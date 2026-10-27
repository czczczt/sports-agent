"""Перенос журнала ERRORS.md в очередь issue + стартовый список known_exception.

    python seed_journal.py

Журнал вёлся вручную (E1…); теперь это история очереди: закрытые проблемы — `resolved`,
ждущие решения — `new` (человеку), заблокированные сетью/заказчиком — `blocked`.
Повторный запуск ничего не дублирует.
"""
from __future__ import annotations

import re
from pathlib import Path

import db

# id -> (stage, kind, кто разбирает). Классификация — по смыслу записи в журнале.
JOURNAL = {
    "E1": ("fetch", "geo_block", "infra"), "E2": ("fetch", "timeout", "infra"),
    "E3": ("fetch", "browser_denied", "human"), "E4": ("fetch", "timeout", "infra"),
    "E5": ("parse", "api_contract", "agent"), "E6": ("parse", "name_order", "agent"),
    "E7": ("parse", "hidden_field", "agent"), "E8": ("parse", "missing_field", "human"),
    "E9": ("check", "check_failed", "agent"), "E10": ("parse", "bad_place", "agent"),
    "E11": ("parse", "unknown_status", "agent"), "E12": ("check", "check_failed", "agent"),
    "E13": ("fetch", "no_protocol", "agent"), "E14": ("parse", "relay", "human"),
    "E15": ("parse", "missing_field", "human"), "E16": ("match", "club_mask", "human"),
    "E17": ("match", "missing_field", "human"), "E18": ("dedup", "duplicate", "agent"),
    "E19": ("fetch", "geo_block", "infra"), "E20": ("parse", "unknown_status", "agent"),
    "E21": ("store", "db_constraint", "agent"), "E22": ("check", "check_failed", "agent"),
    "E23": ("fetch", "timeout", "infra"), "E24": ("parse", "unknown_status", "agent"),
    "E25": ("parse", "missing_field", "agent"), "E26": ("parse", "anonymous_row", "agent"),
    "E27": ("parse", "data_quirk", "human"), "E28": ("check", "check_failed", "human"),
    "E29": ("fetch", "rate_limit", "infra"), "E30": ("parse", "missing_field", "agent"),
    "E31": ("match", "missing_field", "human"), "E32": ("parse", "unknown_distance", "agent"),
    "E33": ("dedup", "logic_bug", "agent"), "E34": ("dedup", "wrong_assumption", "human"),
}
DATA_QUIRKS = {"E26", "E27", "E28"}  # особенности данных, а не ошибки

# Известные исключения: при совпадении проблема получает статус `known`, а не уходит агенту.
KNOWN = [
    ("runc", "check_failed", r"\b(60|100|200|400) м\b.*время_растёт_с_местом",
     "Спринт с финалом: финалисты ранжируются по финалу, остальные по забегам", "E28"),
]


def status_of(cell: str, jid: str) -> str:
    if jid in DATA_QUIRKS and "✅" not in cell:
        return "known"
    if "✅" in cell:
        return "resolved"
    if "⛔" in cell:
        return "blocked"
    return "new"


def main() -> None:
    con = db.connect()
    text = (Path(__file__).parent / "ERRORS.md").read_text(encoding="utf-8")
    n = 0
    for line in text.splitlines():
        m = re.match(r"\|\s*(E\d+)\s*\|", line)
        if not m:
            continue
        jid = m.group(1)
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # колонки: ID | Где | Что случилось | Причина | Что сделали | Статус
        where, what, cause, done, status_cell = (cells + [""] * 6)[1:6]
        stage, kind, assignee = JOURNAL.get(jid, ("unknown", "journal", "human"))
        status = status_of(status_cell, jid)
        con.execute("""INSERT INTO issue(stage, kind, object_ref, fingerprint, details, status, assignee,
                       journal_ref, resolved_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s='resolved' THEN now() END)
                       ON CONFLICT(fingerprint) DO UPDATE SET details=excluded.details, status=excluded.status,
                       stage=excluded.stage, kind=excluded.kind, assignee=excluded.assignee""",
                    (stage, kind, where, f"journal|{jid}",
                     f"Что: {what}\nПричина: {cause}\nСделано: {done}\nСтатус: {status_cell}",
                     status, assignee, jid, status))
        n += 1
    con.cursor().executemany("INSERT INTO known_exception(source, kind, pattern, reason, journal_ref) "
                             "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", KNOWN)
    con.commit()
    print(f"журнал: {n} записей; по статусам:",
          dict(con.execute("SELECT status, count(*) FROM issue WHERE fingerprint LIKE 'journal|%' "
                           "GROUP BY status").fetchall()),
          "| known_exception:", con.execute("SELECT count(*) FROM known_exception").fetchone()[0])


if __name__ == "__main__":
    main()

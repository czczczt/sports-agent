"""Дедупликация стартов и результатов между площадками (spec, раздел 7).

    python dedup.py

1. Старты. Пара стартов с разных площадок — дубль, если:
   - совпадает external_id (одна платформа на нескольких сайтах, RR), или
   - один день + на дистанциях одной длины совпадает ≥ MIN_OVERLAP результатов
     (одно и то же ФИО с тем же временем ±1 с). Похожесть названия только отбирает кандидатов:
     названия на площадках пишут по-разному («СберПрайм Московский Марафон» / «Московский марафон 2026»).
   Основным (canonical) становится старт площадки с меньшим source.priority.
2. Результаты. В дубле строка неосновной площадки получает duplicate_of = id строки основной.
   Ничего не удаляем: дубли просто исключаются из подсчётов.
Оценка: в зеркале одного старта на russiarunning ↔ timerman participantId совпадает у одного человека — это эталон.
Только для зеркал: participantId привязан к старту, между разными стартами он не повторяется (E34),
поэтому эталоном сопоставления атлета между стартами он не служит.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from difflib import SequenceMatcher

import db

MIN_OVERLAP = 0.3       # доля результатов меньшей дистанции, совпавших по ФИО+времени
TITLE_CANDIDATE = 0.35  # нижний порог похожести названий, чтобы не сравнивать всё со всем


def norm_name(s: str | None) -> str | None:
    """'Иванов  Пётр' / 'Пётр Иванов' -> 'иванов петр' (порядок слов не важен, E6)."""
    if not s:
        return None
    toks = re.findall(r"[a-zа-я]+", s.lower().replace("ё", "е"))
    return " ".join(sorted(toks)) or None


def norm_title(s: str | None) -> str:
    return " ".join(re.findall(r"[a-zа-я0-9]+", (s or "").lower().replace("ё", "е")))


def load(con):
    events = con.execute("""SELECT c.id, s.name, c.external_id, c.name, c.date_begin::text, s.platform, s.priority
                            FROM competition c JOIN source s ON s.id = c.source_id ORDER BY c.id""").fetchall()
    races = defaultdict(list)
    for rid, eid, dist in con.execute("SELECT id, competition_id, distance_m FROM race ORDER BY id").fetchall():
        races[eid].append((rid, dist))
    return events, races


def results_of(con, race_id: int) -> dict[tuple, int]:
    """(норм. ФИО, секунда чистого/грязного времени) -> id результата; только финишёры с временем."""
    out = {}
    for rid, name, chip, gun in con.execute("""SELECT id, full_name_raw, chip_time_s, gun_time_s FROM result
                                               WHERE race_id = %s AND status = 'FIN' ORDER BY id""",
                                            (race_id,)).fetchall():
        n, t = norm_name(name), chip if chip is not None else gun
        if n and t is not None:
            out[(n, round(t))] = rid
    return out


def match_results(a: dict, b: dict) -> list[tuple[int, int]]:
    """Пары (id_a, id_b): то же ФИО и время в пределах ±1 с."""
    pairs = []
    for (n, t), ida in a.items():
        for dt in (0, -1, 1):  # время совпадает ±1 с (после округления до секунды)
            idb = b.get((n, t + dt))
            if idb is not None:
                pairs.append((ida, idb))
                break
    return pairs


def same_distance(d1, d2) -> bool:
    return bool(d1 and d2 and abs(d1 - d2) <= 0.02 * max(d1, d2))


def main() -> None:
    con = db.connect()
    con.execute("UPDATE competition SET canonical_competition_id = NULL")
    con.execute("UPDATE result SET duplicate_of = NULL")
    events, races = load(con)
    by_date = defaultdict(list)
    for e in events:
        by_date[e[4]].append(e)

    report = {"пары_стартов": [], "дубли_результатов": 0}
    for day, evs in by_date.items():
        for i, a in enumerate(evs):
            for b in evs[i + 1:]:
                if a[1] == b[1]:
                    continue  # внутри одной площадки дублей не ищем
                # E33: external_id сравниваем только внутри одной платформы (у runc/grom это коды и слаги,
                # совпадение с id другой платформы ничего не значит)
                same_ext = a[5] == b[5] and a[2] == b[2]
                title_sim = SequenceMatcher(None, norm_title(a[3]), norm_title(b[3])).ratio()
                if not same_ext and title_sim < TITLE_CANDIDATE:
                    continue
                main_e, dup_e = sorted((a, b), key=lambda e: (e[6], e[0]))
                race_pairs, n_dup, best_overlap = [], 0, 0.0
                for ra, da in races[main_e[0]]:
                    for rb, dbb in races[dup_e[0]]:
                        if not same_distance(da, dbb):
                            continue
                        ma, mb = results_of(con, ra), results_of(con, rb)
                        if not ma or not mb:
                            continue
                        pairs = match_results(ma, mb)
                        overlap = len(pairs) / min(len(ma), len(mb))
                        best_overlap = max(best_overlap, overlap)
                        if overlap >= MIN_OVERLAP:
                            race_pairs.append((ra, rb, pairs))
                if not (same_ext or race_pairs):
                    continue
                con.execute("UPDATE competition SET canonical_competition_id = %s WHERE id = %s",
                            (main_e[0], dup_e[0]))
                for _, _, pairs in race_pairs:
                    con.cursor().executemany("UPDATE result SET duplicate_of = %s WHERE id = %s",
                                             [(x, y) for x, y in pairs])
                    n_dup += len(pairs)
                report["дубли_результатов"] += n_dup
                report["пары_стартов"].append({
                    "дата": day, "основной": f"{main_e[1]}: {main_e[3]}", "дубль": f"{dup_e[1]}: {dup_e[3]}",
                    "по_external_id": same_ext, "похожесть_названий": round(title_sim, 2),
                    "лучшее_перекрытие_результатов": round(best_overlap, 3), "склеено_результатов": n_dup})
    con.commit()
    report["оценка_на_participantId"] = evaluate(con)
    report["записей_всего"] = con.execute("SELECT count(*) FROM result").fetchone()[0]
    report["записей_без_дублей"] = con.execute("SELECT count(*) FROM result WHERE duplicate_of IS NULL").fetchone()[0]
    (db.DATA_DIR / "report_dedup.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "пары_стартов"}, ensure_ascii=False))
    for p in report["пары_стартов"]:
        print(json.dumps(p, ensure_ascii=False))


def evaluate(con) -> dict:
    """Эталон: в дублях RR (russiarunning ↔ timerman) у одного человека одинаковый participantId.
    precision — доля склеенных пар с одинаковым id; recall — доля пар финишёров с одинаковым id, которые склеены."""
    rows = con.execute("""
        SELECT r.id, r.external_participant_id, r.duplicate_of, x.competition_id, e.canonical_competition_id, r.status
        FROM result r JOIN race x ON x.id = r.race_id JOIN competition e ON e.id = x.competition_id
        JOIN source s ON s.id = e.source_id
        WHERE s.name IN ('russiarunning', 'timerman')""").fetchall()
    pid = {r[0]: r[1] for r in rows}
    linked = [(r[0], r[2]) for r in rows if r[2] is not None]
    tp = sum(1 for a, b in linked if pid.get(a) and pid.get(a) == pid.get(b))
    # все финишёры дублирующих стартов, у которых есть «близнец» с тем же participantId в основном старте
    dup_events = {r[3]: r[4] for r in rows if r[4] is not None}
    by_event_pid = defaultdict(dict)
    for r in rows:
        if r[5] == "FIN":
            by_event_pid[r[3]][r[1]] = r[0]
    should = sum(1 for dup, main in dup_events.items() for p in by_event_pid[dup] if p in by_event_pid[main])
    return {"склеено_пар": len(linked), "верных": tp, "должно_быть": should,
            "precision": round(tp / len(linked), 4) if linked else None,
            "recall": round(tp / should, 4) if should else None}


if __name__ == "__main__":
    main()

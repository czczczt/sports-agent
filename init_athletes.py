"""
Детерминированная инициализация таблиц спортсменов (athlete, result_athlete, athlete_assessment_cache).
НЕ МЕНЯЕТ существующие таблицы (source, event, race, result, issue, known_exception).
Создает только новые вспомогательные таблицы и индексы.
"""
import sqlite3
import re
import time
from collections import defaultdict, Counter


def norm_name(name: str) -> str:
    if not name:
        return ""
    s = name.lower().replace("ё", "е")
    tokens = sorted(re.findall(r"[a-zа-я0-9]+", s))
    return " ".join(tokens)


def setup_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS athlete (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        display_name TEXT NOT NULL,
        name_key TEXT NOT NULL,
        gender TEXT,
        birth_year INTEGER,
        city TEXT,
        region TEXT,
        club TEXT,
        starts_count INTEGER DEFAULT 0,
        results_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_athlete_name_key ON athlete(name_key);")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_athlete_birth_year ON athlete(birth_year);")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS result_athlete (
        result_id INTEGER PRIMARY KEY,
        athlete_id INTEGER NOT NULL REFERENCES athlete(id)
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_result_athlete_athlete ON result_athlete(athlete_id);")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS athlete_assessment_cache (
        athlete_id INTEGER PRIMARY KEY REFERENCES athlete(id),
        assessment_text TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        model TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()


def populate_athletes(db_path: str = "running.db"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    setup_schema(conn)

    # Проверяем, заполнена ли уже таблица athlete
    count = cur.execute("SELECT count(*) FROM athlete").fetchone()[0]
    if count > 0:
        print(f"Таблица athlete уже содержит {count} записей. Пропуск генерации.")
        conn.close()
        return

    print("Начало группировки результатов в спортсменов...")
    t0 = time.time()
    rows = cur.execute("""
        SELECT r.id, r.full_name_raw, r.gender, r.birth_year, r.age, e.date_begin, r.city, r.region, r.club_raw, r.status, r.duplicate_of
        FROM result r
        JOIN race ra ON ra.id = r.race_id
        JOIN event e ON e.id = ra.event_id
    """).fetchall()
    print(f"Загружено {len(rows)} строк за {time.time() - t0:.2f} сек.")

    groups = defaultdict(list)
    for r in rows:
        rid, name_raw, gender, byear, age, dbegin, city, region, club, status, dup = r
        if not name_raw:
            continue
        nkey = norm_name(name_raw)
        cyear = byear
        if cyear is None and age is not None and dbegin:
            try:
                cyear = int(dbegin[:4]) - age
            except Exception:
                pass
        groups[(nkey, gender or "")].append({
            "rid": rid, "name_raw": name_raw, "year": cyear,
            "city": city, "region": region, "club": club,
            "status": status, "dup": dup
        })

    athletes_to_insert = []
    links_to_insert = []
    athlete_id = 0

    for (nkey, gender), items in groups.items():
        with_year = [it for it in items if it["year"] is not None]
        no_year = [it for it in items if it["year"] is None]

        clusters = []
        if with_year:
            with_year.sort(key=lambda x: x["year"])
            current_cluster = [with_year[0]]
            for it in with_year[1:]:
                # Допуск в 1 год между соседними результатами внутри одного человека
                if it["year"] - current_cluster[-1]["year"] <= 1:
                    current_cluster.append(it)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [it]
            clusters.append(current_cluster)

        if not clusters:
            if no_year:
                clusters.append(no_year)
        else:
            if len(clusters) == 1:
                clusters[0].extend(no_year)
            else:
                if no_year:
                    clusters.append(no_year)

        for cl in clusters:
            athlete_id += 1
            names = [x["name_raw"] for x in cl if x["name_raw"]]
            disp_name = Counter(names).most_common(1)[0][0] if names else nkey
            years = [x["year"] for x in cl if x["year"] is not None]
            rep_year = Counter(years).most_common(1)[0][0] if years else None
            cities = [x["city"] for x in cl if x["city"]]
            rep_city = Counter(cities).most_common(1)[0][0] if cities else None
            regions = [x["region"] for x in cl if x["region"]]
            rep_region = Counter(regions).most_common(1)[0][0] if regions else None
            clubs = [x["club"] for x in cl if x["club"]]
            rep_club = Counter(clubs).most_common(1)[0][0] if clubs else None
            
            # Завершенные старты без дублей
            fin_starts = sum(1 for x in cl if x["status"] == "FIN" and x["dup"] is None)
            total_results = len(cl)

            athletes_to_insert.append((
                athlete_id, disp_name, nkey, gender if gender else None,
                rep_year, rep_city, rep_region, rep_club, fin_starts, total_results
            ))
            for x in cl:
                links_to_insert.append((x["rid"], athlete_id))

    print(f"Сформировано {len(athletes_to_insert)} спортсменов. Запись в БД...")
    cur.executemany("""
        INSERT INTO athlete (id, display_name, name_key, gender, birth_year, city, region, club, starts_count, results_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, athletes_to_insert)

    cur.executemany("""
        INSERT INTO result_athlete (result_id, athlete_id)
        VALUES (?, ?)
    """, links_to_insert)

    conn.commit()
    conn.close()
    print(f"Успешно сохранено: {len(athletes_to_insert)} спортсменов, {len(links_to_insert)} связей.")


if __name__ == "__main__":
    populate_athletes()

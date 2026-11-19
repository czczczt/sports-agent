import sqlite3
from init_athletes import norm_name, is_dummy_club, setup_schema, populate_athletes


def test_norm_name_and_dummy_club():
    assert norm_name("Иванов Иван") == "иван иванов"
    assert norm_name("Петров-Водкин Кузьма") == "водкин кузьма петров"
    assert norm_name("") == ""
    assert is_dummy_club("нет") is True
    assert is_dummy_club("Лично") is True
    assert is_dummy_club("Клуб Бега") is False


def test_populate_athletes_sqlite_in_memory(tmp_path):
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE event (
        id INTEGER PRIMARY KEY,
        date_begin TEXT
    );
    """)
    cur.execute("INSERT INTO event VALUES (1, '2026-05-15');")

    cur.execute("""
    CREATE TABLE race (
        id INTEGER PRIMARY KEY,
        event_id INTEGER
    );
    """)
    cur.execute("INSERT INTO race VALUES (1, 1);")

    cur.execute("""
    CREATE TABLE result (
        id INTEGER PRIMARY KEY,
        race_id INTEGER,
        full_name_raw TEXT,
        gender TEXT,
        birth_year INTEGER,
        age INTEGER,
        city TEXT,
        region TEXT,
        club_raw TEXT,
        status TEXT,
        duplicate_of INTEGER
    );
    """)
    cur.execute("""
    INSERT INTO result VALUES
    (1, 1, 'Иванов Иван', 'M', 1990, NULL, 'Москва', 'Москва', 'Сбер', 'FIN', NULL),
    (2, 1, 'Иван Иванов', 'M', 1990, NULL, 'Москва', 'Москва', 'Сбер', 'FIN', NULL),
    (3, 1, 'Петрова Анна', 'F', 1995, NULL, 'Казань', 'Татарстан', 'Лично', 'FIN', NULL);
    """)
    conn.commit()
    conn.close()

    res = populate_athletes(str(db_file))
    assert res["skipped"] is False
    assert res["athletes"] == 2  # 2 unique athletes ('иван иванов', 'анна петрова')
    assert res["links"] == 3

    # Check that subsequent call skips
    res2 = populate_athletes(str(db_file))
    assert res2["skipped"] is True

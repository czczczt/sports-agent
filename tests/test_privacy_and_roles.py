from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.privacy_service import (
    anonymize_non_employee_results,
    purge_expired_raw_records,
)


def test_athlete_summary_privacy_by_role(client, auth_headers):
    user_headers = auth_headers("user")
    resp_user = client.get("/api/athletes/1/summary", headers=user_headers)
    assert resp_user.status_code == 200, resp_user.text
    data_user = resp_user.json()["athlete"]
    assert data_user["birth_date"] is None
    assert data_user["middle_name"] is None
    assert data_user["city"] is None
    assert data_user["club"] is None
    assert data_user["birth_year"] == 1990
    assert "Фёдоров" in data_user["display_name"]

    admin_headers = auth_headers("admin")
    resp_admin = client.get("/api/athletes/1/summary", headers=admin_headers)
    assert resp_admin.status_code == 200, resp_admin.text
    data_admin = resp_admin.json()["athlete"]
    assert data_admin["birth_date"] == "1990-05-15"
    assert data_admin["middle_name"] == "Иванович"

    captain_headers = auth_headers("captain")
    resp_captain = client.get("/api/athletes/1/summary", headers=captain_headers)
    assert resp_captain.status_code == 200, resp_captain.text
    data_captain = resp_captain.json()["athlete"]
    assert data_captain["birth_date"] == "1990-05-15"
    assert data_captain["middle_name"] == "Иванович"


def test_athlete_search_privacy(client, auth_headers):
    headers = auth_headers("user")
    resp = client.get(
        "/api/athletes/search?last_name=Фёдоров&birth_year=1990", headers=headers
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) >= 1
    item = items[0]
    assert item["birth_date"] is None
    assert item["middle_name"] is None
    assert item["city"] is None
    assert item["club"] is None


def test_race_protocol_non_employee_anonymized(client, auth_headers):
    headers = auth_headers("user")
    resp = client.get("/api/races/1", headers=headers)
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert len(results) == 3

    emp_res = next(r for r in results if r["result_id"] == 1)
    assert emp_res["athlete_id"] == 1
    assert emp_res["full_name_raw"] == "Фёдоров Иван"
    assert emp_res["bib"] == "A-7"

    non_emp_res = next(r for r in results if r["result_id"] == 3)
    assert non_emp_res["athlete_id"] is None
    assert non_emp_res["full_name_raw"] == "Участник"
    assert non_emp_res["bib"] is None
    assert non_emp_res["club_raw"] is None
    assert non_emp_res["place_abs"] == 3
    assert non_emp_res["chip_time_s"] == 2600


def test_rating_api_minimal_fields(client, auth_headers):
    headers = auth_headers("user")
    resp = client.get("/api/rating", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "rows" in data
    assert len(data["rows"]) >= 1
    row = data["rows"][0]
    allowed_keys = {
        "rank",
        "athlete_id",
        "display_name",
        "birth_year",
        "gender",
        "points",
        "best_points",
        "starts_count",
        "rank_delta",
    }
    assert set(row.keys()).issubset(allowed_keys)


@pytest.mark.asyncio
async def test_anonymize_non_employee_batch(imported_url):
    engine = create_async_engine(
        imported_url.replace("postgresql:", "postgresql+asyncpg:")
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    async with session_factory() as session:
        updated = await anonymize_non_employee_results(session)
        await session.commit()
        assert updated >= 1

    with psycopg.connect(imported_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT full_name_raw, bib, is_anonymized FROM result WHERE id=3")
        row = cur.fetchone()
        assert row[0] == "Участник"
        assert row[1] is None
        assert row[2] is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_raw_ttl_purging(imported_url, tmp_path):
    f_old = tmp_path / "old.json"
    f_old.write_text('{"old": true}', encoding="utf-8")
    f_new = tmp_path / "new.json"
    f_new.write_text('{"new": true}', encoding="utf-8")

    now = datetime.now(UTC)
    old_time = now - timedelta(days=120)
    new_time = now - timedelta(days=10)

    with psycopg.connect(imported_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw(source_id, request_key, content_hash, storage_path, fetched_at)
            VALUES (1, 'req_old', 'hash_old', %s, %s),
                   (1, 'req_new', 'hash_new', %s, %s)
            """,
            (str(f_old), old_time, str(f_new), new_time),
        )

    engine = create_async_engine(
        imported_url.replace("postgresql:", "postgresql+asyncpg:")
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    async with session_factory() as session:
        purged = await purge_expired_raw_records(session, days=90)
        await session.commit()
        assert purged == 1

    assert not f_old.exists()
    assert f_new.exists()

    with psycopg.connect(imported_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT purged_at FROM raw WHERE request_key='req_old'")
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT purged_at FROM raw WHERE request_key='req_new'")
        assert cur.fetchone()[0] is None

    await engine.dispose()

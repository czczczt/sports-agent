"""Exercise Wave 2 through the collection API and PostgreSQL worker."""
import asyncio
from datetime import date, timedelta

import procrastinate
import psycopg
import requests

from app.pipeline import pilot, sources
from app.worker import pilot_collect_task


def test_trail_collection_stores_reference_points_and_requests_missing_elevation(
    pilot_client, migrated_url, monkeypatch,
):
    monkeypatch.setattr(pilot, "DATABASE_URL", migrated_url)
    as_of = date(2026, 11, 24)
    period_start = as_of - timedelta(days=365)
    archived_date = as_of - timedelta(days=366)
    resultszone_date = archived_date

    class FixedDate(date):
        @classmethod
        def today(cls):
            return as_of

    monkeypatch.setattr(pilot, "date", FixedDate)
    elevation = None
    result_count = 1
    chip_time = None
    fetch_event = sources.fetch_event

    def external(source, code):
        if source in {"myfinish", "orgeo"}:
            return fetch_event(source, code)
        if source in {"russiarunning", "resultszone"}:
            archived = source == "resultszone"
            return {
                "competition": {
                    "external_id": code, "title": "Fixture road race", "sport": "run",
                    "date_begin": (resultszone_date if archived else period_start).isoformat(),
                    "url": "https://results.zone/" if archived else "https://results.russiarunning.com/",
                },
                "races": [{"race": {
                    "external_id": "archive-5" if archived else "road-5",
                    "name_raw": "5 км", "sport": "run", "race_type": "individual",
                    "is_final": True, "place_by": "gun", "total_count": 1, "distance_km": 5,
                }, "rows": [{
                    "external_participant_id": "runner", "full_name_raw": "Тест Бегун", "gender": "M",
                    "status": "FIN", "place_abs": 1, "chip_time_s": None, "gun_time_s": 1200,
                    "birth_year": 1987, "club_raw": "Сбер",
                }]}],
            }
        if source == "racetime":
            return {
                "competition": {"external_id": code, "title": "Fixture official race", "sport": "run",
                                "date_begin": as_of.isoformat(), "url": "https://results.racetime.online/"},
                "races": [{"race": {
                    "external_id": "official-5", "name_raw": "5 км", "sport": "run", "race_type": "individual",
                    "is_final": True, "place_by": "official", "total_count": 1, "distance_km": 5,
                }, "rows": [{
                    "external_participant_id": "official", "full_name_raw": "Тест Хронометраж", "gender": None,
                    "status": "FIN", "place_abs": 1, "chip_time_s": chip_time, "gun_time_s": None,
                    "official_time_s": 1210,
                }]}],
            }
        return {
            "competition": {"external_id": code, "title": "Fixture trail", "sport": "trail",
                            "date_begin": as_of.isoformat(), "url": "https://toplist.run/"},
            "races": [{"race": {
                "external_id": "trail-42", "name_raw": "42 км", "sport": "trail", "race_type": "individual",
                "is_final": True, "place_by": "gun", "total_count": result_count,
                "elevation_gain_m": elevation, "distance_km": 42,
            }, "rows": [{
                "external_participant_id": "finisher", "full_name_raw": "Тест Первый", "gender": "M",
                "status": "FIN", "place_abs": 1, "chip_time_s": None, "gun_time_s": 12000, "toplist_points": 412.5,
            }]}],
        }

    async def consume():
        app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=migrated_url))
        app.task(name=pilot_collect_task.name, queue="collect", pass_context=True,
                 retry=procrastinate.RetryStrategy(max_attempts=3, wait=0))(pilot_collect_task.func)
        async with app.open_async():
            await app.run_worker_async(queues=["collect"], wait=False)

    def execute(source="toplist", code="fixture-trail"):
        response = pilot_client.post("/api/v1/runs", json={
            "kind": "collect", "source": source, "event_code": code,
        })
        assert response.status_code == 202, response.text
        asyncio.run(consume())
        return pilot_client.get(f"/api/v1/runs/{response.json()['run_id']}").json()

    monkeypatch.setattr(sources, "fetch_event", external)
    assert pilot_client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
    archived_run = execute("resultszone", "fixture-archived-road")
    assert archived_run["status"] == "succeeded", archived_run
    assert archived_run["rating_version_id"] is None
    [archived_event] = pilot_client.get("/api/events", params={"source": "resultszone"}).json()
    assert archived_event["date_begin"] == archived_date.isoformat()
    [archived_race] = archived_event["races"]
    [archived_result] = pilot_client.get(f"/api/races/{archived_race['id']}/results").json()
    assert archived_result["gun_time_s"] == 1200
    assert archived_result["athlete_id"] is not None

    with psycopg.connect(migrated_url) as connection:
        connection.execute(
            "INSERT INTO rating_norm(year,distance_class,gender,value,unit) VALUES (%s,'5000m','M',1200,'s') "
            "ON CONFLICT (year,distance_class,gender) DO UPDATE SET value=1200", (as_of.year,),
        )
    baseline = execute("russiarunning", "fixture-road")
    assert baseline["status"] == "succeeded", baseline
    before = pilot_client.get("/api/rating").json()
    assert baseline["rating_version_id"] is not None
    assert before["version_id"] == baseline["rating_version_id"]
    assert before["period_start"] == period_start.isoformat()
    assert before["period_end"] == as_of.isoformat()
    [rated_runner] = before["rows"]
    assert rated_runner["points"] == 1000 and rated_runner["starts_count"] == 1

    archived_repeat = execute("resultszone", "fixture-archived-road")
    assert archived_repeat["status"] == "succeeded", archived_repeat
    assert archived_repeat["rating_version_id"] is None
    [repeated_event] = pilot_client.get("/api/events", params={"source": "resultszone"}).json()
    assert repeated_event["id"] == archived_event["id"]
    [repeated_race] = repeated_event["races"]
    assert repeated_race["id"] == archived_race["id"]
    [repeated_result] = pilot_client.get(f"/api/races/{repeated_race['id']}/results").json()
    assert repeated_result["result_id"] == archived_result["result_id"]
    assert repeated_result["athlete_id"] == archived_result["athlete_id"]
    assert pilot_client.get("/api/rating").json() == before

    with psycopg.connect(migrated_url) as connection:
        road_id = connection.execute("SELECT id FROM race WHERE external_id='road-5'").fetchone()[0]
    road_result = pilot_client.get(f"/api/races/{road_id}/results").json()[0]
    assert road_result["athlete_id"] is not None and road_result["points"] == 1000
    run = execute()
    assert run["status"] == "succeeded", run
    assert run["rating_version_id"] is None
    assert pilot_client.get("/api/rating").json() == before

    events = pilot_client.get("/api/events", params={"source": "toplist"}).json()
    assert [event["sport"] for event in events] == ["trail"]
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT toplist_points FROM result WHERE toplist_points IS NOT NULL").fetchall() == [(412.5,)]
        assert connection.execute("SELECT sport, elevation_gain_m FROM race WHERE sport_type='trail'").fetchall() == [("trail", None)]
        assert connection.execute(
            "SELECT status, assignee FROM issue WHERE kind='missing_elevation_gain'"
        ).fetchall() == [("new", "human")]
        connection.execute("UPDATE race SET elevation_gain_m=1800 WHERE sport_type='trail'")

    assert execute()["status"] == "succeeded"
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute(
            "SELECT elevation_gain_m FROM race WHERE sport_type='trail'"
        ).fetchall() == [(1800,)]
        assert connection.execute(
            "SELECT status FROM issue WHERE kind='missing_elevation_gain'"
        ).fetchall() == [("resolved",)]

    elevation = 1900
    assert execute()["status"] == "succeeded"
    result_count = 2
    assert execute()["status"] == "failed"
    assert pilot_client.get("/api/rating").json() == before
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT toplist_points FROM result WHERE toplist_points IS NOT NULL").fetchall() == [(412.5,)]
        assert connection.execute("SELECT elevation_gain_m FROM race WHERE sport_type='trail'").fetchall() == [(1900,)]
        assert connection.execute(
            "SELECT status FROM issue WHERE kind='missing_elevation_gain'"
        ).fetchall() == [("resolved",)]


    official_run = execute("racetime", "fixture-official")
    assert official_run["status"] == "succeeded", official_run
    assert official_run["rating_version_id"] is None
    with psycopg.connect(migrated_url) as connection:
        race_id = connection.execute("SELECT id FROM race WHERE external_id='official-5'").fetchone()[0]
    results = pilot_client.get(f"/api/races/{race_id}/results")
    assert results.status_code == 200
    result = results.json()[0]
    assert (result["chip_time_s"], result["gun_time_s"], result["official_time_s"]) == (None, None, 1210)
    assert result["full_name_raw"] == "Участник" and result["athlete_id"] is None and result["points"] is None
    assert "20:10" in result["time_formatted"]
    chip_time = 1198
    official_run = execute("racetime", "fixture-official")
    assert official_run["status"] == "succeeded" and official_run["rating_version_id"] is None
    result = pilot_client.get(f"/api/races/{race_id}/results").json()[0]
    assert result["chip_time_s"] == 1198 and "20:10" in result["time_formatted"]
    assert pilot_client.get("/api/rating").json() == before


    def blocked(self, method, url, **kwargs):
        response = requests.Response()
        response.status_code = 403
        return response

    monkeypatch.setattr(requests.Session, "request", blocked)
    for source in ("myfinish", "orgeo"):
        unavailable = execute(source, "12345")
        assert unavailable["status"] == "failed"
        assert "HTTP 403" in unavailable["error"] and "manual import" in unavailable["error"]
        assert unavailable["rating_version_id"] is None
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT count(*) FROM competition").fetchone()[0] == 4
    assert pilot_client.get("/api/rating").json() == before

    resultszone_date = period_start
    counted = execute("resultszone", "fixture-archived-road")
    assert counted["status"] == "succeeded", counted
    assert counted["rating_version_id"] is not None
    [runner_with_both_starts] = pilot_client.get("/api/rating").json()["rows"]
    assert runner_with_both_starts["starts_count"] == 2

    resultszone_date = archived_date
    corrected = execute("resultszone", "fixture-archived-road")
    assert corrected["status"] == "succeeded", corrected
    rating = pilot_client.get("/api/rating").json()
    assert rating["version_id"] == corrected["rating_version_id"] != counted["rating_version_id"]
    assert rating["rows"] == before["rows"]

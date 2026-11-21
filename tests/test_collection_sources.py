"""Exercise the shared HTTP and queue boundary with two RR platforms."""
import asyncio
import json
from datetime import date
from urllib.parse import urlsplit

import procrastinate
import psycopg
import requests

from app.pipeline import pilot
from app.worker import pilot_collect_task
from parser_running import rr_platform


def test_same_event_code_is_independent_and_ski_does_not_change_running_rating(
    pilot_client, migrated_url, monkeypatch,
):
    monkeypatch.setattr(pilot, "DATABASE_URL", migrated_url)
    monkeypatch.setattr(rr_platform, "DELAY_S", 0)
    seen = set()

    def external(self, method, url, **kwargs):
        platform = urlsplit(url).netloc
        seen.add(platform)
        sport = {
            "timerman.org": "run", "results.legkovrace.ru": "ski-race", "results.pionercup.ru": "ski-biathlon",
        }[platform]
        if url.endswith("/events/get"):
            assert kwargs["json"]["eventCode"] == "same-code"
            payload = {
                "id": "same-external-id", "title": "Source event", "beginDate": date.today().isoformat(),
                "disciplineCode": sport, "races": [
                    {"id": "same-race", "name": "5 км", "distance": 5, "disciplineCode": sport}
                ],
            }
        elif url.endswith("/results/options/get"):
            payload = {"isFinalProtocol": True}
        else:
            assert url.endswith("/results/individual/get")
            payload = {"totalCount": 1, "results": [{
                "participantId": "one", "fullName": "Тест Первый", "position": 1, "gender": 0,
                "birthYear": 1990, "raceClub": "Сбер", "status": 0, "individualResult": "00:20:00",
            }]}
            if sport == "ski-biathlon":
                payload["results"][0]["timeResult"] = "00:22:00"
                payload["results"].append({
                    "participantId": "two", "fullName": "Тест Второй", "gender": 0, "position": 2,
                    "birthYear": 1991, "status": 0, "individualResult": "00:19:50", "timeResult": "00:22:50",
                })
                payload["totalCount"] = 2
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode()
        return response

    monkeypatch.setattr(requests.Session, "request", external)

    async def consume():
        app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=migrated_url))
        app.task(name=pilot_collect_task.name, queue="collect", pass_context=True)(pilot_collect_task.func)
        async with app.open_async():
            await app.run_worker_async(queues=["collect"], wait=False, concurrency=2)

    def queue(source):
        response = pilot_client.post("/api/v1/runs", json={
            "kind": "collect", "source": source, "event_code": "same-code",
        })
        assert response.status_code == 202, response.text
        return response.json()["run_id"]

    with psycopg.connect(migrated_url) as connection:
        connection.execute(
            "INSERT INTO rating_norm(year,distance_class,gender,value,unit) VALUES (%s,'5000m','M',1200,'s') "
            "ON CONFLICT (year,distance_class,gender) DO UPDATE SET value=1200", (date.today().year,),
        )
    assert pilot_client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
    runs = {source: queue(source) for source in ("timerman", "legkovrace", "pionercup")}
    asyncio.run(consume())
    for source, run_id in runs.items():
        status = pilot_client.get(f"/api/v1/runs/{run_id}").json()
        assert status["source"] == source
        assert status["status"] == "succeeded", status
        assert bool(status["rating_version_id"]) == (source == "timerman")
    assert seen == {"timerman.org", "results.legkovrace.ru", "results.pionercup.ru"}
    rows = pilot_client.get("/api/rating").json()["rows"]
    assert len(rows) == 1
    assert rows[0]["points"] == 1000
    assert rows[0]["starts_count"] == 1
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT count(*) FROM competition").fetchone()[0] == 3
        assert connection.execute(
            """SELECT r.chip_time_s, r.official_time_s FROM result r JOIN race ra ON ra.id=r.race_id
               WHERE ra.source_discipline='ski-biathlon' ORDER BY r.position"""
        ).fetchall() == [(1200, 1320), (1190, 1370)]



def test_probeg_and_official_protocol_publish_one_finish(pilot_client, migrated_url, monkeypatch):
    from app.pipeline import sources

    monkeypatch.setattr(pilot, "DATABASE_URL", migrated_url)
    primary_url = "https://results.russiarunning.com/event/example/results"
    today = date.today()

    def external(source, code):
        reported_by_probeg = source == "probeg"
        return {
            "competition": {
                "external_id": code, "title": "Агрегатор" if reported_by_probeg else "Первоисточник",
                "date_begin": today.isoformat(), "sport": "run",
                "url": "https://probeg.org/event/123/" if reported_by_probeg else primary_url,
                "canonical_url": primary_url if reported_by_probeg else None,
            },
            "races": [{"race": {
                "external_id": "5k", "name_raw": "5 км", "distance_km": 5, "sport": "run",
                "race_type": "individual", "place_by": "chip", "is_final": True, "total_count": 1,
            }, "rows": [{
                "external_participant_id": "runner-1", "full_name_raw": "Петров Пётр",
                "birth_year": 1990, "gender": "M", "club_raw": "Сбер" if reported_by_probeg else None,
                "status": "FIN", "place_abs": 1, "chip_time_s": 1200, "gun_time_s": 1201,
            }]}],
        }

    async def consume():
        queue = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=migrated_url))
        queue.task(name=pilot_collect_task.name, queue="collect", pass_context=True)(pilot_collect_task.func)
        async with queue.open_async():
            await queue.run_worker_async(queues=["collect"], wait=False, concurrency=2)

    monkeypatch.setattr(sources, "fetch_event", external)
    with psycopg.connect(migrated_url) as connection:
        connection.execute(
            "INSERT INTO rating_norm(year,distance_class,gender,value,unit) VALUES (%s,'5000m','M',1200,'s') "
            "ON CONFLICT (year,distance_class,gender) DO UPDATE SET value=1200", (today.year,),
        )

    assert pilot_client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
    for source, code in (("probeg", "123"), ("russiarunning", "example"), ("probeg", "123")):
        response = pilot_client.post("/api/v1/runs", json={"kind": "collect", "source": source, "event_code": code})
        assert response.status_code == 202, response.text
        asyncio.run(consume())
        status = pilot_client.get(f"/api/v1/runs/{response.json()['run_id']}").json()
        assert status["status"] == "succeeded", status
        rows = pilot_client.get("/api/rating").json()["rows"]
        assert [(row["starts_count"], row["points"]) for row in rows] == [(1, 1000)]
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT count(*) FROM result").fetchone()[0] == 2
        assert connection.execute(
            """SELECT official_source.name FROM result mirror
                JOIN result official ON official.id=mirror.duplicate_of
                JOIN race ON race.id=official.race_id
                JOIN competition ON competition.id=race.competition_id
                JOIN source official_source ON official_source.id=competition.source_id"""
        ).fetchall() == [("russiarunning",)]

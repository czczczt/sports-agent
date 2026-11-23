"""Anonymized fixtures for the public Results.zone and RaceTime protocol contracts."""

import asyncio
import json
from datetime import date, timedelta

import procrastinate
import psycopg
import pytest
import requests

from app.pipeline import pilot, racetime, resultszone
from app.pipeline.errors import PilotRejected
from app.worker import pilot_collect_task


def _zone_page(**embedded):
    return "<script>" + "".join(f"general.{key}={json.dumps(value)};" for key, value in embedded.items()) + "</script>"


@pytest.fixture
def zone_pages():
    entries = [
        {"id": race_id, "name": name, "distance": distance, "start_by": "start",
         "finish_by": "distance", "live": False, "slug": "sample",
         "self": f"/sample/races/{race_id}/results"}
        for race_id, name, distance in ((1, "Бег 5 км", 5000), (2, "Бег 7 км", 7000),
                                       (3, "Ходьба 5 км", 5000))
    ]
    pages = {"/sample": _zone_page(
        event={"slug": "sample", "name": "Образец", "date_start": "2025-05-30",
               "sport": "running", "races": entries},
        event_results_statistics={"stats": [{"id": x["id"], "total": 2, "q": 2} for x in entries]},
    )}
    for entry in entries[:2]:
        for page in (1, 2):
            path = entry["self"] + ("?page=2" if page == 2 else "")
            pages[path] = _zone_page(
                race={**entry, "splits": [{"sport": "running"}]},
                page_info={"totalRows": 2, "perPage": 1, "totalPages": 2,
                           "currentPage": page, "nextPage": 2 if page == 1 else None},
                heats=[{"race_id": entry["id"], "uuid": f"participant-{page}", "bib": str(page),
                        "name": f"Участник {page}", "gender": "female", "status": "Q",
                        "rank_abs": page, "rank_gender": page, "result_time": 1200 + page,
                        "result_time_start": 1200 + page, "result_time_gun": 1201 + page}],
            )
    return pages


def test_resultszone_supported_and_nonrating_distance(zone_pages):
    result = resultszone._collect(zone_pages.__getitem__, "sample")
    assert [(item["race"]["distance_km"], len(item["rows"])) for item in result["races"]] == [(5, 2), (7, 2)]
    assert result["races"][0]["rows"][0]["official_time_s"] == 1201
    assert result["review_items"] == [{"kind": "unsupported_discipline", "external_ref": "/sample/races/3/results"}]


@pytest.mark.parametrize("change", ["shape", "pagination", "identity"])
def test_resultszone_changed_protocol_is_rejected(zone_pages, change):
    path = "/sample/races/1/results?page=2"
    page = zone_pages[path]
    if change == "shape":
        page = page.replace("general.heats", "general.changed")
    elif change == "pagination":
        page = page.replace('"currentPage": 2', '"currentPage": 1')
    else:
        page = page.replace('"race_id": 1', '"race_id": 2')
    zone_pages[path] = page
    with pytest.raises(PilotRejected):
        resultszone._collect(zone_pages.__getitem__, "sample")

def _guid(number):
    return f"00000000-0000-0000-0000-{number:012d}"


@pytest.mark.parametrize("partial", [False, True])
def test_racetime_uses_published_official_timing_and_checks_all_distances(monkeypatch, partial):
    stage = _guid(1)
    groups = [{
        "guid": _guid(i), "displayName": f"{i} км",
        "categories": [{"guid": _guid(10 + i), "displayName": "Абсолют", "isTeam": False}],
    } for i in (5, 10)]
    variables = {
        "RACE_STAGE_GUID": stage, "RACE_STAGE_INFO": {"raceStageGuid": stage, "startDateTime": "2025-04-02"},
        "HAS_RESULTS": True, "GROUPS_AND_CATEGORIES": groups, "BASE_URL": racetime._RESULTS_TEMPLATE,
        "API_KEY": "fixture-key", "HEADER_NAME": "LIMETIME-API-KEY",
    }
    home = "<title>Fixture RaceTime</title><script>" + "".join(
        f"var {name} = {json.dumps(value)};" for name, value in variables.items()
    ) + "</script>"
    calendar = """<figcaption><div class="media-header"><a href="/sample">Race</a></div>
                  <div class="media-subheader"><div>Бег</div></div></figcaption>"""

    def external(self, url, **kwargs):
        response = requests.Response()
        response.status_code = 200
        if url == racetime.BASE_URL + "/sample":
            response._content = home.encode()
        elif url == racetime.BASE_URL + "/2025":
            response._content = calendar.encode()
        else:
            assert url.startswith("https://services-results.limetime.io/results/get/")
            assert kwargs["headers"] == {"LIMETIME-API-KEY": "fixture-key"}
            second = url.endswith(_guid(20))
            response._content = json.dumps({
                "isSuccess": True, "totalCount": 2 if second and partial else 1,
                "data": [{"raceStageRegistrationGuid": _guid(100 if second else 50),
                          "account": {"firstName": "Test", "lastName": "Runner", "age": -1 if second else "31"}, "position": 1,
                          "isDisqualified": False, "isOtl": False, "isOnStart": True, "isFinished": True,
                          "resultTime": "00:42:10" if second else "00:20:10"}],
            }).encode()
        return response

    monkeypatch.setattr(requests.Session, "get", external)
    monkeypatch.setattr(racetime, "sleep", lambda _: None)
    if partial:
        with pytest.raises(PilotRejected, match="Incomplete RaceTime"):
            racetime.fetch_event("sample")
        return
    event = racetime.fetch_event("sample")
    assert [(item["race"]["distance_km"], item["race"]["place_by"]) for item in event["races"]] == [
        (5, "official"), (10, "official"),
    ]
    assert [item["rows"][0]["official_time_s"] for item in event["races"]] == [1210, 2530]
    assert [item["rows"][0]["age"] for item in event["races"]] == [31, None]
    assert all(item["rows"][0]["gender"] is None for item in event["races"])

def test_resultszone_http_worker_and_failed_refresh(pilot_client, migrated_url, monkeypatch, zone_pages):
    monkeypatch.setattr(pilot, "DATABASE_URL", migrated_url)
    monkeypatch.setattr(resultszone, "sleep", lambda _: None)
    day = date.today() - timedelta(days=1)
    zone_pages["/sample"] = zone_pages["/sample"].replace("2025-05-30", day.isoformat())
    root = "/sample/races/1/results"
    zone_pages[root] = zone_pages[root].replace('"bib": "1"', '"club": "Sber Team", "bib": "1"')
    failed = False

    def external(self, url, **kwargs):
        path = url.removeprefix(resultszone.BASE_URL)
        body = zone_pages[path]
        if failed and path == root + "?page=2":
            body = body.replace("general.heats", "general.changed")
        response = requests.Response()
        response.status_code = 200
        response._content = body.encode("utf-8")
        return response

    async def consume():
        worker = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=migrated_url))
        worker.task(name=pilot_collect_task.name, queue="collect", pass_context=True,
                    retry=procrastinate.RetryStrategy(max_attempts=3, wait=0))(pilot_collect_task.func)
        async with worker.open_async():
            await worker.run_worker_async(queues=["collect"], wait=False)

    def execute():
        response = pilot_client.post("/api/v1/runs", json={
            "kind": "collect", "source": "resultszone", "event_code": "sample",
        })
        assert response.status_code == 202
        asyncio.run(consume())
        return pilot_client.get(f"/api/v1/runs/{response.json()['run_id']}").json()

    monkeypatch.setattr(requests.Session, "get", external)
    assert pilot_client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
    with psycopg.connect(migrated_url) as connection:
        connection.execute(
            "INSERT INTO rating_norm(year,distance_class,gender,value,unit) VALUES (%s,'5000m','F',1201,'s') "
            "ON CONFLICT (year,distance_class,gender) DO UPDATE SET value=1201", (day.year,),
        )
    first = execute()
    assert first["status"] == "succeeded", first
    second = execute()
    assert second["status"] == "succeeded", second
    assert second["processed_distances"] == 2
    before = pilot_client.get("/api/rating").json()
    assert before["version_id"] == second["rating_version_id"] and before["rows"][0]["points"] == 1000
    failed = True
    rejection = execute()
    assert rejection["status"] == "failed" and "heats" in rejection["error"]
    assert pilot_client.get("/api/rating").json() == before
    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT count(*) FROM result").fetchone()[0] == 4
        assert connection.execute("SELECT kind FROM issue").fetchall() == [("unsupported_discipline",)]

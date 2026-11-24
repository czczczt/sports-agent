"""The bulk admin workflow through HTTP, Procrastinate and PostgreSQL."""

import asyncio

import pytest
from procrastinate import App, PsycopgConnector, RetryStrategy

BASE = "/api/admin/collection"


@pytest.fixture
def bulk_client(pilot_client, migrated_url, monkeypatch):
    from app.modules.bulk_collection import publication_service

    monkeypatch.setattr(publication_service, "DATABASE_URL", migrated_url)
    return pilot_client


def test_bulk_collection_source_catalog_is_admin_only(bulk_client):
    response = bulk_client.get(f"{BASE}/sources")
    assert response.status_code == 401
    assert bulk_client.post("/api/auth/login", json={"username": "user", "password": "user"}).status_code == 200
    assert bulk_client.get(f"{BASE}/sources").status_code == 403
    assert bulk_client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200

    response = bulk_client.get(f"{BASE}/sources")
    assert response.status_code == 200, response.text
    catalog = {source["code"]: source for source in response.json()}
    assert catalog["russiarunning"]["automatic"]
    assert not catalog["toplist"]["automatic"]
    assert catalog["tristats"]["enabled"]



def _protocol(source, code, title, seconds, *, canonical_url=None):
    site = {"resultszone": "https://results.zone", "probeg": "https://probeg.org", "grom": "https://grom.place"}
    url = f"{site[source]}/{code}"
    return {
        "competition": {
            "external_id": code, "code": code, "title": title, "date_begin": "2020-06-14",
            "place": "Екатеринбург", "sport": "run", "url": url, "canonical_url": canonical_url,
        },
        "races": [{
            "race": {
                "external_id": "5k", "name_raw": "5 км", "distance_km": 5.0, "sport": "run",
                "race_type": "individual", "is_final": True, "place_by": "gun",
                "total_count": len(seconds), "url": url,
            },
            "rows": [{
                "external_participant_id": str(position), "full_name_raw": f"Участник {position}",
                "gender": "M", "status": "FIN", "place_abs": position, "gun_time_s": time,
            } for position, time in enumerate(seconds, start=1)],
        }],
    }


def _consume_bulk_jobs(client, url, batch_id):
    from app.worker import bulk_discover_task, bulk_event_task

    async def drain():
        worker = App(connector=PsycopgConnector(conninfo=url))
        for task in (bulk_discover_task, bulk_event_task):
            worker.task(name=task.name, queue="bulk-collect", pass_context=True,
                        retry=RetryStrategy(max_attempts=3, wait=0))(task.func)
        async with worker.open_async():
            running = asyncio.create_task(worker.run_worker_async(queues=["bulk-collect"], concurrency=3))
            try:
                for _ in range(150):
                    if running.done():
                        running.result()
                        raise AssertionError("The worker exited before completing the batch")
                    response = await asyncio.to_thread(client.get, f"{BASE}/batches/{batch_id}")
                    assert response.status_code == 200, response.text
                    detail = response.json()
                    if not any(row["status"] in {"queued", "running"} for row in detail["sources"]):
                        return
                    await asyncio.sleep(0.1)
                raise AssertionError(detail)
            finally:
                running.cancel()
                await asyncio.gather(running, return_exceptions=True)

    asyncio.run(drain())


def _bulk_batch(client, url, sources, starts):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
    response = client.post(f"{BASE}/batches", json={
        "sources": sources,
        "starts": [{"source": source, "event_code": code} for source, code in starts],
    })
    assert response.status_code == 202, response.text
    batch_id = response.json()["id"]
    _consume_bulk_jobs(client, url, batch_id)
    assert client.get(f"{BASE}/batches").json()[0]["id"] == batch_id
    response = client.get(f"{BASE}/batches/{batch_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_bulk_collection_shows_one_official_competition_before_approval(bulk_client, migrated_url, monkeypatch):
    from app.modules.bulk_collection import collection

    def external(source, event_code):
        if source == "resultszone":
            return _protocol(source, event_code, "Летний тестовый забег", [1200, 1300])
        return _protocol(source, event_code, "Летний тестовый забег", [1200],
                         canonical_url="https://results.zone/official")

    monkeypatch.setattr(collection, "fetch_event", external)
    batch = _bulk_batch(bulk_client, migrated_url, ["resultszone", "probeg", "toplist"],
                        [("resultszone", "official"), ("probeg", "mirror")])
    [event] = batch["events"]
    assert event["participants"] == 2
    assert event["source"] == "resultszone"
    [race] = event["races"]
    assert not race["warning"] and len(race["protocols"]) == 2
    assert bulk_client.get("/api/events").json() == []

    path = f"{BASE}/batches/{batch['id']}/approve"
    command = {"draft_ids": event["draft_ids"], "resolutions": [], "preview_revision": batch["preview_revision"]}
    approved = bulk_client.post(path, json=command)
    assert approved.status_code == 200, approved.text
    replay = bulk_client.post(path, json=command)
    assert replay.status_code == 200, replay.text
    assert replay.json() == approved.json()
    [published] = bulk_client.get("/api/events").json()
    [race] = published["races"]
    assert published["source_name"] == "resultszone"
    assert len(bulk_client.get(f"/api/races/{race['id']}/results").json()) == 2


def test_bulk_collection_defers_conflict_and_publishes_other_competition(bulk_client, migrated_url, monkeypatch):
    from app.modules.bulk_collection import collection

    def external(source, event_code):
        if event_code == "different":
            return _protocol(source, event_code, "Другой тестовый старт", [1500])
        if source == "resultszone":
            return _protocol(source, event_code, "Летний тестовый забег", [1200, 1300])
        return _protocol(source, event_code, "Летний тестовый забег", [1250, 1350, 1450])

    monkeypatch.setattr(collection, "fetch_event", external)
    batch = _bulk_batch(bulk_client, migrated_url, ["resultszone", "grom"],
                        [("resultszone", "official"), ("grom", "conflict"), ("grom", "different")])
    events = {event["title"]: event for event in batch["events"]}
    disputed = events["Летний тестовый забег"]
    separate = events["Другой тестовый старт"]
    [race] = disputed["races"]
    assert race["warning"]
    assert {p["source"]: p["participants"] for p in race["protocols"]} == {"resultszone": 2, "grom": 3}
    assert all(p["url"] and p["is_final"] is True for p in race["protocols"])
    assert bulk_client.get("/api/events").json() == []

    path = f"{BASE}/batches/{batch['id']}"
    result = bulk_client.post(f"{path}/approve", json={
        "draft_ids": separate["draft_ids"] + disputed["draft_ids"],
        "resolutions": [], "preview_revision": batch["preview_revision"],
    })
    assert result.status_code == 200, result.text
    assert set(result.json()["pending_draft_ids"]) == set(disputed["draft_ids"])
    assert [event["title"] for event in bulk_client.get("/api/events").json()] == ["Другой тестовый старт"]

    stale = bulk_client.post(f"{path}/approve", json={
        "draft_ids": disputed["draft_ids"], "resolutions": [],
        "preview_revision": batch["preview_revision"],
    })
    assert stale.status_code == 409, stale.text
    assert [event["title"] for event in bulk_client.get("/api/events").json()] == ["Другой тестовый старт"]

    preview = bulk_client.get(path).json()
    disputed = next(event for event in preview["events"] if event["title"] == "Летний тестовый забег")
    [race] = disputed["races"]
    official = next(p for p in race["protocols"] if p["source"] == "resultszone")
    result = bulk_client.post(f"{path}/approve", json={
        "draft_ids": disputed["draft_ids"], "preview_revision": preview["preview_revision"],
        "resolutions": [{"race_key": race["key"], "protocol_key": official["key"]}],
    })
    assert result.status_code == 200, result.text
    published = {event["title"]: event for event in bulk_client.get("/api/events").json()}
    [race] = published["Летний тестовый забег"]["races"]
    assert len(bulk_client.get(f"/api/races/{race['id']}/results").json()) == 2



def test_bulk_collection_catalog_continues_after_failed_source(bulk_client, migrated_url, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from app.modules.bulk_collection import collection
    from app.pipeline.errors import PilotRejected
    from parser_running.rr_platform import RRClient

    now = datetime.now(UTC).replace(second=0, microsecond=0)
    catalog = [
        {"id": "recent", "code": "recent", "disciplineCode": "run", "beginDate": (now - timedelta(days=3)).isoformat()},
        {"id": "old", "code": "old", "disciplineCode": "run", "beginDate": (now - timedelta(days=45)).isoformat()},
    ]
    monkeypatch.setattr(RRClient, "event_catalog_page",
                        lambda self, skip, take: {"totalCount": len(catalog), "list": catalog[skip:skip + take]})

    def external(source, event_code):
        if source == "orgeo":
            raise PilotRejected("Only live results")
        event = _protocol("resultszone", event_code, "Тестовый старт " + event_code, [1200])
        event["competition"]["url"] = "https://results.russiarunning.com/event/" + event_code
        return event

    monkeypatch.setattr(collection, "fetch_event", external)
    batch = _bulk_batch(bulk_client, migrated_url, ["russiarunning", "orgeo", "toplist"], [("orgeo", "live")])
    assert {row["code"]: row["status"] for row in batch["sources"]} == {
        "orgeo": "failed", "russiarunning": "completed", "toplist": "unsupported",
    }
    assert [row["title"] for row in batch["events"]] == ["Тестовый старт recent"]

    catalog[1]["title"] = "В каталоге изменились данные старта"
    subsequent = _bulk_batch(bulk_client, migrated_url, ["russiarunning"], [])
    assert [row["title"] for row in subsequent["events"]] == ["Тестовый старт old"]


def test_bulk_collection_recovers_from_unstorable_payload(migrated_url, monkeypatch):
    import psycopg

    import app.modules.runs.service as service
    from app.modules.bulk_collection import collection

    monkeypatch.setattr(service, "DATABASE_URL", migrated_url)
    event = _protocol("resultszone", "nul", "Private\0payload", [1200])
    monkeypatch.setattr(collection, "fetch_event", lambda source, event_code: event)
    with psycopg.connect(migrated_url) as db:
        source_id = db.execute(
            "INSERT INTO source(name,base_url,platform) VALUES ('resultszone','https://example.test','resultszone') RETURNING id"
        ).fetchone()[0]
        batch_id = db.execute("INSERT INTO bulk_batch DEFAULT VALUES RETURNING id").fetchone()[0]
        db.execute(
            "INSERT INTO bulk_source(batch_id,source_id,status,is_automatic) VALUES (%s,%s,'queued',false)",
            (batch_id, source_id),
        )
        draft_id = db.execute(
            "INSERT INTO bulk_draft(batch_id,source_id,event_code,status) VALUES (%s,%s,'nul','queued') RETURNING id",
            (batch_id, source_id),
        ).fetchone()[0]

    asyncio.run(collection.collect_draft(draft_id, final_attempt=True))

    with psycopg.connect(migrated_url) as db:
        draft = db.execute("SELECT status,error,payload FROM bulk_draft WHERE id=%s", (draft_id,)).fetchone()
        source = db.execute(
            "SELECT status,error FROM bulk_source WHERE batch_id=%s AND source_id=%s", (batch_id, source_id)
        ).fetchone()
    assert draft[0] == "failed" and draft[2] is None
    assert "Private" not in draft[1]
    assert source[0] == "failed" and "Private" not in source[1]



def test_bulk_approval_rebuilds_running_rating_once_per_package(bulk_client, migrated_url, monkeypatch):
    from datetime import date, timedelta

    import psycopg

    from app.modules.bulk_collection import collection

    start_date = date.today() - timedelta(days=1)
    titles = {"one": "Лесная дистанция", "two": "Городской стадион"}

    def external(source, event_code):
        event = _protocol(source, event_code, titles[event_code], [1200])
        event["competition"]["date_begin"] = start_date.isoformat()
        event["races"][0]["rows"][0].update({"club_raw": "Сбер", "birth_year": 1990})
        return event

    monkeypatch.setattr(collection, "fetch_event", external)
    with psycopg.connect(migrated_url) as db:
        db.execute(
            "INSERT INTO rating_norm(year,distance_class,gender,value,unit) VALUES (%s,'5000m','M',1200,'s')",
            (start_date.year,),
        )
    batch = _bulk_batch(bulk_client, migrated_url, ["resultszone"],
                        [("resultszone", "one"), ("resultszone", "two")])
    before = bulk_client.get("/api/rating").json()
    assert before["total"] == 0

    path = f"{BASE}/batches/{batch['id']}/approve"
    command = {"draft_ids": [draft for event in batch["events"] for draft in event["draft_ids"]],
               "resolutions": [], "preview_revision": batch["preview_revision"]}
    published = bulk_client.post(path, json=command)
    assert published.status_code == 200, published.text
    result = published.json()
    assert result["rating_version_id"] is not None
    assert result["published_races"] == 2
    current = bulk_client.get("/api/rating").json()
    assert current["version_id"] == result["rating_version_id"]
    [athlete] = current["rows"]
    assert athlete["starts_count"] == 2 and athlete["points"] == 2000

    replay = bulk_client.post(path, json=command)
    assert replay.status_code == 200 and replay.json() == result
    assert bulk_client.get("/api/rating").json() == current

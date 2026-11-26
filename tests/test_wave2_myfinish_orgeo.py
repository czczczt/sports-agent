import asyncio
import json
from contextlib import AbstractContextManager, nullcontext
from dataclasses import replace
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import procrastinate
import psycopg
import pytest
import requests
from fastapi.testclient import TestClient

from app.pipeline import myfinish, orgeo, orgeo_pdf, pilot
from app.pipeline.errors import PilotRejected
from app.worker import pilot_collect_task


def _response(status: int = 200, body: str | bytes = "") -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.encoding = "utf-8"
    response._content = body.encode("utf-8") if isinstance(body, str) else body
    response._content_consumed = True
    return response


@pytest.mark.parametrize("status", [403, 500])
def test_myfinish_reports_protocol_failure(monkeypatch, status):
    get = Mock(return_value=_response(status))
    monkeypatch.setattr(myfinish.requests, "get", get)

    with pytest.raises(PilotRejected, match=rf"protocol data returned HTTP {status}.*manual import"):
        myfinish.fetch_event("9215")

    assert get.call_args.args == (myfinish.DATA_URL,)
    assert get.call_args.kwargs["params"]["evid"] == "9215"
    assert get.call_args.kwargs["params"]["d"] == 2
    assert get.call_args.kwargs["allow_redirects"] is False


def test_myfinish_successful_metadata_is_not_a_final_protocol(monkeypatch):
    monkeypatch.setattr(myfinish.requests, "get", Mock(return_value=_response(body="{}")))

    with pytest.raises(PilotRejected, match="final protocol format is unverified"):
        myfinish.fetch_event("9215")


@pytest.fixture
def orgeo_get(monkeypatch):
    get = Mock()
    monkeypatch.setattr(orgeo.requests.Session, "get", get)
    return get


ORGEO_EVENT = '<link itemprop="url" href="http://orgeo.ru/event/111" rel="author">'
OFFICIAL_EVENT = (
    ORGEO_EVENT
    + """
<div itemscope itemtype="http://schema.org/SportsEvent">
  <meta itemprop="name" content="Тестовый забег">
  <meta itemprop="startDate" content="2026-08-14">
  <meta itemprop="endDate" content="2026-08-15">
  <div itemscope itemtype="http://schema.org/Person"><meta itemprop="name" content="Организатор"></div>
</div>
<a href="/files/event/file/111_0123456789.pdf">Официальные результаты</a>
<a href="/files/event/file/111_9876543210.pdf">Официальные результаты</a>
"""
)


def _protocol_page(
    section: str | None,
    records: list[list[str]],
    *,
    first: bool,
) -> Mock:
    page = Mock()
    lines = (
        ["Соревнования по бегу", "«Тестовый забег»", "15.08.2026", "ПРОТОКОЛ РЕЗУЛЬТАТОВ"]
        if first
        else ["№ Фамилия, имя"]
    )
    if section:
        lines.append(section)
    page.extract_text_lines.return_value = [{"text": line, "top": index * 10} for index, line in enumerate(lines)]
    table = Mock(bbox=(0, 100, 100, 200))
    table.extract.return_value = [[*orgeo_pdf.HEADERS, "Место"], *records]
    page.find_tables.return_value = [table]
    return page


@pytest.fixture
def official_orgeo(monkeypatch: pytest.MonkeyPatch, orgeo_get: Mock) -> Mock:
    records = [
        ["1", "Первая Участница", "", "1985", "", "50", "00:20:55", "", "1"],
        ["2", "Вторая Участница", "", "1990", "", "51", "СОШЁЛ", "", ""],
    ]
    absolute = [
        _protocol_page("Абсолют Ж-21 км", records[:1], first=True),
        _protocol_page(None, records[1:], first=False),
    ]
    category = [_protocol_page("Женщины 21 км, 21.15 км", records, first=True)]

    def open_pdf(stream: BytesIO) -> AbstractContextManager[SimpleNamespace]:
        pages = absolute if stream.read().endswith(b"absolute") else category
        return nullcontext(SimpleNamespace(pages=pages))

    def get(url: str, **_options: object) -> requests.Response:
        if "/event/info/" in url:
            return _response(body=OFFICIAL_EVENT + _orgeo_live_sub(9))
        if url.endswith("0123456789.pdf"):
            return _response(body=b"%PDF-absolute")
        if url.endswith("9876543210.pdf"):
            return _response(body=b"%PDF-category")
        pytest.fail("The adapter attempted to use Live instead of the official PDFs")

    monkeypatch.setattr(orgeo_pdf.pdfplumber, "open", open_pdf)
    orgeo_get.side_effect = get
    return orgeo_get


def _orgeo_live_sub(sub_id):
    return f'<a href="/live/#/example-run/{sub_id}">Live</a>'


def _orgeo_rows(status):
    return _response(
        body=json.dumps(
            {
                "51": {
                    "bib": "51",
                    "group_name": "Group A",
                    "ref_id": "fixture-row",
                    "result_status": status,
                    "finish": "00:29:09" if status == "0" else None,
                    "finish_ms": "85" if status == "0" else "0",
                }
            }
        )
    )


def test_orgeo_reports_event_with_only_official_file(orgeo_get):
    orgeo_get.return_value = _response(
        body=ORGEO_EVENT + '<a href="/files/event/file/111_abcd.pdf">Official results</a>'
    )

    with pytest.raises(PilotRejected, match="no public Live JSON protocol.*manual import"):
        orgeo.fetch_event("example-run")

    orgeo_get.assert_called_once()


def test_orgeo_partial_export_reports_unfinished_sub_event(orgeo_get):
    orgeo_get.side_effect = [
        _response(body=ORGEO_EVENT + _orgeo_live_sub(1) + _orgeo_live_sub(3)),
        _orgeo_rows("0"),
        _orgeo_rows(None),
    ]

    with pytest.raises(PilotRejected, match="incomplete for start 3.*manual import"):
        orgeo.fetch_event("example-run")

    assert [call.args[0] for call in orgeo_get.call_args_list] == [
        "https://orgeo.ru/event/info/example-run",
        "https://orgeo.ru/event/export/event_id/111/sub_id/1/format/json",
        "https://orgeo.ru/event/export/event_id/111/sub_id/3/format/json",
    ]


def test_orgeo_live_results_require_official_protocol(orgeo_get):
    orgeo_get.side_effect = [
        _response(body=ORGEO_EVENT + '<a href="/live/#/example-run">Live</a>' + _orgeo_live_sub(1)),
        _orgeo_rows("0"),
    ]

    with pytest.raises(PilotRejected, match="Live JSON does not certify final results"):
        orgeo.fetch_event("111")


def test_orgeo_imports_official_distance_and_status(official_orgeo: Mock) -> None:
    from app.pipeline.validation import validate_event

    event = orgeo.fetch_event("111")
    validate_event(event)
    assert event["competition"]["date_begin"] == "2026-08-15"
    [protocol] = event["races"]
    assert protocol["race"]["external_id"] == "21150m-f"
    assert protocol["race"]["is_final"] is True
    assert protocol["race"]["distance_km"] == 21.15
    assert [(row["bib"], row["status"], row["official_time_s"], row["place_abs"]) for row in protocol["rows"]] == [
        ("50", "FIN", 1255.0, 1),
        ("51", "DNF", None, None),
    ]
    assert official_orgeo.call_count == 3


def test_orgeo_rejects_disagreement_between_official_documents() -> None:
    day = date(2026, 8, 15)
    row = orgeo_pdf.Row("Тестовый Участник", "50", None, 1985, 1255.0, "FIN", 1)
    absolute = orgeo_pdf.Report(
        "absolute",
        day,
        [orgeo_pdf.Section("M", 5000, [row])],
        "https://example.test/absolute",
    )
    category = orgeo_pdf.Report(
        "category",
        day,
        [orgeo_pdf.Section("M", 5000, [replace(row, time_s=1256.0)])],
        "https://example.test/category",
    )

    with pytest.raises(PilotRejected, match="disagree on participant coverage or results"):
        orgeo_pdf.reconcile_reports(absolute, category)


def test_orgeo_worker_reuses_rows_and_rejects_incomplete_live(
    pilot_client: TestClient,
    migrated_url: str,
    monkeypatch: pytest.MonkeyPatch,
    official_orgeo: Mock,
) -> None:
    monkeypatch.setattr(pilot, "DATABASE_URL", migrated_url)
    assert pilot_client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).is_success

    async def consume() -> None:
        app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=migrated_url))
        app.task(
            name=pilot_collect_task.name,
            queue="collect",
            pass_context=True,
            retry=procrastinate.RetryStrategy(max_attempts=3, wait=0),
        )(pilot_collect_task.func)
        async with app.open_async():
            await app.run_worker_async(queues=["collect"], wait=False)

    def execute() -> dict:
        requested = pilot_client.post(
            "/api/v1/runs",
            json={
                "kind": "collect",
                "source": "orgeo",
                "event_code": "111",
            },
        )
        assert requested.status_code == 202, requested.text
        asyncio.run(consume())
        return pilot_client.get(f"/api/v1/runs/{requested.json()['run_id']}").json()

    def saved() -> list[tuple]:
        with psycopg.connect(migrated_url) as connection:
            return connection.execute("SELECT id, bib, official_time_s, status FROM result ORDER BY bib").fetchall()

    first = execute()
    assert first["status"] == "succeeded" and first["rating_version_id"] is None, first
    original = saved()
    assert [row[1:] for row in original] == [("50", 1255.0, "FIN"), ("51", None, "DNF")]
    assert execute()["status"] == "succeeded"
    assert saved() == original

    live_page = ORGEO_EVENT + '<a href="/live/#/example-run">Live</a>' + _orgeo_live_sub(9)
    official_orgeo.side_effect = [_response(body=live_page), _orgeo_rows(None)] * 4
    rejected = execute()
    assert rejected["status"] == "failed" and "incomplete for start 9" in rejected["error"]
    assert saved() == original


@pytest.mark.parametrize("source", [myfinish, orgeo])
def test_sources_reject_urls_in_place_of_ids(source, monkeypatch):
    get = Mock()
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests, "get", get)

    with pytest.raises(PilotRejected, match="Invalid.*event ID"):
        source.fetch_event("https://example.test/event/1")

    get.assert_not_called()

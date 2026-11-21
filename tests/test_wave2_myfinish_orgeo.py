import json
from unittest.mock import Mock

import pytest
import requests

from app.pipeline import myfinish, orgeo
from app.pipeline.errors import PilotRejected


def _response(status=200, body=""):
    response = requests.Response()
    response.status_code = status
    response.encoding = "utf-8"
    response._content = body.encode("utf-8")
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


def _orgeo_live_sub(sub_id):
    return f'<a href="/live/#/example-run/{sub_id}">Live</a>'


def _orgeo_rows(status):
    return _response(body=json.dumps({"51": {
        "bib": "51", "group_name": "Group A", "ref_id": "fixture-row",
        "result_status": status, "finish": "00:29:09" if status == "0" else None,
        "finish_ms": "85" if status == "0" else "0",
    }}))


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


@pytest.mark.parametrize("source", [myfinish, orgeo])
def test_sources_reject_urls_in_place_of_ids(source, monkeypatch):
    get = Mock()
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests, "get", get)

    with pytest.raises(PilotRejected, match="Invalid.*event ID"):
        source.fetch_event("https://example.test/event/1")

    get.assert_not_called()

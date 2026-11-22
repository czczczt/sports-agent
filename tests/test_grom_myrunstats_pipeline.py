import html
import json
from unittest.mock import Mock

import pytest
import requests

from app.pipeline import grom, myrunstats
from app.pipeline.errors import PilotRejected


def test_grom_reuses_raceresult_rows(monkeypatch):
    monkeypatch.setattr(grom, 'sleep', lambda seconds: None)
    url = "https://grom.place/results/example-run"
    path = f"{url}/discipline/5%20%D0%BA%D0%BC"
    event = (f'<title>Результаты по соревнованиюТестовый забег | grom.place</title>'
             f'<time>19 сентября 2025</time><a href="{path}">5 км</a>')
    raw = {"Bib": 42, "Firstname": "Анна", "Lastname": "Примерова", "Finished": True,
           "Gender": "F", "Club": "SBER Team", "ColumnName1": "Chip Time", "ColumnData1": "18:32",
           "ColumnName2": "Gun Time", "ColumnData2": "18:40", "ColumnName3": "Место среди всех/всего",
           "ColumnData3": "1/1", "ColumnName4": "Место по возрасту/всего", "ColumnData4": "1/1"}
    protocol = f'<race-results :initial-rows="{html.escape(json.dumps([raw]))}"></race-results>'
    bodies = {url: event, path: protocol}

    def get(self, target, *, timeout, allow_redirects):
        assert timeout == (5, 15) and not allow_redirects
        return Mock(status_code=200, text=bodies[target])

    monkeypatch.setattr(requests.Session, "get", get)
    parsed = grom.fetch_event("example-run")
    assert parsed["competition"]["date_begin"] == "2025-09-19"
    assert parsed["competition"]["sport"] == "run"
    item, = parsed["races"]
    assert item["race"]["total_count"] is None
    assert item["race"]["is_final"] is None
    row, = item["rows"]
    assert row["external_participant_id"] == "42"
    assert row["club_raw"] == "SBER Team"
    assert (row["chip_time_s"], row["gun_time_s"], row["place_age_group"]) == (1112, 1120, 1)

    bodies[path] = '<race-results :initial-rows="[]"></race-results>'
    with pytest.raises(PilotRejected, match="empty"):
        grom.fetch_event("example-run")


def test_grom_leaves_transport_timeout_for_queue(monkeypatch):
    def get(self, target, **kwargs):
        raise requests.Timeout()

    monkeypatch.setattr(requests.Session, "get", get)
    with pytest.raises(requests.Timeout):
        grom.fetch_event("example-run")


@pytest.mark.parametrize("duplicate", [False, True])
def test_myrunstats_published_pagination_and_official_source(monkeypatch, duplicate):
    monkeypatch.setattr(myrunstats, 'sleep', lambda seconds: None)
    monkeypatch.setattr(myrunstats, "PAGE_SIZE", 1)
    calls = []

    def get(self, target, *, params, timeout, allow_redirects):
        assert timeout == (5, 15) and not allow_redirects
        path = target.removeprefix(f"{myrunstats.BASE}/api/v1")
        if path == "/events/297":
            payload = {
                "event_id": 297, "event_name": "Тестовый пробег", "event_date": "2025-09-06",
                "event_type": {"type_name": "Run"}, "has_published_protocol": True,
                "distances": [{"event_distance_id": 717, "distance_length": 5000.0, "length_unit": "m"}],
            }
        elif path == "/protocols":
            assert params == {"event_id": "297"}
            payload = [
                {"protocol_id": 500, "protocol_status": "Draft", "is_active": True},
                {"protocol_id": 837, "protocol_status": "Published", "is_active": True, "event_id": 297,
                 "event_distance_id": 717, "distance_name": "5K",
                 "result_url": "https://results.russiarunning.com/event/test-run/results/5km"},
            ]
        else:
            assert path == "/protocols/837/results"
            page = params["page"]
            calls.append(page)
            payload = {
                "page": page, "size": 1, "pages": 2, "total": 2,
                "items": [{"protocol_id": 837, "protocol_id_seq": 7 if duplicate else 6 + page,
                           "public_id": None, "status_id": 1, "is_relay": False,
                           "bib": str(page), "first_name": "Алекс", "last_name": "Примеров", "gender": "M",
                           "finish_chip_time": f"18:3{page}", "finish_gun_time": f"18:4{page}",
                           "finish_position_overall": page, "club_main": "SBER Team"}],
            }
        return Mock(status_code=200, **{"json.return_value": payload})

    monkeypatch.setattr(requests.Session, "get", get)
    if duplicate:
        with pytest.raises(PilotRejected, match="Duplicate MyRunStats participant"):
            myrunstats.fetch_event("297")
    else:
        parsed = myrunstats.fetch_event("297")
        assert parsed["competition"]["canonical_url"] == "https://results.russiarunning.com/event/test-run/results"
        item, = parsed["races"]
        assert item["race"]["total_count"] == 2
        assert item["race"]["distance_km"] == 5
        assert [r["external_participant_id"] for r in item["rows"]] == ["7", "8"]
        assert item["rows"][0]["chip_time_s"] == 1111
        assert item["rows"][0]["club_raw"] == "SBER Team"
    assert calls == [1, 2]


@pytest.mark.parametrize(("source_status", "expected"), [(3, "DNF"), (4, "DSQ")])
def test_myrunstats_preserves_verified_non_finish_statuses(source_status, expected):
    row = myrunstats._row({"protocol_id_seq": 7, "status_id": source_status, "finish_position_overall": 123})
    assert row["status"] == expected
    assert row["place_abs"] is None

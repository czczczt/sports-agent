"""Verify public TopList pagination and TriStats division consistency offline."""
import json

import pytest
import requests

from app.pipeline import toplist, tristats
from app.pipeline.errors import PilotRejected
from app.pipeline.validation import validate_event


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


@pytest.mark.parametrize("incomplete", [False, True])
def test_toplist_keeps_reference_points_and_unknown_elevation(monkeypatch, incomplete):
    distances = [
        {"id": 11, "length": 24, "climb": 1400, "resultsCount": 1},
        {"id": 12, "length": 15, "climb": 0, "resultsCount": 1},
    ]

    def external(self, url, **kwargs):
        if url.endswith("/race/7"):
            return response({
                "id": 7, "kindOfSport": {"id": 10}, "name": "Trail",
                "beginDate": "2025-05-01", "resultsCount": 2, "distances": distances,
            })
        distance = int(url.rsplit("/", 1)[1])
        assert kwargs["params"] == {"from": 0, "length": 50, "sort": "position"}
        rows = [{
            "id": distance, "raceId": 7, "raceDistanceId": distance, "resultStatus": {"name": "-"},
            "raceResult": "02:30:00", "resultType": "time", "position": 1,
            "rating": 42.5 if distance == 11 else None,
            "athlete": {"surname": "Test", "name": "Runner", "gender": {"id": 1}},
        }]
        return response({"from": 0, "length": 50, "total": 1,
                         "competition": [] if incomplete and distance == 12 else rows})

    monkeypatch.setattr(requests.Session, "get", external)
    monkeypatch.setattr(toplist, "sleep", lambda _: None)
    if incomplete:
        with pytest.raises(PilotRejected, match="pagination"):
            toplist.fetch_event("7")
        return

    event = toplist.fetch_event("7")
    validate_event(event)
    assert [item["race"]["elevation_gain_m"] for item in event["races"]] == [1400, None]
    assert [item["rows"][0]["toplist_points"] for item in event["races"]] == [42.5, None]


@pytest.mark.parametrize("division_count", [1, 2])
def test_tristats_verifies_each_division_in_its_own_group(monkeypatch, division_count):
    path = "/ironstar/sirius/half/2025"
    genders = [("M", "M35", "/m35"), ("F", "F35", "/f35")]
    rows = [{
        "ResultId": i, "Sex": gender, "Division": group, "DivisionUrl": division, "Racer": f"Test {i}",
        "Names": ["Swim", "Финиш"], "Times": ["00:30:00", "05:15:00"],
        "SexRank": 1, "DivisionRank": 1,
    } for i, (gender, group, division) in enumerate(genders, 1)]

    def external(self, url, **kwargs):
        if url.endswith("/rus/race" + path):
            return response({
                "RaceId": 9, "Date": "2025-05-01", "RaceUrl": path, "RaceName": "Sirius Half",
                "RacerCount": 2, "FemaleCount": 1,
            })
        if url.endswith("/result" + path):
            return response(rows)
        gender, group, division = next(item for item in genders if url.endswith(item[2]))
        return response({"RaceUrl": path, "DivisionUrl": division, "DivisionName": group,
                         "RacerCount": division_count if gender == "F" else 1})

    monkeypatch.setattr(requests.Session, "get", external)
    monkeypatch.setattr(tristats, "sleep", lambda _: None)
    if division_count != 1:
        with pytest.raises(PilotRejected, match="division protocol"):
            tristats.fetch_event("ironstar__sirius__half__2025")
        return

    event = tristats.fetch_event("ironstar__sirius__half__2025")
    validate_event(event)
    race = event["races"][0]
    assert race["race"]["distance_class"] == "half"
    assert [(row["age_group"], row["place_age_group"]) for row in race["rows"]] == [("M35", 1), ("F35", 1)]


def test_tristats_reports_access_failure_at_the_source(monkeypatch):
    monkeypatch.setattr(requests.Session, "get", lambda self, *a, **kw: response({}, 403))
    with pytest.raises(requests.HTTPError) as error:
        tristats.fetch_event("ironstar__sirius__half__2025")
    assert error.value.response.status_code == 403

from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from app.pipeline import ironstar, russialoppet
from app.pipeline.errors import PilotRejected
from app.pipeline.validation import validate_event


def test_ironstar_keeps_personal_and_relay_finish_and_category_separate(monkeypatch):
    event = {"id": "event", "code": "IronStarTest", "title": "IRONSTAR Test",
             "disciplineCode": "triathlon", "beginDate": "2025-10-12T00:00:00", "races": [
                 {"id": "individual", "name": "Individual", "disciplineCode": "triathlon",
                  "isRelay": False, "distance": 0},
                 {"id": "relay", "name": "Relay", "disciplineCode": "triathlon-relay",
                  "isRelay": True, "distance": 51.5},
             ]}
    personal = {"participantId": "person", "fullName": "Example Athlete", "gender": 0,
                "status": 0, "position": 13, "individualGenderPosition": 11,
                "genderAgeNominationName": "M 35-39", "individualGenderAgePosition": 2,
                "individualAgePosition": 3, "individualResult": "02:12:00",
                "stageResults": [{"individualResult": "00:30:00", "position": 1}]}
    relay = {"teamId": "team", "teamName": "Example Team", "status": 0,
             "position": 9, "genderAgeNominationName": "Relay.Mix", "genderAgeNominationPosition": 4,
             "individualResult": "02:20:00", "participants": [personal],
             "stagesResults": [{"individualResult": "00:28:00", "position": 1}]}

    def relay_request(method, path, body):
        assert method == "POST" and path == "/results/relay/get"
        assert body["raceId"] == "relay" and body["isStagesOn"] is False
        return {"totalCount": 1, "results": [relay]}

    def options(_):
        return {"isFinalProtocol": True, "stagesInfo": [
            {"disciplineCode": "swimming", "stagesInfo": [{"distance": 1.5}]},
            {"disciplineCode": "cycling", "stagesInfo": [{"distance": 18}, {"distance": 40}]},
            {"disciplineCode": "running", "stagesInfo": [{"distance": 5}, {"distance": 10}]},
        ]}
    client = SimpleNamespace(get_event=lambda _: event, race_options=options, _call=relay_request,
                             individual_results=lambda *_: ([personal], 1),
                             s=SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(ironstar, "RRClient", lambda *_args, **_kwargs: client)

    result = ironstar.fetch_event("IronStarTest")
    validate_event(result)
    individual, team = result["races"]
    assert individual["race"]["distance_km"] == 51.5
    assert team["race"]["race_type"] == "relay"
    person_row, team_row = individual["rows"][0], team["rows"][0]
    assert (person_row["place_abs"], person_row["place_age_group"], person_row["chip_time_s"]) == (13, 2, 7920)
    assert (team_row["external_participant_id"], team_row["place_age_group"], team_row["chip_time_s"]) == (
        "team", 4, 8400,
    )
    assert team_row["gender"] is None

    client.race_options = lambda _: {"isFinalProtocol": False}
    with pytest.raises(PilotRejected, match="No final"):
        ironstar.fetch_event("IronStarTest")


def _ski_page(distance, sex, label, rows="", navigation=""):
    return (
        f'<div class="filter-distance"><select><option selected '
        f'value="?distance={distance}&amp;gender={sex}">{label}</option></select></div>'
        + (f'<table class="results-list">{rows}</table>' if rows else "")
        + navigation
    )


def _ski_row(record, group="", group_place="1", duration="1:20:30"):
    cells = ("1", '<a href="/results/p/25/">Пример Атлет</a>', "1990", "", "Команда", "Город", "418",
             duration, "0:00:00", "350", group, group_place, "0:00:00")
    return f'<tr class="results-item" id="bx_123_{record}">' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


@pytest.mark.parametrize("label,distance,distance_km", [
    ("Марафон (50 км)", "marathon-50-km", 50),
    ("Полумарафон (30 км)", "cup30km", 30),
])
def test_russialoppet_verifies_index_count_and_keeps_optional_leader(monkeypatch, label, distance, distance_km):
    root = russialoppet.BASE + "/results/2025/"
    race_url = root + "850/"
    date_url = russialoppet.BASE + "/events/test2025.html"
    count = 3

    def get(_, url, params=None):
        if url == race_url and params is None:
            html = (
                '<h1 id="pagetitle">Марафон 2025 год</h1><p class="link-to-detail">'
                '<a href="/events/test2025.html">Страница марафона</a></p>'
                + _ski_page(distance, "", label)
            )
        elif url == date_url:
            html = ('<p class="hero-subtitle">Сезон 2025</p><time class="race-date" '
                    'datetime="2025-03-01"></time>')
        elif url == root:
            html = f'<h2 class="bx_catalog_tile_title"><a href="{race_url}">Гонка</a><span>Участников: {count}</span></h2>'
        else:
            assert url == race_url and params["distance"] == distance and params["PAGEN_1"] == 1
            sex = params["gender"]
            row = _ski_row(51, "М 35-39") if sex == "M" else _ski_row(52, "Ж 35-39", "3") + _ski_row(53)
            html = _ski_page(distance, sex, label, row)
        return BeautifulSoup(html, "lxml")

    monkeypatch.setattr(russialoppet, "_get", get)
    event = russialoppet.fetch_event("2025-850")
    validate_event(event)
    (race,) = event["races"]
    assert race["race"]["season"] == 2025
    assert race["race"]["series"] == "russialoppet"
    assert race["race"]["distance_km"] == distance_km
    assert event["competition"]["date_begin"] == "2025-03-01"
    with_leader, without_leader, without_group = race["rows"]
    assert with_leader["place_age_group"] == 1
    assert with_leader["chip_time_s"] == 4830
    assert without_leader["age_group"] == "Ж 35-39" and without_leader["place_age_group"] == 3
    assert without_group["gender"] == "F" and without_group["place_age_group"] is None

    count = 4
    with pytest.raises(PilotRejected, match="Incomplete"):
        russialoppet.fetch_event("2025-850")


def test_russialoppet_rejects_redirects_and_bounds_requests(monkeypatch):
    sleeps = []
    monkeypatch.setattr(russialoppet.time, "sleep", sleeps.append)

    def redirect(url, **kwargs):
        assert url == russialoppet.BASE
        assert kwargs == {"params": None, "timeout": (5, 20), "allow_redirects": False}
        return SimpleNamespace(status_code=302, raise_for_status=lambda: None)

    with pytest.raises(PilotRejected, match="Unexpected Russialoppet HTTP response"):
        russialoppet._get(SimpleNamespace(get=redirect), russialoppet.BASE)
    assert sleeps == [0.5]

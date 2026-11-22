"""Anonymized shapes from probeg.org/event/54476/ and /race/129181/."""

import pytest
from bs4 import BeautifulSoup

from app.pipeline import probeg
from app.pipeline.errors import PilotRejected
from app.pipeline.validation import validate_event

EVENT = """
<h1>Городской забег</h1>
<dl>
<dt>Когда</dt><dd>8–9 августа 2026</dd>
<dt>Где</dt><dd><a href="/races/city/31/">Примерск</a><div>Место старта: Парк</div></dd>
<dt>Тип забега</dt><dd>шоссе</dd>
<dt>Дистанции</dt><dd><ul class="event-info-races">
  <li><a href="/race/201/"><b>5 км (2 участника)</b></a></li>
  <li><a href="/race/202/"><b>полумарафон (1 участник)</b></a></li>
  <li><a href="/race/203/">10 км</a></li>
</ul></dd>
<dt>Документы</dt><dd>
  <a href="https://results.russiarunning.com/event/example/results/5km">Протокол</a>
  <a href="https://results.russiarunning.com/event/archive/results">Предварительный протокол</a>
</dd>
</dl>
<a class="race-nav prev" href="/race/200/">Прошлый год</a>
"""
MAN = """
<tr><td>1</td><td><div class="name-row"><a href="/runner/301/"><b>Иван
<span>Иванов</span></b></a></div><span class="only-xs">Примерск</span></td>
<td>7</td><td>Примерск, Россия</td><td>0:20:00</td><td>1</td>
<td>Мужчины<br>(1 из 1)</td><td>41 год</td><td>СБТ</td><td>Грязное время: 0:20:02</td></tr>
"""
WOMAN = """
<tr class="girl"><td>2</td><td><div class="name-row"><b>Анна Сергеева</b></div></td>
<td>8</td><td>Россия</td><td>0:20:03</td><td>1</td>
<td>Женщины<br>(1 из 1)</td><td>1986</td><td></td><td>Грязное время: 0:20:05</td></tr>
"""


def race_html(race, count, first, last, rows, *, has_next=False):
    navigation = '<nav class="pages"><a aria-label="Следующая страница" href="?page=2#raceTable">→</a></nav>'
    return f"""
    <link rel="canonical" href="https://probeg.org/race/{race}/">
    <h1><a href="/event/100/">Городской забег</a></h1>
    <form id="raceTable"></form>
    <p class="muted small">Найдено: {count} · показаны {first}–{last}</p>
    <table class="t results-t">
       <tr><th>Место</th><th>Имя</th><th>Стартовый<br>номер</th>
       <th>Город, страна</th><th>Результат</th><th>Место среди<br>мужчин/женщин</th>
       <th>Группа<br>(место в ней)</th><th>Дата рождения,<br>возраст</th>
       <th>Клуб</th><th>Комментарий</th></tr>
       {rows}
    </table>
    {navigation if has_next else ''}
    """


@pytest.fixture
def pages(monkeypatch):
    second_race_row = MAN.replace("<td>7</td>", "<td></td>").replace("0:20:", "1:20:")
    pages = {
        "/event/100/": EVENT,
        "/race/201/": race_html(201, 2, 1, 1, MAN, has_next=True),
        "/race/201/?page=2": race_html(201, 2, 2, 2, WOMAN),
        "/race/202/": race_html(202, 1, 1, 1, second_race_row),
    }
    monkeypatch.setattr(probeg, "_page", lambda session, path: BeautifulSoup(pages[path], "html.parser"))
    return pages


def test_collect_probeg_event(pages):
    event = probeg.fetch_event("100")
    validate_event(event)
    competition = event["competition"]
    assert competition["external_id"] == "100"
    assert competition["date_begin"] == "2026-08-08"
    assert competition["date_end"] == "2026-08-09"
    assert competition["canonical_url"] == "https://results.russiarunning.com/event/example/results"
    assert competition["place"] == "Примерск"
    assert competition["address"] == "Парк"

    first, second = event["races"]
    assert (first["race"]["external_id"], first["race"]["total_count"], first["race"]["distance_km"]) == ("201", 2, 5)
    assert (second["race"]["external_id"], second["race"]["total_count"], second["race"]["distance_km"]) == ("202", 1, 21.0975)
    linked, unlinked = first["rows"]
    assert linked["full_name_raw"] == "Иван Иванов"
    assert linked["source_profile_id"] == "301"
    assert linked["external_participant_id"] == "bib:7"
    assert (linked["chip_time_s"], linked["gun_time_s"], linked["age"]) == (1200, 1202, 41)
    assert unlinked["source_profile_id"] is None
    assert unlinked["external_participant_id"] == "bib:8"
    assert (unlinked["gender"], unlinked["birth_year"]) == ("F", 1986)
    assert second["rows"][0]["external_participant_id"] == "profile:301"
    assert event == probeg.fetch_event("100")


def test_result_identity_survives_profile_link_added(pages):
    initial = probeg.fetch_event("100")["races"][0]["rows"][1]
    pages["/race/201/?page=2"] = pages["/race/201/?page=2"].replace(
        "<b>Анна Сергеева</b>", '<a href="/runner/302/"><b>Анна Сергеева</b></a>'
    )
    updated = probeg.fetch_event("100")["races"][0]["rows"][1]
    assert initial["external_participant_id"] == updated["external_participant_id"]
    assert updated["source_profile_id"] == "302"


def test_nonfinisher_is_included(pages):
    pages["/race/201/?page=2"] = race_html(201, 2, 2, 2, WOMAN.replace("0:20:03", "DNS"))
    event = probeg.fetch_event("100")
    validate_event(event)
    row = event["races"][0]["rows"][1]
    assert row["status"] == "DNS"
    assert row["chip_time_s"] is None


@pytest.mark.parametrize(("replacement", "diagnostic"), [
    (race_html(201, 3, 2, 2, WOMAN), "count differs"),
    (race_html(201, 2, 1, 1, MAN), "out of sequence"),
    (race_html(201, 2, 2, 2, MAN), "Duplicate"),
    (race_html(201, 2, 2, 2, WOMAN).replace("/event/100/", "/event/999/"), "does not belong"),
    (race_html(201, 2, 2, 2, WOMAN.replace("0:20:03", "ошибка")), "result time"),
])
def test_reject_incomplete_or_corrupt_protocol(pages, replacement, diagnostic):
    pages["/race/201/?page=2"] = replacement
    with pytest.raises(PilotRejected, match=diagnostic):
        probeg.fetch_event("100")


def test_registration_and_preliminary_protocol_are_not_canonical(pages):
    pages["/event/100/"] = pages["/event/100/"].replace(">Протокол<", ">Регистрация<")
    assert probeg.fetch_event("100")["competition"]["canonical_url"] is None


@pytest.mark.parametrize("code", ["", "100?gender=1", "//example.org/", "event/100", "0"])
def test_reject_invalid_event_id(code):
    with pytest.raises(PilotRejected, match="event ID"):
        probeg.fetch_event(code)



def test_trail_is_not_classified_as_road_running(pages):
    pages["/event/100/"] = pages["/event/100/"].replace("шоссе", "кросс или трейл")
    event = probeg.fetch_event("100")
    validate_event(event)
    assert event["competition"]["sport"] == "trail"
    assert all(item["race"]["sport"] == "trail" for item in event["races"])

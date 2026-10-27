"""Синтетические страницы в формате площадок. Фамилии выдуманные: реальные ФИО в тесты не кладём."""
import html
import json

RUNC = "https://results.runc.run"


def runc_url(code: str, distance_id: str, common: bool = False) -> str:
    return f"{RUNC}/event/{code}/finishers/distance/{distance_id}/{'common/' if common else ''}page/1/page_size/1000/"


def runc_page(code: str, rows: list[tuple]) -> str:
    """rows: (место, ФИО, «М34», номер, результат). Вёрстка — как у results.runc.run."""
    items = "".join(f"""
<a class="results-table__values" href="/event/{code}/result/{bib}/">
 <div class="results-table__values-item results-table__col-place"><div class="results-table__values-item-place">{place}</div></div>
 <div class="results-table__values-item results-table__col-name">
  <div class="results-table__values-item-name">{name}</div>
  <div class="results-table__values-item-country">Россия, {grp}</div></div>
 <div class="results-table__values-item results-table__col-number">{bib}</div>
 <div class="results-table__values-item results-table__col-pace">3:00</div>
 <div class="results-table__values-item text-r results-table__col-result">{result}</div>
</a>""" for place, name, grp, bib, result in rows)
    return (f'<h3 class="results-top__heading">Участники <span class="results-top__heading-count">({len(rows)})'
            f"</span></h3>{items}")


def grom_page(rows: list[dict]) -> str:
    """rows: словари в формате :initial-rows grom.place (данные RaceResult)."""
    return f'<div><results-table :initial-rows="{html.escape(json.dumps(rows, ensure_ascii=False), quote=True)}">' \
           f"</results-table></div>"


def grom_row(bib, last, first, gender, place, finished=True, chip="0:40:00,00", club="", age_group="Male 25-29"):
    names = {1: "Место среди всех/всего", 2: "Место по полу/всего", 3: "Chip Time", 4: "Gun Time"}
    data = {1: place, 2: place, 3: chip, 4: chip}
    row = {"Bib": bib, "Lastname": last, "Firstname": first, "Gender": gender, "AgeGroup": age_group,
           "Club": club, "Finished": finished, "Time": chip, "DateOfBirth": "1990", "Relay": "No"}
    for k in names:
        row[f"ColumnName{k}"], row[f"ColumnData{k}"] = names[k], data[k]
    return row

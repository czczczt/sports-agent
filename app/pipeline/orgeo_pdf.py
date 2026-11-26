"""Parse the paired absolute and age-group PDFs published by an Orgeo organizer."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import Literal

import pdfplumber
from pdfminer.pdfexceptions import PDFException
from pdfplumber.table import Table
from pypdfium2 import PdfiumError

from app.pipeline.errors import PilotRejected
from parser_running.normalize import to_seconds

Gender = Literal["M", "F"]
ReportKind = Literal["absolute", "category"]
Key = tuple[Gender, int]
HEADERS = (
    "№",
    "Фамилия, имя",
    "Коллектив",
    "ГР",
    "Разряд",
    "Номер",
    "Результат",
    "Отставание",
)
KM = r"\d+(?:[.,]\d{1,3})?"
ABSOLUTE = re.compile(rf"Абсолют\s+([МЖ])\s*-\s*({KM})\s*км", re.I)
CATEGORY = re.compile(rf"(Девушки|Женщины|Юноши|Мужчины)\b.*,\s*({KM})\s*км", re.I)
FOOTER = re.compile(r"Главный (?:судья|секретарь):", re.I)
STATUS = {
    "СОШЕЛ": "DNF",
    "НЕ СТАРТОВАЛ": "DNS",
    "ДИСКВАЛИФИЦИРОВАН": "DSQ",
    "DNF": "DNF",
    "DNS": "DNS",
    "DSQ": "DSQ",
    "NC": "NC",
}
MAX_PAGES = 80


@dataclass(frozen=True)
class Row:
    name: str
    bib: str
    club: str | None
    birth_year: int
    time_s: float | None
    status: str
    place: int | None

    def identity(self) -> tuple[str, int, float | None, str]:
        return self.name, self.birth_year, self.time_s, self.status


@dataclass
class Section:
    gender: Gender
    meters: int
    rows: list[Row] = field(default_factory=list)


@dataclass(frozen=True)
class Report:
    kind: ReportKind
    day: date
    sections: list[Section]
    url: str


def _normalize(value: str) -> str:
    return " ".join(value.split()).strip(' «»"').casefold()


def _section(title: str) -> tuple[ReportKind, Section] | None:
    absolute = ABSOLUTE.fullmatch(title)
    category = CATEGORY.fullmatch(title)
    if absolute:
        return "absolute", Section("M" if absolute[1].upper() == "М" else "F", _meters(absolute[2]))
    if category:
        gender: Gender = "F" if category[1].casefold() in {"девушки", "женщины"} else "M"
        return "category", Section(gender, _meters(category[2]))
    return None


def _meters(text: str) -> int:
    meters = round(float(text.replace(",", ".")) * 1000)
    if not 0 < meters <= 500_000:
        raise PilotRejected("Orgeo PDF contains an invalid distance")
    return meters


def _add_rows(section: Section, table: list[list[str | None]], day: date) -> None:
    if not table:
        raise PilotRejected("Orgeo PDF contains an empty table")
    header, *records = table
    columns = [index for index, value in enumerate(header) if value is not None]
    labels = tuple(header[index] for index in columns)
    if labels not in (HEADERS, (*HEADERS, "Место")):
        raise PilotRejected("Orgeo PDF has unrecognized protocol columns")
    footer_seen = False
    for record in records:
        if len(record) != len(header):
            raise PilotRejected("Orgeo PDF has an incomplete table row")
        cells = [" ".join((record[index] or "").split()) for index in columns]
        if FOOTER.fullmatch(cells[0]):
            footer_seen = True
            continue
        if footer_seen or any(value for i, value in enumerate(record) if i not in columns):
            raise PilotRejected("Orgeo PDF table has unexpected content")
        number, name, club, year, _, bib, result, _, *place = cells
        if number != str(len(section.rows) + 1):
            raise PilotRejected("Orgeo PDF row numbering is incomplete")
        if not name or not re.fullmatch(r"[0-9]+", bib) or not year.isdecimal():
            raise PilotRejected("Orgeo PDF row has incomplete participant identity")
        if not 1900 <= int(year) <= day.year:
            raise PilotRejected("Orgeo PDF row has an invalid birth year")
        seconds = to_seconds(result)
        status = STATUS.get(result.upper().replace("Ё", "Е"))
        if seconds is not None and seconds > 0:
            status = "FIN"
        elif status is None or (place and place[0]):
            raise PilotRejected("Orgeo PDF row has an unknown result or status")
        rank = None
        if status == "FIN":
            rank = len(section.rows) + 1
            if place:
                if not place[0].isdecimal() or not 1 <= int(place[0]) <= rank:
                    raise PilotRejected("Orgeo PDF finisher has an invalid place")
                rank = int(place[0])
            elif section.rows:
                previous = section.rows[-1].time_s
                if previous is None or seconds is None or seconds <= previous:
                    raise PilotRejected("Orgeo PDF order does not establish a finisher's place")
        section.rows.append(Row(name, bib, club or None, int(year), seconds, status, rank))


def read_report(payload: bytes, url: str, title: str) -> Report:
    if not payload.startswith(b"%PDF-"):
        raise PilotRejected("Orgeo official attachment is not a PDF")
    try:
        with pdfplumber.open(BytesIO(payload)) as pdf:
            if not 1 <= len(pdf.pages) <= MAX_PAGES:
                raise PilotRejected("Orgeo PDF page count is outside supported bounds")
            return _read_pages(pdf.pages, url, title)
    except PilotRejected:
        raise
    except (PDFException, PdfiumError, ValueError, TypeError, IndexError, KeyError) as exc:
        raise PilotRejected("Orgeo official PDF is unreadable") from exc


def _read_pages(pages: list[pdfplumber.page.Page], url: str, title: str) -> Report:
    kind: ReportKind | None = None
    sections: list[Section] = []
    day: date | None = None
    for index, page in enumerate(pages):
        lines = page.extract_text_lines()
        if index == 0:
            heading = [line["text"] for line in lines[:8]]
            dates = [re.match(r"(\d{2}\.\d{2}\.\d{4})\b", line) for line in heading]
            date_value = next((match[1] for match in dates if match), None)
            if (
                "ПРОТОКОЛ РЕЗУЛЬТАТОВ" not in heading
                or not any(_normalize(line) == _normalize(title) for line in heading)
                or date_value is None
            ):
                raise PilotRejected("Orgeo PDF title or date does not match the event")
            if not any(re.search(r"\bпо бегу\b", line, re.I) for line in heading):
                raise PilotRejected("Orgeo official PDF is not a supported running protocol")
            day = datetime.strptime(date_value, "%d.%m.%Y").date()
        else:
            if not lines:
                raise PilotRejected("Orgeo PDF has a page without readable text")

        tables = page.find_tables()
        if not tables or day is None:
            raise PilotRejected("Orgeo PDF has missing or unrecognized protocol tables")
        contents: list[tuple[float, Table | tuple[ReportKind, Section]]] = [(table.bbox[1], table) for table in tables]
        contents.extend((line["top"], parsed) for line in lines if (parsed := _section(line["text"])) is not None)
        # A heading may be at the foot of one page while its table starts on the next.
        for _, content in sorted(contents, key=lambda item: item[0]):
            if isinstance(content, tuple):
                if sections and not sections[-1].rows:
                    raise PilotRejected("Orgeo PDF contains a section without a table")
                section_kind, section = content
                if kind not in (None, section_kind):
                    raise PilotRejected("Orgeo PDF mixes absolute and category sections")
                kind = section_kind
                sections.append(section)
            elif not sections:
                raise PilotRejected("Orgeo PDF table has no identified distance and group")
            else:
                _add_rows(sections[-1], content.extract(), day)
    if not kind or day is None or any(not section.rows for section in sections):
        raise PilotRejected("Orgeo PDF has no complete protocol")
    return Report(kind, day, sections, url)


def reconcile_reports(absolute: Report, category: Report) -> list[dict[str, object]]:
    references: dict[tuple[Gender, str], list[tuple[int, Row]]] = defaultdict(list)
    for section in category.sections:
        for row in section.rows:
            references[section.gender, row.bib].append((section.meters, row))

    races: list[dict[str, object]] = []
    seen: set[Key] = set()
    for section in absolute.sections:
        rows: list[dict[str, object]] = []
        distances: set[int] = set()
        for row in section.rows:
            matches = references[section.gender, row.bib]
            eligible = [
                index
                for index, (meters, detail) in enumerate(matches)
                if abs(meters - section.meters) <= 250 and detail.identity() == row.identity()
            ]
            if len(eligible) != 1:
                raise PilotRejected("Orgeo official protocols disagree on participant coverage or results")
            meters, _ = matches.pop(eligible[0])
            distances.add(meters)
            rows.append(
                {
                    "external_participant_id": row.bib,
                    "bib": row.bib,
                    "full_name_raw": row.name,
                    "gender": section.gender,
                    "birth_year": row.birth_year,
                    "club_raw": row.club,
                    "official_time_s": row.time_s,
                    "status": row.status,
                    "place_abs": row.place,
                    "place_gender": row.place,
                }
            )
        if len(distances) != 1:
            raise PilotRejected("Orgeo official protocols disagree on the distance")
        meters = distances.pop()
        key = section.gender, meters
        if key in seen:
            raise PilotRejected("Orgeo official PDF lists the same group twice")
        seen.add(key)
        gender = "мужчины" if section.gender == "M" else "женщины"
        races.append(
            {
                "race": {
                    "external_id": f"{meters}m-{section.gender.lower()}",
                    "name_raw": f"{meters / 1000:g} км — {gender}",
                    "distance_km": meters / 1000,
                    "is_final": True,
                    "sport": "run",
                    "race_type": "individual",
                    "place_by": "official",
                    "url": absolute.url,
                    "total_count": len(rows),
                },
                "rows": rows,
            }
        )
    if any(references.values()):
        raise PilotRejected("Orgeo category protocol has additional participants")
    return races

"""OCR ФИО, которые в PDF нарисованы картинкой (протоколы WSRP, напечатанные через doPDF).

Как ищем ячейку: на странице находим строку по стартовому номеру (колонка "Ст.№") и месту,
а ячейку ФИО берём между правым краем номера и левым краем даты рождения. Вырезаем этот
прямоугольник, рендерим в 400 dpi и распознаём Tesseract (rus, одна строка: --psm 7).

Модель rus.traineddata лежит в ./tessdata (вызываем с --tessdata-dir, права администратора не нужны).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

TESSDATA = Path(__file__).parent / "tessdata"
TESSERACT = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DOB_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4}|(19|20)\d{2})$")
RESOLUTION = 400


@dataclass
class RowCell:
    page: int
    bbox: tuple[float, float, float, float]  # x0, top, x1, bottom
    has_text: bool                             # в ячейке есть текстовый слой (для оценки точности)
    text: str                                  # текст ячейки из текстового слоя (если есть)


def find_name_cells(pdf: pdfplumber.PDF) -> dict[tuple[int | None, int], RowCell]:
    """(место, номер) -> ячейка ФИО(+регион).
    Строки финишёров: "место номер [ФИО] дата ...". Строки секций НС/НФ: "номер [ФИО] дата ..." -> (None, номер)."""
    cells = {}
    for pi, page in enumerate(pdf.pages):
        words = page.extract_words()
        rows: dict[int, list[dict]] = {}
        for w in words:
            rows.setdefault(round(w["top"]), []).append(w)
        # слова одной строки могут отличаться по top на 1-2 pt — склеиваем соседние ключи
        merged: list[list[dict]] = []
        for top in sorted(rows):
            if merged and abs(merged[-1][0]["top"] - top) < 3:
                merged[-1] += rows[top]
            else:
                merged.append(list(rows[top]))
        for row in merged:
            row.sort(key=lambda w: w["x0"])
            if len(row) < 2 or not row[0]["text"].isdigit():
                continue
            if row[1]["text"].isdigit() and not DOB_RE.match(row[1]["text"]):
                place, bib, bib_w, start = int(row[0]["text"]), int(row[1]["text"]), row[1], 2
            else:
                place, bib, bib_w, start = None, int(row[0]["text"]), row[0], 1
            dob = next((w for w in row[start:] if DOB_RE.match(w["text"])), None)
            if dob is None:
                continue
            x0, x1 = bib_w["x1"] + 2, dob["x0"] - 2
            if x1 - x0 < 10:
                continue
            top = min(w["top"] for w in row) - 2
            bottom = max(w["bottom"] for w in row) + 2
            inside = [w["text"] for w in row if w["x0"] >= x0 - 1 and w["x1"] <= x1 + 1]
            cells[(place, bib)] = RowCell(pi, (x0, top, x1, bottom), bool(inside), " ".join(inside))
    return cells


def ocr_cell(page: pdfplumber.page.Page, bbox) -> str:
    img = page.crop(bbox).to_image(resolution=RESOLUTION).original.convert("L")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cell.png"
        img.save(p)
        out = subprocess.run([TESSERACT, str(p), "stdout", "-l", "rus", "--psm", "7",
                              "--tessdata-dir", str(TESSDATA)],
                             capture_output=True, text=True, encoding="utf-8")
    return clean(out.stdout)


def clean(s: str) -> str:
    s = s.replace("\n", " ").strip()
    s = re.sub(r"[|_—–\[\]{}()«»\"']", " ", s)
    toks = re.sub(r"\s+", " ", s).strip().split()
    # код региона OCR иногда читает со строчной буквой: "оМС", "ВЛг"
    if toks and 2 <= len(toks[-1]) <= 4 and toks[-1].isalpha() and sum(c.isupper() for c in toks[-1]) >= 2:
        toks[-1] = toks[-1].upper()
    return " ".join(toks)


def ocr_rows(pdf_path: Path, keys: list[tuple[int | None, int]]) -> dict[tuple[int | None, int], str]:
    """OCR для конкретных строк (место, номер)."""
    out = {}
    with pdfplumber.open(pdf_path) as pdf:
        cells = find_name_cells(pdf)
        for k in keys:
            c = cells.get(k)
            if c is not None:
                out[k] = ocr_cell(pdf.pages[c.page], c.bbox)
    return out

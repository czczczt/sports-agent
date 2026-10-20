"""Оценка точности OCR на строках, где ФИО есть текстом.

Берём ячейку ФИО(+регион) у строк с текстовым слоем, распознаём её как картинку тем же способом,
что и в боевом режиме (ocr_names.ocr_cell), и сравниваем с текстом.
Метрики: доля полностью верных ячеек (exact), CER — доля ошибок по символам (расстояние Левенштейна / длина).

    python eval_ocr.py --per-pdf 8 --max-pdfs 45
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import pandas as pd
import pdfplumber

import sbr_crawler as cr
from ocr_names import find_name_cells, ocr_cell
from parse_protocol import split_ident

P = Path(__file__).parent / "data" / "processed"


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def norm(s: str) -> str:
    return " ".join(s.replace("Ё", "Е").replace("ё", "е").split())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-pdf", type=int, default=8)
    ap.add_argument("--max-pdfs", type=int, default=45)
    args = ap.parse_args()
    rnd = random.Random(42)

    urls = []
    for f in sorted(P.glob("races_*.csv")):
        tag = f.stem.removeprefix("races_")
        races = pd.read_csv(f)
        races = races[~races["discipline"].isin(["relay", "mixed_relay", "single_mixed_relay"])]  # не личные
        urls += [(tag, u) for u in races["source_url"]]
    rnd.shuffle(urls)
    urls = urls[: args.max_pdfs]

    rows = []
    for tag, url in urls:
        path = cr._cache_path(url, ".bin")
        with pdfplumber.open(path) as pdf:
            producer = pdf.metadata.get("Producer", "")
            cells = [c for c in find_name_cells(pdf).values()
                     if c.has_text and any(ch.islower() for ch in c.text)]
            for c in rnd.sample(cells, min(args.per_pdf, len(cells))):
                got = norm(ocr_cell(pdf.pages[c.page], c.bbox))
                truth = norm(c.text)
                t, g = split_ident(truth) or {}, split_ident(got) or {}
                same = lambda k: norm(str(t.get(k) or "")).upper() == norm(str(g.get(k) or "")).upper()
                rows.append({"tag": tag, "producer": producer, "truth": truth, "ocr": got,
                             "exact": got == truth,
                             "last_name": same("last_name"), "first_name": same("first_name"),
                             "last_first": same("last_name") and same("first_name"),
                             "middle_name": same("middle_name"), "region": same("region_code"),
                             "edits": levenshtein(got, truth), "len": len(truth)})
    df = pd.DataFrame(rows)
    df.to_csv(P / "ocr_eval.csv", index=False, encoding="utf-8-sig")

    def summary(d: pd.DataFrame) -> dict:
        return {"ячеек": len(d), "вся_ячейка": round(d.exact.mean(), 4),
                "фамилия": round(d.last_name.mean(), 4), "имя": round(d.first_name.mean(), 4),
                "фамилия+имя": round(d.last_first.mean(), 4), "отчество": round(d.middle_name.mean(), 4),
                "регион": round(d.region.mean(), 4), "CER": round(d.edits.sum() / d.len.sum(), 5)}

    res = {"всего": summary(df),
           "по_выборкам": {t: summary(g) for t, g in df.groupby("tag")},
           "по_PDF_генератору": {p or "?": summary(g) for p, g in df.groupby("producer")},
           "ошибки": df[~df.exact][["truth", "ocr"]].head(30).values.tolist()}
    (P / "ocr_eval.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ok", res["всего"])


if __name__ == "__main__":
    main()

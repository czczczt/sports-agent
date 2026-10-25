"""Прогон: сезон СБР -> итоговые протоколы -> results.csv + отчёт о качестве.

    python run.py --season 2025-2026 --filter kubok-rossii --max-races 30
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

import sbr_base
import sbr_crawler as cr
from ocr_names import ocr_rows
from parse_protocol import parse_pdf, split_ident

OUT = Path(__file__).parent / "data" / "processed"


def fill_names_by_ocr(results, pdf_path: Path, stats: Counter) -> None:
    """ФИО, нарисованные картинкой, распознаём OCR. Проверка — дальше, в sbr_base.enrich
    (совпадение ФИО + даты рождения с базой СБР)."""
    missing = [r for r in results if r.name_missing]
    if not missing:
        return
    texts = ocr_rows(pdf_path, [(r.place, r.bib) for r in missing])
    for r in missing:
        stats["ocr_attempted"] += 1
        ident = split_ident(texts.get((r.place, r.bib), ""))
        if ident is None or ident["name_missing"]:
            continue
        stats["ocr_filled"] += 1
        r.last_name, r.first_name, r.middle_name = ident["last_name"], ident["first_name"], ident["middle_name"]
        r.region_code = r.region_code or ident["region_code"]
        r.name_missing, r.name_source = False, "ocr"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2025-2026")
    ap.add_argument("--filter", default="", help="подстрока в URL соревнования, напр. kubok-rossii")
    ap.add_argument("--max-races", type=int, default=20)
    ap.add_argument("--tag", default="", help="суффикс имён выходных файлов")
    args = ap.parse_args()

    comps = [c for c in cr.list_competitions(args.season) if args.filter in c]
    print(f"соревнований: {len(comps)}")

    races_out, results_out, report = [], [], []
    stats = Counter()
    for comp in comps:
        for race in cr.list_races(comp):
            if stats["races"] >= args.max_races:
                break
            stats["races"] += 1
            files = cr.list_protocols(race)
            fp = cr.final_protocol(files)
            row = {"race_id": race.race_id, "title": race.title, "competition_url": comp,
                   "files": [f.label for f in files]}
            if fp is None:
                stats["no_final_protocol"] += 1
                report.append({**row, "status": "нет итогового протокола"})
                continue
            if not fp.url.lower().endswith(".pdf"):
                stats["not_pdf"] += 1
                report.append({**row, "status": f"не PDF: {fp.url}"})
                continue
            pdf_path = cr._cache_path(fp.url, ".bin")
            cr.fetch(fp.url, binary=True)
            try:
                p = parse_pdf(pdf_path, race.race_id, args.season, fp.url)
            except Exception as e:  # noqa: BLE001 — прототип: фиксируем и идём дальше
                stats["parse_error"] += 1
                report.append({**row, "status": f"ошибка: {type(e).__name__}: {e}"})
                continue
            fill_names_by_ocr(p.results, pdf_path, stats)
            checks = p.checks()
            ok = bool(p.results) and all(checks.values()) and not p.unparsed_lines
            stats["parsed_ok" if ok else "parsed_with_issues"] += 1
            stats["results"] += len(p.results)
            races_out.append(p.race.model_dump())
            results_out += [{**r.model_dump(), "shooting": json.dumps(r.shooting)} for r in p.results]
            report.append({**row, "status": "ok" if ok else "есть проблемы",
                           "discipline": p.race.discipline, "n_results": len(p.results),
                           "shooting_cols": p.shooting_cols, "footer": p.footer_counts,
                           "checks": checks, "unparsed_lines": p.unparsed_lines[:5]})
        if stats["races"] >= args.max_races:
            break

    OUT.mkdir(parents=True, exist_ok=True)
    races_df, results_df = pd.DataFrame(races_out), pd.DataFrame(results_out)
    sbr = {}
    if not results_df.empty:
        matcher = sbr_base.Matcher(sbr_base.load_athletes())
        results_df, sbr = sbr_base.enrich(results_df, races_df, matcher)
        sbr["eval_recovery"] = sbr_base.evaluate_recovery(results_df, races_df, matcher)

    sfx = f"_{args.tag}" if args.tag else ""
    races_df.to_csv(OUT / f"races{sfx}.csv", index=False, encoding="utf-8-sig")
    results_df.to_csv(OUT / f"results{sfx}.csv", index=False, encoding="utf-8-sig")
    (OUT / f"report{sfx}.json").write_text(json.dumps({"stats": stats, "sbr_base": sbr, "races": report},
                                                     ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(dict(stats))
    print(json.dumps(sbr, ensure_ascii=False))


if __name__ == "__main__":
    main()

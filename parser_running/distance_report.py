"""Read-only G9 and before/after scoring audit for PostgreSQL or a legacy snapshot."""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import date
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from distance_classification import classify, load_synonyms
from scoring import calculate, NORMS_2026, load_norms

GOLDEN = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'distance_g9.csv'


def _audit(races: list[dict], rows: Iterable[dict], norms: list[dict],
           synonyms: list[dict] | None, labels: Path) -> dict:
    with labels.open(encoding='utf-8', newline='') as f:
        golden = {(r['name'], int(r['distance_m']) if r['distance_m'] else None):
                  r['expected_class'] or None for r in csv.DictReader(f)}
    contexts = {}
    actual: dict[tuple, set] = {}
    for race in races:
        classification = classify(race, synonyms)
        # calculate also accepts already classified input, preserving the #9 pure API.
        before = {k: race.get(k) for k in ('distance_type', 'discipline', 'date_begin', 'sport_type', 'race_type')}
        after = before | {'distance_type': classification['distance_class'],
                          'discipline': classification['discipline']}
        contexts[race['id']] = (before, after)
        actual.setdefault((race.get('name') or '', race['distance_m']), set()).add(classification['distance_class'])
    totals: list[Counter[str]] = [Counter(), Counter()]
    classes: list[Counter] = [Counter(), Counter()]
    changed = 0
    for row in rows:
        points = []
        for i, context in enumerate(contexts[row['race_id']]):
            outcome = calculate(row, context, norms)
            totals[i]['total'] += 1
            totals[i]['scored' if outcome['points'] is not None else 'unscored'] += 1
            if outcome['points'] is not None:
                classes[i][context['distance_type']] += 1
            points.append(outcome['points'])
        changed += points[0] != points[1]
    mismatches, unlabelled, false_negatives = [], [], []
    correct = labelled = 0
    for (name, metres), found in sorted(actual.items(), key=lambda item: (item[0][0], item[0][1] or 0)):
        detail = {'name': name, 'distance_m': metres, 'actual_classes': sorted(found, key=lambda c: c or '')}
        if (name, metres) not in golden:
            unlabelled.append(detail)
            continue
        labelled += 1
        expected = golden[name, metres]
        if found == {expected}:
            correct += 1
        else:
            mismatches.append(detail | {'expected_class': expected})
            if expected is not None and None in found:
                false_negatives.append(detail | {'expected_class': expected})
    return {
        'before': {**{k: totals[0][k] for k in ('total', 'scored', 'unscored')}, 'classes': dict(sorted(classes[0].items()))},
        'after': {**{k: totals[1][k] for k in ('total', 'scored', 'unscored')}, 'classes': dict(sorted(classes[1].items()))},
        'changed_scores': changed,
        'g9': {'unique_pairs': len(actual), 'labelled_pairs': labelled, 'correct_pairs': correct,
               'accuracy': correct / labelled if labelled else None,
               'coverage': labelled / len(actual) if actual else None,
               'unlabelled_pairs': unlabelled, 'mismatches': mismatches, 'false_negatives': false_negatives}}


def report(con, labels: Path = GOLDEN) -> dict:
    """Audit existing PostgreSQL data without migrations, recalculation or writes."""
    from psycopg.rows import dict_row
    import uuid
    with con.cursor(row_factory=dict_row) as cur:
        races = cur.execute('''SELECT ra.id,ra.name,ra.distance_m,ra.distance_type,ra.race_type,
                                      c.name AS competition_name,c.date_begin,c.sport_type,
                                      to_jsonb(ra)->>'discipline' AS discipline,
                                      to_jsonb(ra)->>'class_source' AS class_source,
                                      to_jsonb(ra)->>'distance_class_override' AS distance_class_override
                               FROM race ra JOIN competition c ON c.id=ra.competition_id''').fetchall()
        has_norms = cur.execute("SELECT to_regclass('norm') IS NOT NULL AS present").fetchone()['present']
        has_synonyms = cur.execute("SELECT to_regclass('distance_synonym') IS NOT NULL AS present").fetchone()['present']
    norms = load_norms(con) if has_norms else NORMS_2026
    synonyms = load_synonyms(con) if has_synonyms else None
    with con.cursor(name='distance_audit_' + uuid.uuid4().hex, row_factory=dict_row) as cur:
        cur.execute('''SELECT r.race_id,r.status,r.gender,r.chip_time_s,r.gun_time_s,r.duplicate_of,
                             (to_jsonb(r)->>'distance_km')::float8 AS distance_km FROM result r''')
        return _audit(races, cur, norms, synonyms, labels)


def snapshot_report(path: Path, labels: Path = GOLDEN) -> dict:
    """Audit the original parser's SQLite snapshot in read-only mode."""
    con = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        races = [dict(row) for row in con.execute('''
            SELECT ra.id,ra.name_raw AS name,ra.distance_m,ra.norm_distance AS distance_type,
                   ra.race_type,e.title AS competition_name,e.date_begin,e.sport AS sport_type
            FROM race ra JOIN event e ON e.id=ra.event_id''')]
        for race in races:
            race['date_begin'] = date.fromisoformat(race['date_begin'][:10]) if race['date_begin'] else None
        rows = (dict(r) for r in con.execute('SELECT race_id,status,gender,chip_time_s,gun_time_s,duplicate_of FROM result'))
        return _audit(races, rows, NORMS_2026, None, labels)
    finally:
        con.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sqlite-snapshot', type=Path, help='Read the legacy parser snapshot instead of PostgreSQL')
    ap.add_argument('--labels', type=Path, default=GOLDEN, help='Manually annotated G9 CSV')
    ap.add_argument('--output', type=Path, help='Write JSON to this file')
    args = ap.parse_args()
    if args.sqlite_snapshot:
        output = snapshot_report(args.sqlite_snapshot, args.labels)
    else:
        import db
        import psycopg
        with psycopg.connect(db.database_url(), options='-c default_transaction_read_only=on') as con:
            output = report(con, args.labels)
    text = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()

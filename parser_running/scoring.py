"""Rebuildable running scores over the existing parser distance classes."""
from __future__ import annotations

import math

FORMULA_VERSION = 'run-v1'

# Customer's normative table, 2026: seconds except 24h (achieved kilometres).
_NORM_VALUES = (
    ('60m', 6.84, 7.5), ('100m', 10.62, 11.75), ('200m', 21.65, 24.4),
    ('400m', 47.9, 54.8), ('800m', 111, 127), ('1000m', 142, 165),
    ('1500m', 228, 259), ('1mile', 243, 279), ('3000m', 486, 555),
    ('5000m', 846, 965), ('10000m', 1760, 2028), ('half_marathon', 3900, 4540),
    ('marathon', 8400, 9600), ('100km', 24960, 28800), ('24h', 245, 216),
)
NORMS_2026 = [dict(year=2026, distance_class=cls, gender=gender, value=value,
                   unit='km' if cls == '24h' else 's')
              for cls, male, female in _NORM_VALUES for gender, value in (('M', male), ('F', female))]



def calculate(result: dict, race: dict, norms: list[dict],
              formula_version: str = FORMULA_VERSION) -> dict:
    """Pure result + stored race context + norms -> points and full explanation.

    A present but invalid chip time is rejected, never silently replaced by gun time.
    """
    start = race.get('date_begin')
    breakdown = {
        'sport': 'run', 'class': race.get('distance_type'), 'discipline': race.get('discipline'),
        'gender': result.get('gender'), 'norm_value': None, 'norm_unit': None,
        'norm_year': None, 'norm_year_requested': start.year if start else None,
        'time_kind': None, 'time_s': None, 'formula': None, 'points': None,
        'formula_version': formula_version}

    def missing(reason):
        return {'points': None, 'reason': reason, 'breakdown': breakdown | {'reason': reason}}

    if result.get('duplicate_of') is not None:
        return missing('duplicate')
    if result.get('status') != 'FIN':
        return missing('not_finisher')
    if race.get('sport_type') not in (None, 'run'):
        return missing('unsupported_sport')
    if race.get('race_type') == 'relay':
        return missing('relay')
    if result.get('gender') not in ('M', 'F'):
        return missing('unknown_gender')
    if not start:
        return missing('missing_date')
    if not race.get('distance_type'):
        return missing('unclassified_distance')
    candidates = [n for n in norms if n['distance_class'] == race['distance_type']
                  and n['gender'] == result['gender']]
    if not candidates:
        return missing('missing_norm')
    earlier = [n for n in candidates if n['year'] <= start.year]
    norm = max(earlier, key=lambda n: n['year']) if earlier else min(candidates, key=lambda n: n['year'])
    breakdown.update(norm_value=norm['value'], norm_unit=norm['unit'], norm_year=norm['year'])
    if (not isinstance(norm['value'], (int, float)) or not math.isfinite(norm['value'])
            or norm['value'] <= 0 or norm['unit'] != ('km' if race['distance_type'] == '24h' else 's')):
        breakdown['norm_value'] = str(norm['value'])
        return missing('invalid_norm')
    if race['distance_type'] == '24h':
        km = result.get('distance_km')
        breakdown['distance_km'] = km
        if km is None:
            return missing('missing_distance')
        if not isinstance(km, (int, float)) or not math.isfinite(km) or km <= 0:
            breakdown['distance_km'] = str(km)
            return missing('invalid_distance')
        points = km / norm['value'] * 1000
        if not math.isfinite(points) or points <= 0:
            return missing('invalid_points')
        breakdown.update(formula=f"{km:g} / {norm['value']:g} × 1000", points=points)
        return {'points': points, 'reason': None, 'breakdown': breakdown}
    kind = 'chip' if result.get('chip_time_s') is not None else 'gun'
    seconds = result.get(f'{kind}_time_s')
    breakdown.update(time_kind=kind, time_s=seconds)
    if seconds is None:
        return missing('missing_time')
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        # Non-finite numbers are not JSON values; preserve their diagnostic representation.
        breakdown['time_s'] = str(seconds)
        return missing('invalid_time')
    points = norm['value'] / seconds * 1000
    if not math.isfinite(points) or points <= 0:
        return missing('invalid_points')
    breakdown.update(formula=f"{norm['value']:g} / {seconds:g} × 1000", points=points)
    return {'points': points, 'reason': None, 'breakdown': breakdown}

# Computed layer is initialized explicitly; the parser/security allowlist is unchanged.
DDL = """
CREATE TABLE IF NOT EXISTS norm (
    year integer NOT NULL CHECK (year BETWEEN 1 AND 9999),
    distance_class text NOT NULL,
    gender text NOT NULL CHECK (gender IN ('M', 'F')),
    value double precision NOT NULL CHECK (value > 0 AND value < 'Infinity'::float8),
    unit text NOT NULL CHECK (unit = CASE WHEN distance_class = '24h' THEN 'km' ELSE 's' END),
    PRIMARY KEY (year, distance_class, gender)
);
CREATE TABLE IF NOT EXISTS score (
    result_id bigint NOT NULL REFERENCES result(id) ON DELETE CASCADE,
    formula_version text NOT NULL,
    points double precision CHECK (points > 0 AND points < 'Infinity'::float8),
    reason text,
    breakdown jsonb NOT NULL,
    PRIMARY KEY (result_id, formula_version),
    CHECK ((points IS NOT NULL AND reason IS NULL) OR (points IS NULL AND reason IS NOT NULL))
);
"""


def initialize(con) -> None:
    """Idempotently add the scoring layer; transaction belongs to the caller."""
    con.execute(DDL)


def seed_norms(con) -> None:
    """Insert missing 2026 norms, preserving values already maintained by an admin."""
    initialize(con)
    with con.cursor() as cur:
        cur.executemany('''INSERT INTO norm(year, distance_class, gender, value, unit)
                          VALUES (%(year)s, %(distance_class)s, %(gender)s, %(value)s, %(unit)s)
                          ON CONFLICT (year, distance_class, gender) DO NOTHING''', NORMS_2026)


def load_norms(con) -> list[dict]:
    from psycopg.rows import dict_row
    with con.cursor(row_factory=dict_row) as cur:
        return cur.execute('SELECT * FROM norm ORDER BY year, distance_class, gender').fetchall()


def get_score(con, result_id: int, formula_version: str = FORMULA_VERSION) -> dict | None:
    """Retrieve a stored score or missing-score explanation, retaining full precision."""
    from psycopg.rows import dict_row
    with con.cursor(row_factory=dict_row) as cur:
        return cur.execute('SELECT * FROM score WHERE result_id = %s AND formula_version = %s',
                           (result_id, formula_version)).fetchone()


def recalculate(con, formula_version: str = FORMULA_VERSION) -> dict:
    """Rebuild this version atomically. Other formula versions are retained.

    Stream parser rows in batches; never fetch the entire result table into memory.
    The caller commits the transaction (or rolls it back).
    """
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    import uuid

    with con.transaction():
        initialize(con)
        norms = load_norms(con)
        with con.cursor(name='scoring_' + uuid.uuid4().hex, row_factory=dict_row) as reader, con.cursor() as writer:
            reader.execute('''SELECT r.id, r.status, r.gender, r.chip_time_s, r.gun_time_s, r.duplicate_of,
                                     ra.distance_type, ra.race_type, c.date_begin, c.sport_type
                              FROM result r JOIN race ra ON ra.id = r.race_id
                              JOIN competition c ON c.id = ra.competition_id ORDER BY r.id''')
            while rows := reader.fetchmany(1000):
                batch = []
                for row in rows:
                    outcome = calculate(row, row, norms, formula_version)
                    batch.append((row['id'], formula_version, outcome['points'], outcome['reason'],
                                  Jsonb(outcome['breakdown'])))
                writer.executemany('''INSERT INTO score(result_id, formula_version, points, reason, breakdown)
                                      VALUES (%s,%s,%s,%s,%s)
                                      ON CONFLICT (result_id, formula_version) DO UPDATE SET
                                      points = excluded.points, reason = excluded.reason, breakdown = excluded.breakdown
                                      WHERE (score.points, score.reason, score.breakdown) IS DISTINCT FROM
                                            (excluded.points, excluded.reason, excluded.breakdown)''', batch)
        return score_report(con, formula_version)


def score_report(con, formula_version: str = FORMULA_VERSION, sample_limit: int = 5) -> dict:
    """Persisted counts/distribution plus bounded full explanations for inspection."""
    from psycopg.rows import dict_row
    params = (formula_version,)
    with con.cursor(row_factory=dict_row) as cur:
        summary = cur.execute('''SELECT count(*) AS total, count(points) AS scored,
                                  count(*) FILTER (WHERE points IS NULL) AS unscored,
                                  min(points) AS minimum, max(points) AS maximum, avg(points) AS mean,
                                  count(*) FILTER (WHERE points < 500) AS under_500,
                                  count(*) FILTER (WHERE points >= 500 AND points < 1000) AS from_500_to_1000,
                                  count(*) FILTER (WHERE points = 1000) AS exactly_1000,
                                  count(*) FILTER (WHERE points > 1000) AS over_1000
                                  FROM score WHERE formula_version = %s''', params).fetchone()
        reasons = cur.execute('''SELECT reason, count(*) AS n FROM score
                                 WHERE formula_version = %s AND reason IS NOT NULL GROUP BY reason ORDER BY reason''', params).fetchall()
        classes = cur.execute('''SELECT coalesce(breakdown->>'class', 'unclassified') AS class, count(*) AS n
                                 FROM score WHERE formula_version = %s GROUP BY 1 ORDER BY 1''', params).fetchall()
        examples = cur.execute('''SELECT * FROM score WHERE formula_version = %s ORDER BY result_id LIMIT %s''',
                               (formula_version, sample_limit)).fetchall()
    return {'formula_version': formula_version,
            **{key: summary[key] for key in ('total', 'scored', 'unscored')},
            'reasons': {r['reason']: r['n'] for r in reasons},
            'classes': {r['class']: r['n'] for r in classes},
            'distribution': {key: value for key, value in summary.items() if key not in ('total', 'scored', 'unscored')},
            'examples': examples}


def main() -> None:
    import argparse
    import json
    import db

    parser = argparse.ArgumentParser(description='Seed 2026 running norms, recalculate versioned scores, inspect JSON explanations.')
    parser.add_argument('--seed', action='store_true', help='Insert missing 2026 norms; preserve existing values')
    parser.add_argument('--recalculate', action='store_true', help='Rebuild this formula version for all results')
    parser.add_argument('--report', action='store_true', help='Show persisted score counts and distribution')
    parser.add_argument('--result-id', type=int, action='append', default=[], help='Show a stored full explanation (repeatable)')
    parser.add_argument('--formula-version', default=FORMULA_VERSION, help='Version label; previous versions are preserved')
    args = parser.parse_args()
    if not (args.seed or args.recalculate or args.report or args.result_id):
        parser.error('choose --seed, --recalculate, --report or --result-id')
    if not args.formula_version.strip():
        parser.error('--formula-version must not be empty')
    with db.connect() as con:
        initialize(con)
        if args.seed:
            seed_norms(con)
        if args.recalculate:
            recalculate(con, args.formula_version)
        output = {'report': score_report(con, args.formula_version),
                  'scores': [get_score(con, result_id, args.formula_version) for result_id in args.result_id]}
    print(json.dumps(output, ensure_ascii=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()

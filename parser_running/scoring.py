"""Rebuildable running scores using the rating-specific distance classifier."""
from __future__ import annotations

import math

FORMULA_VERSION = 'run-v1'

VALID_SPORTS = {'run', 'ski', 'biathlon', 'triathlon', 'trail'}

TRIATHLON_RMAX = {
    'full': 10000,
    'half': 5000,
    'olympic': 2500,
    'sprint': 1250,
    'supersprint': 625,
    'indoor': 625,
}

TRIATHLON_K_MAP = {
    'regular': 1.0,
    'worlds': 1.10,
    'kona': 1.15,
}

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
              formula_version: str = FORMULA_VERSION, synonyms: list[dict] | None = None) -> dict:
    """Pure result + stored race context + norms -> points and full explanation.

    Supports running, ski, biathlon, triathlon, and trail per SPEC v1.3 §9.
    A present but invalid chip time is rejected, never silently replaced by gun time.
    """
    sport = race.get('sport_type') or 'run'
    classification = None
    if sport == 'run' and any(key in race for key in ('distance_m', 'name', 'class_source')):
        from distance_classification import classify
        classification = classify(race, synonyms)
        race = race | {'distance_type': classification['distance_class'],
                       'discipline': classification['discipline']}
    start = race.get('date_begin')
    breakdown = {
        'sport': sport, 'class': race.get('distance_type'), 'discipline': race.get('discipline'),
        'gender': result.get('gender'), 'norm_value': None, 'norm_unit': None,
        'norm_year': None, 'norm_year_requested': start.year if start else None,
        'time_kind': None, 'time_s': None, 'formula': None, 'points': None,
        'formula_version': formula_version}
    if classification is not None:
        breakdown['classification'] = classification

    def missing(reason):
        return {'points': None, 'reason': reason, 'breakdown': breakdown | {'reason': reason}}

    if result.get('duplicate_of') is not None:
        return missing('duplicate')
    if result.get('status') != 'FIN':
        return missing('not_finisher')
    if sport not in VALID_SPORTS:
        return missing('unsupported_sport')
    if result.get('gender') not in ('M', 'F'):
        return missing('unknown_gender')
    if not start:
        return missing('missing_date')

    # 1. ЛЫЖНЫЕ ГОНКИ И БИАТЛОН (SPEC v1.3 §9.2)
    if sport in ('ski', 'biathlon'):
        if race.get('race_type') == 'relay':
            return missing('relay')
        if race.get('is_rl_series'):
            rl_pts = result.get('rl_points')
            if rl_pts is not None and isinstance(rl_pts, (int, float)) and math.isfinite(rl_pts) and rl_pts > 0:
                pts = rl_pts / 7.0
                breakdown.update(points=pts, formula=f"{rl_pts:g} / 7")
                return {'points': pts, 'reason': None, 'breakdown': breakdown}
            return missing('rl_series_excluded_from_place_scoring')

        N = race.get('finishers_count')
        if N is None:
            N = race.get('total_finishers')
        if N is None:
            N = race.get('finishers_gender_count')
        if N is None:
            N = result.get('total_finishers')
        if N is None:
            N = result.get('finishers_gender_count')

        place = result.get('place_gender')
        if place is None:
            place = result.get('place')
        if place is None:
            place = result.get('place_abs')

        if N is None:
            return missing('missing_finishers_count')
        if not isinstance(N, (int, float)) or not math.isfinite(N) or N <= 0:
            return missing('invalid_finishers_count')
        if place is None:
            return missing('missing_place')
        if not isinstance(place, (int, float)) or not math.isfinite(place) or place <= 0 or place > N:
            return missing('invalid_place')

        pts = 100.0 * (N - place + 1) / N
        kind = 'chip' if result.get('chip_time_s') is not None else ('gun' if result.get('gun_time_s') is not None else None)
        seconds = result.get(f'{kind}_time_s') if kind else None
        formula = f"100 × ({N:g} - {place:g} + 1) / {N:g}"
        breakdown.update(place=place, finishers_count=N, time_kind=kind, time_s=seconds, formula=formula, points=pts)
        return {'points': pts, 'reason': None, 'breakdown': breakdown}

    # 2. ТРИАТЛОН (SPEC v1.3 §9.3)
    if sport == 'triathlon':
        if race.get('race_type') == 'relay':
            return missing('relay')
        dist_cls = race.get('distance_type') or race.get('norm_distance') or race.get('distance_class')
        if not dist_cls or dist_cls not in TRIATHLON_RMAX:
            return missing('unclassified_distance')
        R_max = TRIATHLON_RMAX[dist_cls]

        special = race.get('special') or race.get('event_special') or 'regular'
        K = TRIATHLON_K_MAP.get(special, 1.0)

        kind = 'chip' if result.get('chip_time_s') is not None else 'gun'
        T_a = result.get(f'{kind}_time_s')
        if T_a is None:
            return missing('missing_time')
        if not isinstance(T_a, (int, float)) or not math.isfinite(T_a) or T_a <= 0:
            return missing('invalid_time')

        T_l = race.get('leader_time_s') or result.get('leader_time_s') or race.get('group_leader_time_s')
        if T_l is None:
            return missing('missing_leader_time')
        if not isinstance(T_l, (int, float)) or not math.isfinite(T_l) or T_l <= 0:
            return missing('invalid_leader_time')

        T_med = race.get('median_time_s') or result.get('median_time_s') or race.get('group_median_time_s')
        if T_med is None:
            return missing('missing_median_time')
        if not isinstance(T_med, (int, float)) or not math.isfinite(T_med) or T_med <= 0:
            return missing('invalid_median_time')

        B_med = 2.0 * max(0.0, (T_med - T_a) / 60.0)
        raw_pts = (R_max * (1.0 - (T_a - T_l) / T_l) + B_med) * K
        pts = max(0.0, raw_pts)
        formula = f"max(0, ({R_max:g} × (1 - ({T_a:g} - {T_l:g}) / {T_l:g}) + {B_med:.2f}) × {K:g})"
        breakdown.update(time_kind=kind, time_s=T_a, leader_time_s=T_l, median_time_s=T_med,
                         r_max=R_max, k=K, b_med=B_med, formula=formula, points=pts)
        return {'points': pts, 'reason': None, 'breakdown': breakdown}

    # 3. ТРЕЙЛ (SPEC v1.3 §9.4)
    if sport == 'trail':
        if race.get('race_type') == 'relay':
            return missing('relay')
        D_plus = race.get('elevation_gain_m') or race.get('d_plus')
        if D_plus is None:
            return missing('missing_elevation_gain')
        if not isinstance(D_plus, (int, float)) or not math.isfinite(D_plus) or D_plus <= 0:
            return missing('invalid_elevation_gain')

        km = race.get('distance_km') or (race.get('distance_m') / 1000.0 if race.get('distance_m') else None)
        if km is None:
            return missing('missing_distance')
        if not isinstance(km, (int, float)) or not math.isfinite(km) or km <= 0:
            return missing('invalid_distance')

        kind = 'chip' if result.get('chip_time_s') is not None else 'gun'
        T_a = result.get(f'{kind}_time_s')
        if T_a is None:
            return missing('missing_time')
        if not isinstance(T_a, (int, float)) or not math.isfinite(T_a) or T_a <= 0:
            return missing('invalid_time')

        T_l = race.get('leader_time_s') or result.get('leader_time_s') or race.get('group_leader_time_s')
        if T_l is None:
            return missing('missing_leader_time')
        if not isinstance(T_l, (int, float)) or not math.isfinite(T_l) or T_l <= 0:
            return missing('invalid_leader_time')

        T_med = race.get('median_time_s') or result.get('median_time_s') or race.get('group_median_time_s')
        if T_med is None:
            return missing('missing_median_time')
        if not isinstance(T_med, (int, float)) or not math.isfinite(T_med) or T_med <= 0:
            return missing('invalid_median_time')

        R_max = 10.0 * (km + D_plus / 100.0)
        B_med = 2.0 * max(0.0, (T_med - T_a) / 60.0)
        raw_pts = R_max * (1.0 - (T_a - T_l) / T_l) + B_med
        pts = max(0.0, raw_pts)
        formula = f"max(0, 10 × ({km:g} + {D_plus:g} / 100) × (1 - ({T_a:g} - {T_l:g}) / {T_l:g}) + {B_med:.2f})"
        breakdown.update(distance_km=km, elevation_gain_m=D_plus, time_kind=kind, time_s=T_a,
                         leader_time_s=T_l, median_time_s=T_med, r_max=R_max, b_med=B_med,
                         formula=formula, points=pts)
        return {'points': pts, 'reason': None, 'breakdown': breakdown}

    # 4. БЕГ (RUN - по умолчанию)
    if race.get('race_type') == 'relay':
        return missing('relay')
    if not race.get('distance_type'):
        return missing(classification['reason'] if classification else 'unclassified_distance')
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
    import distance_classification
    distance_classification.initialize(con)
    con.execute(DDL)


def seed_norms(con) -> None:
    """Insert missing 2026 norms, preserving values already maintained by an admin."""
    initialize(con)
    from distance_classification import seed_synonyms
    seed_synonyms(con)
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
        from distance_classification import load_synonyms
        synonyms = load_synonyms(con)
        with con.cursor(name='scoring_' + uuid.uuid4().hex, row_factory=dict_row) as reader, con.cursor() as writer:
            reader.execute('''SELECT r.id, r.status, r.gender, r.chip_time_s, r.gun_time_s, r.duplicate_of,
                                     r.distance_km, ra.name, ra.distance_m, ra.distance_type, ra.race_type,
                                     ra.discipline, ra.class_source, ra.distance_class_override,
                                     c.name AS competition_name, c.date_begin, c.sport_type
                              FROM result r JOIN race ra ON ra.id = r.race_id
                              JOIN competition c ON c.id = ra.competition_id ORDER BY r.id''')
            while rows := reader.fetchmany(1000):
                batch = []
                for row in rows:
                    outcome = calculate(row, row, norms, formula_version, synonyms)
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

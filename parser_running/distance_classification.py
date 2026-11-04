"""Rating distance classification; legacy parser normalization stays unchanged."""
from __future__ import annotations

import math
import re

from normalize import NORM_DISTANCES_M

DEFAULT_SYNONYMS = [
    {'pattern': pattern, 'distance_class': cls, 'priority': 100, 'enabled': True}
    for cls, pattern in (
        ('half_marathon', r'(?<!\w)полумарафон\w*|(?<![\w.,])21[.,](?:0975|195|18|1)(?![\d.,])'),
        ('marathon', r'(?<!\w)марафон\w*|(?<![\w.,])42[.,](?:195|2)(?![\d.,])'),
        ('10000m', r'(?<!\w)десятк(?:а|у|е|ой)(?!\w)|(?<![\w.,])10\s*(?:км|km)(?!\w)'),
        ('5000m', r'(?<!\w)(?:паркран|parkrun|пятерк\w*|(?:5|пять)\s*верст\w*)(?!\w)|(?<![\w.,])5\s*(?:км|km)(?!\w)'),
        ('24h', r'(?<!\w)(?:сутки|суточн\w*|24\s*(?:час\w*|h))(?!\w)'),
        ('1mile', r'(?<![\w.,])1\s*(?:миля|mile)(?!\w)'),
    )]

DDL = """
ALTER TABLE race ADD COLUMN IF NOT EXISTS discipline text CHECK (discipline IN ('road','track'));
ALTER TABLE race ADD COLUMN IF NOT EXISTS class_source text NOT NULL DEFAULT 'auto'
    CHECK (class_source IN ('auto','manual'));
ALTER TABLE race ADD COLUMN IF NOT EXISTS distance_class_override text;
ALTER TABLE result ADD COLUMN IF NOT EXISTS distance_km double precision
    CHECK (distance_km > 0 AND distance_km < 'Infinity'::float8);
CREATE TABLE IF NOT EXISTS distance_synonym (
    pattern text PRIMARY KEY CHECK (length(pattern) > 0),
    distance_class text NOT NULL,
    priority integer NOT NULL DEFAULT 100,
    enabled boolean NOT NULL DEFAULT true
);
"""


def initialize(con) -> None:
    """Migrate existing parser tables without replacing legacy distance_type."""
    con.execute(DDL)


def seed_synonyms(con) -> None:
    initialize(con)
    con.cursor().executemany('''INSERT INTO distance_synonym(pattern,distance_class,priority,enabled)
                               VALUES (%(pattern)s,%(distance_class)s,%(priority)s,%(enabled)s)
                               ON CONFLICT (pattern) DO NOTHING''', DEFAULT_SYNONYMS)


def load_synonyms(con) -> list[dict]:
    from psycopg.rows import dict_row
    with con.cursor(row_factory=dict_row) as cur:
        return cur.execute('SELECT * FROM distance_synonym ORDER BY priority,pattern').fetchall()


def set_synonym(con, pattern: str, distance_class: str, priority: int = 100,
                enabled: bool = True) -> None:
    """Admin-maintained regex rule, persisted in the caller's transaction."""
    if distance_class not in (*NORM_DISTANCES_M, '24h'):
        raise ValueError('Unknown distance class')
    if not pattern.strip():
        raise ValueError('Empty synonym pattern')
    re.compile(pattern)
    con.execute('''INSERT INTO distance_synonym(pattern,distance_class,priority,enabled)
                   VALUES (%s,%s,%s,%s) ON CONFLICT (pattern) DO UPDATE SET
                   distance_class=excluded.distance_class, priority=excluded.priority,
                   enabled=excluded.enabled''', (pattern, distance_class, priority, enabled))


def set_manual_class(con, race_id: int, distance_class: str | None) -> None:
    """Assign a class, or explicitly exclude a race with None. Survives reimport."""
    if distance_class is not None and distance_class not in (*NORM_DISTANCES_M, '24h'):
        raise ValueError('Unknown distance class')
    if not con.execute("UPDATE race SET class_source='manual',distance_class_override=%s WHERE id=%s",
                       (distance_class, race_id)).rowcount:
        raise ValueError('Unknown race')


def clear_manual_class(con, race_id: int) -> None:
    if not con.execute("UPDATE race SET class_source='auto',distance_class_override=NULL WHERE id=%s",
                       (race_id,)).rowcount:
        raise ValueError('Unknown race')


def _matches(text: str, rules: list[dict]) -> list[str]:
    matches = [r for r in rules if r.get('enabled', True)
               and re.search(r['pattern'], text.replace('ё', 'е'), re.IGNORECASE)]
    if not matches:
        return []
    priority = min(r.get('priority', 100) for r in matches)
    return sorted({r['distance_class'] for r in matches if r.get('priority', 100) == priority})


def classify(race: dict, synonyms: list[dict] | None = None) -> dict:
    """Stored race context -> rating class, provenance, discipline and exclusion."""
    text = ' '.join(str(race.get(k) or '') for k in ('name', 'competition_name')).lower()
    discipline = race.get('discipline') or (
        'track' if re.search(r'стадион|манеж|дорожк|\btrack\b', text) else 'road')
    if race.get('class_source') == 'manual':
        cls = race.get('distance_class_override')
        valid = cls in (*NORM_DISTANCES_M, '24h')
        return {'distance_class': cls if valid else None, 'discipline': discipline,
                'class_source': 'manual', 'reason': None if valid else
                ('manual_exclusion' if cls is None else 'invalid_manual_class')}
    metres = race.get('distance_m')
    rules = DEFAULT_SYNONYMS if synonyms is None else synonyms
    matches = _matches(str(race.get('name') or ''), rules)
    if not matches:
        # A multi-distance event's name must not turn its children's races into marathons.
        event_matches = _matches(str(race.get('competition_name') or ''), rules)
        explicit_distance = re.search(r'\d+(?:[.,]\d+)?\s*(?:км|km|м|m)\b', str(race.get('name') or ''), re.I)
        if not explicit_distance:
            # Timed events may expose circuit length; it is not achieved distance.
            matches = [c for c in event_matches if c == '24h' or metres is None or
                       (c in NORM_DISTANCES_M and isinstance(metres, (int, float))
                        and abs(NORM_DISTANCES_M[c] - metres) <= NORM_DISTANCES_M[c] * 0.01)]
    if matches:
        cls = matches[0] if len(matches) == 1 else None
        return {'distance_class': cls, 'discipline': discipline, 'class_source': 'synonym',
                'reason': None if cls else 'ambiguous_synonyms'}
    cls = None
    if isinstance(metres, (int, float)) and math.isfinite(metres) and metres > 0:
        closest = min(NORM_DISTANCES_M, key=lambda key: abs(NORM_DISTANCES_M[key] - metres))
        target = NORM_DISTANCES_M[closest]
        if abs(target - metres) <= (0 if discipline == 'track' else target * 0.01):
            cls = closest
    return {'distance_class': cls, 'discipline': discipline, 'class_source': 'metres',
            'reason': None if cls else 'unclassified_distance'}

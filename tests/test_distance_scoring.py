import sys
import csv
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'parser_running'))
from scoring import calculate, NORMS_2026


class DistanceScoringTests(unittest.TestCase):
    def score(self, **race):
        return calculate({'status': 'FIN', 'gender': 'M', 'chip_time_s': 1000},
                         {'date_begin': date(2026, 1, 1)} | race, NORMS_2026)

    def test_track_1600_metres_does_not_score_as_a_mile(self):
        outcome = calculate(
            {'status': 'FIN', 'gender': 'M', 'chip_time_s': 300},
            {'name': '1600 м', 'distance_m': 1600, 'distance_type': '1mile',
             'discipline': 'track', 'date_begin': date(2026, 1, 1)}, NORMS_2026)
        self.assertIsNone(outcome['points'])
        self.assertEqual(outcome['reason'], 'unclassified_distance')

    def test_named_classes_win_before_metres_and_event_titles_do_not_override_races(self):
        cases = [('паркран', None, '5000m'), ('Пять вёрст', None, '5000m'),
                 ('5 вёрст', None, '5000m'), ('пятёрка', None, '5000m'),
                 ('Десятка', 10600, '10000m'), ('10 км', 10500, '10000m'),
                 ('Полумарафон', None, 'half_marathon'), ('21,0975 км', None, 'half_marathon'),
                 ('21,195', None, 'half_marathon'), ('21,18 км', None, 'half_marathon'),
                 ('Марафон', None, 'marathon'), ('42,2', None, 'marathon')]
        for name, metres, expected in cases:
            with self.subTest(name=name):
                outcome = self.score(name=name, distance_m=metres)
                self.assertEqual(outcome['breakdown']['class'], expected)
                self.assertIsNotNone(outcome['points'])
        self.assertEqual(self.score(name='10 км', distance_m=10000,
                                   competition_name='Городской марафон')['breakdown']['class'], '10000m')
        self.assertIsNone(self.score(name='15 км', distance_m=15000,
                                    competition_name='Городской марафон')['points'])
        self.assertEqual(self.score(name='Участники', distance_m=None,
                                   competition_name='Паркран у озера')['breakdown']['class'], '5000m')

    def test_manual_assignment_and_exclusion_override_synonyms(self):
        assigned = self.score(name='Паркран', distance_m=5000, class_source='manual',
                              distance_class_override='10000m')
        self.assertEqual(assigned['breakdown']['class'], '10000m')
        self.assertEqual(assigned['points'], 1760)
        self.assertEqual(assigned['breakdown']['classification']['class_source'], 'manual')
        excluded = self.score(name='Паркран', distance_m=5000, class_source='manual',
                              distance_class_override=None)
        self.assertEqual(excluded['reason'], 'manual_exclusion')
        self.assertIsNone(excluded['points'])

    def test_source_discipline_precedes_keywords_and_road_tolerance_is_one_percent(self):
        for metres, discipline, title, expected in [
            (10100, 'road', 'Забег на стадионе', '10000m'),
            (10101, 'road', '', None), (10001, 'track', '', None),
            (10000, 'track', '', '10000m'), (10001, None, 'Манеж', None),
            (10001, None, 'Дорожка', None), (10001, None, 'Track meet', None),
            (10001, None, '', '10000m')]:
            with self.subTest(metres=metres, discipline=discipline, title=title):
                out = self.score(name='Участники', distance_m=metres,
                                 discipline=discipline, competition_name=title)
                self.assertEqual(out['breakdown']['class'], expected)
        out = self.score(name='15 км', distance_m=15000)
        self.assertEqual(out['reason'], 'unclassified_distance')

    def test_g9_all_manually_labelled_name_length_pairs(self):
        path = Path(__file__).parent / 'fixtures' / 'distance_g9.csv'
        with path.open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 185)
        self.assertEqual(sum(int(r['races']) for r in rows), 297)
        for row in rows:
            with self.subTest(name=row['name'], metres=row['distance_m']):
                out = self.score(name=row['name'], distance_m=int(row['distance_m']) if row['distance_m'] else None)
                self.assertEqual(out['breakdown']['class'], row['expected_class'] or None)

    def test_conflicting_admin_synonyms_require_disambiguation(self):
        race = {'name': 'Новый старт', 'date_begin': date(2026, 1, 1), 'distance_m': 5000}
        result = {'status': 'FIN', 'gender': 'M', 'chip_time_s': 1000}
        rules = [{'pattern': 'новый', 'distance_class': cls, 'priority': 100}
                 for cls in ('5000m', '10000m')]
        self.assertEqual(calculate(result, race, NORMS_2026, synonyms=rules)['reason'], 'ambiguous_synonyms')
        rules[0]['priority'] = 50
        self.assertEqual(calculate(result, race, NORMS_2026, synonyms=rules)['breakdown']['class'], '5000m')

    def test_24_hours_event_uses_achieved_km_instead_of_circuit_length(self):
        race = {'name': 'Участники', 'competition_name': '24 часа', 'distance_m': 1000,
                'date_begin': date(2026, 1, 1)}
        result = {'status': 'FIN', 'gender': 'M', 'distance_km': 250, 'chip_time_s': 86400}
        out = calculate(result, race, NORMS_2026)
        self.assertEqual(out['breakdown']['class'], '24h')
        self.assertAlmostEqual(out['points'], 1020.4081632653061)
        self.assertEqual(out['breakdown']['formula'], '250 / 245 × 1000')
        child = self.score(name='1 км', competition_name='24 часа', distance_m=1000)
        self.assertEqual(child['breakdown']['class'], '1000m')


if __name__ == '__main__':
    unittest.main()

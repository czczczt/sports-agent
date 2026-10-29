import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'parser_running'))
from scoring import calculate, NORMS_2026


class CalculatorTests(unittest.TestCase):
    def test_chip_time_and_requested_year_are_explained(self):
        score = calculate(
            {'status': 'FIN', 'gender': 'M', 'chip_time_s': 2400, 'gun_time_s': 2500},
            {'distance_type': '10000m', 'date_begin': date(2025, 5, 1)},
            [{'year': 2026, 'distance_class': '10000m', 'gender': 'M', 'value': 1760, 'unit': 's'}])
        self.assertAlmostEqual(score['points'], 733.3333333333333)
        self.assertIsNone(score['reason'])
        self.assertEqual(score['breakdown'], {
            'sport': 'run', 'class': '10000m', 'discipline': None, 'gender': 'M',
            'norm_value': 1760, 'norm_unit': 's', 'norm_year': 2026,
            'norm_year_requested': 2025, 'time_kind': 'chip', 'time_s': 2400,
            'formula': '1760 / 2400 × 1000', 'points': score['points'], 'formula_version': 'run-v1'})

    def test_ineligible_results_have_explicit_reasons(self):
        base = {'status': 'FIN', 'gender': 'M', 'chip_time_s': 2400}
        race = {'distance_type': '10000m', 'date_begin': date(2026, 1, 1)}
        norms = [{'year': 2026, 'distance_class': '10000m', 'gender': 'M', 'value': 1760, 'unit': 's'}]
        cases = [({'status': status}, {}, 'not_finisher') for status in ('DNF', 'DSQ', 'DNS', 'NC', 'LAP', None)]
        cases += [({'duplicate_of': 1}, {}, 'duplicate'), ({'gender': None}, {}, 'unknown_gender'),
                  ({}, {'date_begin': None}, 'missing_date'), ({}, {'distance_type': None}, 'unclassified_distance'),
                  ({}, {'race_type': 'relay'}, 'relay'), ({}, {'sport_type': 'trail'}, 'unsupported_sport'),
                  ({}, {'distance_type': '60m'}, 'missing_norm')]
        for patch, race_patch, reason in cases:
            with self.subTest(reason=reason, patch=patch):
                score = calculate(base | patch, race | race_patch, norms)
                self.assertIsNone(score['points'])
                self.assertEqual(score['reason'], reason)
                self.assertEqual(score['breakdown']['reason'], reason)
        for value in (None, 0, -1, float('nan'), float('inf'), 'garbage'):
            with self.subTest(time=value):
                score = calculate(base | {'chip_time_s': value}, race, norms)
                self.assertIsNone(score['points'])
                self.assertEqual(score['reason'], 'missing_time' if value is None else 'invalid_time')

    def test_invalid_norm_and_numeric_overflow_have_reasons(self):
        result = {'status': 'FIN', 'gender': 'M', 'chip_time_s': 2400, 'gun_time_s': 2500}
        race = {'distance_type': '10000m', 'date_begin': date(2026, 1, 1)}
        norm = {'year': 2026, 'distance_class': '10000m', 'gender': 'M', 'value': 1760, 'unit': 's'}
        for bad in (0, -1, float('nan'), float('inf'), None):
            with self.subTest(norm=bad):
                self.assertEqual(calculate(result, race, [norm | {'value': bad}])['reason'], 'invalid_norm')
        self.assertEqual(calculate(result, race, [norm | {'unit': 'km'}])['reason'], 'invalid_norm')
        self.assertEqual(calculate(result | {'chip_time_s': -1}, race, [norm])['reason'], 'invalid_time')
        self.assertEqual(calculate(result | {'chip_time_s': 1e-320}, race, [norm])['reason'], 'invalid_points')

    def test_norm_year_selection_and_uncapped_gun_score(self):
        norms = [{'year': y, 'distance_class': '10000m', 'gender': 'M', 'value': v, 'unit': 's'}
                 for y, v in ((2028, 1800), (2024, 1700), (2026, 1760))]
        result = {'status': 'FIN', 'gender': 'M', 'gun_time_s': 1680}
        for year, selected, expected in ((2026, 2026, 1047.6190476190477),
                                         (2027, 2026, 1047.6190476190477),
                                         (2025, 2024, 1011.9047619047619),
                                         (2023, 2024, 1011.9047619047619)):
            with self.subTest(year=year):
                score = calculate(result, {'distance_type': '10000m', 'date_begin': date(year, 1, 1)}, norms)
                self.assertAlmostEqual(score['points'], expected)
                self.assertEqual(score['breakdown']['norm_year'], selected)
                self.assertEqual(score['breakdown']['norm_year_requested'], year)
                self.assertEqual(score['breakdown']['time_kind'], 'gun')

    def test_golden_2026_table_for_both_genders(self):
        # Independent literal transcription of the customer's 2026 normative table.
        table = [('60m', 6.84, 7.5), ('100m', 10.62, 11.75), ('200m', 21.65, 24.4),
                 ('400m', 47.9, 54.8), ('800m', 111, 127), ('1000m', 142, 165),
                 ('1500m', 228, 259), ('1mile', 243, 279), ('3000m', 486, 555),
                 ('5000m', 846, 965), ('10000m', 1760, 2028), ('half_marathon', 3900, 4540),
                 ('marathon', 8400, 9600), ('100km', 24960, 28800), ('24h', 245, 216)]
        self.assertEqual(len(NORMS_2026), 30)
        for cls, male, female in table:
            for gender, value in (('M', male), ('F', female)):
                with self.subTest(distance=cls, gender=gender):
                    result = {'status': 'FIN', 'gender': gender,
                              'distance_km' if cls == '24h' else 'chip_time_s': value}
                    score = calculate(result, {'distance_type': cls, 'date_begin': date(2026, 1, 1)}, NORMS_2026)
                    self.assertEqual(score['points'], 1000)
                    self.assertEqual(score['breakdown']['norm_value'], value)
                    self.assertEqual(score['breakdown']['norm_unit'], 'km' if cls == '24h' else 's')
        ultra = calculate({'status': 'FIN', 'gender': 'M', 'distance_km': 250},
                          {'distance_type': '24h', 'date_begin': date(2026, 1, 1)}, NORMS_2026)
        self.assertAlmostEqual(ultra['points'], 1020.4081632653061)
        self.assertEqual(ultra['breakdown']['formula'], '250 / 245 × 1000')
        self.assertEqual(ultra['breakdown']['distance_km'], 250)
        for km, reason in ((None, 'missing_distance'), (0, 'invalid_distance'), (-1, 'invalid_distance'),
                           (float('nan'), 'invalid_distance')):
            self.assertEqual(calculate({'status': 'FIN', 'gender': 'M', 'distance_km': km},
                             {'distance_type': '24h', 'date_begin': date(2026, 1, 1)}, NORMS_2026)['reason'], reason)


if __name__ == '__main__':
    unittest.main()

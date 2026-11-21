import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'parser_running'))
from scoring import NORMS_2026, calculate


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
                  ({}, {'race_type': 'relay'}, 'relay'), ({}, {'sport_type': 'curling'}, 'unsupported_sport'),
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

    def test_ski_and_biathlon_scoring(self):
        # Ski race: 100 finishers, place 1 -> 100 * (100 - 1 + 1) / 100 = 100.0
        ski_res = {'status': 'FIN', 'gender': 'M', 'place_gender': 1, 'chip_time_s': 1800}
        ski_race = {'sport_type': 'ski', 'date_begin': date(2026, 2, 1), 'finishers_count': 100}
        score = calculate(ski_res, ski_race, [])
        self.assertEqual(score['points'], 100.0)
        self.assertIsNone(score['reason'])
        self.assertEqual(score['breakdown']['formula'], '100 × (100 - 1 + 1) / 100')

        # Ski race: 100 finishers, place 50 -> 100 * (100 - 50 + 1) / 100 = 51.0
        score_50 = calculate(ski_res | {'place_gender': 50}, ski_race, [])
        self.assertEqual(score_50['points'], 51.0)

        # Biathlon race: 80 finishers, place 10 -> 100 * (80 - 10 + 1) / 80 = 88.75
        biathlon_res = {'status': 'FIN', 'gender': 'F', 'place_gender': 10}
        biathlon_race = {'sport_type': 'biathlon', 'date_begin': date(2026, 2, 15), 'finishers_count': 80}
        score_biathlon = calculate(biathlon_res, biathlon_race, [])
        self.assertEqual(score_biathlon['points'], 88.75)

        # Ineligible ski place (> N or <= 0)
        self.assertEqual(calculate(ski_res | {'place_gender': 101}, ski_race, [])['reason'], 'invalid_place')
        self.assertEqual(calculate(ski_res | {'place_gender': 0}, ski_race, [])['reason'], 'invalid_place')
        self.assertEqual(calculate(ski_res | {'place_gender': None}, ski_race, [])['reason'], 'missing_place')
        self.assertEqual(calculate(ski_res, {'sport_type': 'ski', 'date_begin': date(2026, 2, 1)}, [])['reason'], 'missing_finishers_count')

    def test_ski_rl_series_scoring(self):
        # RL marathon with known points (e.g. 1524 points -> 1524 / 7 = 217.714...)
        res = {'status': 'FIN', 'gender': 'M', 'rl_points': 1524}
        race = {'sport_type': 'ski', 'is_rl_series': True, 'date_begin': date(2026, 3, 1)}
        score = calculate(res, race, [])
        self.assertAlmostEqual(score['points'], 1524.0 / 7.0)
        self.assertEqual(score['breakdown']['formula'], '1524 / 7')

        # RL race without rl_points is excluded from place scoring per SPEC §9.2
        self.assertEqual(calculate({'status': 'FIN', 'gender': 'M'}, race, [])['reason'], 'rl_series_excluded_from_place_scoring')

    def test_triathlon_scoring(self):
        # Olympic (Rmax = 2500), regular (K = 1.0)
        # Winner (Ta = Tl = 7200s, Tmed = 8400s -> Bmed = 2 * (8400 - 7200) / 60 = 40.0)
        # Points = (2500 * (1 - 0) + 40) * 1.0 = 2540.0
        tri_res = {'status': 'FIN', 'gender': 'M', 'chip_time_s': 7200}
        tri_race = {
            'sport_type': 'triathlon',
            'distance_type': 'olympic',
            'date_begin': date(2026, 6, 1),
            'leader_time_s': 7200,
            'median_time_s': 8400,
            'special': 'regular',
        }
        score = calculate(tri_res, tri_race, [])
        self.assertEqual(score['points'], 2540.0)
        self.assertIn('2500', score['breakdown']['formula'])
        self.assertEqual(score['breakdown']['b_med'], 40.0)

        # Half (Rmax = 5000), worlds status (K = 1.10)
        # Ta = 18000s, Tl = 15000s, Tmed = 17000s (slower than median -> Bmed = 0)
        # raw = 5000 * (1 - 3000/15000) = 5000 * 0.8 = 4000. Points = 4000 * 1.10 = 4400.0
        half_res = {'status': 'FIN', 'gender': 'M', 'chip_time_s': 18000}
        half_race = {
            'sport_type': 'triathlon',
            'distance_type': 'half',
            'date_begin': date(2026, 7, 1),
            'leader_time_s': 15000,
            'median_time_s': 17000,
            'special': 'worlds',
        }
        score_half = calculate(half_res, half_race, [])
        self.assertEqual(score_half['points'], 4400.0)
        self.assertEqual(score_half['breakdown']['b_med'], 0.0)

        # Ineligible triathlon missing fields
        self.assertEqual(calculate(tri_res, tri_race | {'leader_time_s': None}, [])['reason'], 'missing_leader_time')
        self.assertEqual(calculate(tri_res, tri_race | {'median_time_s': None}, [])['reason'], 'missing_median_time')
        self.assertEqual(calculate(tri_res, tri_race | {'distance_type': 'unknown_dist'}, [])['reason'], 'unclassified_distance')

    def test_trail_scoring(self):
        # 50 km, D+ = 2500 m -> Rmax = 10 * (50 + 25) = 750
        # Tl = 18000s, Ta = 21600s, Tmed = 23400s -> Bmed = 2 * (23400 - 21600)/60 = 60.0
        # raw = 750 * (1 - 3600/18000) + 60 = 750 * 0.8 + 60 = 600 + 60 = 660.0
        trail_res = {'status': 'FIN', 'gender': 'M', 'chip_time_s': 21600}
        trail_race = {
            'sport_type': 'trail',
            'distance_km': 50.0,
            'elevation_gain_m': 2500,
            'date_begin': date(2026, 8, 1),
            'leader_time_s': 18000,
            'median_time_s': 23400,
        }
        score = calculate(trail_res, trail_race, [])
        self.assertEqual(score['points'], 660.0)
        self.assertEqual(score['breakdown']['r_max'], 750.0)
        self.assertEqual(score['breakdown']['b_med'], 60.0)

        # Missing D+ -> missing_elevation_gain per SPEC §9.4
        self.assertEqual(calculate(trail_res, trail_race | {'elevation_gain_m': None}, [])['reason'], 'missing_elevation_gain')
        self.assertEqual(calculate(trail_res, trail_race | {'distance_km': None, 'distance_m': None}, [])['reason'], 'missing_distance')


if __name__ == '__main__':
    unittest.main()

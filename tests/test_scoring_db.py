import json
import subprocess
import os
import sys
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'parser_running'))
import db
from scoring import initialize, seed_norms, load_norms, recalculate, get_score, score_report
from store import save_results


@unittest.skipUnless(os.environ.get('SCORING_TEST_DATABASE_URL'), 'Set SCORING_TEST_DATABASE_URL to an expendable PostgreSQL database')
class ScoringDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.con = psycopg.connect(os.environ['SCORING_TEST_DATABASE_URL'])
        self.schema = 'scoring_test_' + uuid.uuid4().hex
        self.con.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.con.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
        self.con.execute(db.DDL)
        initialize(self.con)
        self.src = self.con.execute("INSERT INTO source(name, base_url, platform) VALUES ('synthetic', 'https://example.invalid', 'test') RETURNING id").fetchone()[0]
        self.comp = self.con.execute("INSERT INTO competition(source_id, external_id, date_begin, sport_type) VALUES (%s, 'test', '2025-05-01', 'run') RETURNING id", (self.src,)).fetchone()[0]
        self.race = self.con.execute("INSERT INTO race(competition_id, external_id, distance_m, distance_type, race_type) VALUES (%s, '10km', 10000, '10000m', 'individual') RETURNING id", (self.comp,)).fetchone()[0]

    def tearDown(self):
        self.con.rollback()  # schema and all synthetic data disappear, even on failure
        self.con.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(self.schema)))
        self.con.commit()
        self.con.close()

    def add_result(self, **changes):
        row = dict(status='FIN', gender='M', chip_time_s=2400, gun_time_s=2500)
        row.update(changes)
        columns = list(row)
        return self.con.execute(sql.SQL('INSERT INTO result(race_id, {}) VALUES (%s, {}) RETURNING id').format(
            sql.SQL(', ').join(map(sql.Identifier, columns)), sql.SQL(', ').join(sql.Placeholder() for _ in columns)),
            (self.race, *row.values())).fetchone()[0]

    def test_seed_recalculate_and_persisted_report(self):
        seed_norms(self.con)
        seed_norms(self.con)
        self.assertEqual(len(load_norms(self.con)), 30)
        fin = self.add_result()
        self.add_result(status='DNF')
        self.add_result(duplicate_of=fin)
        self.add_result(gender=None)
        report = recalculate(self.con)
        self.assertEqual((report['total'], report['scored'], report['unscored']), (4, 1, 3))
        self.assertEqual(report['reasons'], {'duplicate': 1, 'not_finisher': 1, 'unknown_gender': 1})
        stored = get_score(self.con, fin)
        self.assertAlmostEqual(stored['points'], 733.3333333333333)
        self.assertEqual(stored['breakdown']['norm_year_requested'], 2025)
        self.assertEqual(stored['breakdown']['norm_year'], 2026)
        self.assertEqual(recalculate(self.con), report)
        self.assertEqual(get_score(self.con, fin), stored)
        self.assertEqual(score_report(self.con), report)
        self.assertEqual(report['classes'], {'10000m': 4})
        self.assertEqual(report['distribution']['over_1000'], 0)
        self.assertEqual(report['examples'][0]['result_id'], fin)

    def test_version_history_updated_norms_and_reimport(self):
        seed_norms(self.con)
        fin = self.add_result()
        recalculate(self.con)
        original = get_score(self.con, fin)
        self.con.execute("UPDATE norm SET value = 1800 WHERE distance_class = '10000m' AND gender = 'M'")
        seed_norms(self.con)  # seeded defaults must not overwrite admin-maintained norms
        recalculate(self.con, 'run-v2')
        self.assertEqual(get_score(self.con, fin), original)
        self.assertEqual(get_score(self.con, fin, 'run-v2')['points'], 750)
        self.con.execute("UPDATE result SET status = 'NC' WHERE id = %s", (fin,))
        recalculate(self.con, 'run-v2')
        self.assertEqual(get_score(self.con, fin, 'run-v2')['reason'], 'not_finisher')
        self.assertIsNone(get_score(self.con, fin, 'run-v2')['points'])
        self.assertEqual(get_score(self.con, fin), original)
        save_results(self.con, self.race, [{'status': 'FIN', 'gender': 'F', 'gun_time_s': 2028}])
        self.assertIsNone(get_score(self.con, fin))
        self.assertIsNone(get_score(self.con, fin, 'run-v2'))
        report = recalculate(self.con)
        self.assertEqual((report['total'], report['scored']), (1, 1))
        self.assertEqual(report['examples'][0]['points'], 1000)

    def test_missing_norm_and_cleared_date_are_persisted(self):
        fin = self.add_result()
        self.assertEqual(recalculate(self.con)['reasons'], {'missing_norm': 1})
        self.assertEqual(get_score(self.con, fin)['reason'], 'missing_norm')
        seed_norms(self.con)
        self.assertEqual(recalculate(self.con)['scored'], 1)
        self.con.execute('UPDATE competition SET date_begin = NULL WHERE id = %s', (self.comp,))
        self.assertEqual(recalculate(self.con)['reasons'], {'missing_date': 1})
        self.assertIsNone(get_score(self.con, fin)['breakdown']['norm_year_requested'])

    def test_persisted_distance_rules_and_manual_assignments(self):
        from distance_classification import set_synonym, set_manual_class, clear_manual_class
        from store import save_race
        seed_norms(self.con)
        self.con.execute('UPDATE race SET name=%s,distance_m=NULL,distance_type=NULL WHERE id=%s',
                         ('Новый забег', self.race))
        fin = self.add_result(chip_time_s=846)
        self.assertEqual(recalculate(self.con)['scored'], 0)
        set_synonym(self.con, r'\bновый\b', '5000m')
        self.assertEqual(recalculate(self.con)['scored'], 1)
        self.assertEqual(get_score(self.con, fin)['points'], 1000)
        set_manual_class(self.con, self.race, '10000m')
        self.assertEqual(recalculate(self.con)['scored'], 1)
        self.assertEqual(get_score(self.con, fin)['breakdown']['class'], '10000m')
        save_race(self.con, self.comp, {'external_id': '10km', 'name_raw': 'Новый забег',
                                       'distance_km': None, 'place_by': 'chip'})
        recalculate(self.con)
        self.assertEqual(get_score(self.con, fin)['breakdown']['classification']['class_source'], 'manual')
        set_manual_class(self.con, self.race, None)
        recalculate(self.con)
        self.assertEqual(get_score(self.con, fin)['reason'], 'manual_exclusion')
        clear_manual_class(self.con, self.race)
        recalculate(self.con)
        self.assertEqual(get_score(self.con, fin)['points'], 1000)
        set_synonym(self.con, r'\bновый\b', '10000m')
        seed_norms(self.con)
        recalculate(self.con)
        self.assertEqual(get_score(self.con, fin)['breakdown']['class'], '10000m')
        set_synonym(self.con, r'\bновый\b', '10000m', enabled=False)
        seed_norms(self.con)
        recalculate(self.con)
        self.assertEqual(get_score(self.con, fin)['reason'], 'unclassified_distance')

    def test_24_hour_distance_survives_import_and_is_scored_in_kilometres(self):
        from store import save_race
        seed_norms(self.con)
        race = save_race(self.con, self.comp, {'external_id': '24h', 'name_raw': '24 часа',
                                              'distance_km': None, 'discipline': 'road',
                                              'place_by': 'chip'})
        save_results(self.con, race, [{'status': 'FIN', 'gender': 'M', 'distance_km': 250,
                                       'gun_time_s': 86400}])
        fin = self.con.execute('SELECT id FROM result WHERE race_id=%s', (race,)).fetchone()[0]
        recalculate(self.con)
        score = get_score(self.con, fin)
        self.assertAlmostEqual(score['points'], 1020.4081632653061)
        self.assertEqual(score['breakdown']['distance_km'], 250)
        self.assertEqual(score['breakdown']['discipline'], 'road')
        self.assertEqual(score['breakdown']['formula'], '250 / 245 × 1000')
        save_results(self.con, race, [{'status': 'FIN', 'gender': 'M', 'gun_time_s': 86400}])
        fin = self.con.execute('SELECT id FROM result WHERE race_id=%s', (race,)).fetchone()[0]
        recalculate(self.con)
        self.assertEqual(get_score(self.con, fin)['reason'], 'missing_distance')

    def test_distance_audit_compares_eligible_results_by_class_without_writes(self):
        from distance_report import report
        seed_norms(self.con)
        self.add_result()
        other = self.con.execute("INSERT INTO race(competition_id,external_id,name) VALUES (%s,'park','Паркран') RETURNING id", (self.comp,)).fetchone()[0]
        self.con.execute("INSERT INTO result(race_id,status,gender,chip_time_s) VALUES (%s,'FIN','M',846)", (other,))
        self.con.execute("INSERT INTO result(race_id,status,gender,chip_time_s) VALUES (%s,'DNF','M',846)", (other,))
        audit = report(self.con)
        self.assertEqual(audit['before'], {'total': 3, 'scored': 1, 'unscored': 2, 'classes': {'10000m': 1}})
        self.assertEqual(audit['after'], {'total': 3, 'scored': 2, 'unscored': 1,
                                         'classes': {'10000m': 1, '5000m': 1}})
        self.assertEqual(audit['changed_scores'], 1)
        self.assertEqual(score_report(self.con)['total'], 0)

    def test_cli_seed_recalculate_report_and_result_explanation(self):
        fin = self.add_result()
        self.con.commit()  # subprocess sees only this explicitly isolated synthetic schema
        env = os.environ | {'DATABASE_URL': os.environ['SCORING_TEST_DATABASE_URL'],
                            'PGOPTIONS': '-c search_path=' + self.schema, 'PYTHONIOENCODING': 'utf-8'}
        proc = subprocess.run([sys.executable, 'parser_running/scoring.py', '--seed', '--recalculate',
                               '--report', '--result-id', str(fin)], env=env, capture_output=True,
                              encoding='utf-8', cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data['report']['scored'], 1)
        self.assertEqual(data['scores'][0]['result_id'], fin)
        self.assertEqual(data['scores'][0]['breakdown']['time_kind'], 'chip')


if __name__ == '__main__':
    unittest.main()

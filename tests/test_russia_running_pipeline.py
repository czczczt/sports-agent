"""Full queued pilot with synthetic RR HTTP, a real worker and PostgreSQL."""
import asyncio
from datetime import date, timedelta

import psycopg
import pytest
import requests

from tests.test_russia_running_pilot import pilot_client


def test_pipeline_preserves_protocol_and_publication(pilot_client, migrated_url, monkeypatch):
    import app.pipeline.pilot as pilot
    import app.pipeline.rating_publication as publication
    import app.worker as worker
    import procrastinate
    from parser_running import rr_platform

    monkeypatch.setattr(pilot, 'DATABASE_URL', migrated_url)
    monkeypatch.setattr(rr_platform, 'DELAY_S', 0)
    state = {'partial': False, 'during_fetch': None, 'faster': False, 'omit_distance': False,
             'recalculations_observed': 0}
    today = date.today().isoformat()
    with psycopg.connect(migrated_url) as conn:
        conn.execute("INSERT INTO rating_norm(year,distance_class,gender,value,unit) VALUES (%s,'5000m','M',1200,'s') ON CONFLICT (year,distance_class,gender) DO UPDATE SET value=1200", (date.today().year,))
        conn.execute("INSERT INTO rating_norm(year,distance_class,gender,value,unit) VALUES (%s,'10000m','M',2400,'s') ON CONFLICT (year,distance_class,gender) DO UPDATE SET value=2400", (date.today().year,))

    real_recalculate = publication.recalculate_rating_sync
    def observe_recalculation(*args, **kwargs):
        result = real_recalculate(*args, **kwargs)
        # The real scoring statements have run in the open write transaction.
        # A separate HTTP reader must still see its previous published version.
        if state['during_fetch']:
            state['during_fetch']()
            state['recalculations_observed'] += 1
        return result
    monkeypatch.setattr(publication, 'recalculate_rating_sync', observe_recalculation)

    def external(self, method, url, **kwargs):
        if state['during_fetch']:
            state['during_fetch']()
        if url.endswith('/events/get'):
            payload = {'id': 'event-fixture', 'title': 'Fixture run', 'beginDate': today,
                       'disciplineCode': 'run', 'races': [
                           {'id': 'five-k', 'name': '5 км', 'distance': 5,
                            'disciplineCode': 'run', 'resultsCalculationMethod': 0}]}
            if not state['omit_distance']:
                payload['races'].append({'id': 'ten-k', 'name': '10 км', 'distance': 10,
                                         'disciplineCode': 'run', 'resultsCalculationMethod': 0})
        elif url.endswith('/results/options/get'):
            payload = {'isFinalProtocol': True}
        else:
            assert url.endswith('/results/individual/get')
            rows = [
                {'participantId': 'one', 'number': '1', 'fullName': 'Тест Первый', 'gender': 0,
                 'birthYear': 1990, 'raceClub': 'Сбер', 'status': 0, 'position': 1,
                 'individualGenderPosition': 1, 'individualResult': '00:20:00', 'absoluteResult': '00:20:01'},
                {'participantId': 'two', 'number': '2', 'fullName': 'Тест Второй', 'gender': 0,
                 'birthYear': 1991, 'raceClub': 'Сбер', 'status': 0, 'position': 2,
                 'individualGenderPosition': 2, 'individualResult': '00:25:00', 'absoluteResult': '00:25:01'},
            ]
            if state['faster']:
                rows[0]['individualResult'] = '00:19:00'
            if kwargs['json']['raceId'] == 'ten-k':
                rows[0]['individualResult'], rows[0]['absoluteResult'] = '00:40:00', '00:40:01'
                rows[1]['individualResult'], rows[1]['absoluteResult'] = '00:50:00', '00:50:01'
            payload = {'totalCount': 2, 'results': rows[:1] if state['partial'] else rows}
        response = requests.Response()
        response.status_code = 200
        import json
        response._content = json.dumps(payload).encode()
        return response

    monkeypatch.setattr(requests.Session, 'request', external)
    pilot_client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin'})

    def consume(redeliver=None):
        async def drain():
            app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=migrated_url))
            app.task(name='app.worker.pilot_collect_task', queue='collect', pass_context=True,
                     retry=procrastinate.RetryStrategy(max_attempts=3, wait=0))(worker.pilot_collect_task.func)
            async with app.open_async():
                if redeliver:
                    await app.tasks['app.worker.pilot_collect_task'].defer_async(run_id=redeliver)
                await app.run_worker_async(queues=['collect'], wait=False, concurrency=1)
        asyncio.run(drain())

    def run():
        response = pilot_client.post('/api/v1/runs', json={
            'kind': 'collect', 'source': 'russiarunning', 'event_code': 'fixture-event'})
        assert response.status_code == 202, response.text
        run_id = response.json()['run_id']
        consume()
        return pilot_client.get(f'/api/v1/runs/{run_id}').json()

    # Initial migration from stored ratings must enforce the same 80% guard.
    with psycopg.connect(migrated_url) as conn:
        legacy_ids = []
        for number in range(3):
            athlete_id = conn.execute(
                "INSERT INTO athlete(display_name,name_key) VALUES (%s,%s) RETURNING id",
                (f"Legacy {number}", f"legacy {number}"),
            ).fetchone()[0]
            legacy_ids.append(athlete_id)
            conn.execute(
                """INSERT INTO running_athlete_rating
                   (athlete_id,formula_version,period_start,period_end,points,best_points,starts_count,rank)
                   VALUES (%s,'run-v1',%s,%s,100,100,1,%s)""",
                (athlete_id, (date.today() - timedelta(days=365)).isoformat(), today, number + 1),
            )
    legacy_page = pilot_client.get('/api/rating').json()
    assert legacy_page['version_id'] is None
    assert len(legacy_page['rows']) == 3
    rejected_initial = run()
    assert rejected_initial['status'] == 'failed', rejected_initial
    assert '80%' in rejected_initial['error']
    assert pilot_client.get('/api/rating').json() == legacy_page
    with psycopg.connect(migrated_url) as conn:
        assert conn.execute('SELECT count(*) FROM rating_version').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM result').fetchone()[0] == 0
        conn.execute('DELETE FROM running_athlete_rating WHERE athlete_id = ANY(%s)', (legacy_ids,))
        conn.execute('DELETE FROM athlete WHERE id = ANY(%s)', (legacy_ids,))

    first = run()
    assert first['status'] == 'succeeded', first
    assert first['progress']['processed_distances'] == 2
    def snapshot():
        with psycopg.connect(migrated_url) as conn:
            return (
                conn.execute('SELECT id,external_participant_id,chip_time_s FROM result ORDER BY id').fetchall(),
                conn.execute('SELECT * FROM result_athlete ORDER BY result_id').fetchall(),
                conn.execute('SELECT athlete_id,points,rank FROM rating_version_row WHERE version_id=(SELECT version_id FROM rating_publication) ORDER BY rank').fetchall(),
            )
    expected = snapshot()
    assert len(expected[0]) == len(expected[1]) == 4
    assert len(expected[2]) == 2
    assert [row[1] for row in expected[2]] == [2000, 1600]
    published = pilot_client.get('/api/rating').json()
    assert published['version_id'] == first['rating_version_id']
    assert [row['points'] for row in published['rows']] == [2000, 1600]
    state['during_fetch'] = lambda: assert_snapshot(expected)
    def assert_snapshot(value):
        assert snapshot() == value
        assert pilot_client.get('/api/rating').json() == published
    second = run()
    assert second['status'] == 'succeeded', second
    assert state['recalculations_observed'] == 1
    assert snapshot() == expected
    published = pilot_client.get('/api/rating').json()
    assert published['version_id'] == second['rating_version_id']
    assert [row['points'] for row in published['rows']] == [2000, 1600]
    state['partial'] = True
    failed = run()
    assert failed['status'] == 'failed', failed
    assert failed['error']
    assert snapshot() == expected
    assert pilot_client.get('/api/rating').json() == published
    state['partial'], state['omit_distance'] = False, True
    omitted = run()
    assert omitted['status'] == 'failed', omitted
    assert 'distances' in omitted['error']
    assert snapshot() == expected
    assert pilot_client.get('/api/rating').json() == published
    # Force a genuine database failure during scoring, after rows were updated.
    # Existing published scores survive: the whole write/rebuild is rolled back.
    state['omit_distance'], state['faster'] = False, True
    with psycopg.connect(migrated_url) as conn:
        conn.execute('ALTER TABLE rating_score ADD CONSTRAINT reject_pilot_score CHECK(points < 0) NOT VALID')
    rebuilt = run()
    assert rebuilt['status'] == 'failed', rebuilt
    assert snapshot() == expected
    assert pilot_client.get('/api/rating').json() == published
    with psycopg.connect(migrated_url) as conn:
        conn.execute('ALTER TABLE rating_score DROP CONSTRAINT reject_pilot_score')
    with psycopg.connect(migrated_url) as conn:
        assert conn.execute('SELECT count(*) FROM rating_version').fetchone()[0] == 2
        assert conn.execute('SELECT version_id FROM rating_publication').fetchone()[0] == second['rating_version_id']
    consume(redeliver=second['run_id'])
    with psycopg.connect(migrated_url) as conn:
        assert conn.execute('SELECT count(*) FROM rating_version').fetchone()[0] == 2

    # A real recomputation with no scoring norms yields no ranked athletes.
    # Its controlled rejection must leave the previous publication untouched.
    with psycopg.connect(migrated_url) as conn:
        conn.execute('DELETE FROM rating_norm')
    empty = run()
    assert empty['status'] == 'failed', empty
    assert 'empty' in empty['error'].lower()
    assert snapshot() == expected
    assert pilot_client.get('/api/rating').json() == published
    with psycopg.connect(migrated_url) as conn:
        assert conn.execute('SELECT count(*) FROM rating_version').fetchone()[0] == 2

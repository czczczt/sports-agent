"""HTTP authorization and atomic queue handoff for the RussiaRunning pilot."""
import psycopg
import pytest


def test_pilot_authorization_and_atomic_enqueue(pilot_client, migrated_url):
    body = {'kind': 'collect', 'source': 'russiarunning', 'event_code': 'pilot-event'}
    assert pilot_client.post('/api/v1/runs', json=body).status_code == 401
    assert pilot_client.get('/api/v1/runs/1').status_code == 401
    for username, status in [('user', 403), ('admin', 202)]:
        pilot_client.cookies.clear()
        login = pilot_client.post('/api/auth/login', json={'username': username, 'password': username})
        assert login.status_code == 200
        response = pilot_client.post('/api/v1/runs', json=body)
        assert response.status_code == status, response.text
        if username == 'user':
            assert pilot_client.get('/api/v1/runs/1').status_code == 403
    run_id = response.json()['run_id']
    assert response.json()['status'] == 'queued'
    conflict = pilot_client.post('/api/v1/runs', json=body)
    assert conflict.status_code == 409
    assert conflict.json()['run_id'] == run_id
    status = pilot_client.get(f'/api/v1/runs/{run_id}')
    assert status.status_code == 200
    assert status.json()['progress'] == {'phase': 'queued', 'processed_distances': 0}
    assert status.json()['rating_version_id'] is None
    with psycopg.connect(migrated_url) as conn:
        jobs = conn.execute("SELECT args FROM procrastinate_jobs WHERE task_name='app.worker.pilot_collect_task'").fetchall()
        assert jobs == [({'run_id': run_id},)]
        assert conn.execute('SELECT count(*) FROM pilot_run').fetchone()[0] == 1
    assert pilot_client.post('/api/v1/runs', json={**body, 'event_code': '../bad'}).status_code == 422



def test_enqueue_failure_rolls_back_run(pilot_client, migrated_url, monkeypatch):
    from app.worker import pilot_collect_task

    class BrokenQueue:
        async def defer_async(self, **kwargs):
            raise RuntimeError('Queue insertion failed')

    monkeypatch.setattr(pilot_collect_task, 'configure', lambda **kwargs: BrokenQueue())
    pilot_client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin'})
    with pytest.raises(RuntimeError, match='Queue insertion failed'):
        pilot_client.post('/api/v1/runs', json={
            'kind': 'collect', 'source': 'russiarunning', 'event_code': 'pilot-event',
        })
    with psycopg.connect(migrated_url) as conn:
        assert conn.execute('SELECT count(*) FROM pilot_run').fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM procrastinate_jobs WHERE task_name='app.worker.pilot_collect_task'").fetchone()[0] == 0


def test_simultaneous_admin_requests_share_one_active_run(pilot_client, migrated_url):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    login = pilot_client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin'})
    headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    barrier = Barrier(2)

    def start():
        # Concurrent requests share the app event loop and use separate DB connections.
        barrier.wait(timeout=10)
        return pilot_client.post('/api/v1/runs', headers=headers, json={
            'kind': 'collect', 'source': 'russiarunning', 'event_code': 'parallel-event',
        })

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: start(), range(2)))
    assert sorted(r.status_code for r in responses) == [202, 409]
    assert len({r.json()['run_id'] for r in responses}) == 1
    with psycopg.connect(migrated_url) as conn:
        assert conn.execute('SELECT count(*) FROM pilot_run').fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM procrastinate_jobs WHERE task_name='app.worker.pilot_collect_task'").fetchone()[0] == 1

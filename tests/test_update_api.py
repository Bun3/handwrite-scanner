from fastapi.testclient import TestClient

from app import main, updater, jobs, models


def test_remote_client_cannot_update(monkeypatch):
    monkeypatch.setattr(updater, 'busy', lambda: False)
    client = TestClient(main.app, client=('192.168.1.30', 1234))
    assert client.post('/api/update/install').status_code == 403


def test_cross_origin_cannot_update(monkeypatch):
    monkeypatch.setattr(updater, 'busy', lambda: False)
    client = TestClient(main.app, base_url='http://127.0.0.1', client=('127.0.0.1', 1234))
    assert client.post('/api/update/install', headers={'Origin': 'https://other.test'}).status_code == 403


def test_updates_block_new_jobs_but_allow_status(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path)
    monkeypatch.setattr(updater, 'busy', lambda: True)
    monkeypatch.setattr(jobs, 'list_jobs', lambda: [])
    client = TestClient(main.app)
    assert client.post('/api/jobs', files={'files': ('test.png', b'png')}).status_code == 409
    assert client.get('/api/jobs').status_code == 200


def test_local_user_can_start_update(monkeypatch):
    monkeypatch.setattr(updater, 'busy', lambda: False)
    monkeypatch.setattr(jobs, 'list_jobs', lambda: [])
    monkeypatch.setattr(models, 'status_list', lambda: {'models': []})
    monkeypatch.setattr(updater, 'begin', lambda j, m: {'progress': {'phase': 'downloading'}})
    client = TestClient(main.app, base_url='http://127.0.0.1', client=('127.0.0.1', 1234))
    assert client.post('/api/update/install').json()['progress']['phase'] == 'downloading'


def test_nonlocal_hostname_cannot_trigger_update(monkeypatch):
    monkeypatch.setattr(updater, 'busy', lambda: False)
    client = TestClient(main.app, base_url='http://other.test', client=('127.0.0.1', 1234))
    assert client.post('/api/update/install', headers={'Origin': 'http://other.test'}).status_code == 403

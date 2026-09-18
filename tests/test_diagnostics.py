import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import diagnostics as d


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(d.config, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(d.jobs, 'list_jobs', lambda: [{'state': 'error', 'template': 'PRIVATE NAME', 'error': 'PATIENT SECRET'}])
    d._drafts.clear()
    app = FastAPI()
    app.include_router(d.router)
    return TestClient(app, client=('127.0.0.1', 1234), base_url='http://localhost')


def test_preview_excludes_raw_private_data_and_journal_is_bounded(client):
    try:
        raise ValueError(r'C:\Users\private\patient.pdf secret-token PATIENT SECRET')
    except ValueError as exc:
        for _ in range(110):
            d.record_error(exc, 'unexpected', 'worker')
    r = client.post('/api/diagnostics/preview', json={'code': 'unexpected', 'contact': '', 'description': ''})
    assert r.status_code == 200
    report = r.json()['report']
    text = json.dumps(report)
    assert all(s not in text for s in ['private', 'PATIENT', 'secret-token', 'PRIVATE NAME'])
    assert len(report['events']) <= 100
    assert report['jobs']['error'] == 1
    assert report['events'][-1]['exception'] == 'ValueError'


def test_submission_uses_only_frozen_preview_and_explicit_consent(client, monkeypatch):
    sent = []
    monkeypatch.setattr(d, 'send_report', lambda report: sent.append(report) or 'receipt')
    preview = client.post('/api/diagnostics/preview', json={'description': 'My reproduction'}).json()
    token = preview['token']
    assert client.post('/api/diagnostics/submit', json={'token': token, 'consent': False}).status_code == 400
    d.record_error(RuntimeError('new error'), 'unexpected', 'api')
    r = client.post('/api/diagnostics/submit', json={'token': token, 'consent': True})
    assert r.status_code == 200
    assert sent == [preview['report']]
    assert client.post('/api/diagnostics/submit', json={'token': token, 'consent': True}).status_code == 200
    assert len(sent) == 1


def test_no_cross_origin_or_remote_collection(client):
    assert client.post('/api/diagnostics/preview', json={}, headers={'origin': 'https://evil.test'}).status_code == 403
    app = client.app
    remote = TestClient(app, client=('192.168.1.5', 1234), base_url='http://localhost')
    assert remote.post('/api/diagnostics/preview', json={}).status_code == 403


def test_failed_send_preserves_preview_and_expiry(client, monkeypatch):
    def fail(report):
        raise RuntimeError('network')
    monkeypatch.setattr(d, 'send_report', fail)
    token = client.post('/api/diagnostics/preview', json={}).json()['token']
    assert client.post('/api/diagnostics/submit', json={'token': token, 'consent': True}).status_code == 503
    assert token in d._drafts
    monkeypatch.setattr(d.time, 'monotonic', lambda: 10**20)
    assert client.post('/api/diagnostics/submit', json={'token': token, 'consent': True}).status_code == 410


def test_journal_failure_does_not_break_error_handling(client, monkeypatch):
    monkeypatch.setattr(d, '_journal', lambda: d.config.DATA_DIR)
    d.record_error(PermissionError('PRIVATE PATH'), 'permission', 'api')
    assert client.post('/api/diagnostics/preview', json={}).status_code == 200


def test_job_progress_contains_only_numeric_progress_not_labels(client, monkeypatch):
    monkeypatch.setattr(d.jobs, 'list_jobs', lambda: [{'state': 'error', 'phase': 'recognizing',
        'progress': '2/105페이지 · 3/4 PATIENT NAME', 'template': 'SECRET TEMPLATE'}])
    report = client.post('/api/diagnostics/preview', json={}).json()['report']
    assert report['job_progress'] == [{'state': 'error', 'phase': 'recognizing', 'page': 2, 'total_pages': 105}]
    assert 'PATIENT' not in json.dumps(report)
    assert 'SECRET' not in json.dumps(report)


def test_real_transport_no_redirect_and_receipt_validation(client, monkeypatch):
    original = d.httpx.Client
    observed = []
    def handler(request):
        observed.append(json.loads(request.content))
        return d.httpx.Response(201, json={'receipt': observed[-1]['report_id']})
    monkeypatch.setattr(d.httpx, 'Client', lambda **kw: original(transport=d.httpx.MockTransport(handler), **kw))
    report = d.build_report(d.Preview())
    assert d.send_report(report) == report['report_id']
    assert observed == [report]
    monkeypatch.setattr(d.httpx, 'Client', lambda **kw: original(transport=d.httpx.MockTransport(
        lambda r: d.httpx.Response(302, headers={'location': 'https://evil.test'})), **kw))
    with pytest.raises(d.httpx.HTTPStatusError):
        d.send_report(report)

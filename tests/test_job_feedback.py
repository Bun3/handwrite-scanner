import json
import queue

import httpx
import pytest
from fastapi.testclient import TestClient

from app import jobs, main, templates_store, worker


def test_submit_returns_before_pdf_render(tmp_path, monkeypatch):
    import pymupdf
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(worker, "enqueue", lambda _: None)
    monkeypatch.setattr(pymupdf, "open", lambda *a, **k: pytest.fail("rendered during request"))
    client = TestClient(main.app)
    response = client.post('/api/jobs', files={'files': ('scan.pdf', b'%PDF-invalid')})
    assert response.status_code == 200
    st = client.get('/api/jobs/' + response.json()['id']).json()['status']
    assert st['state'] == 'queued' and st['phase'] == 'preparing'
    assert st['inputs_ready'] is False


def test_prepare_deferred_pdf_then_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path)
    pdf = open('tests/fixtures/dummy-form.pdf', 'rb').read()
    jid = jobs.create(None, [('scan.pdf', pdf)], defer=True)
    st = jobs.status(jid)
    calls = []
    jobs.prepare_inputs(jid, st, lambda: calls.append(True))
    assert st['inputs_ready'] and len(jobs.input_images(jid)) == 1
    before = jobs.input_images(jid)[0].read_bytes()
    jobs.prepare_inputs(jid, st, lambda: pytest.fail('prepared twice'))
    assert jobs.input_images(jid)[0].read_bytes() == before
    assert calls


def test_missing_selected_template_does_not_fall_back(tmp_path, monkeypatch):
    from app.errors import UserError
    monkeypatch.setattr(templates_store, 'TEMPLATES_DIR', tmp_path)
    with pytest.raises(UserError) as exc:
        worker._process('test', {'template': 'missing'})
    assert exc.value.code == 'template_missing'


def test_missing_reference_message(tmp_path, monkeypatch):
    monkeypatch.setattr(templates_store, 'TEMPLATES_DIR', tmp_path)
    templates_store.save('form', [])
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get('/api/templates/form/reference')
    assert response.status_code == 400
    assert response.json()['error_info']['code'] == 'reference_missing'


def test_api_errors_are_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(templates_store, 'TEMPLATES_DIR', tmp_path)
    folder = tmp_path / 'broken'
    folder.mkdir()
    (folder / 'template.json').write_text('broken', encoding='utf-8')
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.get('/api/templates')
    assert response.status_code == 400
    assert response.json()['error_info']['code'] == 'template_invalid'
    assert response.json()['error_info']['action']


def test_worker_records_friendly_error_and_keeps_running(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path)
    monkeypatch.setattr(worker, '_cancel', set())
    for jid in ['bad', 'next']:
        (tmp_path / jid).mkdir()
        jobs.write_status(jid, {'id': jid, 'state': 'queued'})
    q = queue.Queue()
    q.put('bad'); q.put('next')
    class Drain:
        def get(self):
            return q.get_nowait()
    monkeypatch.setattr(worker, '_q', Drain())
    def process(jid, st):
        if jid == 'bad':
            raise httpx.ReadTimeout('raw timeout')
    monkeypatch.setattr(worker, '_process', process)
    with pytest.raises(queue.Empty):
        worker._loop()
    st = jobs.status('bad')
    assert st['error_info']['code'] == 'engine_timeout'
    assert st['error_info']['action']
    assert 'ReadTimeout' in st['error']
    assert jobs.status('next')['state'] == 'done'


def test_cancel_during_preparation_can_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path)
    pdf = open('tests/fixtures/dummy-form.pdf', 'rb').read()
    jid = jobs.create(None, [('one.pdf', pdf), ('two.pdf', pdf)], defer=True)
    st = jobs.status(jid)
    def cancel_after_first():
        if jobs.input_images(jid):
            raise worker._Cancelled()
    with pytest.raises(worker._Cancelled):
        jobs.prepare_inputs(jid, st, cancel_after_first)
    assert not jobs.status(jid)['inputs_ready']
    jobs.prepare_inputs(jid, st, lambda: None)
    assert len(jobs.input_images(jid)) == 2


@pytest.mark.parametrize('kind', ['engine', 'model'])
def test_engine_missing_file_explained(tmp_path, monkeypatch, kind):
    from app import llm, config, models
    from app.errors import UserError
    monkeypatch.setattr(llm, 'is_up', lambda: False)
    engine = tmp_path / 'server.exe'
    monkeypatch.setattr(config, 'LLAMA_SERVER', engine)
    monkeypatch.setattr(models, 'paths', lambda _: (tmp_path / 'model', tmp_path / 'mmproj'))
    if kind == 'model':
        engine.touch()
    with pytest.raises(UserError) as exc:
        llm.ensure_server()
    assert exc.value.code == kind + '_missing'


def test_disk_failure_does_not_kill_worker(tmp_path, monkeypatch):
    import errno
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path)
    monkeypatch.setattr(jobs, '_volatile_status', {})
    (tmp_path / 'full').mkdir()
    jobs.write_status('full', {'id': 'full', 'state': 'queued'})
    q = queue.Queue(); q.put('full')
    class Drain:
        def get(self): return q.get_nowait()
    monkeypatch.setattr(worker, '_q', Drain())
    def fail(*args): raise OSError(errno.ENOSPC, 'disk full')
    monkeypatch.setattr(jobs, 'write_status', fail)
    with pytest.raises(queue.Empty):
        worker._loop()
    assert jobs.status('full')['error_info']['code'] == 'disk_full'


def test_status_write_retries_transient_windows_file_lock(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path)
    (tmp_path / 'j1').mkdir()
    replace = Path.replace
    attempts = []
    def locked_once(path, target):
        attempts.append(True)
        if len(attempts) == 1:
            raise PermissionError('temporary reader lock')
        return replace(path, target)
    monkeypatch.setattr(Path, 'replace', locked_once)
    jobs.write_status('j1', {'id': 'j1', 'state': 'running'})
    assert jobs.status('j1')['state'] == 'running'
    assert len(attempts) == 2


def test_encrypted_pdf_has_password_guidance(tmp_path, monkeypatch):
    import pymupdf
    from app.errors import UserError
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path)
    with pymupdf.open('tests/fixtures/dummy-form.pdf') as doc:
        data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='reader')
    jid = jobs.create(None, [('locked.pdf', data)], defer=True)
    with pytest.raises(UserError) as exc:
        jobs.prepare_inputs(jid, jobs.status(jid), lambda: None)
    assert exc.value.code == 'pdf_password'
    assert not jobs.status(jid)['inputs_ready']


def test_broken_reference_has_specific_guidance(tmp_path, monkeypatch):
    from app.errors import UserError
    monkeypatch.setattr(templates_store, 'TEMPLATES_DIR', tmp_path)
    templates_store.save('form', [])
    (tmp_path / 'form/reference.png').write_bytes(b'broken')
    with pytest.raises(UserError) as exc:
        templates_store.reference_path('form')
    assert exc.value.code == 'reference_invalid'

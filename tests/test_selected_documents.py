import io
import json

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import jobs, main, worker, templates_store, export


def pdf_bytes():
    with pymupdf.open() as doc:
        for i in range(4):
            doc.new_page(width=72, height=100).insert_text((10, 30), str(i + 1))
        return doc.tobytes()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path / 'jobs')
    jobs.JOBS_DIR.mkdir()
    monkeypatch.setattr(templates_store, 'TEMPLATES_DIR', tmp_path / 'templates')
    templates_store.TEMPLATES_DIR.mkdir()
    for name in ['a', 'b']:
        templates_store.save(name, [])
        Image.new('RGB', (72, 100), 'white').save(templates_store.TEMPLATES_DIR / name / 'reference.png')
    monkeypatch.setattr(worker, 'enqueue', lambda _: None)
    return TestClient(main.app, raise_server_exceptions=False)


def test_only_selected_pdf_pages_render_and_source_survives_resume(isolated):
    jid = jobs.create(None, [('scan.pdf', pdf_bytes())], defer=True, templates=['a', 'b'], selections=[[2, 4]])
    st = jobs.status(jid)
    jobs.prepare_inputs(jid, st, lambda: None)
    assert len(jobs.input_images(jid)) == 2
    assert st['templates'] == ['a', 'b']
    assert jobs.page_sources(jid) == [{'source_file': 'scan.pdf', 'source_page': 2}, {'source_file': 'scan.pdf', 'source_page': 4}]
    jobs.prepare_inputs(jid, st, lambda: pytest.fail('already prepared'))
    assert len(jobs.input_images(jid)) == 2


def test_unmatched_registered_forms_never_use_freeform(isolated, monkeypatch):
    jid = jobs.create(None, [('scan.pdf', pdf_bytes())], defer=True, templates=['a', 'b'], selections=[[2, 4]])
    monkeypatch.setattr(worker, 'best_template', lambda *_: (None, None))
    monkeypatch.setattr(worker, '_recognize_freeform', lambda *_: pytest.fail('unregistered document reached OCR'))
    worker._process(jid, jobs.status(jid))
    res = jobs.results(jid)
    assert len(res) == 2 and all(p['skipped'] for p in res)
    assert [p['source_page'] for p in res] == [2, 4]
    worker._process(jid, jobs.status(jid))
    assert jobs.results(jid) == res


def test_different_registered_forms_are_processed_in_one_job(isolated, monkeypatch):
    jid = jobs.create(None, [('scan.pdf', pdf_bytes())], defer=True, templates=['a', 'b'], selections=[[1, 3]])
    choices = iter(['a', 'b'])
    def detect(data, candidates):
        assert [t['name'] for t, _ in candidates] == ['a', 'b']
        return templates_store.get(next(choices)), Image.open(io.BytesIO(data))
    monkeypatch.setattr(worker, 'best_template', detect)
    worker._process(jid, jobs.status(jid))
    res = jobs.results(jid)
    assert [p['template'] for p in res] == ['a', 'b']
    assert [p['source_page'] for p in res] == [1, 3]
    text, _, _ = export.build(jid, res, 'csv')
    assert 'scan.pdf,3' in text


def test_intake_preview_and_start_are_idempotent(isolated):
    r = isolated.post('/api/intake', files={'files': ('scan.pdf', pdf_bytes(), 'application/pdf')})
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft['files'][0]['pages'] == 4
    token = draft['token']
    preview = isolated.get(f'/api/intake/{token}/files/0/pages/2')
    assert preview.status_code == 200
    assert Image.open(io.BytesIO(preview.content)).width <= 600
    payload = {'templates': ['a', 'b'], 'pages': [[2, 4]]}
    first = isolated.post(f'/api/intake/{token}/start', json=payload)
    assert first.status_code == 200, first.text
    assert isolated.post(f'/api/intake/{token}/start', json=payload).json() == first.json()
    assert len(jobs.list_jobs()) == 1
    assert jobs.status(first.json()['id'])['templates'] == ['a', 'b']


@pytest.mark.parametrize('payload', [
    {'templates': [], 'pages': [[1]]}, {'templates': ['missing'], 'pages': [[1]]},
    {'templates': ['a'], 'pages': [[]]}, {'templates': ['a'], 'pages': [[0, 5]]},
    {'templates': ['a'], 'pages': [[True]]}, {'templates': ['../a'], 'pages': [[1]]},
])
def test_invalid_selection_does_not_create_job(isolated, payload):
    draft = isolated.post('/api/intake', files={'files': ('scan.pdf', pdf_bytes())})
    assert draft.status_code == 200
    r = isolated.post(f"/api/intake/{draft.json()['token']}/start", json=payload)
    assert r.status_code == 400, r.text
    assert jobs.list_jobs() == []


def test_selected_pdf_preparation_resumes_after_cancel(isolated):
    jid = jobs.create(None, [('scan.pdf', pdf_bytes())], defer=True, templates=['a'], selections=[[2, 4]])
    st = jobs.status(jid)
    checks = 0
    def cancel_second_page():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise worker._Cancelled()
    with pytest.raises(worker._Cancelled):
        jobs.prepare_inputs(jid, st, cancel_second_page)
    assert len(jobs.input_images(jid)) == 1 and not st['inputs_ready']
    jobs.prepare_inputs(jid, st, lambda: None)
    assert len(jobs.input_images(jid)) == 2
    assert [p['source_page'] for p in jobs.page_sources(jid)] == [2, 4]


def test_no_alignment_engine_does_not_skip_everything_silently(isolated, monkeypatch):
    from app.errors import UserError
    jid = jobs.create(None, [('scan.pdf', pdf_bytes())], defer=True, templates=['a'])
    monkeypatch.setattr(worker, 'HAVE_CV2', False)
    with pytest.raises(UserError) as exc:
        worker._process(jid, jobs.status(jid))
    assert exc.value.code == 'alignment_missing'


def test_real_alignment_selects_two_forms_and_skips_unregistered_page(isolated, monkeypatch):
    import random
    from PIL import ImageDraw
    pictures = []
    for seed, name in enumerate(['a', 'b']):
        rng = random.Random(seed)
        img = Image.new('RGB', (500, 650), 'white')
        draw = ImageDraw.Draw(img)
        for n in range(110):
            x, y = rng.randrange(470), rng.randrange(620)
            draw.rectangle((x, y, x + 15, y + 12), outline='black', width=2)
            draw.text((x, y), str(n), fill='black')
        img.save(templates_store.reference_path(name))
        buf = io.BytesIO(); img.save(buf, 'PNG'); pictures.append(buf.getvalue())
    blank = io.BytesIO(); Image.new('RGB', (500, 650), 'white').save(blank, 'PNG')
    jid = jobs.create(None, [('a.png', pictures[0]), ('unregistered.png', blank.getvalue()), ('b.png', pictures[1])],
                      defer=True, templates=['a', 'b'], selections=[[1], [1], [1]])
    monkeypatch.setattr(worker, '_recognize_freeform', lambda *_: pytest.fail('unregistered OCR'))
    worker._process(jid, jobs.status(jid))
    res = jobs.results(jid)
    assert [p['template'] for p in res] == ['a', None, 'b']
    assert res[1]['skipped'] and not res[0].get('skipped')


def test_intake_rejects_broken_and_encrypted_pdf(isolated):
    bad = isolated.post('/api/intake', files={'files': ('broken.pdf', b'%PDF-broken')})
    assert bad.status_code == 400 and bad.json()['error_info']['code'] == 'pdf_invalid'
    with pymupdf.open(stream=pdf_bytes(), filetype='pdf') as doc:
        locked = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret')
    bad = isolated.post('/api/intake', files={'files': ('locked.pdf', locked)})
    assert bad.status_code == 400 and bad.json()['error_info']['code'] == 'pdf_password'
    assert jobs.list_jobs() == []

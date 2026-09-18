import io
import json
import shutil
import zipfile

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app import jobs, templates_store, worker, main
from app.errors import UserError


@pytest.fixture
def pcs(tmp_path, monkeypatch):
    def switch(name):
        root = tmp_path / name
        for part in ('jobs', 'templates'): (root / part).mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(jobs, 'JOBS_DIR', root / 'jobs')
        monkeypatch.setattr(templates_store, 'TEMPLATES_DIR', root / 'templates')
        return root
    switch('a')
    monkeypatch.setattr(worker, 'enqueue', lambda _: None)
    return switch


def make_job():
    templates_store.save('form', [])
    Image.new('RGB', (80, 100), 'white').save(templates_store.TEMPLATES_DIR / 'form/reference.png')
    buf = io.BytesIO(); Image.new('RGB', (80, 100), 'white').save(buf, 'PNG')
    jid = jobs.create(None, [(f'{i}.png', buf.getvalue()) for i in range(4)], defer=True, templates=['form'])
    st = jobs.status(jid); jobs.prepare_inputs(jid, st, lambda: None)
    st['state'] = 'cancelled'; jobs.write_status(jid, st)
    return jid


def complete(jid, page, value):
    rows = [p for p in (jobs.results(jid) or []) if p['page'] != page]
    rows.append({'page': page, 'template': 'form', 'fields': [{'id': 'f', 'label': 'Name', 'type': 'text', 'value': value, 'confidence': 1}], 'warnings': []})
    jobs.write_results(jid, sorted(rows, key=lambda p: p['page']))
    shutil.copyfile(jobs.input_images(jid)[page], jobs.JOBS_DIR / jid / f'page_{page:03d}.png')


def test_templates_are_frozen_at_job_creation(pcs, monkeypatch):
    from app import job_context
    jid = make_job()
    templates_store.save('form', [{'id': 'changed', 'label': 'Changed', 'type': 'text', 'box': [1, 1, 10, 10]}])
    tpl, ref = job_context.pool(jid)[0]
    assert tpl['fields'] == [] and ref.is_file()
    templates_store.delete('form')
    worker._process(jid, jobs.status(jid))
    assert len(jobs.results(jid)) == 4


def test_roundtrip_resume_and_duplicate_import(pcs):
    from app import transfer
    jid = make_job(); complete(jid, 0, 'reviewed')
    archive = transfer.export_bundle([jid], [])
    raw = archive.read_bytes()
    pcs('b')
    preview = transfer.stage(io.BytesIO(raw))
    assert preview['jobs'][0]['completed'] == 1
    result = transfer.commit(preview['token'], [0], [])
    new = result['jobs'][0]
    assert jobs.status(new)['state'] == 'cancelled'
    assert jobs.results(new)[0]['fields'][0]['value'] == 'reviewed'
    assert not templates_store.list_templates()  # private template still sufficient
    worker._process(new, jobs.status(new))
    assert len(jobs.results(new)) == 4
    duplicate = transfer.stage(io.BytesIO(raw))
    assert duplicate['jobs'][0]['duplicate']
    assert transfer.commit(duplicate['token'], [0], [])['jobs'] == []


def test_split_return_merge_and_resume_sparse_pages(pcs):
    from app import transfer, job_context
    root_a = pcs('a'); jid = make_job()
    archive = transfer.export_bundle([jid], [], split_pages=[2, 3])
    raw = archive.read_bytes()
    assert jobs.status(jid)['delegated_pages'] == [2, 3]
    pcs('b')
    stage = transfer.stage(io.BytesIO(raw)); branch = transfer.commit(stage['token'], [0], [])['jobs'][0]
    complete(branch, 0, 'B-page3'); complete(branch, 1, 'B-page4')
    returned = transfer.export_bundle([branch], []).read_bytes()
    pcs('a')
    stage = transfer.stage(io.BytesIO(returned))
    preview = transfer.merge_preview(stage['token'], 0, jid)
    assert preview['added'] == [2, 3] and preview['conflicts'] == []
    merged = transfer.merge(stage['token'], 0, jid, preview['revision'], {})['job']
    assert [p['page'] for p in jobs.results(merged)] == [2, 3]
    assert jobs.results(jid) is None  # original is never overwritten
    worker._process(merged, jobs.status(merged))
    assert [p['page'] for p in jobs.results(merged)] == [0, 1, 2, 3]
    assert jobs.results(merged)[2]['fields'][0]['value'] == 'B-page3'
    assert job_context.read(merged)['root_id'] == job_context.read(jid)['root_id']


def test_merge_conflicts_require_choice_and_reject_stale_preview(pcs):
    from app import transfer
    jid = make_job(); complete(jid, 0, 'original')
    raw = transfer.export_bundle([jid], []).read_bytes()
    pcs('b'); stage = transfer.stage(io.BytesIO(raw)); other = transfer.commit(stage['token'], [0], [])['jobs'][0]
    complete(other, 0, 'B edit'); returned = transfer.export_bundle([other], []).read_bytes()
    pcs('a'); stage = transfer.stage(io.BytesIO(returned))
    p = transfer.merge_preview(stage['token'], 0, jid)
    assert len(p['conflicts']) == 1
    with pytest.raises(UserError): transfer.merge(stage['token'], 0, jid, p['revision'], {})
    complete(jid, 0, 'A edit')
    with pytest.raises(UserError): transfer.merge(stage['token'], 0, jid, p['revision'], {'0': 'incoming'})
    p = transfer.merge_preview(stage['token'], 0, jid)
    merged = transfer.merge(stage['token'], 0, jid, p['revision'], {'0': 'incoming'})['job']
    assert jobs.results(merged)[0]['fields'][0]['value'] == 'B edit'
    assert jobs.results(jid)[0]['fields'][0]['value'] == 'A edit'


def test_same_name_different_template_is_added_without_overwrite(pcs):
    from app import transfer
    make_job(); raw = transfer.export_bundle([], ['form']).read_bytes()
    pcs('b'); templates_store.save('form', [])
    Image.new('RGB', (80, 100), 'black').save(templates_store.TEMPLATES_DIR / 'form/reference.png')
    original = (templates_store.TEMPLATES_DIR / 'form/reference.png').read_bytes()
    stage = transfer.stage(io.BytesIO(raw)); out = transfer.commit(stage['token'], [], [0])
    assert out['templates'][0] != 'form'
    assert (templates_store.TEMPLATES_DIR / 'form/reference.png').read_bytes() == original


@pytest.mark.parametrize('path', ['../outside', 'C:/outside', '/outside', 'a\\b'])
def test_archive_paths_are_rejected_before_import(pcs, path):
    from app import transfer
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z: z.writestr(path, 'bad')
    buf.seek(0)
    with pytest.raises(UserError): transfer.stage(buf)
    assert jobs.list_jobs() == []


def test_api_refuses_export_of_active_work(pcs):
    jid = make_job(); st = jobs.status(jid); st['state'] = 'running'; jobs.write_status(jid, st)
    response = TestClient(main.app).post('/api/transfer/export', json={'jobs': [jid], 'templates': []})
    assert response.status_code == 400


def repack(raw, edit):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files = {name: z.read(name) for name in z.namelist()}
    edit(files)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for name, content in files.items(): z.writestr(name, content)
    out.seek(0)
    return out


@pytest.mark.parametrize('problem', ['hash', 'version', 'duplicate_page', 'missing_reference', 'unsafe_reference'])
def test_damaged_archive_does_not_register_anything(pcs, problem):
    from app import transfer
    jid = make_job(); raw = transfer.export_bundle([jid], []).read_bytes()
    def edit(files):
        meta = json.loads(files['manifest.json'])
        if problem == 'hash':
            key = next(k for k in files if k.startswith('blobs/'))
            content = bytearray(files[key]); content[-1] ^= 1; files[key] = bytes(content)
        elif problem == 'version': meta['version'] = 999
        elif problem == 'duplicate_page': meta['jobs'][0]['context']['pages'][1]['id'] = meta['jobs'][0]['context']['pages'][0]['id']
        elif problem == 'missing_reference': del meta['jobs'][0]['files'][meta['jobs'][0]['context']['templates'][0]['reference']]
        elif problem == 'unsafe_reference': meta['jobs'][0]['context']['templates'][0]['reference'] = '../../reference.png'
        files['manifest.json'] = json.dumps(meta).encode()
    pcs('b')
    with pytest.raises(UserError): transfer.stage(repack(raw, edit))
    assert not jobs.list_jobs() and not templates_store.list_templates()


def test_old_work_shows_legacy_template_notice(pcs):
    from app import transfer
    jid = make_job()
    (jobs.JOBS_DIR / jid / 'context.json').unlink()
    st = jobs.status(jid); st.pop('context_version'); jobs.write_status(jid, st)
    raw = transfer.export_bundle([jid], []).read_bytes()
    pcs('b'); stage = transfer.stage(io.BytesIO(raw))
    assert stage['jobs'][0]['legacy_templates'] is True


def test_snapshot_loss_does_not_fall_back_to_current_templates(pcs):
    jid = make_job(); (jobs.JOBS_DIR / jid / 'context.json').unlink()
    with pytest.raises(UserError): worker._process(jid, jobs.status(jid))


def test_different_root_merge_rejected_and_delegated_pages_are_skipped(pcs):
    from app import transfer
    first = make_job(); second = make_job()
    raw = transfer.export_bundle([first], [], split_pages=[2, 3]).read_bytes()
    stage = transfer.stage(io.BytesIO(raw))
    with pytest.raises(UserError): transfer.merge_preview(stage['token'], 0, second)
    worker._process(first, jobs.status(first))
    assert [p['page'] for p in jobs.results(first)] == [0, 1]
    transfer.release_assignment(first)
    worker._process(first, jobs.status(first))
    assert [p['page'] for p in jobs.results(first)] == [0, 1, 2, 3]


def test_imported_job_resume_requires_model_choice_and_sparse_edit_uses_page_number(pcs, monkeypatch):
    from app import transfer, models, job_context
    jid = make_job(); complete(jid, 2, 'late result')
    raw = transfer.export_bundle([jid], []).read_bytes()
    pcs('b'); staged = transfer.stage(io.BytesIO(raw)); new = transfer.commit(staged['token'], [0], [])['jobs'][0]
    client = TestClient(main.app)
    r = client.patch(f'/api/jobs/{new}/fields', json={'page': 2, 'id': 'f', 'value': 'reviewed'})
    assert r.status_code == 200 and jobs.results(new)[0]['fields'][0]['value'] == 'reviewed'
    monkeypatch.setattr(models, 'current', lambda: {'id': 'other-model'})
    assert client.post(f'/api/jobs/{new}/resume').status_code == 400
    assert jobs.status(new)['state'] == 'cancelled'
    assert client.post(f'/api/jobs/{new}/resume?accept_current_model=true').status_code == 200
    assert job_context.read(new)['model'] == 'other-model'


def test_api_export_preview_import_roundtrip(pcs):
    jid = make_job(); client = TestClient(main.app)
    r = client.post('/api/transfer/export', json={'jobs': [jid], 'templates': ['form']})
    assert r.status_code == 200, r.text
    archive = client.get(r.json()['url']).content
    named = client.get(r.json()['url'], params={'filename': 'custom.hscan'})
    assert named.content == archive
    assert 'custom.hscan' in named.headers['content-disposition']
    assert client.get(r.json()['url'], params={'filename': '../bad.hscan'}).status_code == 400
    pcs('b')
    preview = client.post('/api/transfer/preview', files={'file': ('work.hscan', archive)})
    assert preview.status_code == 200, preview.text
    result = client.post('/api/transfer/commit', json={'token': preview.json()['token'], 'jobs': [0], 'templates': [0]})
    assert result.status_code == 200, result.text
    assert len(result.json()['jobs']) == 1
    assert templates_store.get('form') is not None


def test_import_rolls_back_only_new_items_when_publication_fails(pcs, monkeypatch):
    from pathlib import Path
    from app import transfer
    jid = make_job(); raw = transfer.export_bundle([jid], ['form']).read_bytes()
    pcs('b'); staged = transfer.stage(io.BytesIO(raw))
    rename = Path.rename
    def fail_job_publish(self, destination):
        if Path(destination).parent == jobs.JOBS_DIR: raise OSError('disk unavailable')
        return rename(self, destination)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', fail_job_publish)
        with pytest.raises(OSError): transfer.commit(staged['token'], [0], [0])
    assert not jobs.list_jobs() and not templates_store.list_templates()
    assert transfer.commit(staged['token'], [0], [0])['jobs']


def test_more_than_1000_pages_keep_identity_order_across_transfer(pcs):
    from app import transfer, job_context
    jid = make_job()
    directory = jobs.JOBS_DIR / jid / 'input'
    for i in range(4, 1002):
        Image.new('RGB', (2, 2), (i % 256, i // 256, 0)).save(directory / f'{i:03d}.png')
    ctx = job_context.read(jid); ctx['pages'] = []; job_context.write(jid, ctx)
    before = job_context.ensure_pages(jid)['pages']
    raw = transfer.export_bundle([jid], []).read_bytes()
    pcs('b'); staged = transfer.stage(io.BytesIO(raw)); new = transfer.commit(staged['token'], [0], [])['jobs'][0]
    after = job_context.read(new)['pages']
    assert before == after
    assert [job_context.file_digest(p) for p in jobs.input_images(new)] == [p['sha256'] for p in after]

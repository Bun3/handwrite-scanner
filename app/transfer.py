"""자료 이동 서비스. 외부 결과는 원본을 보존한 새 작업으로 합친다."""
import copy
import json
import re
import shutil
import threading
import time
import uuid
import zipfile
from functools import wraps

from app import jobs, job_context, templates_store
from app.config import VERSION
from app.errors import UserError
from app.transfer_archive import require, valid_name, validate_job, validate_template, unpack, MAX_META, MAX_TOTAL, MAX_FILE

_lock = threading.RLock()


def serialized(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        with _lock, jobs._io_lock:
            return fn(*args, **kwargs)
    return call


def root():
    p = jobs.JOBS_DIR.parent / 'transfers'; p.mkdir(exist_ok=True)
    return p


def _id():
    return time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:12]


def _json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def idle(job_id):
    require(valid_name(job_id), '잘못된 작업 ID입니다.')
    st = jobs.status(job_id)
    require(st is not None, '작업을 찾을 수 없습니다.')
    require(st['state'] not in ('queued', 'running'), '진행 중인 작업을 중단한 뒤 자료를 내보내거나 합쳐 주세요.')
    return st


def prepare(job_id):
    st = idle(job_id)
    if not st.get('inputs_ready', True):
        jobs.prepare_inputs(job_id, st, lambda: None)
    ctx = job_context.ensure_pages(job_id)
    return st, ctx


def details(job_id):
    with _lock, jobs._io_lock:
        st, ctx = prepare(job_id)
        done = {r['page'] for r in jobs.results(job_id) or []}
        return {'job': job_id, 'pages': [{**p, 'page': i, 'completed': i in done,
                                        'delegated': i in st.get('delegated_pages', [])} for i, p in enumerate(ctx['pages'])],
                'legacy_templates': ctx.get('legacy_templates', False), 'model': ctx['model']}


def _job_payload(job_id, add_file, split_pages=None):
    st, ctx = prepare(job_id)
    result = jobs.results(job_id)
    if result is None and (jobs.JOBS_DIR / job_id / 'results.json').exists():
        require(False, '저장된 결과 파일이 손상되어 내보낼 수 없습니다.')
    result = result or []
    require(job_context.valid_results(job_id, result), '페이지 결과가 손상되어 내보낼 수 없습니다.')
    selected = list(range(len(ctx['pages']))) if split_pages is None else split_pages
    require(isinstance(selected, list) and selected and all(type(n) is int and 0 <= n < len(ctx['pages']) for n in selected))
    selected = sorted(set(selected))
    if split_pages is not None:
        require(not set(selected) & {r['page'] for r in result}, '이미 완료한 페이지는 분담할 수 없습니다.')
    mapping = {old: new for new, old in enumerate(selected)}
    directory = jobs.JOBS_DIR / job_id
    context = copy.deepcopy(ctx); context['pages'] = [ctx['pages'][i] for i in selected]
    if split_pages is not None:
        context['branch_id'] = uuid.uuid4().hex
        context['parent_branch'] = ctx['branch_id']
    state = {k: st[k] for k in ('id', 'template', 'templates', 'created') if k in st}
    state['delegated_pages'] = [mapping[n] for n in st.get('delegated_pages', []) if n in mapping] if split_pages is None else []
    payload = {'status': state, 'context': context, 'files': {}, 'results': [], 'uploads': []}
    images = jobs.input_images(job_id)
    for old, new in mapping.items():
        path = images[old]
        require(job_context.file_digest(path) == ctx['pages'][old]['sha256'], '원본 이미지가 작업 생성 후 변경되었습니다. 새 작업으로 등록하세요.')
        payload['files'][f'input/{new:06d}{path.suffix.lower()}'] = add_file(path)
    for t in context['templates']:
        payload['files'][t['reference']] = add_file(directory / t['reference'])
    for row in result:
        if row['page'] in mapping:
            n = mapping[row['page']]
            payload['results'].append({**row, 'page': n, 'source_file': context['pages'][n]['source_file'], 'source_page': context['pages'][n]['source_page']})
            payload['files'][f'page_{n:03d}.png'] = add_file(directory / f"page_{row['page']:03d}.png")
    if split_pages is None:
        payload['uploads'] = jobs._read(job_id, 'uploads.json') or []
        for item in payload['uploads']:
            require(re.fullmatch(r'[0-9]{3,6}\.bin', str(item.get('stored', ''))))
            payload['files']['uploads/' + item['stored']] = add_file(directory / 'uploads' / item['stored'])
    return payload


@serialized
def export_bundle(job_ids, names, split_pages=None):
    require(isinstance(job_ids, list) and isinstance(names, list) and 0 < len(job_ids) + len(names) <= 500)
    require(all(isinstance(n, str) for n in job_ids + names))
    require(len(set(job_ids)) == len(job_ids) and len(set(names)) == len(names))
    require(split_pages is None or len(job_ids) == 1, '페이지 분담은 작업 하나를 선택하세요.')
    # 모든 작업 상태를 먼저 확인해 일부 작업만 준비된 채 오류가 나지 않게 한다.
    for jid in job_ids: idle(jid)
    blobs = {}
    def add_file(path):
        require(path.is_file() and not path.is_symlink(), '내보내기에 필요한 원본 또는 이미지가 없습니다.')
        sha = job_context.file_digest(path); blobs[sha] = path
        return sha
    manifest = {'format': 'handwrite-scanner', 'version': 1, 'app_version': VERSION, 'templates': [], 'jobs': []}
    for name in names:
        require(valid_name(name)); tpl = templates_store.get(name); validate_template(tpl)
        manifest['templates'].append({'definition': tpl, 'reference': add_file(templates_store.reference_path(name)), 'selected': True})
    for jid in job_ids:
        payload = _job_payload(jid, add_file, split_pages)
        manifest['jobs'].append(payload)
        for t in payload['context']['templates']:
            item = {'definition': t['definition'], 'reference': t['sha256'], 'selected': False}
            if not any(x['definition'] == item['definition'] and x['reference'] == item['reference'] for x in manifest['templates']):
                manifest['templates'].append(item)
    manifest['blobs'] = {sha: path.stat().st_size for sha, path in blobs.items()}
    require(sum(manifest['blobs'].values()) <= MAX_TOTAL, '자료가 너무 큽니다. 작업을 나누어 내보내세요.')
    require(len(blobs) < 100000 and all(size <= MAX_FILE for size in manifest['blobs'].values()), '파일 수 또는 개별 파일 크기가 한도를 초과했습니다. 자료를 나누어 내보내세요.')
    require(len(manifest['templates']) + len(manifest['jobs']) <= 500, '템플릿과 작업 수가 너무 많습니다. 나누어 내보내세요.')
    for job in manifest['jobs']: validate_job(job, manifest['blobs'])
    encoded = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
    require(len(encoded) <= MAX_META, '자료 목록이 너무 큽니다. 작업을 나누어 내보내세요.')
    destination = root() / (uuid.uuid4().hex + '.hscan')
    try:
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
            archive.writestr('manifest.json', encoded)
            for sha, path in blobs.items(): archive.write(path, 'blobs/' + sha)
        if split_pages is not None:
            st = jobs.status(job_ids[0]); st['delegated_pages'] = sorted(set(st.get('delegated_pages', [])) | set(split_pages))
            jobs.write_status(job_ids[0], st)
        return destination
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _staged(token):
    require(re.fullmatch(r'[a-f0-9]{32}', str(token)), '잘못된 불러오기 요청입니다.')
    directory = root() / token
    require((directory / 'manifest.json').is_file(), '불러오기 대기 자료가 만료되었습니다. 파일을 다시 선택하세요.')
    return directory, json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))


def _duplicate(job):
    key = job_context.digest(job)
    return next((s['id'] for s in jobs.list_jobs() if s.get('import_key') == key), None)


def _template_name(tpl, sha, reserved=None):
    existing = {p.name.casefold(): p.name for p in templates_store.TEMPLATES_DIR.iterdir() if p.is_dir()}
    existing.update({n.casefold(): n for n in reserved or []})
    base = tpl['name']; name = base; counter = 1
    while name.casefold() in existing:
        actual = existing[name.casefold()]
        old = templates_store.get(actual)
        if old and {k: v for k, v in old.items() if k != 'name'} == {k: v for k, v in tpl.items() if k != 'name'}:
            ref = templates_store.TEMPLATES_DIR / actual / 'reference.png'
            if ref.is_file() and job_context.file_digest(ref) == sha: return actual, True
        name = base[:120] + f' (가져옴 {counter})'; counter += 1
    return name, False


def preview(token):
    directory, manifest = _staged(token)
    existing = jobs.list_jobs()
    from app import models
    result = {'token': token, 'templates': [], 'jobs': [], 'model': models.current()['id']}
    for t in manifest['templates']:
        name, same = _template_name(t['definition'], t['reference'])
        result['templates'].append({'name': t['definition']['name'], 'destination': name, 'same': same, 'selected': t.get('selected', False)})
    for job in manifest['jobs']:
        ctx = job['context']
        related = [s['id'] for s in existing if (job_context.read(s['id']) or {}).get('root_id') == ctx['root_id']]
        entry = models.entry(ctx['model'])
        result['jobs'].append({'name': job['status']['id'], 'total': len(ctx['pages']), 'completed': len(job['results']),
                               'model': ctx['model'], 'model_label': entry['label'] if entry else ctx['model'], 'model_installed': bool(entry and models.installed(entry)),
                               'legacy_templates': ctx.get('legacy_templates', False), 'duplicate': _duplicate(job), 'related': related})
    return result


@serialized
def stage(stream):
    token = uuid.uuid4().hex; directory = root() / token
    # 정상 생성한 자료 임시 폴더/내보내기 파일만 정리한다.
    for old in root().iterdir():
        if not old.is_symlink() and re.fullmatch(r'[a-f0-9]{32}(\.hscan)?', old.name) and time.time() - old.stat().st_mtime > 86400:
            if old.is_dir(): shutil.rmtree(old)
            else: old.unlink()
    directory.mkdir()
    try:
        manifest = unpack(stream, directory / 'blobs')
        _json(directory / 'manifest.json', manifest)
        return preview(token)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def _build_job(payload, blob_dir, destination, job_id):
    destination.mkdir(); (destination / 'output').mkdir()
    for path, sha in payload['files'].items():
        target = destination / path; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(blob_dir / sha, target)
    context = copy.deepcopy(payload['context']); context['imported'] = True
    _json(destination / 'context.json', context)
    _json(destination / 'input_pages.json', [{'source_file': p['source_file'], 'source_page': p['source_page']} for p in context['pages']])
    _json(destination / 'results.json', payload['results'])
    if payload.get('uploads'): _json(destination / 'uploads.json', payload['uploads'])
    st = {k: payload['status'][k] for k in ('template', 'templates', 'created', 'delegated_pages') if k in payload['status']}
    st.update(id=job_id, state='done' if len(payload['results']) == len(context['pages']) else 'cancelled',
              inputs_ready=True, selected_pages=len(context['pages']), progress='가져온 작업 · 검수하거나 이어하기를 누르세요.',
              import_key=job_context.digest(payload), origin_job=payload['status']['id'], model=context['model'], context_version=1)
    _json(destination / 'status.json', st)


def _indexes(values, size):
    require(isinstance(values, list) and all(type(n) is int and 0 <= n < size for n in values))
    return sorted(set(values))


@serialized
def commit(token, job_indexes, template_indexes, *, copy_duplicates=False):
    directory, manifest = _staged(token)
    selected_jobs = _indexes(job_indexes, len(manifest['jobs'])); selected_templates = _indexes(template_indexes, len(manifest['templates']))
    transaction = root() / ('transaction-' + uuid.uuid4().hex); transaction.mkdir()
    moves, published = [], []
    out = {'jobs': [], 'templates': [], 'skipped': []}
    try:
        reserved = []
        planned_jobs = {}
        for n in selected_templates:
            t = manifest['templates'][n]; name, same = _template_name(t['definition'], t['reference'], reserved)
            out['templates'].append(name)
            if same: continue
            reserved.append(name); staged = transaction / ('template-' + str(n)); staged.mkdir()
            _json(staged / 'template.json', {**t['definition'], 'name': name, 'reference': 'reference.png'})
            shutil.copyfile(directory / 'blobs' / t['reference'], staged / 'reference.png')
            moves.append((staged, templates_store.TEMPLATES_DIR / name))
        for n in selected_jobs:
            payload = manifest['jobs'][n]
            fingerprint = job_context.digest(payload)
            duplicate = _duplicate(payload) or planned_jobs.get(fingerprint)
            if duplicate and not copy_duplicates: out['skipped'].append(duplicate); continue
            jid = _id(); staged = transaction / jid
            _build_job(payload, directory / 'blobs', staged, jid)
            planned_jobs[fingerprint] = jid
            moves.append((staged, jobs.JOBS_DIR / jid)); out['jobs'].append(jid)
        for src, dest in moves:
            require(not dest.exists(), '다른 작업이 같은 이름으로 등록되었습니다. 다시 불러오세요.')
            src.rename(dest); published.append(dest)
        return out
    except Exception:
        for p in reversed(published): shutil.rmtree(p)
        raise
    finally: shutil.rmtree(transaction, ignore_errors=True)


def _merge_plan(token, index, target):
    directory, manifest = _staged(token); _indexes([index], len(manifest['jobs']))
    incoming = manifest['jobs'][index]
    st, ctx = prepare(target)
    require(ctx['root_id'] == incoming['context']['root_id'], '서로 다른 원본 작업은 합칠 수 없습니다.')
    require(ctx['template_digest'] == incoming['context']['template_digest'], '사용한 양식 버전이 달라 합칠 수 없습니다. 별도 작업으로 가져오세요.')
    local = jobs.results(target) or []
    require(job_context.valid_results(target, local), '기존 작업의 결과가 손상되었습니다.')
    local_pages = {p['id']: i for i, p in enumerate(ctx['pages'])}
    mapping = {}
    for n, p in enumerate(incoming['context']['pages']):
        require(p['id'] in local_pages, '대상 작업에 없는 페이지가 있습니다. 전체 원본 작업을 선택하세요.')
        dest = local_pages[p['id']]
        require(p['sha256'] == ctx['pages'][dest]['sha256'], '같은 페이지의 원본 이미지가 다릅니다.')
        mapping[n] = dest
    by_page = {p['page']: p for p in local}
    added, same, conflicts, converted = [], [], [], {}
    for p in incoming['results']:
        n = mapping[p['page']]; source = ctx['pages'][n]
        row = {**p, 'page': n, 'source_file': source['source_file'], 'source_page': source['source_page']}
        converted[n] = row
        old = by_page.get(n)
        if old is None: added.append(n)
        elif {k: v for k, v in old.items() if k not in ('source_file', 'source_page')} == {k: v for k, v in row.items() if k not in ('source_file', 'source_page')}:
            same.append(n)
        else: conflicts.append({'page': n, 'source_file': source['source_file'], 'source_page': source['source_page'], 'local': old, 'incoming': row})
    revision = job_context.digest({'status': st, 'context': ctx, 'results': local, 'incoming': incoming})
    plan = {'added': added, 'same': same, 'conflicts': conflicts, 'revision': revision, 'model_changed': ctx['model'] != incoming['context']['model']}
    return plan, incoming, converted, mapping


@serialized
def merge_preview(token, index, target):
    return _merge_plan(token, index, target)[0]


@serialized
def merge(token, index, target, revision, choices):
    plan, incoming, converted, mapping = _merge_plan(token, index, target)
    require(revision == plan['revision'], '확인 후 결과가 변경되었습니다. 병합 내용을 다시 확인하세요.')
    require(isinstance(choices, dict) and all(choices.get(str(c['page'])) in ('local', 'incoming') for c in plan['conflicts']), '충돌하는 페이지마다 사용할 결과를 선택하세요.')
    directory, _ = _staged(token)
    blobs = {}
    def add(path):
        sha = job_context.file_digest(path); blobs[sha] = path; return sha
    payload = _job_payload(target, add)
    rows = {p['page']: p for p in payload['results']}
    inverse = {dest: src for src, dest in mapping.items()}
    for n, row in converted.items():
        if n in plan['added'] or choices.get(str(n)) == 'incoming':
            rows[n] = row
            sha = incoming['files'][f'page_{inverse[n]:03d}.png']
            blobs[sha] = directory / 'blobs' / sha
            payload['files'][f'page_{n:03d}.png'] = sha
    payload['results'] = sorted(rows.values(), key=lambda p: p['page'])
    payload['status']['delegated_pages'] = [n for n in payload['status'].get('delegated_pages', []) if n not in rows]
    payload['context']['branch_id'] = uuid.uuid4().hex
    payload['context']['merged_from'] = [target, incoming['status']['id']]
    staging = root() / ('transaction-' + uuid.uuid4().hex); staging.mkdir()
    jid = _id()
    try:
        blob_dir = staging / 'blobs'; blob_dir.mkdir()
        for sha, path in blobs.items(): shutil.copyfile(path, blob_dir / sha)
        _build_job(payload, blob_dir, staging / jid, jid)
        require(not (jobs.JOBS_DIR / jid).exists(), '새 작업 ID가 충돌했습니다. 다시 시도하세요.')
        (staging / jid).rename(jobs.JOBS_DIR / jid)
        return {'job': jid}
    finally: shutil.rmtree(staging, ignore_errors=True)


@serialized
def release_assignment(job_id):
    st = idle(job_id); st['delegated_pages'] = []; jobs.write_status(job_id, st)
    return {'ok': True}

"""작업의 양식 사본과 PC를 옮겨도 유지되는 페이지 식별 정보."""
import hashlib
import json
import shutil
import uuid

from app import jobs, templates_store
from app.errors import UserError


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(job_id):
    context = jobs._read(job_id, 'context.json')
    if context is None and (jobs.status(job_id) or {}).get('context_version'):
        raise UserError('context_invalid', '작업에 보관된 양식 정보가 없거나 손상되었습니다.', '원본 PC의 자료 파일에서 다시 가져오세요.')
    return context


def write(job_id, context):
    jobs._write_atomic(job_id, 'context.json', json.dumps(context, ensure_ascii=False))


def capture(job_id, *, legacy=False, refresh=False):
    old = read(job_id)
    if old and not refresh:
        return old
    st = jobs.status(job_id)
    names = st.get('templates')
    if names is None:
        names = [st['template']] if st.get('template') else [t['name'] for t in templates_store.list_templates()]
    target = jobs.JOBS_DIR / job_id / 'context_templates'
    target.mkdir(exist_ok=True)
    captured = []
    for name in names:
        tpl = templates_store.get(name)
        if tpl is None:
            raise UserError('template_missing', f'양식을 찾을 수 없습니다: {name}', '양식을 복원한 뒤 다시 시도하세요.')
        source = templates_store.reference_path(name)
        sha = file_digest(source)
        path = target / f'{sha}.png'
        if not path.exists():
            temporary = target / (uuid.uuid4().hex + '.tmp')
            try:
                shutil.copyfile(source, temporary); temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        captured.append({'definition': tpl, 'reference': f'context_templates/{path.name}', 'sha256': sha})
    from app import models
    context = dict(old or {}, root_id=(old or {}).get('root_id', uuid.uuid4().hex),
                   branch_id=(old or {}).get('branch_id', uuid.uuid4().hex), templates=captured,
                   template_digest=digest(captured), model=models.current()['id'], legacy_templates=legacy,
                   pages=(old or {}).get('pages', []))
    write(job_id, context)
    st['context_version'] = 1
    jobs.write_status(job_id, st)
    return context


def ensure_pages(job_id):
    context = read(job_id) or capture(job_id, legacy=True)
    images = jobs.input_images(job_id)
    if not context['pages']:
        sources = jobs.page_sources(job_id)
        context['pages'] = [{'id': uuid.uuid4().hex, 'sha256': file_digest(path),
                             'source_file': sources[i].get('source_file', path.name) if i < len(sources) else path.name,
                             'source_page': sources[i].get('source_page', i + 1) if i < len(sources) else i + 1}
                            for i, path in enumerate(images)]
        write(job_id, context)
    if len(context['pages']) != len(images):
        raise UserError('transfer_invalid', '작업의 페이지 정보와 원본이 일치하지 않습니다.', '원본 작업을 확인하세요.')
    return context


def pool(job_id):
    context = read(job_id)
    if context is None:
        return None  # 이전 작업은 기존 참조 방식을 유지한다.
    return [(t['definition'], jobs.JOBS_DIR / job_id / t['reference']) for t in context['templates']]


def valid_results(job_id, result):
    if not isinstance(result, list) or any(not isinstance(p, dict) or type(p.get('page')) is not int for p in result):
        return False
    pages = [p['page'] for p in result]
    context = read(job_id)
    if context and context.get('pages'):
        return pages == sorted(set(pages)) and all(0 <= p < len(context['pages']) for p in pages)
    return pages == list(range(len(pages)))


def reference(job_id, name):
    stored = pool(job_id)
    if stored is None:
        return templates_store.reference_path(name)
    return next((ref for tpl, ref in stored if tpl['name'] == name), None)

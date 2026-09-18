"""실행 파일 없이 JSON과 문서만 담는 버전 1 hscan 컨테이너."""
import hashlib
import json
import math
import re
import shutil
import zipfile

from PIL import Image
from app.errors import UserError
from app import job_context

MAX_TOTAL = 8 * 1024**3
MAX_FILE = 2 * 1024**3
MAX_META = 16 * 1024**2
HEX = re.compile(r'^[a-f0-9]{64}$')
UID = re.compile(r'^[a-f0-9]{32}$')
IMAGE = re.compile(r'^input/[0-9]{3,6}\.(png|jpg|jpeg|bmp|webp|tif|tiff)$')
PATH = re.compile(r'^(input/[0-9]{3,6}\.(png|jpg|jpeg|bmp|webp|tif|tiff)|page_[0-9]{3,6}\.png|context_templates/[a-f0-9]{64}\.png|uploads/[0-9]{3,6}\.bin)$')


def require(ok, message='자료 파일의 내용이 올바르지 않습니다.'):
    if not ok:
        raise UserError('transfer_invalid', message, '원본 PC에서 다시 내보내거나 올바른 자료 파일을 선택하세요.')


def valid_name(name):
    return isinstance(name, str) and 0 < len(name) <= 150 and not name.startswith('.') and not re.search(r'[/\\:*?"<>|\x00-\x1f]', name) and name[-1:] not in (' ', '.') and name.split('.')[0].upper() not in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}


def validate_template(tpl):
    require(isinstance(tpl, dict) and valid_name(tpl.get('name')))
    fields = tpl.get('fields'); require(isinstance(fields, list) and len(fields) <= 2000)
    ids = set()
    for f in fields:
        require(isinstance(f, dict) and isinstance(f.get('id'), str) and f['id'] and f['id'] not in ids)
        ids.add(f['id'])
        require(isinstance(f.get('label'), str) and f.get('type') in ('text', 'text_free', 'candidates', 'circle', 'phone', 'number', 'time'))
        box = f.get('box')
        require(isinstance(box, list) and len(box) == 4 and all(type(n) in (int, float) and math.isfinite(n) and 0 <= n < 1000000 for n in box) and box[2] > 0 and box[3] > 0)
        require(isinstance(f.get('candidates', []), list) and all(isinstance(c, str) for c in f.get('candidates', [])))
        require(f.get('type') != 'circle' or bool(f.get('candidates')))
        require(isinstance(f.get('hint', ''), str))
        for k in ('min', 'max'):
            require(k not in f or type(f[k]) in (int, float) and math.isfinite(f[k]))
    rules = tpl.get('rules', [])
    require(isinstance(rules, list) and all(isinstance(r, str) for r in rules))
    from app.rules import resolve, validate_expr
    labels = {f['label']: f['id'] for f in fields}
    for rule in rules:
        require(not validate_expr(resolve(rule, labels)), '가져올 양식에 지원하지 않는 검증 규칙이 있습니다.')


def validate_job(job, blobs):
    require(isinstance(job, dict))
    st, ctx, files, results = job.get('status'), job.get('context'), job.get('files'), job.get('results')
    require(isinstance(st, dict) and isinstance(ctx, dict) and isinstance(files, dict) and isinstance(results, list))
    require(isinstance(st.get('id'), str) and isinstance(st.get('created', ''), str))
    require(UID.fullmatch(str(ctx.get('root_id', ''))) and UID.fullmatch(str(ctx.get('branch_id', ''))))
    require(isinstance(ctx.get('model'), str) and len(ctx['model']) < 200)
    pages, tpls = ctx.get('pages'), ctx.get('templates')
    require(isinstance(pages, list) and 0 < len(pages) <= 50000 and isinstance(tpls, list))
    for path, sha in files.items():
        require(PATH.fullmatch(path) and sha in blobs)
    inputs = sorted(p for p in files if IMAGE.fullmatch(p))
    require(len(inputs) == len(pages))
    ids = set()
    for i, p in enumerate(pages):
        require(isinstance(p, dict) and UID.fullmatch(str(p.get('id', ''))) and p['id'] not in ids)
        ids.add(p['id'])
        require(p.get('sha256') == files[inputs[i]] and isinstance(p.get('source_file'), str) and type(p.get('source_page')) is int and p['source_page'] > 0)
    names = set()
    for t in tpls:
        require(isinstance(t, dict)); validate_template(t.get('definition'))
        require(t['definition']['name'] not in names)
        names.add(t['definition']['name'])
        require(re.fullmatch(r'context_templates/[a-f0-9]{64}\.png', str(t.get('reference', ''))) and files.get(t['reference']) == t.get('sha256'))
    require(ctx.get('template_digest') == job_context.digest(tpls))
    require(st.get('template') is None or st['template'] in names)
    if 'templates' in st:
        require(isinstance(st['templates'], list) and st['templates'] and all(n in names for n in st['templates']))
    seen = set()
    for result in results:
        require(isinstance(result, dict) and type(result.get('page')) is int)
        n = result['page']; require(0 <= n < len(pages) and n not in seen); seen.add(n)
        require(result.get('template') is None or result['template'] in names)
        require(f'page_{n:03d}.png' in files and isinstance(result.get('fields'), list))
        require(isinstance(result.get('warnings', []), list) and all(isinstance(w, str) for w in result.get('warnings', [])))
        fids = set()
        for f in result['fields']:
            require(isinstance(f, dict) and isinstance(f.get('id'), str) and f['id'] not in fids)
            fids.add(f['id'])
            require(isinstance(f.get('label'), str) and isinstance(f.get('value'), str))
            require(type(f.get('confidence')) in (int, float) and math.isfinite(f['confidence']) and 0 <= f['confidence'] <= 1)
            if f.get('box') is not None:
                require(isinstance(f['box'], list) and len(f['box']) == 4 and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v < 1000000 for v in f['box']))
    require([p['page'] for p in results] == sorted(seen))
    delegated = st.get('delegated_pages', [])
    require(isinstance(delegated, list) and all(type(n) is int and 0 <= n < len(pages) and n not in seen for n in delegated))
    uploads = job.get('uploads', [])
    require(isinstance(uploads, list))
    for item in uploads:
        require(isinstance(item, dict) and isinstance(item.get('name'), str) and re.fullmatch(r'[0-9]{3,6}\.bin', str(item.get('stored', ''))))
        require('uploads/' + item['stored'] in files)
        require(item.get('pages') is None or isinstance(item['pages'], list) and all(type(n) is int and n > 0 for n in item['pages']))


def unpack(stream, destination):
    """검증 후 해시 이름으로만 저장. ZIP 경로를 파일 시스템 경로로 사용하지 않는다."""
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            require(0 < len(entries) <= 100000)
            require(len({e.filename for e in entries}) == len(entries))
            require(all(e.filename == 'manifest.json' or re.fullmatch(r'blobs/[a-f0-9]{64}', e.filename) for e in entries))
            require(all(not e.flag_bits & 1 and (e.external_attr >> 16) & 0o170000 != 0o120000 for e in entries))
            meta = archive.getinfo('manifest.json'); require(meta.file_size <= MAX_META)
            total = sum(e.file_size for e in entries)
            require(total <= MAX_TOTAL and all(e.file_size <= MAX_FILE for e in entries), '자료 파일의 허용 크기를 초과했습니다. 작업을 나누어 내보내세요.')
            require(shutil.disk_usage(destination.parent).free > total * 2 + 64 * 1024**2, '자료를 불러올 저장 공간이 부족합니다.')
            manifest = json.loads(archive.read(meta))
            require(manifest.get('format') == 'handwrite-scanner' and manifest.get('version') == 1, '지원하지 않는 자료 파일 버전입니다. 프로그램을 업데이트하세요.')
            blobs = manifest.get('blobs'); require(isinstance(blobs, dict))
            require(set(e.filename for e in entries) == {'manifest.json'} | {'blobs/' + sha for sha in blobs})
            for sha, size in blobs.items():
                require(HEX.fullmatch(sha) and type(size) is int and size == archive.getinfo('blobs/' + sha).file_size)
            require(isinstance(manifest.get('templates'), list) and isinstance(manifest.get('jobs'), list))
            require(len(manifest['templates']) + len(manifest['jobs']) <= 500)
            for t in manifest['templates']:
                validate_template(t.get('definition')); require(t.get('reference') in blobs)
            for job in manifest['jobs']: validate_job(job, blobs)
            destination.mkdir()
            for sha in blobs:
                with archive.open('blobs/' + sha) as src, (destination / sha).open('wb') as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
                require(job_context.file_digest(destination / sha) == sha, '자료 파일이 손상되었습니다. 다시 내보내 주세요.')
            images = {t['reference'] for t in manifest['templates']}
            for job in manifest['jobs']:
                images.update(sha for path, sha in job['files'].items() if not path.startswith('uploads/'))
            for sha in images:
                with Image.open(destination / sha) as image: image.verify()
            return manifest
    except UserError:
        raise
    except (KeyError, ValueError, TypeError, AttributeError, OSError, zipfile.BadZipFile, Image.DecompressionBombError) as exc:
        raise UserError('transfer_invalid', '자료 파일이 손상되었거나 올바른 형식이 아닙니다.', '원본 PC에서 다시 내보내세요.') from exc

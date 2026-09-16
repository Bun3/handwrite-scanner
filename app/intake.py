"""검사 전에 업로드 원본을 보관하고 페이지 선택을 검증한다."""
import io
import json
import re
import shutil
import time
import uuid
import threading

import pymupdf
from PIL import Image

from app import jobs, templates_store
from app.errors import UserError

_lock = threading.RLock()


def _root():
    return jobs.JOBS_DIR.parent / 'intake'


def _directory(token):
    if not re.fullmatch(r'[a-f0-9]{32}', token):
        raise UserError('input_missing', '입력 파일을 찾을 수 없습니다.', '파일을 다시 선택하세요.')
    return _root() / token


def _read(token):
    path = _directory(token) / 'manifest.json'
    if not path.is_file():
        raise UserError('input_missing', '임시 입력이 만료되었거나 없습니다.', '파일을 다시 선택하세요.')
    return json.loads(path.read_text(encoding='utf-8'))


def _pdf(path):
    try:
        # 손상된 PDF의 네이티브 예외가 Windows 파일 핸들을 붙잡지 않도록 메모리로 연다.
        doc = pymupdf.open(stream=path.read_bytes(), filetype='pdf')
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise UserError('pdf_invalid', 'PDF를 읽을 수 없습니다.', 'PDF가 정상적으로 열리는지 확인하고 다시 저장하세요.') from exc
    if doc.needs_pass:
        doc.close()
        raise UserError('pdf_password', '암호가 설정된 PDF입니다.', '암호를 해제한 PDF를 등록하세요.')
    return doc


def create(files):
    with _lock:
        root = _root()
        root.mkdir(parents=True, exist_ok=True)
        for old in root.iterdir():
            if (re.fullmatch(r'[a-f0-9]{32}', old.name) and old.is_dir()
                    and old.resolve().parent == root.resolve() and not old.is_symlink()
                    and time.time() - old.stat().st_mtime > 86400):
                shutil.rmtree(old, ignore_errors=True)
        token = uuid.uuid4().hex
        directory = _directory(token)
        directory.mkdir()
        info = []
        try:
            for index, (name, data) in enumerate(files):
                path = directory / f'{index}.bin'
                path.write_bytes(data)
                is_pdf = name.lower().endswith('.pdf') or data.startswith(b'%PDF-')
                if is_pdf:
                    with _pdf(path) as doc:
                        count = len(doc)
                else:
                    with Image.open(path) as img:
                        img.verify()
                    count = 1
                if not count:
                    raise UserError('empty_input', '빈 문서입니다.', '페이지가 있는 문서를 선택하세요.')
                info.append({'index': index, 'name': name, 'pages': count, 'pdf': is_pdf})
            if not info:
                raise UserError('empty_input', '파일을 선택하세요.', '검사할 문서를 하나 이상 등록하세요.')
            result = {'token': token, 'files': info}
            from app.update_package import write_json
            write_json(directory / 'manifest.json', result)
            return result
        except Exception:
            if directory.resolve().parent == root.resolve():
                shutil.rmtree(directory, ignore_errors=True)
            raise


def preview(token, file_index, page):
    with _lock:
        info = _read(token)['files']
        if not 0 <= file_index < len(info) or not 1 <= page <= info[file_index]['pages']:
            raise UserError('page_invalid', '없는 페이지입니다.', '페이지 선택 화면을 다시 열어 주세요.')
        path = _directory(token) / f'{file_index}.bin'
        if info[file_index]['pdf']:
            with _pdf(path) as doc:
                pg = doc[page - 1]
                scale = min(600 / pg.rect.width, 800 / pg.rect.height, 1)
                return pg.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes('png')
        with Image.open(path) as img:
            img = img.convert('RGB')
            img.thumbnail((600, 800))
            buf = io.BytesIO()
            img.save(buf, 'PNG')
            return buf.getvalue()


def start(token, names, selections):
    with _lock:
        draft = _read(token)
        if draft.get('job_id') and jobs.status(draft['job_id']):
            return draft['job_id']
        if not isinstance(names, list) or not names:
            raise UserError('template_required', '검사할 양식을 하나 이상 선택하세요.', '먼저 템플릿 화면에서 양식을 등록할 수 있습니다.')
        for name in names:
            if (not isinstance(name, str) or not name or name.startswith('.')
                    or re.search(r'[/\\:*?"<>|]', name)):
                raise UserError('template_invalid', '잘못된 양식 이름입니다.', '목록에서 양식을 다시 선택하세요.')
            if templates_store.get(name) is None:
                raise UserError('template_missing', f'양식을 찾을 수 없습니다: {name}', '양식을 다시 등록하고 선택하세요.')
            templates_store.reference_path(name)
        info = draft['files']
        if not isinstance(selections, list) or len(selections) != len(info):
            raise UserError('page_invalid', '페이지 선택을 확인하세요.', '파일별 검사할 페이지를 선택하세요.')
        normalized = []
        for item, selected in zip(info, selections):
            if (not isinstance(selected, list) or any(type(n) is not int or not 1 <= n <= item['pages'] for n in selected)):
                raise UserError('page_invalid', '페이지 번호가 문서 범위를 벗어났습니다.', '표시된 페이지에서 다시 선택하세요.')
            normalized.append(sorted(set(selected)))
        if not any(normalized):
            raise UserError('page_required', '검사할 페이지를 하나 이상 선택하세요.', '전체 선택 또는 페이지 체크박스를 사용하세요.')
        directory = _directory(token)
        pairs = [(item['name'], (directory / f"{item['index']}.bin").read_bytes()) for item in info]
        jid = jobs.create(None, pairs, defer=True, templates=list(dict.fromkeys(names)), selections=normalized)
        from app.update_package import write_json
        draft['job_id'] = jid
        write_json(directory / 'manifest.json', draft)
        return jid

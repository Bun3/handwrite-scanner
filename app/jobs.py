"""job 상태 = data/jobs/<id>/ 파일. status.json / results.json / input/ / output/"""
import json
import time
import uuid
import threading

from app.config import JOBS_DIR
_volatile_status = {}  # 디스크에 오류 상태조차 저장할 수 없을 때 현재 실행 중 안내용
_io_lock = threading.RLock()


def create(template: str | None, files: list[tuple[str, bytes]], *, defer=False,
           templates=None, selections=None) -> str:
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    d = JOBS_DIR / job_id
    (d / "input").mkdir(parents=True)
    (d / "output").mkdir()
    if defer:
        (d / "uploads").mkdir()
        manifest = []
        for i, (name, data) in enumerate(files):
            stored = f"{i:03d}.bin"
            (d / "uploads" / stored).write_bytes(data)
            manifest.append({"name": name, "stored": stored,
                             "pages": selections[i] if selections is not None else None})
        _write_atomic(job_id, "uploads.json", json.dumps(manifest, ensure_ascii=False))
        options = {'templates': templates} if templates is not None else {}
        write_status(job_id, {"id": job_id, "template": template, "state": "queued", **options,
                             "phase": "preparing", "inputs_ready": False,
                             "progress": "접수 완료 · 문서 준비 대기", "created": time.strftime("%Y-%m-%d %H:%M:%S")})
        return job_id
    page = 0
    for name, data in files:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
        if ext == "pdf" or data[:5] == b"%PDF-":
            # 복합기 스캔 PDF: 페이지별 이미지로 분해 (전 양식 1장짜리 전제)
            import pymupdf
            doc = pymupdf.open(stream=data, filetype="pdf")
            for pg in doc:
                pg.get_pixmap(dpi=300).save(d / "input" / f"{page:03d}.png")
                page += 1
            continue
        if not ext.isalnum() or len(ext) > 5:
            ext = "png"
        (d / "input" / f"{page:03d}.{ext}").write_bytes(data)
        page += 1
    write_status(job_id, {"id": job_id, "template": template, "state": "queued",
                          "progress": "", "created": time.strftime("%Y-%m-%d %H:%M:%S")})
    return job_id


def prepare_inputs(job_id, st, check_cancel):
    """새 업로드의 PDF 변환은 워커에서 수행. 기존 작업은 변환 완료로 취급."""
    if st.get("inputs_ready", True):
        return
    from app.errors import UserError
    from PIL import Image
    import pymupdf
    d = JOBS_DIR / job_id
    manifest = json.loads((d / "uploads.json").read_text(encoding="utf-8"))
    page = 0
    sources = []
    for index, item in enumerate(manifest):
        check_cancel()
        selected = item.get('pages')
        if selected == []:
            continue
        src = d / "uploads" / item["stored"]
        with src.open('rb') as stream:
            is_pdf = stream.read(5) == b'%PDF-'
        st.update(phase="preparing", progress=f"문서 준비 · {index + 1}/{len(manifest)} 파일 · {item['name']}")
        write_status(job_id, st)
        if item['name'].lower().endswith('.pdf') or is_pdf:
            try:
                doc = pymupdf.open(src, filetype='pdf')
            except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
                raise UserError('pdf_invalid', f"PDF를 읽을 수 없습니다: {item['name']}", 'PDF가 정상적으로 열리는지 확인하고 다시 저장한 파일을 등록하세요.') from exc
            with doc:
                if doc.needs_pass:
                    raise UserError('pdf_password', '암호가 설정된 PDF입니다.', '암호를 해제한 PDF를 다시 등록하세요.')
                for pg in doc:
                    if selected is not None and pg.number + 1 not in selected:
                        continue
                    check_cancel()
                    st['progress'] = f"PDF 준비 · {index + 1}/{len(manifest)} 파일 · {pg.number + 1}/{len(doc)}페이지"
                    write_status(job_id, st)
                    pg.get_pixmap(dpi=300).save(d / 'input' / f'{page:03d}.png')
                    sources.append({'source_file': item['name'], 'source_page': pg.number + 1})
                    page += 1
        else:
            with Image.open(src) as img:
                img.convert('RGB').save(d / 'input' / f'{page:03d}.png')
            sources.append({'source_file': item['name'], 'source_page': 1})
            page += 1
    if not page:
        raise UserError('empty_input', '처리할 문서 페이지가 없습니다.', '이미지 또는 페이지가 있는 PDF를 등록하세요.')
    _write_atomic(job_id, 'input_pages.json', json.dumps(sources, ensure_ascii=False))
    st.update(inputs_ready=True, selected_pages=page, phase='recognizing', progress=f'문서 준비 완료 · {page}페이지')
    write_status(job_id, st)


def _read(job_id: str, name: str):
    f = JOBS_DIR / job_id / name
    try:
        with _io_lock:
            return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None  # 크래시로 쓰다 만 파일(NUL 등) — 없는 것으로 취급, 서버는 계속 뜬다


def status(job_id: str) -> dict | None:
    return _volatile_status.get(job_id) or _read(job_id, "status.json")


def results(job_id: str) -> list | None:
    return _read(job_id, "results.json")


def _write_atomic(job_id: str, name: str, text: str) -> None:
    # 크래시 순간 쓰다 만 파일이 남지 않게 임시 파일 → 교체
    f = JOBS_DIR / job_id / name
    tmp = f.with_name(name + ".tmp")
    with _io_lock:
        tmp.write_text(text, encoding="utf-8")
        for attempt in range(5):
            try:
                tmp.replace(f)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(.02 * (attempt + 1))


def write_status(job_id: str, st: dict) -> None:
    _write_atomic(job_id, "status.json", json.dumps(st, ensure_ascii=False))
    _volatile_status.pop(job_id, None)


def remember_status_failure(job_id, st, exc):
    from app.errors import explain
    info = explain(exc)
    info['action'] += ' 이 오류 상태는 디스크에 저장하지 못했으므로 프로그램을 닫기 전에 확인해 주세요.'
    _volatile_status[job_id] = dict(st, state='error', error=str(exc), error_info=info)


def write_results(job_id: str, res: list) -> None:
    _write_atomic(job_id, "results.json",
                  json.dumps(res, ensure_ascii=False, indent=2))


def list_jobs() -> list[dict]:
    out = [s for d in sorted(JOBS_DIR.iterdir(), reverse=True)
           if (s := status(d.name))]
    return out


def input_images(job_id: str) -> list:
    return sorted((JOBS_DIR / job_id / "input").iterdir())


def page_sources(job_id):
    return _read(job_id, 'input_pages.json') or []


def delete(job_id: str) -> None:
    import shutil
    target = (JOBS_DIR / job_id).resolve()
    if target.parent != JOBS_DIR.resolve():  # 경로 이탈 방어 (2차 방어선)
        raise ValueError(f"잘못된 작업 경로: {job_id}")
    shutil.rmtree(target, ignore_errors=True)
    _volatile_status.pop(job_id, None)

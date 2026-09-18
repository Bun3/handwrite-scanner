"""llama-server(Qwen2.5-VL) 기동·호출. 외부 API 호출 없음 — 전부 localhost."""
import base64
import subprocess
import time
import threading
from contextvars import ContextVar

import httpx

from app import config
from app.errors import UserError, explain

_URL = f"http://127.0.0.1:{config.LLAMA_PORT}"
_proc = None
_start_lock = threading.Lock()
_engine_state = 'idle'
_engine_error = None
progress_reporter = ContextVar('engine_progress', default=lambda phase: None)


def log_tail():
    try:
        with (config.DATA_DIR / 'logs/engine.log').open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 16000))
            return stream.read().decode('utf-8', errors='replace')
    except OSError:
        return ''


def is_up() -> bool:
    try:
        return httpx.get(_URL + "/health", timeout=2).status_code == 200
    except Exception:
        return False


def status() -> dict:
    """A failed health probe alone does not mean the engine is loading."""
    global _engine_state, _engine_error
    if is_up():
        _engine_state, _engine_error = 'ready', None
        return {'state': 'ready'}
    if _engine_state == 'loading':
        return {'state': 'loading'}
    if _engine_error:
        return {'state': 'error', 'error': dict(_engine_error)}
    if _proc is not None or _engine_state == 'ready':
        return {'state': 'error', 'error': {
            'code': 'engine_connection', 'message': '인식 엔진이 응답하지 않습니다.',
            'action': '작업 목록의 진행 상태를 확인하세요. 오류로 끝난 작업은 이어하기로 다시 시도할 수 있습니다.'}}
    return {'state': 'idle'}


def ensure_server(timeout: int = 300) -> None:
    global _engine_state, _engine_error
    if is_up():
        _engine_state, _engine_error = 'ready', None
        return
    progress_reporter.get()('engine_loading')
    with _start_lock:
        _engine_state, _engine_error = 'loading', None
        try:
            _ensure_server(timeout)
        except Exception as exc:
            _engine_state, _engine_error = 'error', explain(exc)
            raise
        else:
            _engine_state = 'ready'
    progress_reporter.get()('recognizing')


def _ensure_server(timeout: int = 300) -> None:
    """llama-server가 없으면 선택된 모델로 띄우고 로드 완료까지 대기."""
    global _proc
    if is_up():
        return
    from app import models
    model, mmproj = models.paths(models.current())
    if not config.LLAMA_SERVER.is_file():
        raise UserError('engine_missing', '인식 엔진 실행 파일이 없습니다.', '배포 ZIP 전체를 다시 설치 폴더에 덮어쓰고 보안 프로그램이 llama-server.exe를 차단했는지 확인하세요.')
    if not model.is_file() or not mmproj.is_file():
        raise UserError('model_missing', '선택한 인식 모델 파일이 없습니다.', '인식 모델 목록에서 다운로드 상태를 확인하고 설치된 모델을 선택하세요.')
    progress_reporter.get()('engine_loading')
    if _proc is None or _proc.poll() is not None:
        log_path = config.DATA_DIR / 'logs/engine.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('w', encoding='utf-8') as log:
            _proc = subprocess.Popen(
                [str(config.LLAMA_SERVER), "-m", str(model),
                 "--mmproj", str(mmproj), "--port", str(config.LLAMA_PORT),
                 "--host", "127.0.0.1", "-c", "8192"],
                stdout=log, stderr=log,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_up():
            progress_reporter.get()('recognizing')
            return
        if _proc.poll() is not None:
            tail = log_tail()
            if any(s in tail.lower() for s in ('out of memory', 'bad_alloc', 'cannot allocate memory', 'failed to allocate')):
                raise MemoryError('엔진 메모리 할당 실패\n' + tail)
            raise UserError('engine_exited', f'인식 엔진이 시작 중 종료되었습니다 (종료 코드 {_proc.returncode}).',
                            '모델 파일과 설치 상태를 확인하세요. 아래 상세 내용의 엔진 로그를 복사해 전달해 주세요.')
        time.sleep(2)
    raise UserError('engine_start_timeout', '인식 엔진 준비가 제한 시간을 넘었습니다.', '모델을 불러오는 데 오래 걸릴 수 있습니다. 잠시 후 이어하기를 누르거나 더 작은 모델을 선택하세요.')


def restart() -> None:
    """모델 교체 등으로 llama-server 재기동이 필요할 때. 다음 호출 시 새로 뜬다."""
    global _proc, _engine_state, _engine_error
    if _proc is not None and _proc.poll() is None:
        _proc.kill()
    else:  # 다른 프로세스(이전 실행)가 띄운 서버까지 정리
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"],
                       capture_output=True)
    _proc = None
    _engine_state, _engine_error = 'idle', None


def ask_image(image_bytes: bytes, prompt: str, timeout: float = 600) -> str:
    """이미지 한 장 + 프롬프트 → 모델 답변 텍스트."""
    ensure_server()
    b64 = base64.b64encode(image_bytes).decode()
    r = httpx.post(_URL + "/v1/chat/completions", json={
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]}],
    }, timeout=timeout)
    r.raise_for_status()
    try:
        return r.json()["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise UserError('engine_format', '인식 엔진의 응답 형식을 읽을 수 없습니다.', '현재 모델과 엔진의 호환성을 확인하세요. 이어하기로 다시 시도하고 반복되면 상세 내용을 전달해 주세요.') from exc

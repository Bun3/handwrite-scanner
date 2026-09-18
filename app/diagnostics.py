"""Opt-in diagnostic snapshots. Raw logs and exception messages never enter reports."""
import copy
import json
import os
import platform
import re
import secrets
import shutil
import threading
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from app import config, jobs, models

router = APIRouter(prefix='/api/diagnostics')
_lock = threading.RLock()
_drafts = {}
MAX_BYTES = 256 * 1024
# Public submission URL only. Deployment credentials must never be distributed.
REPORT_ENDPOINT = 'https://handwrite-error-reports.bun3-dev.workers.dev/reports'


def _now():
    return datetime.now(timezone.utc).isoformat()


def _symbol(value, fallback='unknown'):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', value) else fallback


def _journal():
    return config.DATA_DIR / 'logs' / 'diagnostic-events.json'


def _events():
    try:
        path = _journal()
        if path.stat().st_size > MAX_BYTES:
            return []
        entries = json.loads(path.read_text(encoding='utf-8'))
        # Rebuild only our own schema, even if the file was edited externally.
        return [dict(time=str(e['time'])[:40] if re.fullmatch(r'[0-9T:+.Z-]+', str(e['time'])) else '',
                     code=_symbol(e.get('code')), source=_symbol(e.get('source')),
                     exception=_symbol(e.get('exception')), frames=[
                         {'module': _symbol(f.get('module')), 'line': int(f['line'])}
                         for f in e.get('frames', [])[:8] if isinstance(f.get('line'), int)])
                for e in entries[-100:]]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return []


def record_error(exc, code, source):
    """Best effort: diagnostics must never hide the original failure."""
    try:
        app_dir = Path(__file__).resolve().parent
        frames = []
        for f in traceback.extract_tb(exc.__traceback__)[-8:]:
            path = Path(f.filename).resolve()
            # Only shipped application module names, no source lines/locals/paths.
            if path.parent == app_dir:
                frames.append({'module': _symbol(path.stem), 'line': f.lineno})
        event = dict(time=_now(), code=_symbol(code), source=_symbol(source),
                     exception=_symbol(type(exc).__name__), frames=frames)
        with _lock:
            events = (_events() + [event])[-100:]
            path = _journal()
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(events), encoding='utf-8')
            temp.replace(path)
    except Exception:
        pass


class Preview(BaseModel):
    kind: Literal['error', 'feedback'] = 'error'
    category: Literal['suggestion', 'usability', 'other'] = 'suggestion'
    code: str = Field(default='unexpected', max_length=80)
    screen: str = Field(default='unknown', max_length=30)
    contact: str = Field(default='', max_length=200)
    description: str = Field(default='', max_length=4000)


class Submission(BaseModel):
    token: str = Field(max_length=100)
    consent: bool = False


def _local(request):
    if (not request.client or request.client.host not in ('127.0.0.1', '::1')
            or request.url.hostname not in ('localhost', '127.0.0.1', '::1')):
        raise HTTPException(403, '오류 보고는 프로그램이 실행 중인 PC에서 localhost로 접속해 주세요.')
    if request.headers.get('origin', str(request.base_url).rstrip('/')).rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, '프로그램 화면에서 직접 오류 보고를 열어 주세요.')


def build_report(data):
    if data.kind == 'feedback':
        if not data.description.strip():
            raise HTTPException(400, '보낼 의견을 입력해 주세요.')
        return dict(schema=1, kind='feedback', category=data.category,
                    report_id=str(uuid.uuid4()), created_at=_now(), app_version=config.VERSION,
                    screen=data.screen if data.screen in ('index', 'template', 'review', 'transfer') else 'unknown',
                    contact=data.contact, description=data.description)
    system = dict(os=platform.system(), release=platform.release(),
                  architecture=platform.machine(), cpu_threads=os.cpu_count(),
                  cpu=platform.processor()[:120], os_build=platform.version()[:120])
    try:
        system['ram_gb'] = models.total_ram_gb()
    except Exception:
        system['ram_gb'] = None
    try:
        system['disk_free_gb'] = round(shutil.disk_usage(config.DATA_DIR).free / 1024**3, 1)
    except OSError:
        system['disk_free_gb'] = None
    try:
        model = _symbol(models.current()['id'])
    except Exception:
        model = 'unknown'
    states = ('queued', 'running', 'done', 'cancelled', 'error')
    progress = []
    try:
        statuses = jobs.list_jobs()
        counts = dict(Counter(s.get('state') for s in statuses if s.get('state') in states))
        for s in statuses:
            if s.get('state') not in ('queued', 'running', 'cancelled', 'error'):
                continue
            phase = s.get('phase') if s.get('phase') in ('preparing', 'recognizing', 'starting_engine', 'loading_model') else 'unknown'
            item = {'state': s['state'], 'phase': phase}
            match = re.match(r'^(\d{1,7})/(\d{1,7})페이지', str(s.get('progress', '')))
            if match:
                item.update(page=int(match[1]), total_pages=int(match[2]))
            progress.append(item)
            if len(progress) == 10:
                break
    except Exception:
        counts = {}
    return dict(schema=1, report_id=str(uuid.uuid4()), created_at=_now(),
                app_version=config.VERSION, system=system, model=model,
                error_code=_symbol(data.code), screen=data.screen if data.screen in
                ('index', 'template', 'review', 'transfer') else 'unknown',
                jobs=counts, job_progress=progress, events=_events(), contact=data.contact,
                description=data.description)


@router.post('/preview')
def preview(data: Preview, request: Request):
    _local(request)
    report = build_report(data)
    if len(json.dumps(report).encode()) > MAX_BYTES:
        raise HTTPException(400, '보고서 크기를 줄여 주세요.')
    token = secrets.token_urlsafe(32)
    with _lock:
        for key, draft in list(_drafts.items()):
            if draft['expires'] < time.monotonic():
                del _drafts[key]
        if len(_drafts) >= 32:
            del _drafts[next(iter(_drafts))]
        _drafts[token] = dict(report=report, expires=time.monotonic() + 900, receipt=None, busy=False)
    return dict(token=token, report=copy.deepcopy(report), can_send=bool(REPORT_ENDPOINT))


def send_report(report):
    if not REPORT_ENDPOINT.startswith('https://'):
        raise RuntimeError('report endpoint not configured')
    # No redirects: never forward a user-approved report to another destination.
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.post(REPORT_ENDPOINT, json=report)
        response.raise_for_status()
        receipt = response.json()['receipt']
        if receipt != report['report_id']:
            raise ValueError('invalid receipt')
        return receipt


@router.post('/submit')
def submit(data: Submission, request: Request):
    _local(request)
    if not data.consent:
        raise HTTPException(400, '전송할 내용을 확인하고 동의해 주세요.')
    with _lock:
        draft = _drafts.get(data.token)
        if not draft or draft['expires'] < time.monotonic():
            raise HTTPException(410, '미리보기가 만료됐습니다. 내용을 다시 확인해 주세요.')
        if draft['receipt']:
            return {'receipt': draft['receipt']}
        if draft['busy']:
            raise HTTPException(409, '이미 전송 중입니다.')
        draft['busy'] = True
    try:
        receipt = send_report(copy.deepcopy(draft['report']))
        with _lock:
            draft['receipt'] = receipt
        return {'receipt': receipt}
    except Exception:
        raise HTTPException(503, '전송하지 못했습니다. 접수 한도 또는 연결 문제일 수 있습니다. 파일로 저장해 전달해 주세요.') from None
    finally:
        with _lock:
            draft['busy'] = False

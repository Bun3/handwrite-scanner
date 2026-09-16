"""공식 릴리스 다운로드와 별도 업데이트 도우미로의 인계."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

import httpx

from app import config, update_package
from app.errors import UserError, explain

_release = {'current': config.VERSION, 'available': False}
_lock = threading.Lock()
_shutdown = None
_args = []
_port = 8000
_fallback = None
ACTIVE = {'downloading', 'verifying', 'waiting', 'installing', 'restarting'}


def configure(shutdown, args, port):
    global _shutdown, _args, _port
    _shutdown, _args, _port = shutdown, list(args), port


def supported():
    return (os.name == 'nt' and getattr(sys, 'frozen', False) and _shutdown is not None
            and (config.BASE_DIR / 'handwrite-updater.exe').is_file())


def state_path():
    return config.DATA_DIR / 'updates/status.json'


def progress():
    if _fallback is not None:
        return _fallback
    try:
        state = json.loads(state_path().read_text(encoding='utf-8'))
        pid = state.get('helper_pid') or state.get('owner_pid')
        if state.get('phase') in ACTIVE and pid and pid != os.getpid() and not update_package.process_alive(pid):
            state.update(phase='error', message='이전 업데이트가 중단되었습니다.',
                         action='현재 프로그램이 실행된다면 다시 업데이트할 수 있습니다. 파일 복구가 필요하면 data/updates의 recover.cmd를 사용하거나 상세 내용을 전달하세요.')
        return state
    except (OSError, ValueError):
        return {'phase': 'idle'}


def busy():
    return progress().get('phase') in ACTIVE


def status():
    return {**{k: v for k, v in _release.items() if k != 'asset'},
            'current': config.VERSION, 'supported': supported(), 'progress': progress()}


def parse_release(data):
    tag = data.get('tag_name', '')
    if data.get('draft') or data.get('prerelease') or not re.fullmatch(r'v?\d+\.\d+\.\d+', tag):
        raise UserError('update_release', '업데이트 가능한 정식 버전을 확인할 수 없습니다.', '잠시 후 다시 확인하세요.')
    latest = tag.lstrip('v')
    base = f'https://github.com/{config.GITHUB_REPO}/releases/'
    asset = next((a for a in data.get('assets', []) if a.get('name') == 'handwrite-scanner.zip'), None)
    available = tuple(map(int, latest.split('.'))) > tuple(map(int, config.VERSION.split('.')))
    result = {'current': config.VERSION, 'available': available, 'latest': latest, 'url': base + 'tag/' + tag}
    if not available:
        return result
    if (not asset or asset.get('browser_download_url') != base + f'download/{tag}/handwrite-scanner.zip'
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or '')
            or not isinstance(asset.get('size'), int) or not 0 < asset['size'] < 1024 ** 3):
        raise UserError('update_asset', '공식 업데이트 파일의 검증 정보를 확인할 수 없습니다.', '다운로드 페이지를 확인하거나 잠시 후 다시 시도하세요.')
    result['asset'] = {'url': asset['browser_download_url'], 'size': asset['size'], 'sha256': asset['digest'][7:]}
    return result


def check():
    global _release
    try:
        response = httpx.get(f'https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest',
                             timeout=15, headers={'Accept': 'application/vnd.github+json'})
        response.raise_for_status()
        _release = parse_release(response.json())
        return _release
    except (httpx.HTTPError, ValueError) as exc:
        raise UserError('update_network', '새 버전 정보를 가져오지 못했습니다.', '인터넷 연결을 확인하고 잠시 후 다시 시도하세요.') from exc


def verify_download(path, asset):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if Path(path).stat().st_size != asset['size'] or digest.hexdigest() != asset['sha256']:
        raise UserError('update_checksum', '다운로드한 업데이트 파일이 공식 파일과 일치하지 않습니다.', '현재 프로그램은 변경하지 않았습니다. 다시 업데이트를 시도하세요.')


def begin(job_list, model_list):
    global _fallback
    with _lock:
        if not supported():
            raise UserError('update_unsupported', '이 실행 환경은 자동 업데이트를 지원하지 않습니다.', 'Windows 배포판에서 실행하세요. 개발 환경에서는 소스 코드를 갱신해야 합니다.')
        if busy():
            raise UserError('update_busy', '이미 업데이트 중입니다.', '업데이트가 완료될 때까지 기다려 주세요.')
        from app import phone
        if phone.is_active():
            raise UserError('update_phone', '휴대폰 업로드가 켜져 있습니다.', '폰 업로드를 끄고 전송이 끝난 뒤 업데이트하세요.')
        if any(j['state'] in ('queued', 'running') for j in job_list) or any(m.get('downloading') for m in model_list):
            raise UserError('update_jobs', '진행 중인 작업 또는 모델 다운로드가 있습니다.', '작업이 완료되거나 중단된 뒤 업데이트를 눌러 주세요.')
        release = check()
        if not release['available']:
            raise UserError('update_current', '이미 최신 버전입니다.', '그대로 사용하시면 됩니다.')
        _fallback = None
        update_package.write_json(state_path(), {'phase': 'downloading', 'percent': 0, 'version': release['latest'], 'owner_pid': os.getpid(),
                                               'message': '업데이트 다운로드 준비 중'})
        threading.Thread(target=_run, args=(release,), daemon=True).start()
        return status()


def _run(release):
    global _fallback
    latest = release['latest']
    def record(phase, message, **extra):
        update_package.write_json(state_path(), dict(phase=phase, message=message, version=latest, owner_pid=os.getpid(), **extra))
    try:
        asset = release['asset']
        if shutil.disk_usage(config.BASE_DIR).free < asset['size'] * 5 + 64 * 1024 ** 2:
            raise OSError(28, '업데이트에 필요한 저장 공간이 부족합니다')
        session = config.DATA_DIR / 'updates' / uuid.uuid4().hex
        session.mkdir(parents=True)
        archive = session / 'release.zip'
        with httpx.stream('GET', asset['url'], follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            received = 0; last = 0
            with archive.open('xb') as stream:
                for chunk in response.iter_bytes(1024 * 1024):
                    received += len(chunk)
                    if received > asset['size']:
                        raise ValueError('공식 배포 크기를 넘는 응답')
                    stream.write(chunk)
                    if time.monotonic() - last > .3:
                        record('downloading', '새 버전을 내려받고 있습니다', percent=int(received * 100 / asset['size']))
                        last = time.monotonic()
        record('verifying', '다운로드한 파일을 검증하고 있습니다')
        verify_download(archive, asset)
        stage = update_package.extract(archive, session / 'stage')
        helper = session / 'handwrite-updater.exe'
        shutil.copy2(config.BASE_DIR / 'handwrite-updater.exe', helper)
        plan = dict(target=str(config.BASE_DIR.resolve()), staged=str(stage.resolve()),
                    backup=str((session / 'backup').resolve()), journal=str((session / 'journal.json').resolve()),
                    parent_pid=os.getpid(), port=_port, args=_args, version=latest, previous=config.VERSION,
                    state_path=str(state_path().resolve()), ready_path=str((session / 'ready').resolve()))
        plan_path = session / 'plan.json'
        update_package.write_json(plan_path, plan)
        (session / 'recover.cmd').write_text('@echo off\r\n"%~dp0handwrite-updater.exe" --recover "%~dp0plan.json"\r\npause\r\n', encoding='utf-8')
        with (session / 'helper.log').open('w', encoding='utf-8') as log:
            child = subprocess.Popen([str(helper), '--plan', str(plan_path)], stdout=log, stderr=log,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 30
        while not Path(plan['ready_path']).exists():
            if child.poll() is not None or time.monotonic() > deadline:
                if child.poll() is None:
                    child.terminate(); child.wait(timeout=10)
                raise RuntimeError('업데이트 도우미를 시작하지 못했습니다')
            time.sleep(.1)
        _shutdown()  # 도우미가 기존 프로세스 핸들을 확보한 뒤 정상 종료
    except Exception as exc:
        info = explain(exc)
        if not isinstance(exc, (UserError, OSError)):
            info = {'message': '업데이트를 준비하지 못했습니다.', 'action': '현재 프로그램은 유지됩니다. 인터넷 연결과 설치 폴더 권한을 확인한 뒤 다시 시도하세요.'}
        try:
            record('error', info['message'], action=info['action'], technical=str(exc))
        except OSError:
            _fallback = dict(phase='error', message=info['message'], action=info['action'], technical=str(exc))

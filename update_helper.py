"""Windows 전용 독립 실행 파일. 서버 종료 후 프로그램 교체 및 실패 복구."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import os
import socket
import time
import urllib.request

from app.update_package import install, rollback, write_json


def parent_handle(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        raise OSError(ctypes.get_last_error(), '기존 프로그램 프로세스를 확인할 수 없습니다')
    return kernel, handle


def validate_plan(path):
    path = Path(path).resolve()
    plan = json.loads(path.read_text(encoding='utf-8'))
    session = path.parent
    target = Path(plan['target']).resolve()
    if session.parent != target / 'data/updates' or path.name != 'plan.json':
        raise ValueError('설치 폴더와 업데이트 작업 폴더가 일치하지 않습니다')
    expected = {'staged': session / 'stage/handwrite-scanner', 'backup': session / 'backup',
                'journal': session / 'journal.json', 'ready_path': session / 'ready',
                'state_path': target / 'data/updates/status.json'}
    for name, value in expected.items():
        if Path(plan[name]).resolve() != value:
            raise ValueError('허용되지 않은 업데이트 경로: ' + name)
    args = argparse.ArgumentParser()
    args.add_argument('--server', action='store_true')
    args.add_argument('--no-browser', action='store_true')
    args.add_argument('--port', type=int, default=8000)
    launch = args.parse_args(plan['args'])
    if launch.port != plan['port'] or not 1 <= launch.port <= 65535:
        raise ValueError('업데이트 재시작 포트가 올바르지 않습니다')
    return plan


def healthy(port, version, process, seconds=90):
    deadline = time.monotonic() + seconds
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with opener.open(f'http://127.0.0.1:{port}/api/health', timeout=3) as response:
                state = json.load(response)
                if state.get('app') == 'ok' and state.get('version') == version:
                    return True
        except Exception:
            pass
        time.sleep(.5)
    return False


def start(plan):
    target = Path(plan['target'])
    args = list(plan['args'])
    if '--no-browser' not in args:
        args.append('--no-browser')
    with (Path(plan['journal']).parent / 'restart.log').open('a', encoding='utf-8') as log:
        return subprocess.Popen([str(target / 'handwrite-scanner.exe'), *args], cwd=target,
                                stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def stop_owned(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=15)


def apply(plan, recover=False):
    new_process = None
    def record(phase, message, **extra):
        write_json(plan['state_path'], dict(phase=phase, message=message, version=plan['version'], helper_pid=os.getpid(), **extra))
    if recover:
        with socket.socket() as probe:
            probe.settimeout(.5)
            if probe.connect_ex(('127.0.0.1', plan['port'])) == 0:
                raise RuntimeError('복구 전에 실행 중인 프로그램을 종료하세요')
    if not recover:
        kernel, handle = parent_handle(plan['parent_pid'])
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        try:
            record('waiting', '프로그램을 종료하고 새 버전으로 전환하고 있습니다')
            Path(plan['ready_path']).write_text('ready', encoding='ascii')
            if kernel.WaitForSingleObject(handle, 90000) != 0:
                record('error', '기존 프로그램이 종료되지 않아 업데이트를 중단했습니다.', action='프로그램을 종료한 뒤 다시 업데이트하세요. 기존 파일은 유지됩니다.')
                return False
        finally:
            kernel.CloseHandle(handle)
    try:
        if recover:
            raise RuntimeError('사용자가 이전 버전 복구를 요청했습니다')
        record('installing', '새 버전 프로그램을 설치하고 있습니다')
        install(plan['target'], plan['staged'], plan['backup'], plan['journal'])
        record('restarting', '새 버전을 실행하고 있습니다. 잠시 기다려 주세요.')
        new_process = start(plan)
        if not healthy(plan['port'], plan['version'], new_process):
            raise RuntimeError('새 버전의 정상 실행을 확인하지 못했습니다')
        record('done', '업데이트가 완료되었습니다.')
        return True
    except Exception as exc:
        stop_owned(new_process)
        try:
            rollback(plan['target'], plan['backup'], plan['journal'])
            previous = start(plan)
            if not healthy(plan['port'], plan['previous'], previous):
                raise RuntimeError('이전 버전 복원 후 실행을 확인하지 못했습니다')
            record('rolled_back', '업데이트에 실패하여 이전 버전으로 복원했습니다.',
                   action='기존 작업과 모델은 유지됩니다. 상세 내용을 확인한 뒤 다시 시도하세요.', technical=str(exc))
        except Exception as recovery_error:
            record('error', '업데이트 복구에 도움이 필요합니다.',
                   action=f"백업 위치: {plan['backup']}. 이 폴더를 삭제하지 말고 상세 내용을 전달해 주세요.",
                   technical=f'{exc}\n{recovery_error}')
        return False


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--plan')
    group.add_argument('--recover')
    args = parser.parse_args()
    plan = validate_plan(args.plan or args.recover)
    apply(plan, recover=bool(args.recover))


if __name__ == '__main__':
    main()

"""배포 파일만 교체하는 표준 라이브러리 기반 트랜잭션. 데이터/모델은 건드리지 않는다."""
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import time
import zipfile
import os

COMPONENTS = ('handwrite-scanner.exe', '_internal', 'handwrite-updater.exe', 'server-mode.bat')


def process_alive(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # 권한 부족이면 종료됐다고 단정하지 않는다.
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(.05)


def extract(archive, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('압축 해제 대상은 새 폴더여야 합니다')
    with zipfile.ZipFile(archive) as z:
        seen = set()
        members = []
        for item in z.infolist():
            name = item.filename
            parts = PurePosixPath(name).parts
            if (not parts or parts[0] != 'handwrite-scanner' or '\\' in name
                    or any(p in ('.', '..') or p.endswith((' ', '.')) or re.search(r'[<>:"|?*\x00-\x1f]', p)
                           or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)', p, re.I)
                           for p in parts)
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError('안전하지 않은 업데이트 압축 경로')
            if len(parts) == 1 and item.is_dir():
                continue
            if len(parts) < 2 or parts[1] not in COMPONENTS or (len(parts) > 2 and parts[1] != '_internal'):
                raise ValueError('배포 프로그램 외 파일이 포함되어 있습니다')
            key = '/'.join(parts).casefold()
            if key in seen:
                raise ValueError('중복된 업데이트 파일 경로')
            seen.add(key)
            members.append(item)
        expanded = sum(i.file_size for i in members)
        if expanded > 2 * 1024 ** 3 or len(members) > 20000:
            raise ValueError('업데이트 압축 크기가 허용 범위를 넘었습니다')
        if shutil.disk_usage(destination.parent).free < expanded + 64 * 1024 ** 2:
            raise OSError(28, '업데이트 압축을 풀 저장 공간이 부족합니다')
        required = ['handwrite-scanner/handwrite-scanner.exe', 'handwrite-scanner/handwrite-updater.exe']
        if not all(n in seen for n in required) or not any(n.startswith('handwrite-scanner/_internal/') for n in seen):
            raise ValueError('업데이트에 필요한 실행 파일이 없습니다')
        destination.mkdir()
        for item in members:
            target = destination.joinpath(*PurePosixPath(item.filename).parts)
            if not target.resolve().is_relative_to(destination):
                raise ValueError('압축 경로 이탈')
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
    return destination / 'handwrite-scanner'


def _child(root, name):
    root = Path(root).resolve()
    child = root / name
    if child.resolve().parent != root or child.is_symlink() or child.is_junction():
        raise ValueError('업데이트 대상에 외부 경로 연결이 있습니다')
    return child


def install(target, staged, backup, journal):
    target, staged, backup = map(lambda p: Path(p).resolve(), (target, staged, backup))
    backup.mkdir(parents=True, exist_ok=False)
    entries = []
    for name in COMPONENTS:
        new, old, saved = _child(staged, name), _child(target, name), _child(backup, name)
        if not new.exists():
            continue
        entries.append({'name': name, 'had_old': old.exists()})
        write_json(journal, entries)  # 이동 전에 기록: 갑작스러운 종료에도 복구 가능
        if old.exists():
            old.replace(saved)
        new.replace(old)


def rollback(target, backup, journal):
    target, backup = Path(target).resolve(), Path(backup).resolve()
    if not Path(journal).exists():
        return
    for item in reversed(json.loads(Path(journal).read_text(encoding='utf-8'))):
        name = item['name']
        if name not in COMPONENTS:
            raise ValueError('잘못된 복구 항목')
        old, saved = _child(target, name), _child(backup, name)
        if saved.exists() or not item['had_old']:
            if old.exists():
                old.replace(_child(backup, 'failed-' + name))
            if saved.exists():
                saved.replace(old)

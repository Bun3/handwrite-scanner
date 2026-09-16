import zipfile
from pathlib import Path

import pytest

from app import update_package


def package(path, extra=None):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('handwrite-scanner/handwrite-scanner.exe', b'new exe')
        z.writestr('handwrite-scanner/_internal/runtime.dll', b'new runtime')
        z.writestr('handwrite-scanner/handwrite-updater.exe', b'helper')
        if extra:
            z.writestr(extra, b'bad')
    return path


@pytest.mark.parametrize('unsafe', [
    'handwrite-scanner/../escape.exe', 'handwrite-scanner/data/settings.json',
    'handwrite-scanner/engine/model', 'handwrite-scanner/_internal/C:/escape',
    'handwrite-scanner/_internal/../escape', 'handwrite-scanner/_internal/file:stream',
    'handwrite-scanner/_internal/runtime.dll.', 'handwrite-scanner/_internal/CON',
    'handwrite-scanner/_internal/RUNTIME.dll',
])
def test_archive_rejects_unsafe_and_user_data(tmp_path, unsafe):
    archive = package(tmp_path / 'release.zip', unsafe)
    with pytest.raises(ValueError):
        update_package.extract(archive, tmp_path / 'stage')
    assert not (tmp_path / 'escape.exe').exists()


def installation(tmp_path):
    install = tmp_path / 'install'; install.mkdir()
    (install / 'handwrite-scanner.exe').write_bytes(b'old exe')
    (install / '_internal').mkdir()
    (install / '_internal/runtime.dll').write_bytes(b'old runtime')
    for name in ['data', 'engine']:
        (install / name).mkdir(); (install / name / 'keep').write_bytes(b'user data')
    return install


def test_replace_preserves_data_and_rollback_restores(tmp_path):
    install = installation(tmp_path)
    stage = update_package.extract(package(tmp_path / 'release.zip'), tmp_path / 'stage')
    backup = tmp_path / 'backup'
    journal = tmp_path / 'journal.json'
    update_package.install(install, stage, backup, journal)
    assert (install / 'handwrite-scanner.exe').read_bytes() == b'new exe'
    for name in ['data', 'engine']:
        assert (install / name / 'keep').read_bytes() == b'user data'
    update_package.rollback(install, backup, journal)
    assert (install / 'handwrite-scanner.exe').read_bytes() == b'old exe'
    assert (install / '_internal/runtime.dll').read_bytes() == b'old runtime'


def test_partial_replacement_is_recoverable(tmp_path, monkeypatch):
    install = installation(tmp_path)
    stage = update_package.extract(package(tmp_path / 'release.zip'), tmp_path / 'stage')
    backup = tmp_path / 'backup'; journal = tmp_path / 'journal.json'
    replace = Path.replace
    def fail_new_runtime(path, target):
        if path == stage / '_internal':
            raise PermissionError('locked')
        return replace(path, target)
    monkeypatch.setattr(Path, 'replace', fail_new_runtime)
    with pytest.raises(PermissionError):
        update_package.install(install, stage, backup, journal)
    update_package.rollback(install, backup, journal)
    assert (install / 'handwrite-scanner.exe').read_bytes() == b'old exe'
    assert (install / '_internal/runtime.dll').read_bytes() == b'old runtime'

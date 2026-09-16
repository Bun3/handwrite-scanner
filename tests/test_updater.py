import hashlib

import pytest

from app import updater
from app.errors import UserError


def release():
    return {'tag_name': 'v99.0.0', 'draft': False, 'prerelease': False,
            'html_url': 'https://github.com/Bun3/handwrite-scanner/releases/tag/v99.0.0',
            'assets': [{'name': 'handwrite-scanner.zip', 'size': 10,
                        'digest': 'sha256:' + 'a' * 64,
                        'browser_download_url': 'https://github.com/Bun3/handwrite-scanner/releases/download/v99.0.0/handwrite-scanner.zip'}]}


def test_only_verified_official_assets_allowed():
    assert updater.parse_release(release())['latest'] == '99.0.0'
    for key, value in [('digest', None), ('browser_download_url', 'https://evil.test/file.zip')]:
        data = release(); data['assets'][0][key] = value
        with pytest.raises(UserError): updater.parse_release(data)


def test_download_checks_size_and_digest(tmp_path):
    path = tmp_path / 'download.zip'; path.write_bytes(b'payload')
    asset = {'size': 7, 'sha256': hashlib.sha256(b'payload').hexdigest()}
    updater.verify_download(path, asset)
    path.write_bytes(b'changed')
    with pytest.raises(UserError): updater.verify_download(path, asset)


def test_update_rejects_active_jobs_before_network(monkeypatch):
    monkeypatch.setattr(updater, 'supported', lambda: True)
    monkeypatch.setattr(updater, 'busy', lambda: False)
    monkeypatch.setattr(updater, 'check', lambda: pytest.fail('network before idle check'))
    with pytest.raises(UserError):
        updater.begin([{'state': 'running'}], [])


def test_source_checkout_cannot_update(monkeypatch):
    monkeypatch.setattr(updater, 'supported', lambda: False)
    with pytest.raises(UserError) as exc:
        updater.begin([], [])
    assert exc.value.code == 'update_unsupported'


@pytest.mark.parametrize('corrupt', [False, True])
def test_download_handoff_only_after_verification(tmp_path, monkeypatch, corrupt):
    import json
    from pathlib import Path
    from tests.test_update_package import package
    from app import config
    monkeypatch.setattr(config, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path / 'data')
    monkeypatch.setattr(updater, '_fallback', None)
    (tmp_path / 'handwrite-updater.exe').write_bytes(b'helper')
    archive = package(tmp_path / 'source.zip').read_bytes()
    asset = {'url': 'https://github.com/example', 'size': len(archive),
             'sha256': ('0' * 64 if corrupt else hashlib.sha256(archive).hexdigest())}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_bytes(self, size): yield archive
    monkeypatch.setattr(updater.httpx, 'stream', lambda *a, **kw: Response())
    shutdown = []
    monkeypatch.setattr(updater, '_shutdown', lambda: shutdown.append(True))
    launched = []
    class Process:
        def __init__(self, argv, **kw):
            launched.append(argv)
            plan = json.loads(Path(argv[-1]).read_text(encoding='utf-8'))
            Path(plan['ready_path']).write_text('ready')
        def poll(self): return None
    monkeypatch.setattr(updater.subprocess, 'Popen', Process)
    updater._run({'latest': '99.0.0', 'asset': asset})
    if corrupt:
        assert not launched and not shutdown
        assert updater.progress()['phase'] == 'error'
    else:
        assert len(launched) == 1 and shutdown == [True]
        assert (tmp_path / 'handwrite-updater.exe').read_bytes() == b'helper'

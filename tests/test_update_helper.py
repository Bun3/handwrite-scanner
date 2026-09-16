import json
from pathlib import Path

import pytest

import update_helper
from app import update_package
from tests.test_update_package import package, installation


def test_bad_new_version_is_rolled_back(tmp_path, monkeypatch):
    target = installation(tmp_path)
    session = target / 'data/updates/test'; session.mkdir(parents=True)
    staged = update_package.extract(package(session / 'release.zip'), session / 'stage')
    plan = dict(target=str(target), staged=str(staged), backup=str(session / 'backup'),
                journal=str(session / 'journal.json'), state_path=str(target / 'data/updates/status.json'),
                ready_path=str(session / 'ready'), parent_pid=1234, version='2.0.0', previous='1.0.0', port=18000, args=['--port', '18000'])
    update_package.write_json(session / 'plan.json', plan)
    assert update_helper.validate_plan(session / 'plan.json') == plan
    class Function:
        def __call__(self, *args): return 0
    class Kernel:
        WaitForSingleObject = Function()
        CloseHandle = Function()
    monkeypatch.setattr(update_helper, 'parent_handle', lambda _: (Kernel(), 1))
    started = []
    monkeypatch.setattr(update_helper, 'start', lambda p: started.append(True) or object())
    monkeypatch.setattr(update_helper, 'stop_owned', lambda _: None)
    monkeypatch.setattr(update_helper, 'healthy', lambda port, version, process: version == '1.0.0')
    assert update_helper.apply(plan) is False
    assert len(started) == 2
    assert (target / 'handwrite-scanner.exe').read_bytes() == b'old exe'
    assert (target / 'data/keep').read_bytes() == b'user data'
    assert json.loads(Path(plan['state_path']).read_text(encoding='utf-8'))['phase'] == 'rolled_back'


def test_plan_rejects_external_target(tmp_path):
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps({'target': str(tmp_path / 'unrelated')}))
    with pytest.raises(ValueError): update_helper.validate_plan(path)

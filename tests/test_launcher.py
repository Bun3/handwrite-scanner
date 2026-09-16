from unittest.mock import Mock

import httpx
import pytest

import launcher


@pytest.mark.skipif(launcher.sys.platform != 'win32', reason='Windows installer mutex')
def test_installer_can_detect_running_program():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    owned = launcher.create_runtime_mutex()
    try:
        probe = kernel.OpenMutexW(0x00100000, False, 'Local\\HandwriteScannerRunning')
        assert probe
        kernel.CloseHandle(probe)
    finally:
        kernel.CloseHandle(owned)


def test_old_server_explains_mixed_version(monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'VERSION', '0.7.1')
    monkeypatch.setattr(launcher, '_port_in_use', lambda _: True)
    monkeypatch.setattr(httpx, 'get', lambda *a, **kw: httpx.Response(200, json={'app': 'ok', 'version': '0.7.0'}))
    message = launcher.existing_server_message(8000)
    assert '0.7.0' in message and '0.7.1' in message
    assert 'handwrite-scanner.exe' in message


def test_free_port_does_not_probe_http(monkeypatch):
    monkeypatch.setattr(launcher, '_port_in_use', lambda _: False)
    monkeypatch.setattr(httpx, 'get', lambda *a, **kw: pytest.fail('HTTP probe on free port'))
    assert launcher.existing_server_message(8000) is None


def test_occupied_port_stops_before_loading_engine_or_opening_browser(monkeypatch):
    from app import engine_setup
    monkeypatch.setattr(launcher, 'existing_server_message', lambda _: 'old server is running')
    monkeypatch.setattr(launcher, '_show_startup_error', Mock())
    monkeypatch.setattr(launcher.sys, 'argv', ['launcher.py', '--no-browser'])
    monkeypatch.setattr(engine_setup, 'ensure_engine', lambda: pytest.fail('engine started'))
    monkeypatch.setattr(launcher.webbrowser, 'open', lambda _: pytest.fail('opened old server'))
    with pytest.raises(SystemExit) as exc:
        launcher.main()
    assert exc.value.code == 1


def test_unrelated_service_is_not_reported_as_scanner(monkeypatch):
    monkeypatch.setattr(launcher, '_port_in_use', lambda _: True)
    monkeypatch.setattr(httpx, 'get', lambda *a, **kw: httpx.Response(200, json={'version': 'other'}))
    assert '다른 프로그램' in launcher.existing_server_message(8000)


@pytest.mark.parametrize('bind_fails', [False, True])
def test_browser_only_opens_after_own_server_is_ready(monkeypatch, bind_fails):
    import threading
    import uvicorn
    from app import engine_setup
    opened = threading.Event()
    monkeypatch.setattr(launcher, 'existing_server_message', lambda _: None)
    monkeypatch.setattr(launcher.sys, 'argv', ['launcher.py'])
    monkeypatch.setattr(engine_setup, 'ensure_engine', lambda: None)
    monkeypatch.setattr(engine_setup, 'free_disk_ok', lambda: True)
    monkeypatch.setattr(launcher.webbrowser, 'open', lambda _: opened.set())
    class Server:
        started = False
        def __init__(self, config): pass
        def run(self):
            assert not opened.is_set()
            if bind_fails:
                raise SystemExit(1)
            self.started = True
            assert opened.wait(2)
    monkeypatch.setattr(uvicorn, 'Server', Server)
    if bind_fails:
        with pytest.raises(SystemExit):
            launcher.main()
        assert not opened.is_set()
    else:
        launcher.main()
        assert opened.is_set()

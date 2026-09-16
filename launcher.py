"""배포판 진입점: 엔진 확보 → 서버 기동 → 브라우저 자동 열기.

일반 실행   : handwrite-scanner.exe            (이 PC 전용, localhost)
서버 모드   : handwrite-scanner.exe --server   (사내 다른 PC가 브라우저로 접속)
CLI 모드    : handwrite-scanner.exe cli ...    (스크립트·AI 에이전트용, 서버 필요)
"""
import argparse
import socket
import sys
import threading
import webbrowser


def create_runtime_mutex():
    """설치 프로그램이 실행 중인 서버를 감지한다. 프로세스 종료 시 자동 해제."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel.CreateMutexW(None, False, 'Local\\HandwriteScannerRunning')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def _port_in_use(port):
    with socket.socket() as probe:
        probe.settimeout(.5)
        return probe.connect_ex(('127.0.0.1', port)) == 0


def existing_server_message(port):
    if not _port_in_use(port):
        return None
    import httpx
    from app.config import VERSION
    try:
        response = httpx.get(f'http://127.0.0.1:{port}/api/health', timeout=4, trust_env=False)
        data = response.json()
        if response.status_code == 200 and isinstance(data, dict) and data.get('app') == 'ok':
            running = data.get('version', '확인 불가')
            return (f'이미 실행 중인 handwrite-scanner 서버가 있습니다.\n'
                    f'실행 중인 서버: v{running} / 지금 실행한 파일: v{VERSION}\n\n'
                    '브라우저를 닫아도 서버는 종료되지 않습니다.\n'
                    '진행 중인 작업을 확인하고 프로그램 창을 종료하세요. 창이 없으면 작업 관리자에서 '
                    'handwrite-scanner.exe를 종료한 뒤 새 파일을 실행하세요.\n'
                    '업데이트 중 EXE 덮어쓰기에 실패했다면 프로그램 종료 후 ZIP 전체를 다시 덮어쓰세요.')
    except (httpx.HTTPError, ValueError):
        pass
    return (f'{port}번 포트를 다른 프로그램이 사용 중이거나 서버 상태를 확인할 수 없습니다.\n'
            '이전 실행 창을 확인해 종료하거나 --port 옵션으로 다른 포트를 지정하세요.')


def _show_startup_error(message, no_browser=False):
    print(message, flush=True)
    if getattr(sys, 'frozen', False) and sys.platform == 'win32' and not no_browser:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, 'handwrite-scanner 실행 확인', 0x30)


def main() -> None:
    if getattr(sys, 'frozen', False) and sys.platform == 'win32':
        create_runtime_mutex()
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from cli import main as cli_main
        sys.exit(cli_main(sys.argv[2:]))
    p = argparse.ArgumentParser()
    p.add_argument("--server", action="store_true",
                   help="사내망의 다른 PC에서 접속 허용 (0.0.0.0 바인드)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    message = existing_server_message(args.port)
    if message:
        _show_startup_error(message, args.no_browser)
        raise SystemExit(1)

    from app.engine_setup import ensure_engine, free_disk_ok
    if not free_disk_ok():
        print("⚠ 디스크 여유 공간이 8GB 미만입니다. 모델 저장에 부족할 수 있습니다.")
    ensure_engine()

    host = "0.0.0.0" if args.server else "127.0.0.1"
    if args.server:
        ip = socket.gethostbyname(socket.gethostname())
        print(f"서버 모드: 다른 PC에서 http://{ip}:{args.port} 로 접속하세요.")
        print("(최초 1회 Windows 방화벽 허용 창이 뜨면 '허용'을 누르세요)")
    import uvicorn

    from app.main import app  # 문자열 임포트는 PyInstaller에서 깨질 수 있어 직접 임포트
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=args.port, log_level="warning"))
    from app import updater
    updater.configure(lambda: setattr(server, 'should_exit', True), sys.argv[1:], args.port)
    stopped = threading.Event()
    if not args.no_browser:
        def open_when_ready():
            while not stopped.wait(.1):
                if server.started:
                    webbrowser.open(f'http://127.0.0.1:{args.port}')
                    return
        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.run()
    finally:
        stopped.set()


if __name__ == "__main__":
    main()

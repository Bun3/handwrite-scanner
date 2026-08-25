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


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from cli import main as cli_main
        sys.exit(cli_main(sys.argv[2:]))
    p = argparse.ArgumentParser()
    p.add_argument("--server", action="store_true",
                   help="사내망의 다른 PC에서 접속 허용 (0.0.0.0 바인드)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    from app.engine_setup import ensure_engine, free_disk_ok
    if not free_disk_ok():
        print("⚠ 디스크 여유 공간이 8GB 미만입니다. 모델 저장에 부족할 수 있습니다.")
    ensure_engine()

    host = "0.0.0.0" if args.server else "127.0.0.1"
    if args.server:
        ip = socket.gethostbyname(socket.gethostname())
        print(f"서버 모드: 다른 PC에서 http://{ip}:{args.port} 로 접속하세요.")
        print("(최초 1회 Windows 방화벽 허용 창이 뜨면 '허용'을 누르세요)")
    if not args.no_browser:
        threading.Timer(2.0, webbrowser.open,
                        [f"http://127.0.0.1:{args.port}"]).start()

    import uvicorn

    from app.main import app  # 문자열 임포트는 PyInstaller에서 깨질 수 있어 직접 임포트
    uvicorn.run(app, host=host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

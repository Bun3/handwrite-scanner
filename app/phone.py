"""폰 촬영 업로드: 필요한 순간에만 LAN에 여는 보조 리스너 + 1회용 토큰 QR.

단독 모드에서도 "폰 업로드 켜기" 동안만 0.0.0.0:8001 이 열리고,
끄면 리스너가 내려가 다시 완전 로컬로 돌아간다. 토큰이 없으면 접근 거부.
"""
import base64
import io
import secrets
import socket
import threading

from fastapi import FastAPI, HTTPException, UploadFile

from app import jobs, worker

PHONE_PORT = 8001

_token: str | None = None
_server = None  # uvicorn.Server

phone_app = FastAPI()

_PAGE = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>문서 촬영 업로드</title><style>
body{font-family:'Malgun Gothic',sans-serif;margin:0;padding:24px;background:#f5f6f8}
.card{background:#fff;border-radius:12px;padding:24px;max-width:440px;margin:0 auto;
box-shadow:0 1px 4px rgba(0,0,0,.1)}h2{margin-top:0}
input[type=file]{width:100%;margin:12px 0}
button{width:100%;padding:14px;font-size:17px;background:#2c7be5;color:#fff;border:0;border-radius:8px}
#msg{margin-top:14px;font-size:15px}</style></head><body><div class="card">
<h2>📷 문서 촬영 업로드</h2>
<p>문서가 화면에 꽉 차고 초점이 맞게 찍어주세요. 여러 장 선택 가능합니다.</p>
<form id="f"><input type="file" name="files" accept="image/*" capture="environment" multiple required>
<button>업로드</button></form><div id="msg"></div>
<script>
document.getElementById('f').onsubmit = async e => {
  e.preventDefault();
  const m = document.getElementById('msg');
  m.textContent = '업로드 중...';
  const r = await fetch(location.pathname + '/upload', {method:'POST', body:new FormData(e.target)});
  m.textContent = r.ok ? '✅ 업로드 완료! PC에서 인식이 시작됐습니다. 더 찍어 올려도 됩니다.'
                       : '❌ 실패했습니다. 다시 시도해주세요.';
  if (r.ok) e.target.reset();
};
</script></div></body></html>"""


def _check(token: str):
    if _token is None or token != _token:
        raise HTTPException(403, "만료되었거나 잘못된 접근입니다")


@phone_app.get("/p/{token}")
def page(token: str):
    _check(token)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_PAGE)


@phone_app.post("/p/{token}/upload")
async def upload(token: str, files: list[UploadFile]):
    _check(token)
    pairs = [(f.filename, await f.read()) for f in files]
    job_id = jobs.create(None, pairs)  # 템플릿 자동 판별
    worker.enqueue(job_id)
    return {"id": job_id}


def _lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # 실제 전송 없음, 라우팅 조회용
        return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())
    finally:
        s.close()


def start() -> dict:
    """리스너 기동(이미 떠 있으면 재사용) + 새 토큰 발급. 반환: {url, qr(data URI)}"""
    global _token, _server
    import qrcode
    import uvicorn
    _token = secrets.token_urlsafe(12)
    if _server is None:
        config = uvicorn.Config(phone_app, host="0.0.0.0", port=PHONE_PORT,
                                log_level="warning")
        _server = uvicorn.Server(config)
        threading.Thread(target=_server.run, daemon=True).start()
    url = f"http://{_lan_ip()}:{PHONE_PORT}/p/{_token}"
    buf = io.BytesIO()
    qrcode.make(url).save(buf, "PNG")
    qr = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return {"url": url, "qr": qr}


def stop() -> None:
    """토큰 무효화 + 리스너 종료 → 다시 완전 로컬."""
    global _token, _server
    _token = None
    if _server is not None:
        _server.should_exit = True
        _server = None

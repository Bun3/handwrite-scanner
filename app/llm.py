"""llama-server(Qwen2.5-VL) 기동·호출. 외부 API 호출 없음 — 전부 localhost."""
import base64
import subprocess
import time

import httpx

from app import config

_URL = f"http://127.0.0.1:{config.LLAMA_PORT}"
_proc = None


def is_up() -> bool:
    try:
        return httpx.get(_URL + "/health", timeout=2).status_code == 200
    except Exception:
        return False


def ensure_server(timeout: int = 300) -> None:
    """llama-server가 없으면 선택된 모델로 띄우고 로드 완료까지 대기."""
    global _proc
    if is_up():
        return
    from app import models
    model, mmproj = models.paths(models.current())
    _proc = subprocess.Popen(
        [str(config.LLAMA_SERVER), "-m", str(model),
         "--mmproj", str(mmproj), "--port", str(config.LLAMA_PORT),
         "--host", "127.0.0.1", "-c", "8192"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_up():
            return
        if _proc.poll() is not None:
            raise RuntimeError(
                f"llama-server 종료됨 (exit {_proc.returncode}). "
                "메모리 부족이면 설정에서 더 작은 모델을 선택하세요.")
        time.sleep(2)
    raise RuntimeError("llama-server 기동 시간 초과")


def restart() -> None:
    """모델 교체 등으로 llama-server 재기동이 필요할 때. 다음 호출 시 새로 뜬다."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.kill()
    else:  # 다른 프로세스(이전 실행)가 띄운 서버까지 정리
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"],
                       capture_output=True)
    _proc = None


def ask_image(image_bytes: bytes, prompt: str, timeout: float = 600) -> str:
    """이미지 한 장 + 프롬프트 → 모델 답변 텍스트."""
    ensure_server()
    b64 = base64.b64encode(image_bytes).decode()
    r = httpx.post(_URL + "/v1/chat/completions", json={
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]}],
    }, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

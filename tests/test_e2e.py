"""E2E: 휴가신청서 샘플 → 정답 일치 검증.

서버가 떠 있어야 한다 (run.ps1). 모델 추론 포함이라 수 분 소요.
실행: .venv/Scripts/python -X utf8 -m pytest tests/test_e2e.py -v -s
"""
import time

import httpx
import pytest

BASE = "http://127.0.0.1:8000"

TRUTH = {
    "성명": "홍길동",
    "비상시 연락처": "010-1234-5678",
    "일시": "2026년 8월 21일 9시부터 2026년 8월 22일 18시까지 1일간",
    "월차잔여수(전)": "7",
    "월차잔여수(후)": "6",
    "사유": "개인 사유",
    "승인종류": "월차",
}


def _server_up():
    try:
        return httpx.get(BASE + "/api/health", timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _server_up(), reason="서버 미기동")
def test_vacation_form():
    r = httpx.post(BASE + "/api/jobs", data={"template": "휴가신청서"},
                   files=[("files", ("vacation-filled.png",
                           open("tests/fixtures/vacation-filled.png", "rb"),
                           "image/png"))])
    job_id = r.json()["id"]
    deadline = time.time() + 1800
    while time.time() < deadline:
        d = httpx.get(f"{BASE}/api/jobs/{job_id}", timeout=10).json()
        if d["status"]["state"] in ("done", "error"):
            break
        time.sleep(10)
    assert d["status"]["state"] == "done", d["status"].get("error")
    got = {f["label"]: f["value"] for f in d["results"][0]["fields"]}
    norm = lambda s: " ".join(s.split())
    wrong = {k: (got.get(k), v) for k, v in TRUTH.items()
             if norm(got.get(k, "")) != norm(v)}
    assert not wrong, f"불일치: {wrong}"

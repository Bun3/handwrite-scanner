"""E2E: 더미 휴가신청서(tests/fixtures/gen_dummy.py 산출물) → 정답 일치 검증.

서버가 떠 있어야 한다 (run.ps1). 모델 추론 포함이라 수 분 소요.
실행: .venv/Scripts/python -X utf8 -m pytest tests/test_e2e.py -v -s
"""
import json
import time

import httpx
import pytest

BASE = "http://127.0.0.1:8000"
TEMPLATE = "dummy-vacation"
FIX = "tests/fixtures"

TRUTH = {
    "성명": "홍길동",
    "연락처": "010-1234-5678",
    "잔여일수": "5",
    "사유": "개인 사유",
    "승인종류": "월차",
}


def _server_up():
    try:
        return httpx.get(BASE + "/api/health", timeout=10).status_code == 200
    except Exception:
        return False


def _ensure_template():
    httpx.post(BASE + "/api/templates", data={"name": TEMPLATE},
               files={"file": ("dummy-form.pdf",
                      open(f"{FIX}/dummy-form.pdf", "rb"), "application/pdf")},
               timeout=60).raise_for_status()
    fields = json.load(open(f"{FIX}/dummy-template.json", encoding="utf-8"))
    httpx.put(f"{BASE}/api/templates/{TEMPLATE}",
              json={"fields": fields}, timeout=30).raise_for_status()


def _run_job(template: str, files=None) -> dict:
    r = httpx.post(BASE + "/api/jobs", data={"template": template},
                   files=files or [("files", ("dummy-filled.png",
                           open(f"{FIX}/dummy-filled.png", "rb"), "image/png"))])
    job_id = r.json()["id"]
    deadline = time.time() + 1800
    while time.time() < deadline:
        d = httpx.get(f"{BASE}/api/jobs/{job_id}", timeout=10).json()
        if d["status"]["state"] in ("done", "error"):
            break
        time.sleep(10)
    assert d["status"]["state"] == "done", d["status"].get("error")
    return d


def _assert_truth(d: dict):
    got = {f["label"]: f["value"] for f in d["results"][0]["fields"]}
    norm = lambda s: " ".join(s.split())
    wrong = {k: (got.get(k), v) for k, v in TRUTH.items()
             if norm(got.get(k, "")) != norm(v)}
    assert not wrong, f"불일치: {wrong}"


@pytest.mark.skipif(not _server_up(), reason="서버 미기동")
def test_dummy_vacation_form():
    _ensure_template()
    _assert_truth(_run_job(TEMPLATE))


@pytest.mark.skipif(not _server_up(), reason="서버 미기동")
def test_skip_unrelated_page():
    """지정 양식과 다른 서류(증빙 등)는 LLM 호출 없이 건너뜀. 추론 없어 수 초면 끝."""
    import io
    from PIL import Image
    _ensure_template()
    buf = io.BytesIO()
    Image.new("RGB", (800, 1100), "white").save(buf, "PNG")  # 특징점 없는 백지 = 정합 불가
    d = _run_job(TEMPLATE, files=[("files", ("blank.png", buf.getvalue(), "image/png"))])
    page = d["results"][0]
    assert page.get("skipped") is True and page["fields"] == []


@pytest.mark.skipif(not _server_up(), reason="서버 미기동")
def test_auto_detect_template():
    """템플릿 미지정 업로드 → 페이지별 자동 판별로 같은 결과."""
    _ensure_template()
    d = _run_job("")
    assert d["results"][0]["template"] == TEMPLATE
    _assert_truth(d)

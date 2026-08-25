"""CLI 스모크 테스트. 서버가 떠 있어야 한다 (run.ps1).

건너뜀 경로만 쓰므로 LLM 추론 없이 수 초면 끝난다.
"""
import json

import pytest

import cli
from tests.test_e2e import TEMPLATE, _ensure_template, _server_up

pytestmark = pytest.mark.skipif(not _server_up(), reason="서버 미기동")


def run(capsys, *argv):
    cli.main(list(argv))
    return json.loads(capsys.readouterr().out)


def test_health(capsys):
    assert run(capsys, "health")["app"] == "ok"


def test_templates_list_and_get(capsys):
    _ensure_template()
    assert any(t["name"] == TEMPLATE for t in run(capsys, "templates", "list"))
    assert run(capsys, "templates", "get", TEMPLATE)["name"] == TEMPLATE


def test_submit_wait_export_delete(tmp_path, capsys):
    _ensure_template()
    from PIL import Image
    f = tmp_path / "blank.png"
    Image.new("RGB", (800, 1100), "white").save(f)  # 백지 = 정합 실패 → 건너뜀
    job_id = run(capsys, "jobs", "submit", str(f), "--template", TEMPLATE)["id"]
    d = run(capsys, "jobs", "wait", job_id, "--timeout", "120")
    assert d["status"]["state"] == "done"
    assert d["results"][0].get("skipped") is True
    out = tmp_path / "out.csv"
    saved = run(capsys, "jobs", "export", job_id, "--fmt", "csv", "-o", str(out))
    assert out.exists() and saved["bytes"] > 0
    run(capsys, "jobs", "delete", job_id)


def test_circle_requires_candidates(tmp_path, capsys):
    _ensure_template()
    bad = tmp_path / "fields.json"
    bad.write_text(json.dumps([{"id": "c1", "label": "선택", "type": "circle",
                                "box": [0, 0, 10, 10], "candidates": []}]),
                   encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["templates", "update", TEMPLATE, "--fields", str(bad)])
    assert "후보" in capsys.readouterr().err


def test_server_down_error(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--server", "http://127.0.0.1:59999", "health"])
    assert "연결" in capsys.readouterr().err

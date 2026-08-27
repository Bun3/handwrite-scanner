import pytest

from app import jobs


def test_delete_containment(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    with pytest.raises(ValueError):
        jobs.delete("../evil")
    with pytest.raises(ValueError):
        jobs.delete("a/b")


def test_corrupt_status_ignored(tmp_path, monkeypatch):
    """크래시로 쓰다 만 status.json(NUL 등)이 있어도 서버가 뜨고 목록에서 빠진다."""
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    d = tmp_path / "j1"
    d.mkdir()
    (d / "status.json").write_bytes(b"\x00" * 183)
    assert jobs.status("j1") is None
    assert jobs.list_jobs() == []
    jobs.write_status("j1", {"id": "j1"})   # 원자적 쓰기로 복구 가능
    assert jobs.status("j1") == {"id": "j1"}
    assert not (d / "status.json.tmp").exists()


def test_process_resumes_from_partial_results(tmp_path, monkeypatch):
    """크래시 후 재개 시 완료된 페이지 프리픽스는 재인식하지 않는다."""
    from PIL import Image
    from app import templates_store, worker
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    d = tmp_path / "j1"
    (d / "input").mkdir(parents=True)
    for i in range(2):  # 백지 2장 = 정합 실패 → 건너뜀 경로 (LLM 불필요)
        Image.new("RGB", (400, 500), "white").save(d / "input" / f"{i:03d}.png")
    monkeypatch.setattr(templates_store, "get",
                        lambda n: {"name": n, "fields": [], "rules": []})
    monkeypatch.setattr(templates_store, "reference_path",
                        lambda n: "tests/fixtures/dummy-filled.png")
    st = {"id": "j1", "template": "x", "state": "running", "progress": ""}
    jobs.write_status("j1", st)
    jobs.write_results("j1", [{"page": 0, "aligned": None, "template": None,
                               "skipped": True, "fields": [], "warnings": ["MARKER"]}])
    worker._process("j1", st)
    res = jobs.results("j1")
    assert len(res) == 2
    assert res[0]["warnings"] == ["MARKER"]      # 페이지 0은 이전 결과 유지
    assert res[1].get("skipped") is True         # 페이지 1만 새로 처리


def test_pdf_split(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    pdf = open("tests/fixtures/dummy-form.pdf", "rb").read()
    png = open("tests/fixtures/dummy-filled.png", "rb").read()
    job_id = jobs.create(None, [("scan.pdf", pdf), ("photo.png", png)])
    names = [p.name for p in jobs.input_images(job_id)]
    assert names == ["000.png", "001.png"]  # PDF 1페이지 + 이미지 1장, 번호 연속

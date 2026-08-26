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


def test_pdf_split(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    pdf = open("tests/fixtures/dummy-form.pdf", "rb").read()
    png = open("tests/fixtures/dummy-filled.png", "rb").read()
    job_id = jobs.create(None, [("scan.pdf", pdf), ("photo.png", png)])
    names = [p.name for p in jobs.input_images(job_id)]
    assert names == ["000.png", "001.png"]  # PDF 1페이지 + 이미지 1장, 번호 연속

import pytest

from app import jobs


def test_delete_containment(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    with pytest.raises(ValueError):
        jobs.delete("../evil")
    with pytest.raises(ValueError):
        jobs.delete("a/b")


def test_pdf_split(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    pdf = open("tests/fixtures/dummy-form.pdf", "rb").read()
    png = open("tests/fixtures/dummy-filled.png", "rb").read()
    job_id = jobs.create(None, [("scan.pdf", pdf), ("photo.png", png)])
    names = [p.name for p in jobs.input_images(job_id)]
    assert names == ["000.png", "001.png"]  # PDF 1페이지 + 이미지 1장, 번호 연속

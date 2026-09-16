import queue

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import jobs, main, templates_store, worker


@pytest.fixture
def setup_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(worker, "_q", queue.Queue())
    monkeypatch.setattr(worker, "_cancel", set())
    directory = tmp_path / "j1"
    (directory / "input").mkdir(parents=True)
    for i in range(3):
        Image.new("RGB", (40, 50), "white").save(directory / "input" / f"{i:03d}.png")
    monkeypatch.setattr(templates_store, "get", lambda _: {"name": "form", "fields": []})
    monkeypatch.setattr(templates_store, "reference_path", lambda _: "unused")
    monkeypatch.setattr(worker, "HAVE_CV2", True)
    monkeypatch.setattr(worker, "to_reference", lambda *_: (None, False))
    jobs.write_status("j1", {"id": "j1", "template": "form", "state": "error", "error": "old error"})
    jobs.write_results("j1", [{"page": 0, "fields": [{"value": "edited"}]},
                              {"page": 1, "skipped": True, "fields": []}])
    return TestClient(main.app), directory


@pytest.mark.parametrize("state", ["error", "cancelled"])
def test_resume_preserves_completed_and_skipped_pages(setup_job, state):
    client, directory = setup_job
    st = jobs.status("j1")
    st["state"] = state
    jobs.write_status("j1", st)
    before = (directory / "results.json").read_bytes()
    worker.cancel("j1")
    assert client.post("/api/jobs/j1/resume").status_code == 200
    assert (directory / "results.json").read_bytes() == before
    st = jobs.status("j1")
    assert st["state"] == "queued" and not st.get("error")
    assert worker._q.get_nowait() == "j1"
    worker._process("j1", st)
    results = jobs.results("j1")
    assert len(results) == 3
    assert results[0]["fields"][0]["value"] == "edited"
    assert results[1]["skipped"] and results[2]["skipped"]


@pytest.mark.parametrize("state", ["queued", "running", "done"])
def test_resume_rejects_other_states(setup_job, state):
    client, directory = setup_job
    st = jobs.status("j1")
    st["state"] = state
    jobs.write_status("j1", st)
    before = (directory / "results.json").read_bytes()
    assert client.post("/api/jobs/j1/resume").status_code == 409
    assert (directory / "results.json").read_bytes() == before
    assert worker._q.empty()


def test_resume_missing_job(setup_job):
    client, _ = setup_job
    assert client.post("/api/jobs/missing/resume").status_code == 404


def test_rerun_still_clears_results(setup_job):
    client, directory = setup_job
    assert client.post("/api/jobs/j1/rerun").status_code == 200
    assert not (directory / "results.json").exists()


def test_resume_before_any_page_completed(setup_job):
    client, directory = setup_job
    (directory / "results.json").unlink()
    assert client.post("/api/jobs/j1/resume").status_code == 200
    worker._process("j1", jobs.status("j1"))
    assert len(jobs.results("j1")) == 3


@pytest.mark.parametrize("contents", ['invalid json', '[{"page": 1}]'])
def test_resume_does_not_silently_replace_invalid_results(setup_job, contents):
    client, directory = setup_job
    path = directory / "results.json"
    path.write_text(contents, encoding="utf-8")
    assert client.post("/api/jobs/j1/resume").status_code == 409
    assert path.read_text(encoding="utf-8") == contents
    assert jobs.status("j1")["state"] == "error"
    assert worker._q.empty()


def test_cancel_queued_then_resume_does_not_process_twice(setup_job, monkeypatch):
    client, _ = setup_job
    st = jobs.status("j1")
    st["state"] = "queued"
    jobs.write_status("j1", st)
    worker.enqueue("j1")
    assert client.post("/api/jobs/j1/cancel").status_code == 200
    assert client.post("/api/jobs/j1/resume").status_code == 200
    calls = []
    process = worker._process
    def tracked(*args):
        calls.append(args[0])
        process(*args)
    monkeypatch.setattr(worker, "_process", tracked)
    pending = worker._q
    class Drain:
        def get(self):
            return pending.get_nowait()
    monkeypatch.setattr(worker, "_q", Drain())
    with pytest.raises(queue.Empty):
        worker._loop()
    assert calls == ["j1"]
    assert jobs.status("j1")["state"] == "done"

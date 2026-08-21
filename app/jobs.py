"""job 상태 = data/jobs/<id>/ 파일. status.json / results.json / input/ / output/"""
import json
import time
import uuid

from app.config import JOBS_DIR


def create(template: str | None, files: list[tuple[str, bytes]]) -> str:
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    d = JOBS_DIR / job_id
    (d / "input").mkdir(parents=True)
    (d / "output").mkdir()
    for i, (name, data) in enumerate(files):
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
        if not ext.isalnum() or len(ext) > 5:
            ext = "png"
        (d / "input" / f"{i:03d}.{ext}").write_bytes(data)
    write_status(job_id, {"id": job_id, "template": template, "state": "queued",
                          "progress": "", "created": time.strftime("%Y-%m-%d %H:%M:%S")})
    return job_id


def _read(job_id: str, name: str):
    f = JOBS_DIR / job_id / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def status(job_id: str) -> dict | None:
    return _read(job_id, "status.json")


def results(job_id: str) -> list | None:
    return _read(job_id, "results.json")


def write_status(job_id: str, st: dict) -> None:
    (JOBS_DIR / job_id / "status.json").write_text(
        json.dumps(st, ensure_ascii=False), encoding="utf-8")


def write_results(job_id: str, res: list) -> None:
    (JOBS_DIR / job_id / "results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")


def list_jobs() -> list[dict]:
    out = [s for d in sorted(JOBS_DIR.iterdir(), reverse=True)
           if (s := status(d.name))]
    return out


def input_images(job_id: str) -> list:
    return sorted((JOBS_DIR / job_id / "input").iterdir())

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
    page = 0
    for name, data in files:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
        if ext == "pdf" or data[:5] == b"%PDF-":
            # 복합기 스캔 PDF: 페이지별 이미지로 분해 (전 양식 1장짜리 전제)
            import pymupdf
            doc = pymupdf.open(stream=data, filetype="pdf")
            for pg in doc:
                pg.get_pixmap(dpi=300).save(d / "input" / f"{page:03d}.png")
                page += 1
            continue
        if not ext.isalnum() or len(ext) > 5:
            ext = "png"
        (d / "input" / f"{page:03d}.{ext}").write_bytes(data)
        page += 1
    write_status(job_id, {"id": job_id, "template": template, "state": "queued",
                          "progress": "", "created": time.strftime("%Y-%m-%d %H:%M:%S")})
    return job_id


def _read(job_id: str, name: str):
    f = JOBS_DIR / job_id / name
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None  # 크래시로 쓰다 만 파일(NUL 등) — 없는 것으로 취급, 서버는 계속 뜬다


def status(job_id: str) -> dict | None:
    return _read(job_id, "status.json")


def results(job_id: str) -> list | None:
    return _read(job_id, "results.json")


def _write_atomic(job_id: str, name: str, text: str) -> None:
    # 크래시 순간 쓰다 만 파일이 남지 않게 임시 파일 → 교체
    f = JOBS_DIR / job_id / name
    tmp = f.with_name(name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(f)


def write_status(job_id: str, st: dict) -> None:
    _write_atomic(job_id, "status.json", json.dumps(st, ensure_ascii=False))


def write_results(job_id: str, res: list) -> None:
    _write_atomic(job_id, "results.json",
                  json.dumps(res, ensure_ascii=False, indent=2))


def list_jobs() -> list[dict]:
    out = [s for d in sorted(JOBS_DIR.iterdir(), reverse=True)
           if (s := status(d.name))]
    return out


def input_images(job_id: str) -> list:
    return sorted((JOBS_DIR / job_id / "input").iterdir())


def delete(job_id: str) -> None:
    import shutil
    target = (JOBS_DIR / job_id).resolve()
    if target.parent != JOBS_DIR.resolve():  # 경로 이탈 방어 (2차 방어선)
        raise ValueError(f"잘못된 작업 경로: {job_id}")
    shutil.rmtree(target, ignore_errors=True)

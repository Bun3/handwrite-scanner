import re

from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import export, jobs, llm, pdf_gen, templates_store, worker
from app.config import GITHUB_REPO, JOBS_DIR, STATIC_DIR, VERSION

app = FastAPI(title="handwrite-scanner")

_update = {"current": VERSION, "available": False}


def _ver(tag: str) -> tuple:
    return tuple(int(x) for x in tag.lstrip("v").split("."))


def _check_update():
    """GitHub 최신 릴리스 확인. 오프라인이면 조용히 넘어감."""
    import httpx
    try:
        r = httpx.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                      timeout=5, follow_redirects=True)
        tag = r.json()["tag_name"]
        _update.update(latest=tag.lstrip("v"), url=r.json()["html_url"],
                       available=_ver(tag) > _ver(VERSION))
    except Exception:
        pass


def _safe(name: str) -> str:
    """경로 순회 방지: 파일/디렉터리 이름으로 쓰이는 URL 파라미터 검증."""
    if not name or re.search(r'[/\\:*?"<>|]', name) or name.startswith("."):
        raise HTTPException(400, "잘못된 이름")
    return name


@app.on_event("startup")
def _startup():
    import threading
    worker.start()
    threading.Thread(target=_check_update, daemon=True).start()


@app.get("/api/health")
def health():
    return {"app": "ok", "llm": llm.is_up(), "version": VERSION}


@app.get("/api/update")
def update_info():
    return _update


# ---------- 템플릿 ----------

@app.get("/api/templates")
def templates_list():
    return templates_store.list_templates()


@app.post("/api/templates")
async def template_create(name: str = Form(...), file: UploadFile = None):
    _safe(name)
    if file is not None:
        templates_store.set_reference(name, await file.read(), file.filename)
    tpl = templates_store.get(name) or templates_store.save(name, [])
    return tpl


@app.put("/api/templates/{name}")
async def template_update(name: str, body: dict):
    return templates_store.save(_safe(name), body["fields"])


@app.get("/api/templates/{name}/reference")
def template_reference(name: str):
    return FileResponse(templates_store.reference_path(_safe(name)))


@app.delete("/api/templates/{name}")
def template_delete(name: str):
    templates_store.delete(_safe(name))
    return {"ok": True}


# ---------- 작업 ----------

@app.post("/api/jobs")
async def job_create(files: list[UploadFile], template: str = Form("")):
    pairs = [(f.filename, await f.read()) for f in files]
    job_id = jobs.create(template or None, pairs)
    worker.enqueue(job_id)
    return {"id": job_id}


@app.get("/api/jobs")
def jobs_list():
    return jobs.list_jobs()


@app.get("/api/jobs/{job_id}")
def job_get(job_id: str):
    st = jobs.status(_safe(job_id))
    if not st:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"status": st, "results": jobs.results(job_id)}


@app.patch("/api/jobs/{job_id}/fields")
async def job_field_update(job_id: str, body: dict):
    """검수 수정: {page, id, value}"""
    res = jobs.results(_safe(job_id))
    for f in res[body["page"]]["fields"]:
        if f["id"] == body["id"]:
            f["value"] = body["value"]
            f["confidence"] = 1.0
    jobs.write_results(job_id, res)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/page/{n}")
def job_page(job_id: str, n: int):
    return FileResponse(JOBS_DIR / _safe(job_id) / f"page_{n:03d}.png")


@app.get("/api/jobs/{job_id}/export")
def job_export(job_id: str, fmt: str = "md"):
    if fmt not in ("md", "txt", "csv"):
        raise HTTPException(400, "fmt는 md|txt|csv")
    res = jobs.results(_safe(job_id))
    if res is None:
        raise HTTPException(404, "결과 없음")
    content, fname, mt = export.build(job_id, res, fmt)
    return Response(content, media_type=mt, headers={
        "Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/api/jobs/{job_id}/pdf")
def job_pdf(job_id: str, kind: str = "searchable", inline: bool = False):
    if kind not in ("searchable", "clean", "text"):
        raise HTTPException(400, "kind는 searchable|clean|text")
    path = pdf_gen.generate(_safe(job_id), kind)
    if inline:  # 브라우저 탭에서 바로 보기 (다운로드 표식 없음)
        return FileResponse(path, media_type="application/pdf")
    return FileResponse(path, filename=f"{job_id}-{kind}.pdf")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))

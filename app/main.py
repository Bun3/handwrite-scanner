import re

from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import jobs, llm, pdf_gen, templates_store, worker
from app.config import JOBS_DIR, STATIC_DIR

app = FastAPI(title="handwrite-scanner")


def _safe(name: str) -> str:
    """경로 순회 방지: 파일/디렉터리 이름으로 쓰이는 URL 파라미터 검증."""
    if not name or re.search(r'[/\\:*?"<>|]', name) or name.startswith("."):
        raise HTTPException(400, "잘못된 이름")
    return name


@app.on_event("startup")
def _startup():
    worker.start()


@app.get("/api/health")
def health():
    return {"app": "ok", "llm": llm.is_up()}


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


@app.get("/api/jobs/{job_id}/pdf")
def job_pdf(job_id: str, kind: str = "searchable"):
    if kind not in ("searchable", "clean", "text"):
        raise HTTPException(400, "kind는 searchable|clean|text")
    path = pdf_gen.generate(_safe(job_id), kind)
    return FileResponse(path, filename=f"{job_id}-{kind}.pdf")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))

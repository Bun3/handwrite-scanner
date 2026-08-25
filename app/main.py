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


# ---------- 인식 모델 ----------

@app.get("/api/models")
def models_list():
    from app import models
    return models.status_list()


@app.post("/api/models/{model_id}/download")
def models_download(model_id: str):
    from app import models
    if not models.entry(model_id):
        raise HTTPException(404, "알 수 없는 모델")
    models.start_download(model_id)
    return {"ok": True}


@app.post("/api/models/{model_id}/select")
def models_select(model_id: str):
    from app import models
    if any(s["state"] in ("running", "queued") for s in jobs.list_jobs()):
        raise HTTPException(409, "인식 작업이 진행 중입니다. 완료 후 모델을 바꾸세요.")
    try:
        e = models.select(model_id)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return {"ok": True, "label": e["label"]}


# ---------- 폰 업로드 ----------

@app.post("/api/phone/start")
def phone_start():
    from app import phone
    return phone.start()


@app.post("/api/phone/stop")
def phone_stop():
    from app import phone
    phone.stop()
    return {"ok": True}


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
    rules = body.get("rules")
    if rules:
        from app.rules import validate_expr
        for expr in rules:
            err = validate_expr(expr)
            if err:
                raise HTTPException(400, f"규칙 오류 '{expr}': {err}")
    return templates_store.save(_safe(name), body["fields"], rules)


@app.get("/api/templates/{name}/reference")
def template_reference(name: str):
    return FileResponse(templates_store.reference_path(_safe(name)))


@app.delete("/api/templates/{name}")
def template_delete(name: str):
    templates_store.delete(_safe(name))
    return {"ok": True}


@app.post("/api/templates/{name}/autodetect")
def template_autodetect(name: str):
    """기준 이미지에서 입력란을 VLM으로 감지해 필드 초안 반환 (베타 — 사람이 조정)."""
    import io
    import json as _json
    import re as _re

    from PIL import Image
    ref = templates_store.reference_path(_safe(name))
    if not ref.exists():
        raise HTTPException(404, "기준 이미지 없음")
    img = Image.open(ref)
    W, H = img.size
    small = img.copy()
    small.thumbnail((1000, 1400))
    buf = io.BytesIO()
    small.save(buf, "PNG")
    raw = llm.ask_image(buf.getvalue(), (
        "이 문서 양식에서 사람이 손글씨로 값을 적도록 비워 둔 입력란을 모두 찾아라. "
        "각 입력란에 대해 인쇄된 라벨 텍스트와 빈칸 영역의 경계 상자를 구하라. "
        "좌표는 이미지 좌상단 기준 0~1000 상대좌표의 [x0,y0,x1,y1]이다. "
        '결과는 JSON 배열로만 출력하라: [{"label":"성명","box":[x0,y0,x1,y1]}]'))
    m = _re.search(r"\[.*\]", raw, _re.S)
    try:
        items = _json.loads(m.group()) if m else []
    except _json.JSONDecodeError:
        raise HTTPException(502, "감지 결과 해석 실패 — 다시 시도해 보세요")
    fields = []
    for i, it in enumerate(items):
        try:
            x0, y0, x1, y1 = [float(v) for v in it["box"]]
        except (KeyError, TypeError, ValueError):
            continue
        fields.append({
            "id": f"auto{i}", "label": str(it.get("label", f"필드{i + 1}")),
            "type": "text",
            "box": [int(x0 / 1000 * W), int(y0 / 1000 * H),
                    max(10, int((x1 - x0) / 1000 * W)),
                    max(10, int((y1 - y0) / 1000 * H))],
            "candidates": []})
    return {"fields": fields}


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
    safe_id = _safe(job_id)
    st = jobs.status(safe_id)
    if not st:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"status": st, "results": jobs.results(safe_id)}


@app.patch("/api/jobs/{job_id}/fields")
async def job_field_update(job_id: str, body: dict):
    """검수 수정: {page, id, value}. 후보 타입인데 목록에 없는 값이면 학습 제안."""
    safe_id = _safe(job_id)
    res = jobs.results(safe_id)
    page = res[body["page"]]
    suggest = None
    for f in page["fields"]:
        if f["id"] == body["id"]:
            f["value"] = body["value"]
            f["confidence"] = 1.0
            tpl_name = page.get("template") or (jobs.status(safe_id) or {}).get("template")
            if (tpl_name and f.get("type") in ("candidates", "circle")
                    and body["value"].strip()):
                tpl = templates_store.get(tpl_name)
                tf = next((x for x in (tpl or {}).get("fields", [])
                           if x["id"] == f["id"]), None)
                if tf is not None and body["value"] not in tf.get("candidates", []):
                    suggest = {"template": tpl_name, "field_id": f["id"],
                               "value": body["value"]}
    jobs.write_results(safe_id, res)
    return {"ok": True, "suggest": suggest}


@app.post("/api/templates/{name}/candidates")
async def template_add_candidate(name: str, body: dict):
    """{field_id, value} → 후보목록에 추가 (검수 학습)"""
    return {"added": templates_store.add_candidate(_safe(name),
                                                   body["field_id"], body["value"])}


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    safe_id = _safe(job_id)
    st = jobs.status(safe_id)
    if not st:
        raise HTTPException(404, "작업 없음")
    if st["state"] == "queued":
        st["state"] = "cancelled"
        jobs.write_status(safe_id, st)
        worker.cancel(safe_id)
        return {"ok": True}
    if st["state"] == "running":
        worker.cancel(safe_id)  # 진행 중인 필드 하나는 끝내고 멈춤
        return {"ok": True}
    raise HTTPException(409, "이미 종료된 작업입니다")


@app.delete("/api/jobs/{job_id}")
def job_delete(job_id: str):
    safe_id = _safe(job_id)
    st = jobs.status(safe_id)
    if not st:
        raise HTTPException(404, "작업 없음")
    if st["state"] == "running":
        raise HTTPException(409, "처리 중인 작업은 삭제할 수 없습니다. 완료 후 삭제하세요.")
    jobs.delete(safe_id)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/page/{n}")
def job_page(job_id: str, n: int):
    return FileResponse(JOBS_DIR / _safe(job_id) / f"page_{n:03d}.png")


@app.get("/api/search")
def search(q: str):
    """전 작업의 인식 결과에서 부분 문자열 검색.

    ponytail: 파일 전수 스캔 — 작업 수천 건 넘어가면 인덱스 도입.
    """
    q = q.strip().lower()
    if not q:
        return []
    hits = []
    for st in jobs.list_jobs():
        for page in jobs.results(st["id"]) or []:
            for f in page["fields"]:
                if q in str(f.get("value", "")).lower():
                    hits.append({"job": st["id"], "page": page["page"],
                                 "template": page.get("template") or st.get("template"),
                                 "label": f["label"], "value": f["value"],
                                 "created": st.get("created", "")})
                    if len(hits) >= 200:
                        return hits
    return hits


@app.get("/api/export-merged")
def export_merged(template: str, fmt: str = "csv"):
    """해당 템플릿으로 인식된 완료 작업 전체를 하나의 표로 병합."""
    if fmt not in ("md", "txt", "csv"):
        raise HTTPException(400, "fmt는 md|txt|csv")
    _safe(template)
    job_list = []
    for st in jobs.list_jobs():
        if st["state"] != "done":
            continue
        res = jobs.results(st["id"])
        if res and any((p.get("template") or st.get("template")) == template
                       for p in res):
            job_list.append((st, res))
    if not job_list:
        raise HTTPException(404, "해당 템플릿으로 완료된 작업 없음")
    content, fname, mt = export.merged(template, job_list, fmt)
    from urllib.parse import quote
    # ASCII filename 폴백 필수 — filename*만 주면 일부 브라우저/다운로드 매니저가
    # 파일명을 못 정해 다운로드가 깨진다
    return Response(content, media_type=mt, headers={
        "Content-Disposition":
            f'attachment; filename="merged.{fmt}"; '
            f"filename*=UTF-8''{quote(fname)}"})


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

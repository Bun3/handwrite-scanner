"""백그라운드 인식 워커. CPU 순차 처리라 스레드 1개 + Queue."""
import io
import json
import queue
import re
import threading
import traceback

from app import jobs, llm, postprocess, templates_store
from app.align import to_reference

_q: "queue.Queue[str]" = queue.Queue()

PAD = 8  # 필드 crop 여백(px)


def enqueue(job_id: str) -> None:
    _q.put(job_id)


def start() -> None:
    threading.Thread(target=_loop, daemon=True).start()
    for st in jobs.list_jobs():  # 재시작 시 미완료 job 재개
        if st["state"] in ("queued", "running"):
            st["state"] = "queued"
            jobs.write_status(st["id"], st)
            enqueue(st["id"])


def _loop() -> None:
    while True:
        job_id = _q.get()
        st = jobs.status(job_id)
        try:
            st["state"] = "running"
            jobs.write_status(job_id, st)
            _process(job_id, st)
            st["state"] = "done"
            st["progress"] = ""
        except Exception:
            st["state"] = "error"
            st["error"] = traceback.format_exc(limit=3)
        jobs.write_status(job_id, st)


def _process(job_id: str, st: dict) -> None:
    tpl = templates_store.get(st["template"]) if st.get("template") else None
    images = jobs.input_images(job_id)
    results = []
    job_dir = jobs.JOBS_DIR / job_id
    for page_no, img_path in enumerate(images):
        data = img_path.read_bytes()
        if tpl:
            fields = _recognize_with_template(job_id, st, tpl, data, page_no,
                                              len(images), job_dir)
            aligned_ok = fields.pop("_aligned")
            results.append({"page": page_no, "aligned": aligned_ok,
                            "fields": fields["fields"]})
        else:
            import shutil
            shutil.copy(img_path, job_dir / f"page_{page_no:03d}.png")
            results.append({"page": page_no, "aligned": None,
                            "fields": _recognize_freeform(data)})
        jobs.write_results(job_id, results)


def _recognize_with_template(job_id, st, tpl, data, page_no, total_pages,
                             job_dir):
    aligned, ok = to_reference(
        data, templates_store.reference_path(tpl["name"]))
    aligned.save(job_dir / f"page_{page_no:03d}.png")
    out = []
    for i, f in enumerate(tpl["fields"]):
        st["progress"] = f"{page_no + 1}/{total_pages}페이지 · {i + 1}/{len(tpl['fields'])} {f['label']}"
        jobs.write_status(job_id, st)
        x, y, w, h = f["box"]
        crop = aligned.crop((max(0, x - PAD), max(0, y - PAD),
                             x + w + PAD, y + h + PAD))
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        raw = llm.ask_image(buf.getvalue(), _prompt(f))
        value, conf = _post(raw, f)
        out.append({"id": f["id"], "label": f["label"], "type": f["type"],
                    "box": f["box"], "raw": raw, "value": value,
                    "confidence": round(conf, 2)})
    return {"fields": out, "_aligned": ok}


def _prompt(f: dict) -> str:
    label, t = f["label"], f["type"]
    if t == "circle":
        return (f"이 이미지에는 다음 선택지들이 인쇄되어 있고, 그중 하나에 손으로 "
                f"동그라미(또는 체크)가 표시되어 있다: {', '.join(f['candidates'])}. "
                "표시된 항목 하나만 정확히 그대로 출력하라. 설명 금지.")
    base = (f"이 이미지는 문서 양식에서 '{label}' 칸을 잘라낸 것이다. "
            "인쇄된 라벨은 무시하고 손으로 쓴 내용만 읽어라. ")
    if t == "phone":
        base += "전화번호다. 숫자와 하이픈만 출력하라. "
    elif t == "number":
        base += "숫자다. 숫자만 출력하라. "
    elif f.get("candidates"):
        base += f"값은 다음 후보 중 하나다: {', '.join(f['candidates'])}. 가장 일치하는 후보를 그대로 출력하라. "
    base += "설명 없이 값만 출력하라. 비어 있으면 '없음'을 출력하라."
    if f.get("hint"):
        base += " " + f["hint"]
    return base


def _post(raw: str, f: dict) -> tuple[str, float]:
    if f["type"] == "circle" or (f.get("candidates") and f["type"] != "text_free"):
        return postprocess.match_candidate(raw, f.get("candidates") or [])
    return postprocess.validate(raw, f["type"])


def _recognize_freeform(data: bytes) -> list:
    raw = llm.ask_image(data, (
        "이 문서 양식의 모든 항목을 읽어라. 인쇄된 라벨을 키로, 손글씨 값을 값으로 하는 "
        'JSON 객체 하나만 출력하라. 예: {"성명": "홍길동"}. 다른 텍스트 금지.'))
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        parsed = json.loads(m.group()) if m else {}
    except json.JSONDecodeError:
        parsed = {"인식결과": raw}
    return [{"id": f"f{i}", "label": k, "type": "text",
             "box": None, "raw": str(v),
             "value": postprocess.normalize_ws(str(v)), "confidence": 0.5}
            for i, (k, v) in enumerate(parsed.items())]

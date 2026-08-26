"""백그라운드 인식 워커. CPU 순차 처리라 스레드 1개 + Queue."""
import io
import json
import queue
import re
import threading
import traceback

from app import jobs, llm, postprocess, templates_store
from app.align import HAVE_CV2, best_template, to_reference

_q: "queue.Queue[str]" = queue.Queue()
_cancel: set[str] = set()

def _pad(img_width: int) -> int:
    """필드 crop 여백. 고정 px는 300dpi 스캔에서 1mm도 안 돼 경계에 걸친
    글씨가 잘리므로 이미지 폭에 비례(약 2mm)시킨다."""
    return max(8, img_width // 100)


class _Cancelled(Exception):
    pass


def enqueue(job_id: str) -> None:
    _q.put(job_id)


def cancel(job_id: str) -> None:
    """협조적 중단 요청 — 진행 중인 필드 하나는 끝내고 멈춘다."""
    _cancel.add(job_id)


def _check_cancel(job_id: str) -> None:
    if job_id in _cancel:
        raise _Cancelled()


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
        if st is None or st["state"] == "cancelled":  # 대기 중 삭제·중단된 작업
            _cancel.discard(job_id)
            continue
        try:
            st["state"] = "running"
            jobs.write_status(job_id, st)
            _process(job_id, st)
            st["state"] = "done"
            st["progress"] = ""
        except _Cancelled:
            st["state"] = "cancelled"
            st["progress"] = ""
        except Exception:
            st["state"] = "error"
            st["error"] = traceback.format_exc(limit=3)
        _cancel.discard(job_id)
        jobs.write_status(job_id, st)


def _process(job_id: str, st: dict) -> None:
    tpl_fixed = templates_store.get(st["template"]) if st.get("template") else None
    detect_pool = None
    if not tpl_fixed:  # 템플릿 미지정 = 페이지별 자동 판별 (실패 시 freeform)
        detect_pool = [(t, templates_store.reference_path(t["name"]))
                       for t in templates_store.list_templates()]
    images = jobs.input_images(job_id)
    # 크래시 복구: 이전 실행이 완료한 페이지 프리픽스는 건너뛰고 이어간다.
    # (재인식 버튼은 results.json을 지우고 시작하므로 항상 처음부터)
    done = jobs.results(job_id) or []
    results = done if all(p.get("page") == i for i, p in enumerate(done)) else []
    job_dir = jobs.JOBS_DIR / job_id
    for page_no, img_path in enumerate(images):
        if page_no < len(results):
            continue
        _check_cancel(job_id)
        data = img_path.read_bytes()
        tpl, aligned, ok = tpl_fixed, None, None
        if tpl_fixed:
            aligned, ok = to_reference(
                data, templates_store.reference_path(tpl_fixed["name"]))
            if HAVE_CV2 and not ok:
                # 지정 양식과 정합 실패 = 사이에 끼인 증빙 등 다른 서류 → 인식 생략
                import shutil
                shutil.copy(img_path, job_dir / f"page_{page_no:03d}.png")
                results.append({"page": page_no, "aligned": None,
                                "template": None, "skipped": True, "fields": [],
                                "warnings": ["지정한 양식과 일치하지 않아 인식하지 않고 건너뛰었습니다"]})
                jobs.write_results(job_id, results)
                continue
        elif detect_pool:
            tpl, aligned = best_template(data, detect_pool)
            ok = tpl is not None
        if tpl:
            fields = _recognize_fields(job_id, st, tpl, aligned, page_no,
                                       len(images), job_dir)
            warnings = _apply_rules(tpl, fields)
            results.append({"page": page_no, "aligned": ok,
                            "template": tpl["name"], "fields": fields,
                            "warnings": warnings})
        else:
            import shutil
            shutil.copy(img_path, job_dir / f"page_{page_no:03d}.png")
            st["progress"] = (f"{page_no + 1}/{len(images)}페이지 · "
                              "양식 미인식 — 전체 추출 중 (가장 오래 걸리는 단계)")
            jobs.write_status(job_id, st)
            fields = _recognize_freeform(data)
            results.append({"page": page_no, "aligned": None, "template": None,
                            "fields": fields,
                            "warnings": [] if fields else
                            ["문서에서 양식 항목을 찾지 못했습니다 — 문서 사진이 맞는지 확인하세요"]})
        jobs.write_results(job_id, results)


def _recognize_fields(job_id, st, tpl, aligned, page_no, total_pages, job_dir):
    aligned.save(job_dir / f"page_{page_no:03d}.png")
    out = []
    for i, f in enumerate(tpl["fields"]):
        _check_cancel(job_id)
        st["progress"] = f"{page_no + 1}/{total_pages}페이지 · {i + 1}/{len(tpl['fields'])} {f['label']}"
        jobs.write_status(job_id, st)
        x, y, w, h = f["box"]
        pad = _pad(aligned.width)
        crop = aligned.crop((max(0, x - pad), max(0, y - pad),
                             x + w + pad, y + h + pad))
        if crop.width < 1000:  # 작은 crop은 VLM 인식률이 떨어짐 → 업스케일
            s = min(3, 1000 / crop.width)
            crop = crop.resize((int(crop.width * s), int(crop.height * s)))
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        raw = llm.ask_image(buf.getvalue(), _prompt(f))
        value, conf = _post(raw, f)
        value, conf = _second_pass(buf.getvalue(), f, value, conf)
        out.append({"id": f["id"], "label": f["label"], "type": f["type"],
                    "box": f["box"], "raw": raw, "value": value,
                    "confidence": round(conf, 2)})
    return out


def _apply_rules(tpl: dict, fields: list) -> list[str]:
    """교차 필드 검증·유추. 위반 규칙의 관련 필드는 신뢰도를 낮춰 검수 강조.

    "fid = 식" 유추 규칙: 대상이 비어 있으면 식의 값으로 채우고(신뢰도 0.75),
    값이 있으면 등식 검증. 유추값이 필드 min/max를 벗어나면 채우지 않는다
    (예: 종일 휴가의 근무시간 차를 '총 시간'에 넣는 오류 방지).
    """
    from app import rules as rules_mod
    warnings = []
    values = {f["id"]: f["value"] for f in fields}
    by_id = {f["id"]: f for f in fields}
    label_ids = {f["label"]: f["id"] for f in tpl["fields"] if f.get("label")}
    for expr in tpl.get("rules", []):
        try:
            violated = False
            resolved = rules_mod.resolve(expr, label_ids)  # 라벨로 쓴 규칙 → id
            assign = rules_mod.parse_assign(resolved)
            if assign:
                tid, rhs = assign
                target = by_id.get(tid)
                val = rules_mod.evaluate(rhs, values)
                if target is None or val is None:
                    continue
                cur = str(target["value"]).strip()
                if cur.lstrip("-").isdigit():
                    violated = int(cur) != val
                else:
                    fdef = next((x for x in tpl["fields"] if x["id"] == tid), {})
                    if fdef.get("min", val) <= val <= fdef.get("max", val):
                        target["value"] = str(val)
                        target["confidence"] = 0.75  # 유추값 — 검수 훑어보기 선
                        values[tid] = target["value"]
                        warnings.append(f"빈 값 유추: {target['label']} = {val}")
                    continue
            else:
                violated = rules_mod.check(resolved, values) is False
            if violated:
                warnings.append(f"검증 실패: {expr}")
                for f in fields:
                    if f["id"] in rules_mod.rule_ids(resolved):
                        f["confidence"] = min(f["confidence"], 0.5)
        except (SyntaxError, ValueError):
            warnings.append(f"규칙 오류: {expr}")
    return warnings


def _prompt(f: dict) -> str:
    label, t = f["label"], f["type"]
    if t == "circle":
        return (f"이 이미지에는 다음 선택지들이 인쇄되어 있다: {', '.join(f['candidates'])}. "
                "그중 하나에 손으로 표시가 되어 있다. 표시는 동그라미, 체크(✓), 빗금, "
                "밑줄, 덧칠 등 어떤 형태든 될 수 있다. 인쇄된 글자 위나 주변에 손글씨 "
                "획이 겹쳐지거나 더럽혀진 항목을 찾아, 그 항목 하나만 정확히 그대로 "
                "출력하라. 아무 표시도 없으면 '없음'을 출력하라. 설명 금지.")
    base = (f"이 이미지는 문서 양식에서 '{label}' 칸을 잘라낸 것이다. "
            "인쇄된 라벨은 무시하고 손으로 쓴 내용만 읽어라. ")
    if t == "phone":
        base += ("전화번호다. 휴대전화면 하이픈 제외 정확히 숫자 11개다. "
                 "겹치거나 붙어 쓰인 숫자도 각각 세어 모두 읽어라. "
                 "숫자와 하이픈만 출력하라. ")
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


def _second_pass(crop_png: bytes, f: dict, value: str, conf: float):
    """1차 인식의 흔한 오독을 검증하는 2차 처리.

    - number + min/max 선언: 범위 밖이면 한글 손글씨 삐침(1 오인) 보정
    - phone: 마지막 자리가 혼동 쌍(7/9)이면 이지선다 재질문으로 확정

    확대 배율을 바꿔 재질문하는 방식은 실험 결과 배율마다 다른 후보를
    확신 있게 내놓아(같은 crop이 1.15x=없음/2x=이순덕/2.3x=이관희) 오히려
    그럴듯한 오답을 만들었다 — 빈 값 + 낮은 신뢰도로 검수에 넘기는 게 정직하다.
    """
    if f["type"] == "number" and ("min" in f or "max" in f):
        value, conf = postprocess.clamp_number(
            value, conf, f.get("min", 0), f.get("max", 10 ** 9))
    elif f["type"] == "phone":
        digits = value.replace("-", "")
        if len(digits) == 11 and digits[-1] in "79":
            ans = llm.ask_image(crop_png, (
                "이 전화번호의 마지막 숫자는 7인가 9인가? "
                "위쪽에 작은 고리(원)가 있으면 9, 각진 꺾임이면 7이다. "
                "숫자 하나만 출력하라."))
            d = ans.strip()[-1:]
            if d in "79" and d != digits[-1]:
                value = value[:-1] + d
    return value, conf


def _recognize_freeform(data: bytes) -> list:
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    if img.width > 1600:  # 대형 사진은 축소 — 문서 텍스트 판독에 충분하고 훨씬 빠름
        img.thumbnail((1600, 2400))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        data = buf.getvalue()
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

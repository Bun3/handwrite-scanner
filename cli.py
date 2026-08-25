"""AI 에이전트·스크립트용 CLI — 실행 중인 서버의 REST API를 감싸는 얇은 클라이언트.

사용:  python cli.py <명령> ...           (배포판: handwrite-scanner.exe cli <명령> ...)
전제:  프로그램(서버)이 떠 있어야 한다. 기본 http://127.0.0.1:8000, --server 로 변경.
출력:  전부 JSON(stdout). 오류는 JSON(stderr) + 종료코드 1. 파일 저장 명령은 {"saved": 경로}.

예시:
  python cli.py jobs submit 문서.pdf --template 휴가신청서 --wait
  python cli.py jobs export <job_id> --fmt csv -o out.csv
  python cli.py search 홍길동
"""
import argparse
import json
import mimetypes
import re
import sys
import time
from pathlib import Path

import httpx

DONE_STATES = ("done", "error", "cancelled")


def _out(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _die(msg: str) -> None:
    print(json.dumps({"error": msg}, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)


def _req(c: httpx.Client, method: str, url: str, **kw) -> httpx.Response:
    try:
        r = c.request(method, url, **kw)
    except httpx.ConnectError:
        _die(f"서버에 연결할 수 없습니다 ({c.base_url}). 프로그램을 먼저 실행하세요.")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        _die(f"HTTP {r.status_code}: {detail}")
    return r


def _save(r: httpx.Response, out: str | None, default: str) -> None:
    if not out:
        m = re.search(r'filename="([^"]+)"', r.headers.get("content-disposition", ""))
        out = m.group(1) if m else default
    Path(out).write_bytes(r.content)
    _out({"saved": str(Path(out).resolve()), "bytes": len(r.content)})


def _upload_files(paths: list[str]) -> list:
    files = []
    for p in paths:
        path = Path(p)
        if not path.is_file():
            _die(f"파일 없음: {p}")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        files.append(("files", (path.name, path.read_bytes(), mime)))
    return files


def _wait(c: httpx.Client, job_id: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = _req(c, "GET", f"/api/jobs/{job_id}").json()
        if d["status"]["state"] in DONE_STATES:
            return d
        time.sleep(5)
    _die(f"시간 초과({timeout}초). 'jobs get {job_id}' 로 계속 확인할 수 있습니다.")


# ── 명령 구현 ──────────────────────────────────────────────────────────

def cmd_health(c, a): _out(_req(c, "GET", "/api/health").json())
def cmd_update(c, a): _out(_req(c, "GET", "/api/update").json())
def cmd_search(c, a): _out(_req(c, "GET", "/api/search", params={"q": a.query}).json())


def cmd_jobs_submit(c, a):
    r = _req(c, "POST", "/api/jobs", files=_upload_files(a.files),
             data={"template": a.template or ""})
    job_id = r.json()["id"]
    _out(_wait(c, job_id, a.timeout) if a.wait else {"id": job_id})


def cmd_jobs_list(c, a): _out(_req(c, "GET", "/api/jobs").json())
def cmd_jobs_get(c, a): _out(_req(c, "GET", f"/api/jobs/{a.id}").json())
def cmd_jobs_wait(c, a):
    if a.all:
        deadline = time.time() + a.timeout
        while time.time() < deadline:
            all_jobs = _req(c, "GET", "/api/jobs").json()
            if not any(s["state"] in ("queued", "running") for s in all_jobs):
                return _out(all_jobs)
            time.sleep(5)
        _die(f"시간 초과({a.timeout}초). 아직 진행 중인 작업이 있습니다.")
    if not a.id:
        _die("작업 id 또는 --all 이 필요합니다")
    _out(_wait(c, a.id, a.timeout))
def cmd_jobs_cancel(c, a): _out(_req(c, "POST", f"/api/jobs/{a.id}/cancel").json())
def cmd_jobs_delete(c, a): _out(_req(c, "DELETE", f"/api/jobs/{a.id}").json())


def cmd_jobs_set(c, a):
    _out(_req(c, "PATCH", f"/api/jobs/{a.id}/fields",
              json={"page": a.page, "id": a.field, "value": a.value}).json())


def cmd_jobs_export(c, a):
    r = _req(c, "GET", f"/api/jobs/{a.id}/export", params={"fmt": a.fmt})
    _save(r, a.output, f"{a.id}.{a.fmt}")


def cmd_jobs_pdf(c, a):
    r = _req(c, "GET", f"/api/jobs/{a.id}/pdf", params={"kind": a.kind})
    _save(r, a.output, f"{a.id}-{a.kind}.pdf")


def cmd_jobs_original(c, a):
    r = _req(c, "GET", f"/api/jobs/{a.id}/original")
    _save(r, a.output, f"{a.id}-original.bin")


def cmd_tpl_list(c, a): _out(_req(c, "GET", "/api/templates").json())


def cmd_tpl_get(c, a):
    tpl = next((t for t in _req(c, "GET", "/api/templates").json()
                if t["name"] == a.name), None)
    _out(tpl) if tpl else _die(f"템플릿 없음: {a.name}")


def cmd_tpl_create(c, a):
    path = Path(a.file)
    if not path.is_file():
        _die(f"파일 없음: {a.file}")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    _out(_req(c, "POST", "/api/templates", data={"name": a.name},
              files={"file": (path.name, path.read_bytes(), mime)}).json())


def cmd_tpl_update(c, a):
    body = {}
    if a.fields:
        body["fields"] = json.loads(Path(a.fields).read_text(encoding="utf-8"))
    if a.rules is not None:
        body["rules"] = a.rules
    if not body:
        _die("--fields 또는 --rules 중 하나는 필요합니다")
    _out(_req(c, "PUT", f"/api/templates/{a.name}", json=body).json())


def cmd_tpl_delete(c, a): _out(_req(c, "DELETE", f"/api/templates/{a.name}").json())
def cmd_tpl_autodetect(c, a): _out(_req(c, "POST", f"/api/templates/{a.name}/autodetect").json())


def cmd_tpl_candidate(c, a):
    _out(_req(c, "POST", f"/api/templates/{a.name}/candidates",
              json={"field_id": a.field, "value": a.value}).json())


def cmd_models_list(c, a): _out(_req(c, "GET", "/api/models").json())
def cmd_models_download(c, a): _out(_req(c, "POST", f"/api/models/{a.id}/download").json())
def cmd_models_select(c, a): _out(_req(c, "POST", f"/api/models/{a.id}/select").json())


def cmd_export_merged(c, a):
    r = _req(c, "GET", "/api/export-merged",
             params={"template": a.template, "fmt": a.fmt})
    _save(r, a.output, f"merged-{a.template}.{a.fmt}")


# ── 파서 ──────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="handwrite-scanner cli", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server", default="http://127.0.0.1:8000",
                   help="서버 주소 (기본 %(default)s)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="서버·엔진 상태").set_defaults(fn=cmd_health)
    sub.add_parser("update", help="새 버전 확인").set_defaults(fn=cmd_update)
    s = sub.add_parser("search", help="인식 결과 전체 검색")
    s.add_argument("query")
    s.set_defaults(fn=cmd_search)

    jobs = sub.add_parser("jobs", help="인식 작업").add_subparsers(dest="sub", required=True)
    s = jobs.add_parser("submit", help="문서 업로드(이미지·PDF 여러 개 가능)")
    s.add_argument("files", nargs="+")
    s.add_argument("--template", help="양식 이름 (생략 시 자동 판별)")
    s.add_argument("--wait", action="store_true", help="완료까지 대기 후 결과 출력")
    s.add_argument("--timeout", type=int, default=3600)
    s.set_defaults(fn=cmd_jobs_submit)
    jobs.add_parser("list", help="작업 목록").set_defaults(fn=cmd_jobs_list)
    for name, fn, help_ in (("get", cmd_jobs_get, "상태+인식 결과"),
                            ("cancel", cmd_jobs_cancel, "작업 중단"),
                            ("delete", cmd_jobs_delete, "작업 삭제")):
        s = jobs.add_parser(name, help=help_)
        s.add_argument("id")
        s.set_defaults(fn=fn)
    s = jobs.add_parser("wait", help="완료까지 대기 후 결과 출력 (--all: 전체 작업 완료 대기)")
    s.add_argument("id", nargs="?")
    s.add_argument("--all", action="store_true", help="모든 대기·진행 중 작업이 끝날 때까지 대기")
    s.add_argument("--timeout", type=int, default=3600)
    s.set_defaults(fn=cmd_jobs_wait)
    s = jobs.add_parser("set", help="검수: 필드 값 수정")
    s.add_argument("id")
    s.add_argument("--page", type=int, default=0)
    s.add_argument("--field", required=True, help="필드 id")
    s.add_argument("--value", required=True)
    s.set_defaults(fn=cmd_jobs_set)
    s = jobs.add_parser("export", help="표 내보내기")
    s.add_argument("id")
    s.add_argument("--fmt", choices=("md", "txt", "csv"), default="md")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_jobs_export)
    s = jobs.add_parser("pdf", help="PDF 다운로드")
    s.add_argument("id")
    s.add_argument("--kind", choices=("searchable", "clean", "text"), default="searchable")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_jobs_pdf)
    s = jobs.add_parser("original", help="원본 파일 다운로드(여러 장이면 zip)")
    s.add_argument("id")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_jobs_original)

    tpl = sub.add_parser("templates", help="양식 템플릿").add_subparsers(dest="sub", required=True)
    tpl.add_parser("list", help="템플릿 목록(필드 포함)").set_defaults(fn=cmd_tpl_list)
    for name, fn, help_ in (("get", cmd_tpl_get, "템플릿 하나 조회"),
                            ("delete", cmd_tpl_delete, "템플릿 삭제"),
                            ("autodetect", cmd_tpl_autodetect, "기준 이미지에서 필드 자동 감지(베타)")):
        s = tpl.add_parser(name, help=help_)
        s.add_argument("name")
        s.set_defaults(fn=fn)
    s = tpl.add_parser("create", help="기준 양식 파일로 템플릿 생성")
    s.add_argument("name")
    s.add_argument("--file", required=True, help="빈 양식 PDF/이미지")
    s.set_defaults(fn=cmd_tpl_create)
    s = tpl.add_parser("update", help="필드/규칙 갱신")
    s.add_argument("name")
    s.add_argument("--fields", help="fields 배열 JSON 파일 경로")
    s.add_argument("--rules", nargs="*", help="검증 규칙 식 목록")
    s.set_defaults(fn=cmd_tpl_update)
    s = tpl.add_parser("add-candidate", help="필드 후보목록에 값 추가")
    s.add_argument("name")
    s.add_argument("--field", required=True, help="필드 id")
    s.add_argument("--value", required=True)
    s.set_defaults(fn=cmd_tpl_candidate)

    mdl = sub.add_parser("models", help="인식 모델").add_subparsers(dest="sub", required=True)
    mdl.add_parser("list", help="모델 목록·상태").set_defaults(fn=cmd_models_list)
    for name, fn in (("download", cmd_models_download), ("select", cmd_models_select)):
        s = mdl.add_parser(name, help=f"모델 {name}")
        s.add_argument("id", help="모델 id (예: qwen3vl-8b)")
        s.set_defaults(fn=fn)

    s = sub.add_parser("export-merged", help="같은 양식의 완료 작업 전체를 한 표로")
    s.add_argument("--template", required=True)
    s.add_argument("--fmt", choices=("md", "txt", "csv"), default="csv")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_export_merged)
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    with httpx.Client(base_url=args.server, timeout=120) as c:
        args.fn(c, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

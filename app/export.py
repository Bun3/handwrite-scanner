"""인식 결과를 표 형태 텍스트로 내보내기 (md / txt / csv). 작업 단위 + 통합(머지)."""
import csv
import io


def merged(template: str, job_list: list[tuple[dict, list]], fmt: str
           ) -> tuple[str, str, str]:
    """같은 템플릿의 여러 작업을 하나로 병합. job_list: [(status, results)].

    각 문서(페이지)에 작업ID·처리일시를 붙여 한 목록으로 만든 뒤 기존 형식 재사용.
    """
    pages = []
    for st, res in job_list:
        for page in res or []:
            if (page.get("template") or st.get("template")) != template:
                continue  # 혼합 작업에서 다른 양식 페이지 제외
            fields = ([{"label": "작업ID", "value": st["id"]},
                       {"label": "처리일시", "value": st.get("created", "")}]
                      + page["fields"])
            pages.append({"fields": fields})
    content, _, mt = build(template, pages, fmt)
    return content, f"{template}-통합.{fmt}", mt


def build(job_id: str, res: list, fmt: str) -> tuple[str, str, str]:
    """반환: (내용, 파일명, media_type)"""
    pages = [[(f["label"], f.get("value", "")) for f in p["fields"]] for p in res]
    if fmt == "md":
        out = []
        for i, rows in enumerate(pages):
            out += [f"## {i + 1} 페이지", "", "| 필드 | 값 |", "|---|---|"]
            out += [f"| {l} | {v} |" for l, v in rows]
            out.append("")
        return "\n".join(out), f"{job_id}.md", "text/markdown; charset=utf-8"
    if fmt == "txt":
        out = []
        for i, rows in enumerate(pages):
            w = max((len(l) for l, _ in rows), default=0)
            out.append(f"[{i + 1} 페이지]")
            out += [f"{l.ljust(w)} | {v}" for l, v in rows]
            out.append("")
        return "\n".join(out), f"{job_id}.txt", "text/plain; charset=utf-8"
    # csv: 모든 페이지의 필드 구성이 같으면 페이지당 한 행(엑셀 집계용), 아니면 세로 형식
    buf = io.StringIO()
    w = csv.writer(buf)
    label_sets = [[l for l, _ in rows] for rows in pages]
    if label_sets and all(ls == label_sets[0] for ls in label_sets):
        w.writerow(["페이지"] + label_sets[0])
        for i, rows in enumerate(pages):
            w.writerow([i + 1] + [v for _, v in rows])
    else:
        w.writerow(["페이지", "필드", "값"])
        for i, rows in enumerate(pages):
            for l, v in rows:
                w.writerow([i + 1, l, v])
    # BOM: 엑셀이 한글 CSV를 UTF-8로 인식하게
    return "﻿" + buf.getvalue(), f"{job_id}.csv", "text/csv; charset=utf-8"

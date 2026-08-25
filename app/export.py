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
    """반환: (내용, 파일명, media_type).

    시트 형태 고정: 페이지당 한 행, 필드 라벨이 컬럼. 컬럼은 전 페이지 라벨의
    합집합(첫 등장 순)이라 필드 구성이 다른 페이지(건너뜀·자유 추출)는 공란으로 채운다.
    """
    labels: list[str] = []
    for p in res:
        for f in p["fields"]:
            if f["label"] not in labels:
                labels.append(f["label"])
    header = ["페이지"] + labels
    rows = [[str(i + 1)] + [dict((f["label"], f.get("value", "")) for f in p["fields"])
                            .get(l, "") for l in labels]
            for i, p in enumerate(res)]
    if fmt == "md":
        out = ["| " + " | ".join(header) + " |",
               "|" + "---|" * len(header)]
        out += ["| " + " | ".join(r) + " |" for r in rows]
        return "\n".join(out), f"{job_id}.md", "text/markdown; charset=utf-8"
    if fmt == "txt":
        widths = [max(len(header[c]), *(len(r[c]) for r in rows), 0) if rows
                  else len(header[c]) for c in range(len(header))]
        line = lambda r: " | ".join(v.ljust(widths[c]) for c, v in enumerate(r))
        return "\n".join([line(header)] + [line(r) for r in rows]), \
            f"{job_id}.txt", "text/plain; charset=utf-8"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    # BOM: 엑셀이 한글 CSV를 UTF-8로 인식하게
    return "﻿" + buf.getvalue(), f"{job_id}.csv", "text/csv; charset=utf-8"

"""PDF 3종 생성.

- searchable: 원본 이미지 + 필드 위치에 흐린 회색 텍스트(드래그·복사 가능)
- clean: 빈 양식(템플릿 기준 이미지) 위에 인식 텍스트를 활자로 조판
- text: "라벨: 값" 목록 재구성
"""
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app import jobs, templates_store
from app.config import JOBS_DIR

pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))


def generate(job_id: str, kind: str):
    out = JOBS_DIR / job_id / "output" / f"{kind}.pdf"
    res_file = JOBS_DIR / job_id / "results.json"
    if out.exists() and out.stat().st_mtime >= res_file.stat().st_mtime:
        return out  # 결과가 안 바뀌었으면 재생성하지 않음 (스트리밍 중 덮어쓰기 방지)
    tmp = out.with_name(out.name + ".tmp")
    res = jobs.results(job_id)
    {"searchable": _searchable, "clean": _clean, "text": _text}[kind](job_id, res, tmp)
    try:
        tmp.replace(out)
    except OSError:
        pass  # ponytail: 이전 파일을 아직 스트리밍 중이면 기존 파일 유지, 다음 요청 때 교체
    return out


def _fit_font(c, value, size, max_w):
    tw = pdfmetrics.stringWidth(value, "Malgun", size)
    if tw > max_w:  # 박스 폭 초과 시 축소 (검색·복사가 목적이라 크기보다 완전성)
        size = max(4, size * max_w / tw)
    c.setFont("Malgun", size)
    return size


def _page_canvas(c, img_path, out):
    w, h = Image.open(img_path).size
    pw, ph = 595, 595 * h / w  # A4 폭 기준 비율 유지
    if c is None:
        c = canvas.Canvas(str(out), pagesize=(pw, ph))
    else:
        c.setPageSize((pw, ph))
    c.drawImage(str(img_path), 0, 0, pw, ph)
    return c, pw, ph, pw / w


def _searchable(job_id: str, res: list, out) -> None:
    c = None
    for page in res:
        img_path = JOBS_DIR / job_id / f"page_{page['page']:03d}.png"
        c, pw, ph, scale = _page_canvas(c, img_path, out)
        c.setFillColorRGB(0.45, 0.45, 0.45)
        c.setFillAlpha(0.6)
        for f in page["fields"]:
            if not f.get("box") or not f.get("value"):
                continue
            x, y, bw, bh = f["box"]
            # 수기를 덜 가리도록 박스 하단에 작게
            size = _fit_font(c, f["value"], min(max(6, bh * scale * 0.4), 11),
                             bw * scale)
            c.drawString((x + 4) * scale, ph - (y + bh) * scale + 3, f["value"])
        c.setFillAlpha(1)
        c.showPage()
    c.save()


def _interior(dark, x, y, w, h):
    """필드 박스에서 표 테두리선을 피한 안쪽 영역을 찾는다.

    사용자가 그린 박스는 테두리선에 몇 px 걸치기 마련이라, 박스 가장자리
    20% 구간에서 픽셀 절반 이상이 어두운 행/열(=테두리선)을 감지해 그
    안쪽으로 물러난다.
    """
    sub = dark[y:y + h, x:x + w]
    def trim(ratio, n):
        zone = max(4, int(n * 0.2))
        lines = [i for i in range(zone) if ratio[i] > 0.5]
        lo = (max(lines) + 6) if lines else 6
        lines = [i for i in range(n - zone, n) if ratio[i] > 0.5]
        hi = (min(lines) - 6) if lines else n - 6
        return lo, max(hi, lo + 1)
    t, b = trim(sub.mean(axis=1), h)
    left, r = trim(sub.mean(axis=0), w)
    return x + left, y + t, r - left, b - t


def _clean(job_id: str, res: list, out) -> None:
    """빈 양식 배경 + 인식 텍스트 활자 조판. 템플릿 없는 작업은 text 형식으로 폴백."""
    import numpy as np
    st = jobs.status(job_id)
    ref = templates_store.reference_path(st["template"]) if st.get("template") else None
    if not (ref and ref.exists()):
        return _text(job_id, res, out)
    dark = np.array(Image.open(ref).convert("L")) < 128
    c = None
    for page in res:
        c, pw, ph, scale = _page_canvas(c, ref, out)
        for f in page["fields"]:
            if not f.get("box") or not f.get("value"):
                continue
            # 칸 안의 인쇄 골격(빈칸 안내문 등)을 테두리선은 피해서 흰색으로 덮고 조판
            x, y, bw, bh = _interior(dark, *f["box"])
            c.setFillColorRGB(1, 1, 1)
            c.rect(x * scale, ph - (y + bh) * scale,
                   bw * scale, bh * scale, stroke=0, fill=1)
            c.setFillColorRGB(0.05, 0.05, 0.2)
            size = _fit_font(c, f["value"], min(max(8, bh * scale * 0.5), 13),
                             (bw - 8) * scale)
            c.drawString((x + 4) * scale, ph - (y + bh / 2) * scale - size * 0.35,
                         f["value"])
        c.showPage()
    c.save()


def _text(job_id: str, res: list, out) -> None:
    c = canvas.Canvas(str(out), pagesize=A4)
    w, h = A4
    for page in res:
        y = h - 60
        c.setFont("Malgun", 11)
        for f in page["fields"]:
            c.drawString(50, y, f"{f['label']}: {f.get('value', '')}")
            y -= 20
            if y < 50:
                c.showPage()
                c.setFont("Malgun", 11)
                y = h - 60
        c.showPage()
    c.save()

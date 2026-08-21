"""PDF 2종 생성: searchable(원본+투명 텍스트층) / text(라벨: 값 재구성)."""
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app import jobs
from app.config import JOBS_DIR

pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))


def generate(job_id: str, kind: str):
    out = JOBS_DIR / job_id / "output" / f"{kind}.pdf"
    res = jobs.results(job_id)
    (_searchable if kind == "searchable" else _text)(job_id, res, out)
    return out


def _searchable(job_id: str, res: list, out) -> None:
    c = None
    for page in res:
        img_path = JOBS_DIR / job_id / f"page_{page['page']:03d}.png"
        w, h = Image.open(img_path).size
        pw, ph = 595, 595 * h / w  # A4 폭 기준 비율 유지
        scale = pw / w
        if c is None:
            c = canvas.Canvas(str(out), pagesize=(pw, ph))
        else:
            c.setPageSize((pw, ph))
        c.drawImage(str(img_path), 0, 0, pw, ph)
        for f in page["fields"]:
            if not f.get("box") or not f.get("value"):
                continue
            x, y, bw, bh = f["box"]
            size = max(6, bh * scale * 0.6)
            tw = pdfmetrics.stringWidth(f["value"], "Malgun", size)
            if tw > bw * scale:  # 박스 폭 초과 시 축소 (검색·복사가 목적이라 크기보다 완전성)
                size = max(4, size * bw * scale / tw)
            t = c.beginText(x * scale, ph - (y + bh * 0.8) * scale)
            t.setFont("Malgun", size)
            t.setTextRenderMode(3)  # invisible
            t.textLine(f["value"])
            c.drawText(t)
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

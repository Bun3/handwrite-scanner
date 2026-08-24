"""더미 테스트 픽스처 생성기 — 개인정보 없는 가상의 휴가신청서.

산출물: dummy-form.pdf(빈 양식), dummy-filled.png(작성본, 300dpi),
dummy-template.json(필드 좌표 — 코드로 계산하므로 정확).
실행: .venv/Scripts/python -X utf8 tests/fixtures/gen_dummy.py
"""
import json
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))

W, H = A4                       # 595 x 842 pt
TOP, RH = 180, 48               # 표 시작(위에서부터), 행 높이
LX, MX, RX = 60, 170, 535       # 표 좌우, 라벨/값 구분선
ROWS = ["성    명", "연 락 처", "잔여일수", "사    유", "승인종류"]
OPTS = ["지각", "조퇴", "결근", "병가", "반차", "월차", "경조사"]
OPT_X = [MX + 18 + i * 50 for i in range(len(OPTS))]
S = 300 / 72                    # pt → 300dpi px

VALUES = ["홍길동", "010-1234-5678", "5", "개인 사유", None]  # 승인종류는 동그라미


def make_form() -> None:
    c = canvas.Canvas(str(HERE / "dummy-form.pdf"), pagesize=A4)
    c.setFont("Malgun", 26)
    c.drawCentredString(W / 2, H - 90, "휴 가 신 청 서")
    c.setFont("Malgun", 12)
    for i, label in enumerate(ROWS):
        y = H - (TOP + i * RH)          # 행 상단 (pdf 좌표)
        c.rect(LX, y - RH, RX - LX, RH)
        c.line(MX, y, MX, y - RH)
        c.drawString(LX + 12, y - RH / 2 - 4, label)
    for x, opt in zip(OPT_X, OPTS):     # 승인종류 선택지 인쇄
        y = H - (TOP + 4 * RH)
        c.drawString(x, y - RH / 2 - 4, opt)
    c.setFont("Malgun", 16)
    c.drawCentredString(W / 2, 60, "테 스 트 기 관")
    c.save()


def make_filled() -> None:
    doc = pymupdf.open(HERE / "dummy-form.pdf")
    pix = doc[0].get_pixmap(dpi=300)
    pix.save(HERE / "dummy-filled.png")
    im = Image.open(HERE / "dummy-filled.png")
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 40)
    for i, v in enumerate(VALUES):
        if v is None:
            continue
        x = (MX + 25) * S
        y = (TOP + i * RH + RH / 2) * S - 20
        d.text((x, y), v, fill=(20, 20, 60), font=font)
    # 승인종류 '월차'에 동그라미
    ox = OPT_X[OPTS.index("월차")] * S
    oy = (TOP + 4 * RH + RH / 2) * S
    d.ellipse([ox - 18, oy - 40, ox + 130, oy + 40], outline=(20, 20, 60), width=6)
    im.save(HERE / "dummy-filled.png")


def make_template() -> None:
    def box(i):  # i번째 행의 값 영역 (300dpi px, 위 기준)
        return [int(MX * S), int((TOP + i * RH) * S),
                int((RX - MX) * S), int(RH * S)]
    fields = [
        {"id": "name", "label": "성명", "type": "candidates", "box": box(0),
         "candidates": ["홍길동", "김철수", "이영희", "박민수"]},
        {"id": "phone", "label": "연락처", "type": "phone", "box": box(1)},
        {"id": "days", "label": "잔여일수", "type": "number", "box": box(2),
         "min": 0, "max": 11},
        {"id": "reason", "label": "사유", "type": "text", "box": box(3)},
        {"id": "kind", "label": "승인종류", "type": "circle", "box": box(4),
         "candidates": OPTS},
    ]
    (HERE / "dummy-template.json").write_text(
        json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    make_form()
    make_filled()
    make_template()
    print("생성 완료:", *[p.name for p in HERE.glob("dummy-*")])

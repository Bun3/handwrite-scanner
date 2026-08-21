"""템플릿 저장소: data/templates/<이름>/template.json + reference.png"""
import io
import json

from PIL import Image

from app.config import TEMPLATES_DIR


def list_templates() -> list[dict]:
    out = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        f = d / "template.json"
        if f.exists():
            out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


def get(name: str) -> dict | None:
    f = TEMPLATES_DIR / name / "template.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def save(name: str, fields: list[dict]) -> dict:
    d = TEMPLATES_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    tpl = {"name": name, "reference": "reference.png", "fields": fields}
    (d / "template.json").write_text(
        json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8")
    return tpl


def set_reference(name: str, data: bytes, filename: str) -> None:
    """기준 이미지 등록. PDF면 1페이지를 300dpi로 렌더."""
    d = TEMPLATES_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    if filename.lower().endswith(".pdf"):
        import pymupdf
        doc = pymupdf.open(stream=data, filetype="pdf")
        pix = doc[0].get_pixmap(dpi=300)
        pix.save(d / "reference.png")
    else:
        Image.open(io.BytesIO(data)).convert("RGB").save(d / "reference.png")


def reference_path(name: str):
    return TEMPLATES_DIR / name / "reference.png"


def delete(name: str) -> None:
    import shutil
    shutil.rmtree(TEMPLATES_DIR / name, ignore_errors=True)

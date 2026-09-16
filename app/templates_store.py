"""템플릿 저장소: data/templates/<이름>/template.json + reference.png"""
import io
import json

from PIL import Image

from app.config import TEMPLATES_DIR
from app.errors import UserError


def list_templates() -> list[dict]:
    if not TEMPLATES_DIR.is_dir():
        raise UserError('templates_missing', '템플릿 폴더를 찾을 수 없습니다.', '설치 폴더의 data/templates를 백업에서 복원하거나 프로그램을 다시 실행하고 템플릿을 등록하세요.')
    out = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        f = d / "template.json"
        if f.exists():
            out.append(get(d.name))
    return out


def get(name: str) -> dict | None:
    f = TEMPLATES_DIR / name / "template.json"
    if not f.exists():
        return None
    try:
        tpl = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(tpl, dict) or tpl.get('name') != name or not isinstance(tpl.get('fields'), list):
            raise ValueError('invalid template structure')
        for field in tpl['fields']:
            if (not isinstance(field, dict) or not all(k in field for k in ('id', 'label', 'type', 'box'))
                    or not isinstance(field['box'], list) or len(field['box']) != 4
                    or not all(isinstance(n, (int, float)) for n in field['box'])
                    or field['box'][2] <= 0 or field['box'][3] <= 0):
                raise ValueError('invalid field definition')
        return tpl
    except (ValueError, UnicodeError) as exc:
        raise UserError('template_invalid', f"템플릿 설정이 손상되었습니다: {name}", '템플릿 화면에서 다시 등록하거나 data/templates의 해당 템플릿을 백업에서 복원하세요.') from exc


def save(name: str, fields: list[dict], rules: list[str] | None = None) -> dict:
    d = TEMPLATES_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    if rules is None:  # 미전달 시 기존 규칙 유지
        rules = (get(name) or {}).get("rules", [])
    tpl = {"name": name, "reference": "reference.png", "fields": fields,
           "rules": rules}
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
    path = TEMPLATES_DIR / name / "reference.png"
    if not path.is_file():
        raise UserError('reference_missing', f"템플릿의 기준 이미지가 없습니다: {name}", '템플릿 화면에서 같은 이름으로 기준 양식 파일을 다시 등록하거나 reference.png를 복원하세요.')
    try:
        with Image.open(path) as img:
            img.verify()
    except (ValueError, SyntaxError, Image.UnidentifiedImageError) as exc:
        raise UserError('reference_invalid', f'템플릿의 기준 이미지를 읽을 수 없습니다: {name}', '템플릿 화면에서 기준 양식 파일을 다시 등록하세요.') from exc
    return path


def add_candidate(name: str, field_id: str, value: str) -> bool:
    """검수에서 학습된 후보를 목록에 추가. 반환: 실제 추가 여부."""
    tpl = get(name)
    if not tpl or not value.strip():
        return False
    for f in tpl["fields"]:
        if f["id"] == field_id:
            cands = f.setdefault("candidates", [])
            if value not in cands:
                cands.append(value)
                save(name, tpl["fields"])
                return True
    return False


def delete(name: str) -> None:
    import shutil
    shutil.rmtree(TEMPLATES_DIR / name, ignore_errors=True)

"""불일치 필드 프롬프트/해상도 실험용 스크립트 (수동 실행)."""
import io
import sys

sys.path.insert(0, ".")
from app import llm, templates_store
from app.align import to_reference

data = open("tests/fixtures/vacation-filled.png", "rb").read()
aligned, _ = to_reference(data, templates_store.reference_path("휴가신청서"))
tpl = templates_store.get("휴가신청서")
F = {f["id"]: f for f in tpl["fields"]}


def crop(fid, pad=8, scale=1):
    x, y, w, h = F[fid]["box"]
    c = aligned.crop((x - pad, y - pad, x + w + pad, y + h + pad))
    if scale != 1:
        c = c.resize((int(c.width * scale), int(c.height * scale)))
    buf = io.BytesIO()
    c.save(buf, "PNG")
    return buf.getvalue()


def run(fid, prompt, scale=1, tag=""):
    out = llm.ask_image(crop(fid, scale=scale), prompt)
    print(f"[{fid} x{scale} {tag}] {out!r}", flush=True)


DIGIT_HINT = ("한국식 손글씨 특징에 주의하라: 7은 왼쪽에 짧은 세로 삐침을 먼저 긋는 "
              "경우가 많으니 삐침+7 을 17로 오인하지 마라. 9는 위가 동그란 고리 모양이라 "
              "7과 다르다. 8은 B처럼 보일 수 있다.")

if __name__ == "__main__":
    run("phone", "손으로 쓴 휴대전화 번호(010으로 시작하는 11자리)를 읽어라. "
        "먼저 각 숫자의 모양을 왼쪽부터 하나씩 한 줄로 분석하라. 특히 위쪽에 작은 "
        "고리(동그라미)가 있는 숫자는 9, 없으면 7이다. 분석 후 마지막 줄에 "
        "'답: 010-XXXX-XXXX' 형식으로만 출력하라.", 3, "cot")
    run("pre", "이 칸에 손으로 쓴 숫자를 읽어라. 먼저 획을 분석하라: 왼쪽의 짧은 "
        "삐침 획은 별개의 숫자 1이 아니라 다음 숫자의 시작 획(장식)일 수 있다. "
        "삐침이 오른쪽 숫자와 크기가 다르고 짧다면 무시하라. "
        "분석 후 마지막 줄에 '답: N' 형식으로만 출력하라.", 3, "cot")

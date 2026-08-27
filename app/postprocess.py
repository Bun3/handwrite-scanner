"""인식 결과 후처리: 후보 매칭·형식 검증·신뢰도. LLM 환각 방어선."""
import re
from difflib import SequenceMatcher

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _jamo(text: str) -> str:
    """한글 음절을 자모로 분해 — 획 하나 차이(찬/천)를 부분 일치로 취급하기 위함."""
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out.append(_CHO[code // 588])
            out.append(_JUNG[code % 588 // 28])
            if code % 28:
                out.append(_JONG[code % 28])
        else:
            out.append(ch)
    return "".join(out)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _jamo(normalize_ws(a)), _jamo(normalize_ws(b))).ratio()


def match_candidate(text: str, candidates: list[str]) -> tuple[str, float]:
    """후보 목록에서 최근접 선택. 반환: (후보, 신뢰도=유사도)."""
    t = normalize_ws(text)
    if not t or t == "없음":  # 빈칸 응답을 후보로 강제 매칭하면 오답이 그럴듯해짐
        return "", 0.3
    if not candidates:
        return t, 0.5
    best = max(candidates, key=lambda c: similarity(t, c))
    return best, similarity(t, best)


_DIGIT_FIX = str.maketrans("OoIlZzSsBg", "0011225589")


def validate(text: str, field_type: str) -> tuple[str, float]:
    """타입별 정규화. 반환: (정규화 값, 신뢰도)."""
    t = normalize_ws(text)
    if not t or t == "없음":  # 빈칸 — 값 비우고 검수 강조
        return "", 0.3
    if field_type == "phone":
        digits = re.sub(r"\D", "", t.translate(_DIGIT_FIX))
        if len(digits) == 11 and digits.startswith("01"):
            return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}", 0.9
        if len(digits) == 10 and digits.startswith("0"):
            return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}", 0.8
        return t, 0.3
    if field_type == "number":
        digits = re.sub(r"\D", "", t.translate(_DIGIT_FIX))
        return (digits, 0.9) if digits else (t, 0.3)
    if field_type == "time":
        # "9" / "09:00" / "9.30" / "18시" 등 → 정시는 시(정수)만, 아니면 H:MM.
        # 정시를 정수로 두는 이유: 규칙 엔진(정수 산술)이 그대로 동작한다.
        m = re.search(r"(\d{1,2})\s*[:.시]?\s*(\d{2})?", t.translate(_DIGIT_FIX))
        if m:
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            if hour <= 24 and minute < 60:
                return (str(hour), 0.9) if minute == 0 else (f"{hour}:{minute:02d}", 0.9)
        return t, 0.3
    return t, 0.7  # text 등: 형식 검증 없음


def clamp_number(value: str, conf: float, lo: int, hi: int) -> tuple[str, float]:
    """범위 제약 검증. 범위 밖 + 선행 1 은 한글 손글씨 7의 삐침 오인으로 보정.

    ponytail: 삐침 보정은 선행 1 제거뿐인 단순 휴리스틱 — 오독 유형이 늘면
    이지선다 재질문으로 확장.
    """
    if not value.isdigit():
        return value, conf
    n = int(value)
    if lo <= n <= hi:
        return value, conf
    if len(value) > 1 and value[0] == "1" and lo <= int(value[1:]) <= hi:
        return value[1:], 0.55  # 검수 강조선(0.7) 아래로
    return value, 0.3

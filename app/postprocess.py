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
    if not candidates:
        return text, 0.5
    best = max(candidates, key=lambda c: similarity(text, c))
    return best, similarity(text, best)


_DIGIT_FIX = str.maketrans("OoIlZzSsBg", "0011225589")


def validate(text: str, field_type: str) -> tuple[str, float]:
    """타입별 정규화. 반환: (정규화 값, 신뢰도)."""
    t = normalize_ws(text)
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
    return t, 0.7  # text 등: 형식 검증 없음

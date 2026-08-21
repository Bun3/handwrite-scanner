from app.postprocess import match_candidate, normalize_ws, similarity, validate


def test_normalize_ws():
    assert normalize_ws("  개인   사유\n") == "개인 사유"
    assert normalize_ws("2026년 8월  21일") == "2026년 8월 21일"


def test_match_candidate_exact():
    best, conf = match_candidate("홍길동", ["홍길동", "김영수", "이민호"])
    assert best == "홍길동"
    assert conf == 1.0


def test_match_candidate_misread():
    # 오인식 "홍길둥" → 자모 단위로 가장 가까운 "홍길동" 선택
    best, conf = match_candidate("홍길둥", ["홍길동", "김영수", "이민호"])
    assert best == "홍길동"
    assert conf > 0.7


def test_similarity_jamo():
    assert similarity("홍길동", "홍길둥") > similarity("홍길동", "김영수")


def test_validate_phone():
    assert validate("010ㅡ1234 5678", "phone")[0] == "010-1234-5678"
    assert validate("010-1234-5678", "phone")[0] == "010-1234-5678"
    assert validate("OIO-1234-5678", "phone")[0] == "010-1234-5678"


def test_validate_number():
    assert validate(" 7 ", "number")[0] == "7"
    assert validate("6일", "number")[0] == "6"


def test_validate_text_passthrough():
    assert validate("개인  사유", "text")[0] == "개인 사유"

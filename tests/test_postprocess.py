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


def test_export_formats():
    from app.export import build
    res = [{"fields": [{"label": "성명", "value": "홍길동"},
                       {"label": "사유", "value": "개인 사유"}]},
           {"fields": [{"label": "성명", "value": "김영수"},
                       {"label": "사유", "value": "병가"}]}]
    md = build("j1", res, "md")[0]
    assert "| 성명 | 홍길동 |" in md and "## 2 페이지" in md
    txt = build("j1", res, "txt")[0]
    assert "성명 | 홍길동" in txt
    csv_out = build("j1", res, "csv")[0]
    assert "페이지,성명,사유" in csv_out          # 구성 동일 → 페이지당 한 행
    assert "2,김영수,병가" in csv_out
    res[1]["fields"].append({"label": "비고", "value": "x"})
    assert "페이지,필드,값" in build("j1", res, "csv")[0]  # 구성 다름 → 세로 형식


def test_clamp_number():
    from app.postprocess import clamp_number
    assert clamp_number("7", 0.9, 0, 11) == ("7", 0.9)          # 범위 내 유지
    v, c = clamp_number("17", 0.9, 0, 11)                        # 삐침 보정
    assert v == "7" and c < 0.7
    assert clamp_number("25", 0.9, 0, 11)[1] == 0.3              # 보정 불가
    assert clamp_number("abc", 0.9, 0, 11) == ("abc", 0.9)       # 숫자 아님

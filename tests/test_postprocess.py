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


def test_version_compare():
    from app.main import _ver
    assert _ver("v0.2.0") > _ver("0.1.0")
    assert _ver("0.10.0") > _ver("0.9.9")
    assert not _ver("v0.1.0") > _ver("0.1.0")


def test_empty_answer_not_forced():
    """모델이 '없음'(빈칸)이라 답하면 후보로 강제 매칭하지 않고 빈 값 + 검수 강조."""
    from app.postprocess import match_candidate, validate
    assert match_candidate("없음", ["이경근", "이순덕"]) == ("", 0.3)
    assert match_candidate("  ", ["이경근"]) == ("", 0.3)
    assert validate("없음", "text") == ("", 0.3)
    assert validate("없음", "phone") == ("", 0.3)


def test_optional_field_empty_is_calm():
    """'비어있어도 정상' 필드는 빈 값이 빨간색(0.3)이 아니라 0.9."""
    from app.worker import _post
    assert _post("없음", {"type": "number", "optional": True}) == ("", 0.9)
    assert _post("없음", {"type": "number"}) == ("", 0.3)
    assert _post("5", {"type": "number", "optional": True}) == ("5", 0.9)  # 값 있으면 평소대로


def test_export_formats():
    from app.export import build
    res = [{"fields": [{"label": "성명", "value": "홍길동"},
                       {"label": "사유", "value": "개인 사유"}]},
           {"fields": [{"label": "성명", "value": "김영수"},
                       {"label": "사유", "value": "병가"}]}]
    md = build("j1", res, "md")[0]
    assert "| 페이지 | 성명 | 사유 |" in md and "| 1 | 홍길동 | 개인 사유 |" in md
    txt = build("j1", res, "txt")[0]
    assert txt.splitlines()[0].split(" | ")[1].strip() == "성명"
    csv_out = build("j1", res, "csv")[0]
    assert "페이지,성명,사유" in csv_out          # 페이지당 한 행, 라벨이 컬럼
    assert "2,김영수,병가" in csv_out
    # 구성이 달라도(건너뜀·자유 추출) 세로로 안 떨어지고 합집합 컬럼 + 공란
    res[1]["fields"].append({"label": "비고", "value": "x"})
    res.append({"fields": []})                    # 건너뛴 페이지
    csv_out = build("j1", res, "csv")[0]
    assert "페이지,성명,사유,비고" in csv_out
    assert "1,홍길동,개인 사유," in csv_out
    assert "3,,," in csv_out


def test_export_merged():
    from app.export import merged
    j1 = ({"id": "job1", "created": "2026-08-25", "template": "휴가"},
          [{"template": "휴가", "fields": [{"label": "성명", "value": "홍길동"}]}])
    j2 = ({"id": "job2", "created": "2026-08-26", "template": None},
          [{"template": "휴가", "fields": [{"label": "성명", "value": "김철수"}]},
           {"template": "다른양식", "fields": [{"label": "성명", "value": "제외대상"}]}])
    csv_out, fname, _ = merged("휴가", [j1, j2], "csv")
    assert "페이지,작업ID,처리일시,성명" in csv_out
    assert "1,job1,2026-08-25,홍길동" in csv_out
    assert "2,job2,2026-08-26,김철수" in csv_out
    assert "제외대상" not in csv_out          # 다른 양식 페이지 제외
    assert fname == "휴가-통합.csv"


def test_clamp_number():
    from app.postprocess import clamp_number
    assert clamp_number("7", 0.9, 0, 11) == ("7", 0.9)          # 범위 내 유지
    v, c = clamp_number("17", 0.9, 0, 11)                        # 삐침 보정
    assert v == "7" and c < 0.7
    assert clamp_number("25", 0.9, 0, 11)[1] == 0.3              # 보정 불가
    assert clamp_number("abc", 0.9, 0, 11) == ("abc", 0.9)       # 숫자 아님

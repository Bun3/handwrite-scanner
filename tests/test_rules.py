import pytest

from app.rules import check, evaluate, parse_assign, rule_ids, validate_expr


def test_check_pass_fail():
    assert check("pre - post >= 0", {"pre": "7", "post": "6"}) is True
    assert check("pre - post >= 0", {"pre": "5", "post": "6"}) is False
    assert check("days == pre - post", {"days": "1", "pre": "7", "post": "6"}) is True


def test_check_non_numeric_is_indeterminate():
    assert check("pre - post >= 0", {"pre": "칠", "post": "6"}) is None
    assert check("pre >= 0", {}) is None


def test_rule_ids():
    assert rule_ids("days == pre - post") == {"days", "pre", "post"}


def test_validate_expr():
    assert validate_expr("pre - post >= 0") is None
    assert validate_expr("__import__('os')") is not None   # 함수 호출 금지
    assert validate_expr("pre ** 99999") is not None        # 지수 미허용
    assert validate_expr("pre >") is not None               # 문법 오류


def test_no_eval_escape():
    with pytest.raises((SyntaxError, ValueError)):
        check("(lambda: 1)()", {})


def test_resolve_labels():
    from app.rules import resolve
    ids = {"총 시간": "f1", "시작시간": "f2", "종료시간": "f3", "시작": "f4"}
    assert resolve("총 시간 = 종료시간 - 시작시간", ids) == "f1 = f3 - f2"
    assert resolve("시작 >= 0", ids) == "f4 >= 0"       # 긴 라벨 우선 치환
    assert resolve("f9 >= 0", ids) == "f9 >= 0"          # id 직접 사용도 유지


def test_apply_rules_label_syntax():
    from app.worker import _apply_rules
    tpl = {"fields": [{"id": "a1", "label": "시작"}, {"id": "b2", "label": "종료"}],
           "rules": ["종료 >= 시작"]}
    f = [{"id": "a1", "label": "시작", "value": "5", "confidence": 0.9},
         {"id": "b2", "label": "종료", "value": "3", "confidence": 0.9}]
    w = _apply_rules(tpl, f)
    assert any("검증 실패" in x for x in w)
    assert f[0]["confidence"] == 0.5 and f[1]["confidence"] == 0.5


def test_assign_rule():
    assert parse_assign("total = end - start") == ("total", "end - start")
    assert parse_assign("end - start >= 0") is None
    assert rule_ids("total = end - start") == {"total", "end", "start"}
    assert validate_expr("total = end - start") is None
    assert validate_expr("total = end **") is not None
    assert evaluate("end - start", {"end": "18", "start": "15"}) == 3
    assert evaluate("end - start", {"end": "", "start": "15"}) is None


def test_apply_rules_infer_and_check():
    from app.worker import _apply_rules
    tpl = {"fields": [{"id": "s", "min": 9, "max": 18}, {"id": "e"},
                      {"id": "t", "min": 1, "max": 8}],
           "rules": ["t = e - s", "e >= s"]}

    def mk(s, e, t):
        return [{"id": "s", "label": "시작", "value": s, "confidence": 0.9},
                {"id": "e", "label": "종료", "value": e, "confidence": 0.9},
                {"id": "t", "label": "총시간", "value": t, "confidence": 0.3}]

    f = mk("15", "18", "")                      # 빈 값 → 유추
    w = _apply_rules(tpl, f)
    assert f[2]["value"] == "3" and f[2]["confidence"] == 0.75
    assert any("유추" in x for x in w)

    f = mk("9", "18", "")                       # 유추값 9 > max 8 → 채우지 않음
    assert _apply_rules(tpl, f) == [] and f[2]["value"] == ""

    f = mk("15", "18", "5")                     # 값 있음 + 등식 위반 → 검증 실패
    f[2]["confidence"] = 0.9
    w = _apply_rules(tpl, f)
    assert any("검증 실패" in x for x in w) and f[2]["confidence"] == 0.5

    f = mk("15", "", "")                        # 우변 미완성 → 조용히 통과 (하나만 유효 허용)
    assert _apply_rules(tpl, f) == []

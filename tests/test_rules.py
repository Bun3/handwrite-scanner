import pytest

from app.rules import check, rule_ids, validate_expr


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

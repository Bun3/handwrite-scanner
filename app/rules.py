"""템플릿 교차 필드 검증 규칙. 예: "pre - post >= 0", "days == pre - post"

필드 id를 변수로 쓰는 정수 산술·비교식만 허용 (ast 화이트리스트, eval 금지).
값이 정수로 해석되지 않는 필드가 규칙에 쓰이면 그 규칙은 판단 불가로 통과 처리.

유추 규칙: "fid = 식" 형태. 대상 필드가 비어 있으면 식의 값으로 채우고,
값이 있으면 등식 검증으로 동작한다 (워커에서 처리).
"""
import ast
import operator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
        ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}


def _eval(node, vars_):
    if isinstance(node, ast.Expression):
        return _eval(node.body, vars_)
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in vars_:
            raise ValueError(f"알 수 없는 필드 id: {node.id}")
        return vars_[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, vars_)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left, vars_), _eval(node.right, vars_))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 \
            and type(node.ops[0]) in _CMP:
        return _CMP[type(node.ops[0])](_eval(node.left, vars_),
                                       _eval(node.comparators[0], vars_))
    raise ValueError(f"허용되지 않는 식: {ast.dump(node)[:60]}")


def parse_assign(expr: str) -> tuple[str, str] | None:
    """'fid = 식' 형태면 (대상 fid, 우변 식 문자열) 반환, 아니면 None."""
    try:
        tree = ast.parse(expr, mode="exec")
    except SyntaxError:
        return None
    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Assign) \
            and len(tree.body[0].targets) == 1 \
            and isinstance(tree.body[0].targets[0], ast.Name):
        return tree.body[0].targets[0].id, ast.unparse(tree.body[0].value)
    return None


def rule_ids(expr: str) -> set[str]:
    a = parse_assign(expr)
    src = f"{a[0]} == ({a[1]})" if a else expr
    return {n.id for n in ast.walk(ast.parse(src, mode="eval"))
            if isinstance(n, ast.Name)}


def _int_vars(expr: str, values: dict[str, str]) -> dict[str, int] | None:
    vars_ = {}
    for fid in {n.id for n in ast.walk(ast.parse(expr, mode="eval"))
                if isinstance(n, ast.Name)}:
        v = str(values.get(fid, "")).strip()
        if not v.lstrip("-").isdigit():
            return None
        vars_[fid] = int(v)
    return vars_


def check(expr: str, values: dict[str, str]) -> bool | None:
    """규칙 평가. 반환: True(통과)/False(위반)/None(판단 불가 — 값이 정수 아님)."""
    vars_ = _int_vars(expr, values)
    if vars_ is None:
        return None
    return bool(_eval(ast.parse(expr, mode="eval"), vars_))


def evaluate(expr: str, values: dict[str, str]) -> int | None:
    """산술식 값 계산. 쓰인 필드가 정수가 아니면 None."""
    vars_ = _int_vars(expr, values)
    if vars_ is None:
        return None
    v = _eval(ast.parse(expr, mode="eval"), vars_)
    return int(v) if isinstance(v, int) and not isinstance(v, bool) else None


def validate_expr(expr: str) -> str | None:
    """편집기 저장용 문법 검사. 반환: 오류 메시지 또는 None."""
    a = parse_assign(expr)
    src = f"{a[0]} == ({a[1]})" if a else expr
    try:
        _eval(ast.parse(src, mode="eval"),
              {fid: 1 for fid in rule_ids(expr)})
        return None
    except (SyntaxError, ValueError) as e:
        return str(e)

"""条件分支表达式求值（对齐 TPC condition_value.py / graph_utils.eval_condition）。

表达式为结构化 dict，禁止 eval：
    {"field": "amount", "op": "gte", "value": 100000}
    field 支持点路径（a.b）与 form./org. 前缀；op ∈ eq/ne/gt/gte/lt/lte/in/contains。
"""

from __future__ import annotations

import operator
from typing import Any


def _is_numeric_string(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _money_scalar(val: dict) -> float | None:
    for key in ("rmb_amount", "amount"):
        raw = val.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def normalize_scalar(val: Any) -> Any:
    """将变量值/条件期望值统一为可比较标量（移植 TPC normalize_condition_scalar）。"""
    if val is None or val == "":
        return val
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, dict):
        if "amount" in val or "rmb_amount" in val or "currency" in val:
            return _money_scalar(val)
        return val
    if isinstance(val, list):
        return [normalize_scalar(x) for x in val]
    if isinstance(val, str):
        s = val.strip()
        if s.lower() == "true":
            return True
        if s.lower() == "false":
            return False
        if s != "" and _is_numeric_string(s):
            try:
                return float(s) if "." in s else int(s)
            except ValueError:
                pass
        return s
    return val


def values_equal(actual: Any, expected: Any) -> bool:
    a = normalize_scalar(actual)
    b = normalize_scalar(expected)
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) is bool(b)
    return a == b


_OPS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


def get_var(variables: dict, field: str) -> Any:
    """变量取值：先顶层，再 form.* / org.* 前缀，最后点路径逐层下钻。"""
    if not field:
        return None
    if field in variables:
        return variables[field]
    form = variables.get("form") if isinstance(variables.get("form"), dict) else {}
    if field in form:
        return form[field]
    if field.startswith("form."):
        return form.get(field[5:])
    if field.startswith("org."):
        org = variables.get("org") or {}
        return org.get(field[4:])
    parts = field.split(".")
    cur: Any = variables
    for p in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    if cur is not None:
        return cur
    return form.get(field)


def eval_condition(expr: Any, variables: dict) -> bool:
    """求值分支表达式；空/default 视为命中。结构化 dict，绝不 eval 字符串。"""
    if expr is None or expr == "" or expr is True or expr == "default":
        return True
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, str):
        s = expr.strip()
        if s in ("default", "true"):
            return True
        if s == "false":
            return False
        return False  # 不解析自由文本表达式，防注入
    if isinstance(expr, dict):
        if expr.get("default"):
            return True
        field = expr.get("field") or expr.get("key")
        op = expr.get("op", "eq")
        expected = normalize_scalar(expr.get("value"))
        if not field:
            return False
        actual = normalize_scalar(get_var(variables, field))
        if op in ("gt", "gte", "lt", "lte"):
            try:
                return bool(_OPS[op](float(actual), float(expected)))
            except (TypeError, ValueError):
                return False
        if op == "eq":
            return values_equal(actual, expected)
        if op == "ne":
            return not values_equal(actual, expected)
        if op == "in":
            options = expected if isinstance(expected, list) else [expected]
            return any(values_equal(actual, o) for o in options)
        if op == "contains":
            if isinstance(actual, list):
                return any(values_equal(x, expected) for x in actual)
            if isinstance(actual, str) and isinstance(expected, str):
                return expected in actual
            return False
        return False
    return bool(expr)

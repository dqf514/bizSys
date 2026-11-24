"""条件分支表达式求值（审批引擎 + OA 表单条件共用）。

表达式为结构化 AST，禁止 eval：

单条规则::

    {"field": "amount", "op": "gte", "value": 100000}

条件组（rules 非空即视为组，logic ∈ and/or，可嵌套）::

    {"logic": "and", "rules": [
        {"field": "amount", "op": "between", "value": [1000, 10000]},
        {"field": "dept", "op": "in", "value": ["财务部", "总经办"]},
    ]}

field 支持点路径（a.b）与 form./org. 前缀；
op ∈ eq/ne/gt/gte/lt/lte/in/contains/between/empty/not_empty。

**E1（企业微信移植）新增**：条件组（多规则 and/or）、数值区间 between、空/非空判定。
企业微信原始 op 编码（op1..op6）的推定映射见 `app/seeds/wecom_templates.py::OP_MAP`。
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
        if "hours" in val:  # E1：假勤原子（时长小时数）
            try:
                return float(val["hours"])
            except (TypeError, ValueError):
                return val
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
            except (TypeError, ValueError):
                pass
        return s
    return val


def values_equal(actual: Any, expected: Any) -> bool:
    a = normalize_scalar(actual)
    b = normalize_scalar(expected)
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) is bool(b)
    return a == b


def is_empty_value(val: Any) -> bool:
    """空值判定：None / 空串 / 空集合。"""
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() == ""
    if isinstance(val, (list, tuple, dict, set)):
        return len(val) == 0
    return False


_OPS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


def _to_float(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _between(actual: Any, expected: Any) -> bool:
    """区间判定（闭区间）：expected 为 [lo, hi] / (lo, hi) / {"min":..,"max":..}。"""
    lo = hi = None
    if isinstance(expected, dict):
        lo = expected.get("min", expected.get("lo"))
        hi = expected.get("max", expected.get("hi"))
    elif isinstance(expected, (list, tuple)) and len(expected) == 2:
        lo, hi = expected[0], expected[1]
    if lo is None and hi is None:
        return False
    a = _to_float(actual)
    if a is None:
        return False
    if lo is not None:
        b = _to_float(lo)
        if b is None or a < b:
            return False
    if hi is not None:
        b = _to_float(hi)
        if b is None or a > b:
            return False
    return True


def eval_rule_value(op: str, actual: Any, expected: Any, *, list_eq_contains: bool = False) -> bool:
    """单条规则的标量求值（引擎与 OA 表单条件共用同一套 op 语义）。

    - ``list_eq_contains``：实际值是数组时，``eq`` 是否按「包含任一」判定。
      引擎（流程分支）用 False（严格相等）；OA 表单条件用 True（多选控件勾选语义）。
    """
    op = op or "eq"
    a = normalize_scalar(actual)
    e = normalize_scalar(expected)
    if op == "empty":
        return is_empty_value(a)
    if op == "not_empty":
        return not is_empty_value(a)
    if op == "between":
        return _between(a, e)
    if isinstance(a, list):
        if op == "eq":
            return any(values_equal(x, e) for x in a) if list_eq_contains else values_equal(a, e)
        if op == "ne":
            return (not any(values_equal(x, e) for x in a)) if list_eq_contains else (not values_equal(a, e))
        if op == "in":
            options = e if isinstance(e, list) else [e]
            return any(any(values_equal(x, o) for o in options) for x in a)
        if op == "contains":
            return any(values_equal(x, e) for x in a)
        return False
    if op in ("gt", "gte", "lt", "lte"):
        fa, fe = _to_float(a), _to_float(e)
        if fa is None or fe is None:
            return False
        return bool(_OPS[op](fa, fe))
    if op == "eq":
        return values_equal(a, e)
    if op == "ne":
        return not values_equal(a, e)
    if op == "in":
        options = e if isinstance(e, list) else [e]
        return any(values_equal(a, o) for o in options)
    if op == "contains":
        if isinstance(a, str) and isinstance(e, str):
            return e in a
        return False
    return False


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
    """求值分支表达式；空/default 视为命中。结构化 dict，绝不 eval 字符串。

    支持**条件组**：``{"logic": "and"|"or", "rules": [子表达式...]}``（可嵌套）。
    """
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
    if isinstance(expr, list):
        # 规则数组按「全部满足」处理（与旧版单规则语义兼容）
        return all(eval_condition(e, variables) for e in expr)
    if isinstance(expr, dict):
        if expr.get("default"):
            return True
        rules = expr.get("rules")
        if isinstance(rules, list):
            logic = str(expr.get("logic") or "and").lower()
            if not rules:
                return True
            results = [eval_condition(r, variables) for r in rules]
            return all(results) if logic != "or" else any(results)
        field = expr.get("field") or expr.get("key")
        op = expr.get("op", "eq")
        expected = expr.get("value")
        if not field:
            return False
        actual = get_var(variables, field)
        return eval_rule_value(op, actual, expected)
    return bool(expr)

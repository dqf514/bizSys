"""OA 服务：表单校验 / 发起（接 F1 审批引擎，未绑定直通）/ 统计 / 异常干预 / 流程事件回写。"""

import ast
import json
import re
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common import recycle
from app.common.events import ApprovalCompleted, ApprovalRejected, ApprovalWithdrawn, subscribe
from app.common.pagination import PageParams, page_result
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.admin.models import Dept, UserDept
from app.modules.approval import engine
from app.modules.approval import service as approval_svc
from app.modules.approval.condition import eval_rule_value
from app.modules.approval.graph import parse_json
from app.modules.approval.models import (
    ApprovalCc,
    ApprovalDefinition,
    ApprovalInstance,
    ApprovalNode,
    ApprovalRecord,
    ApprovalTask,
)
from app.modules.auth.models import User
from app.modules.contract.models import Contract
from app.modules.crm.models import Customer
from app.modules.oa.models import OaForm, OaInstance
from app.modules.oa.schemas import (
    ATTENDANCE_REF_TYPES,
    EXPOSABLE_TYPES,
    HR_REF_TYPES,
    LAYOUT_TYPES,
    OPTION_TYPES,
    ConditionGroup,
    FormFieldIn,
)
from app.modules.report.models import Report
from app.modules.task.models import Task
from app.services.numbering import next_no

# ---------------- 公式表达式（E1：企业微信 Formula 控件） ----------------

# 企业微信公式写法形如「Money-a + Money-b」：控件类型前缀 + 控件标识
_FORMULA_PREFIX_RE = re.compile(r"\b(?:Money|Number|money|number)-")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
# E1：聚合函数 SUM(表key.列key) / HOURS(字段key) —— 移植自企微公式控件
_SUM_CALL_RE = re.compile(r"\bSUM\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
_HOURS_CALL_RE = re.compile(r"\bHOURS\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
_AGG_TOKEN_RE = re.compile(r"^__agg\d+__$")


def _formula_refs(expr: str) -> list[str]:
    """提取公式引用的控件标识（去重，保持出现顺序）。"""
    src = _FORMULA_PREFIX_RE.sub("", expr or "")
    src = _SUM_CALL_RE.sub(" ", src)
    src = _HOURS_CALL_RE.sub(" ", src)
    refs: list[str] = []
    for m in _IDENT_RE.finditer(src):
        name = m.group(0)
        if name not in refs:
            refs.append(name)
    return refs


def _hours_of(value) -> float | None:
    """假勤时长（小时）归一：数值 / {"hours":n} / 起止日期对。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if "hours" in value:
            try:
                return float(value["hours"])
            except (TypeError, ValueError):
                return None
        start, end = value.get("start"), value.get("end")
        if start and end:
            return _hours_between(start, end)
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return _hours_between(value[0], value[1])
    return None


def _hours_between(start, end) -> float | None:
    """起止时间差（小时）；按天对齐时按自然日 ×24。"""
    s = _parse_datetime(start)
    e = _parse_datetime(end)
    if s is None or e is None:
        return None
    delta = (e - s).total_seconds() / 3600.0
    if delta < 0:
        return None
    return delta


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None
    raw = value.strip().replace("/", "-")
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _sum_of_column(data: dict, table_key: str, col_key: str) -> float | None:
    """明细表某列求和（无表 / 无列 → None）。"""
    rows = data.get(table_key)
    if not isinstance(rows, list):
        return None
    total = 0.0
    found = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        cell = row.get(col_key)
        if isinstance(cell, bool) or cell is None or cell == "":
            continue
        try:
            total += float(cell)
        except (TypeError, ValueError):
            return None
        found = True
    return total if found else 0.0


def _extract_aggregates(expr: str) -> tuple[str, list[tuple[str, str]]]:
    """把 SUM(...)/HOURS(...) 抽成占位符，返回 (剩余表达式, [(kind, arg)])。"""
    calls: list[tuple[str, str]] = []

    def _sum_sub(m: re.Match) -> str:
        calls.append(("sum", f"{m.group(1)}.{m.group(2)}"))
        return f"__agg{len(calls) - 1}__"

    def _hours_sub(m: re.Match) -> str:
        calls.append(("hours", m.group(1)))
        return f"__agg{len(calls) - 1}__"

    src = _SUM_CALL_RE.sub(_sum_sub, expr)
    src = _HOURS_CALL_RE.sub(_hours_sub, src)
    return src, calls


def _eval_formula(expr: str, data: dict) -> float | None:
    """受限公式求值：只允许 ``+ - * /``、数字、字段引用与 SUM()/HOURS() 聚合；不可求值返回 None。"""
    src = _FORMULA_PREFIX_RE.sub("", expr or "").strip()
    if not src:
        return None
    src = src.replace("×", "*").replace("÷", "/").replace("－", "-").replace("＋", "+")

    src, calls = _extract_aggregates(src)
    agg_values: list[float] = []
    for kind, arg in calls:
        if kind == "sum":
            table_key, _, col_key = arg.partition(".")
            value = _sum_of_column(data, table_key, col_key)
        else:
            value = _hours_of(data.get(arg))
        if value is None:
            return None
        agg_values.append(value)

    def _repl(m: re.Match) -> str:
        name = m.group(0)
        if _AGG_TOKEN_RE.match(name):
            return name
        return f"_v({name!r})" if name in data else name

    src = _IDENT_RE.sub(_repl, src)
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        return None
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.USub,
        ast.UAdd,
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id == "_v"):
                return None
            if node.keywords or len(node.args) != 1:
                return None
            continue
        if not isinstance(node, allowed):
            return None

    def _v(key: str) -> float:
        val = data.get(key)
        if isinstance(val, bool):
            return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    env: dict = {"_v": _v, "__builtins__": {}}
    for idx, value in enumerate(agg_values):
        env[f"__agg{idx}__"] = value
    try:
        return float(eval(compile(tree, "<formula>", "eval"), env))
    except Exception:
        return None


def _compute_formulas(fields: list[FormFieldIn], data: dict) -> None:
    """提交前用服务端计算结果覆盖公式字段（前端算的值不作数）。"""
    for f in fields:
        if f.type != "formula" or not f.key or not f.formula.strip():
            continue
        value = _eval_formula(f.formula, data)
        if value is not None:
            data[f.key] = value


# ---------------- 表单 schema / 数据校验 ----------------


def validate_fields(fields: list[FormFieldIn]) -> None:
    """发布前校验字段定义（非法 → 62002）。"""
    errors: list[str] = []
    keys: set[str] = set()
    known_keys = {f.key for f in fields if f.key}
    for f in fields:
        label = f.label or f.key
        if f.type in LAYOUT_TYPES:
            continue  # 布局控件不占数据位
        if f.key in keys:
            errors.append(f"字段 key 重复：{f.key}")
        keys.add(f.key)
        if f.type in OPTION_TYPES and f.options_source == "manual" and not f.options and not f.cascade:
            errors.append(f"字段「{label}」需要配置选项")
        if f.type in OPTION_TYPES and f.options_source == "dict" and not f.dict_type:
            errors.append(f"字段「{label}」使用字典数据源但未配置字典类型")
        if f.expose_variable and f.type not in EXPOSABLE_TYPES:
            errors.append(f"字段「{label}」类型 {f.type} 不能作为流程变量")
        if f.cascade:
            parent = (f.cascade.get("parent") or "") if isinstance(f.cascade, dict) else ""
            if parent not in known_keys:
                errors.append(f"字段「{label}」级联父控件不存在：{parent or '未配置'}")
        if f.type == "resource":
            if not f.resource:
                errors.append(f"字段「{label}」未配置资源类型")
            for m in f.mappings:
                if m.to not in known_keys or m.to == f.key:
                    errors.append(f"字段「{label}」带出目标控件不存在：{m.to}")
        # ---- E1 新控件校验 ----
        if f.type == "table":
            if not f.columns:
                errors.append(f"字段「{label}」明细表未配置子列")
            col_keys: set[str] = set()
            for c in f.columns:
                if not c.key:
                    errors.append(f"字段「{label}」明细列「{c.label}」缺少标识")
                elif c.key in col_keys:
                    errors.append(f"字段「{label}」明细列标识重复：{c.key}")
                else:
                    col_keys.add(c.key)
                if c.type == "select" and not c.options:
                    errors.append(f"字段「{label}」明细列「{c.label}」下拉未配置选项")
        if f.type == "formula":
            if not f.formula.strip():
                errors.append(f"字段「{label}」未配置计算公式")
            else:
                for ref in _formula_refs(f.formula):
                    if ref not in known_keys:
                        errors.append(f"字段「{label}」公式引用的控件不存在：{ref}")
                for kind, agg in _extract_aggregates(_FORMULA_PREFIX_RE.sub("", f.formula))[1]:
                    if kind == "sum":
                        table_key, _, col_key = agg.partition(".")
                        table_field = next((x for x in fields if x.key == table_key), None)
                        if table_field is None or table_field.type != "table":
                            errors.append(f"字段「{label}」公式引用的明细表不存在：{table_key}")
                        elif col_key not in {c.key for c in table_field.columns}:
                            errors.append(f"字段「{label}」公式引用的明细列不存在：{table_key}.{col_key}")
                    elif kind == "hours":
                        if agg not in known_keys:
                            errors.append(f"字段「{label}」公式引用的控件不存在：{agg}")
                    elif agg not in known_keys:
                        errors.append(f"字段「{label}」公式引用的控件不存在：{agg}")
        if f.type == "attendance" and f.ref_type not in ATTENDANCE_REF_TYPES:
            errors.append(f"字段「{label}」假勤原子类型非法（可选 {', '.join(ATTENDANCE_REF_TYPES)}）")
        if f.type == "hr_ref" and f.ref_type not in HR_REF_TYPES:
            errors.append(f"字段「{label}」人事原子类型非法（可选 {', '.join(HR_REF_TYPES)}）")
        for group, gname in ((f.show_when, "显示"), (f.required_when, "必填"), (f.readonly_when, "只读")):
            for r in (group.rules if group else []):
                if r.field not in known_keys:
                    errors.append(f"字段「{label}」{gname}条件引用控件不存在：{r.field}")
    if not fields:
        errors.append("至少需要一个字段")
    if errors:
        raise BizException(R.OA_SCHEMA_INVALID, "；".join(errors))


def _is_empty(v) -> bool:
    return v is None or v == "" or v == []


def _parse_date(v: str) -> date | None:
    try:
        return datetime.strptime(str(v), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ---------------- 条件逻辑求值（与前端 formLogic 语义一致） ----------------


def _eval_rule(rule, data: dict) -> bool:
    """单条条件求值。

    - 多选控件（实际值为数组）按「包含任一」判定 eq/ne/contains；
    - 区间（between）/ 集合（in）/ 空值（empty, not_empty）走审批引擎共用语义
      （``app.modules.approval.condition.eval_rule_value``），保证流程分支与表单条件口径一致。
    - ``rules`` 非空时本条是**条件组**，按 logic（and/or）递归求值。
    """
    if rule.rules:
        return _eval_rule_list(rule.rules, rule.logic, data)
    actual = data.get(rule.field)
    return eval_rule_value(rule.op, actual, rule.value, list_eq_contains=True)


def _eval_rule_list(rules, logic: str, data: dict) -> bool:
    if not rules:
        return True
    results = [_eval_rule(r, data) for r in rules]
    return all(results) if logic != "or" else any(results)


def eval_condition(group: ConditionGroup | None, data: dict) -> bool:
    """条件组求值：无规则视为恒真（未配置条件）。"""
    if not group or not group.rules:
        return True
    return _eval_rule_list(group.rules, group.logic, data)


def _visible(f: FormFieldIn, data: dict) -> bool:
    """showWhen 不满足 → 隐藏，提交时跳过校验。"""
    return eval_condition(f.show_when, data)


def _effective_required(f: FormFieldIn, data: dict) -> bool:
    if f.required:
        return True
    if f.required_when and f.required_when.rules:
        return eval_condition(f.required_when, data)
    return False


def _allowed_options(f: FormFieldIn, data: dict) -> list[str] | None:
    """当前可选选项（str 列表）；None = 不做成员校验（字典源选项由字典维护）。"""
    if f.options_source == "dict":
        return None
    if isinstance(f.cascade, dict):
        parent_val = data.get(f.cascade.get("parent") or "")
        mapping = f.cascade.get("map") or {}
        key = "" if parent_val is None else str(parent_val)
        allowed = mapping.get(key)
        if isinstance(allowed, list):
            return [str(o) for o in allowed]
    return [str(o) for o in f.options]


def _validate_value(f: FormFieldIn, v, errors: list[str], data: dict) -> None:
    label = f.label or f.key
    if _is_empty(v):
        if _effective_required(f, data):
            errors.append(f"{label} 为必填项")
        return
    if f.type in ("text", "textarea"):
        if not isinstance(v, str):
            errors.append(f"{label} 必须是文本")
        elif f.maxlength and len(v) > f.maxlength:
            errors.append(f"{label} 超长（最大 {f.maxlength} 字）")
    elif f.type in ("number", "money"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{label} 必须是数字")
    elif f.type == "date":
        if _parse_date(v) is None:
            errors.append(f"{label} 日期格式应为 YYYY-MM-DD")
    elif f.type == "daterange":
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            errors.append(f"{label} 应为 [开始日期, 结束日期]")
        else:
            start, end = _parse_date(v[0]), _parse_date(v[1])
            if start is None or end is None:
                errors.append(f"{label} 日期格式应为 YYYY-MM-DD")
            elif start > end:
                errors.append(f"{label} 结束日期不能早于开始日期")
    elif f.type in ("select", "radio"):
        allowed = _allowed_options(f, data)
        if allowed is not None and str(v) not in allowed:
            errors.append(f"{label} 选项非法")
    elif f.type == "checkbox":
        allowed = _allowed_options(f, data)
        if not isinstance(v, list) or (allowed is not None and any(str(x) not in allowed for x in v)):
            errors.append(f"{label} 选项非法")
    elif f.type == "file":
        if not isinstance(v, list) or any(not isinstance(x, str) or not x for x in v):
            errors.append(f"{label} 应为附件 URL 列表")
    elif f.type == "user":
        if f.multiple:
            if not isinstance(v, list) or any(isinstance(x, bool) or not isinstance(x, int) for x in v):
                errors.append(f"{label} 应为人员 ID 列表")
        elif isinstance(v, bool) or not isinstance(v, int):
            errors.append(f"{label} 应为人员 ID")
    elif f.type == "resource":
        rid = v.get("id") if isinstance(v, dict) else None
        if (
            not isinstance(v, dict)
            or isinstance(rid, bool)
            or not isinstance(rid, int)
            or not isinstance(v.get("name"), str)
        ):
            errors.append(f"{label} 应为资源对象（id + name）")
    elif f.type == "table":
        if not isinstance(v, list):
            errors.append(f"{label} 应为明细表行列表")
        else:
            col_keys = {c.key for c in f.columns if c.key}
            for idx, row in enumerate(v):
                if not isinstance(row, dict):
                    errors.append(f"{label} 第 {idx + 1} 行不是对象")
                    continue
                for c in f.columns:
                    if not c.key:
                        continue
                    cell = row.get(c.key)
                    if c.required and _is_empty(cell):
                        errors.append(f"{label} 第 {idx + 1} 行「{c.label}」为必填项")
                        continue
                    if _is_empty(cell):
                        continue
                    if c.type in ("number", "money") and (
                        isinstance(cell, bool) or not isinstance(cell, (int, float))
                    ):
                        errors.append(f"{label} 第 {idx + 1} 行「{c.label}」必须是数字")
                    elif c.type == "date" and _parse_date(cell) is None:
                        errors.append(f"{label} 第 {idx + 1} 行「{c.label}」日期格式应为 YYYY-MM-DD")
                extra = set(row.keys()) - col_keys
                if extra:
                    errors.append(f"{label} 第 {idx + 1} 行含未定义列：{'、'.join(sorted(extra))}")
    elif f.type == "formula":
        # 公式由服务端计算，提交值只做类型兜底（不信任前端算出的数）
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{label} 必须是数字")
    elif f.type == "phone":
        if not isinstance(v, str) or not _PHONE_RE.match(v.strip()):
            errors.append(f"{label} 手机号格式不正确")
    elif f.type == "location":
        if not isinstance(v, str):
            errors.append(f"{label} 应为位置文本")
        elif f.maxlength and len(v) > f.maxlength:
            errors.append(f"{label} 超长（最大 {f.maxlength} 字）")
    elif f.type in ("attendance", "hr_ref"):
        kind = v.get("kind") if isinstance(v, dict) else None
        allowed = ATTENDANCE_REF_TYPES if f.type == "attendance" else HR_REF_TYPES
        if not isinstance(v, dict) or kind not in allowed:
            errors.append(f"{label} 原子类型非法（可选 {'、'.join(allowed)}）")
        elif f.ref_type and kind != f.ref_type:
            errors.append(f"{label} 原子类型应为 {f.ref_type}")


def validate_data(fields: list[FormFieldIn], data: dict) -> None:
    """提交数据校验（非法 → 62003）；schema 之外的键忽略；布局控件与条件隐藏字段跳过。"""
    errors: list[str] = []
    data = data or {}
    for f in fields:
        if f.type in LAYOUT_TYPES or not f.key:
            continue
        if not _visible(f, data):
            continue
        _validate_value(f, data.get(f.key), errors, data)
    if errors:
        raise BizException(R.OA_DATA_INVALID, "；".join(errors))


def schema_of(form: OaForm) -> dict:
    return parse_json(form.schema_json, {}) or {}


def fields_of(form: OaForm) -> list[FormFieldIn]:
    return [FormFieldIn.model_validate(x) for x in schema_of(form).get("fields") or []]


def normalized_fields(form: OaForm) -> list[dict]:
    """统一输出 camelCase：种子/历史存量是 snake_case（FormFieldIn 双向兼容），前端只认 camel。"""
    return [f.model_dump(by_alias=True) for f in fields_of(form)]


# ---------------- 发起 / 直通 ----------------


def _exposed_variables(fields: list[FormFieldIn], data: dict) -> dict:
    return {
        f.key: data.get(f.key)
        for f in fields
        if f.key and f.expose_variable and _visible(f, data or {}) and not _is_empty(data.get(f.key))
    }


def _flow_variables(fields: list[FormFieldIn], data: dict, form: OaForm, user: User) -> dict:
    """流程变量 = 暴露字段 + ``org.*``（申请人组织）+ ``form.*``（表单身份）。

    E1：企微条件里大量引用「申请人」「申请部门」「表单类型」，统一收敛到这两个命名空间。
    """
    variables = _exposed_variables(fields, data)
    variables["org"] = {
        "applicantId": user.id,
        "applicantName": user.name or user.username,
        "deptId": user.dept_id,
        "deptName": user.dept_name or "",
    }
    variables["form"] = {
        "formKey": form.key,
        "formName": form.name,
        "category": form.category or "",
        "instanceNo": "",
    }
    return variables


def _form_payload(form: OaForm, with_schema: bool = True) -> dict:
    return {
        "id": form.id,
        "key": form.key,
        "name": form.name,
        "formVersion": form.form_version,
        "status": form.status,
        "category": form.category,
        "icon": form.icon,
        "sort": form.sort,
        "description": form.description,
        "flowDefinitionId": form.flow_definition_id,
        "fields": normalized_fields(form) if with_schema else None,
        "scope": _scope_of(form),
        "publishedAt": form.published_at.strftime("%Y-%m-%d %H:%M:%S") if form.published_at else "",
        "createTime": form.create_time.strftime("%Y-%m-%d %H:%M:%S") if form.create_time else "",
    }


def apply(db: Session, form_id: int, user: User, data: dict) -> OaInstance:
    """发起 OA 申请：校验 → 发 OA 号 → 存单据 → 有绑定流程走引擎，未绑定直通（提交即通过）。"""
    form = db.get(OaForm, form_id)
    if not form or form.deleted or form.status != "published":
        raise BizException(R.OA_FORM_NOT_PUBLISHED)
    # E1：可见范围外的人不允许发起（目录已裁剪，这里防直调接口）
    if not _scope_allows(db, _scope_of(form), user):
        raise BizException(R.AUTH_FORBIDDEN, http_status=403)
    fields = fields_of(form)
    data = dict(data or {})
    # E1：公式字段由服务端重算（前端算的值不作数）
    _compute_formulas(fields, data)
    validate_data(fields, data)

    inst = OaInstance(
        display_no=next_no(db, "oa"),
        form_id=form.id,
        form_key=form.key,
        form_name=form.name,
        form_version=form.form_version,
        category=form.category,
        schema_json=form.schema_json,
        applicant_id=user.id,
        applicant_name=user.name or user.username,
        form_data=json.dumps(data or {}, ensure_ascii=False),
        status="running",
        create_by=user.id,
    )
    db.add(inst)
    db.flush()  # 先落库拿到 id，作为审批 biz_id

    definition = db.get(ApprovalDefinition, form.flow_definition_id) if form.flow_definition_id else None
    if form.flow_definition_id and (not definition or definition.deleted or not definition.enabled):
        raise BizException(R.OA_INVALID_STATE, "绑定的流程定义不存在或未启用")
    if not definition:
        # 未绑定流程定义 → 直通（与 F3 任务/结算一致）
        inst.status = "approved"
        inst.finished_at = datetime.now()
        db.flush()
        return inst

    flow = engine.start(
        db,
        biz_type="oa",
        biz_id=inst.id,
        definition_id=definition.id,
        title=f"{inst.display_no} {form.name}",
        initiator=user,
        form_snapshot={
            "displayNo": inst.display_no,
            "formKey": form.key,
            "formName": form.name,
            "category": form.category,
            "data": data or {},
        },
        variables=_flow_variables(fields, data, form, user),
    )
    inst.flow_instance_id = flow.id
    db.flush()
    return inst


# ---------------- 流程事件回写（同事务，biz_type='oa'） ----------------


def _writeback(db: Session, biz_id: int, instance_id: int, status: str) -> None:
    inst = db.get(OaInstance, biz_id)
    if not inst or inst.deleted or inst.status != "running":
        return
    inst.status = status
    inst.flow_instance_id = instance_id
    if status in ("approved", "rejected", "withdrawn"):
        inst.finished_at = datetime.now()
    inst.update_time = datetime.now()


def _on_completed(event: ApprovalCompleted) -> None:
    if event.biz_type == "oa":
        _writeback(event.db, event.biz_id, event.instance_id, "approved")


def _on_rejected(event: ApprovalRejected) -> None:
    if event.biz_type == "oa":
        _writeback(event.db, event.biz_id, event.instance_id, "rejected")


def _on_withdrawn(event: ApprovalWithdrawn) -> None:
    if event.biz_type == "oa":
        _writeback(event.db, event.biz_id, event.instance_id, "withdrawn")


def register_flow_handlers() -> None:
    """F5：审批处理器注册入口，由 ``app.modules.approval.wiring.install()`` 显式装配。

    不再在模块 import 时自动订阅 —— 漏一个 import 就会让单据永久卡在 approving。
    """
    subscribe(ApprovalCompleted, _on_completed)
    subscribe(ApprovalRejected, _on_rejected)
    subscribe(ApprovalWithdrawn, _on_withdrawn)



# ---------------- 用户侧查询 ----------------


def _scope_of(form: OaForm) -> dict:
    """模板可见范围：{depts:[],roles:[],users:[]}；空字典 = 全员可见。"""
    return parse_json(form.scope_json, {}) or {}


def _scope_json(scope: dict | None) -> str | None:
    """可见范围入库前归一：只保留 depts/roles/users 三个列表；全空 → None（= 全员可见）。"""
    if not isinstance(scope, dict):
        return None
    out: dict[str, list[str]] = {}
    for key in ("depts", "roles", "users"):
        vals = scope.get(key) or []
        if isinstance(vals, str):
            vals = [vals]
        out[key] = [str(v) for v in vals if v not in (None, "")]
    if not any(out.values()):
        return None
    return json.dumps(out, ensure_ascii=False)


def _dept_ids_of_user(db: Session, user: User) -> set[int]:
    """用户所属部门（含任职表全部任职 + user.dept_id 旧字段兼容）。"""
    ids: set[int] = set()
    for did in db.scalars(
        select(UserDept.dept_id).where(UserDept.user_id == user.id, UserDept.deleted == 0)
    ).all():
        if did:
            ids.add(int(did))
    if user.dept_id:
        ids.add(int(user.dept_id))
    return ids


def _dept_with_descendants(db: Session, dept_ids: set[int]) -> set[int]:
    """部门集合 → 自身 + 全部下级部门 id。"""
    if not dept_ids:
        return set()
    rows = db.execute(select(Dept.id, Dept.parent_id).where(Dept.deleted == 0)).all()
    children: dict[int, list[int]] = {}
    for did, pid in rows:
        children.setdefault(int(pid or 0), []).append(int(did))
    out: set[int] = set()
    stack = list(dept_ids)
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))
    return out


def _scope_allows(db: Session, scope: dict, user: User) -> bool:
    """模板可见范围判定：部门 / 角色 / 账号任一维度命中即放行；全空 = 全员可见。"""
    if not scope:
        return True
    # 超管旁路：可见范围只约束普通用户，管理员始终可见（与权限体系口径一致）
    if "super" in set(user.role_codes or []):
        return True
    depts = [str(x) for x in (scope.get("depts") or [])]
    roles = [str(x) for x in (scope.get("roles") or [])]
    users = [str(x) for x in (scope.get("users") or [])]
    if not depts and not roles and not users:
        return True
    if users and (user.username in users or str(user.id) in users):
        return True
    if roles and set(roles) & set(user.role_codes or []):
        return True
    if depts:
        rows = db.execute(select(Dept.id, Dept.name).where(Dept.deleted == 0)).all()
        id_by_name = {str(name): int(did) for did, name in rows}
        target_ids: set[int] = set()
        for d in depts:
            if d.isdigit():
                target_ids.add(int(d))
            elif d in id_by_name:
                target_ids.add(id_by_name[d])
        if target_ids & _dept_with_descendants(db, _dept_ids_of_user(db, user)):
            return True
    return False


def catalog(db: Session, user: User | None = None) -> list[dict]:
    """模板目录：published 表单按 category 分组（category 展示名由前端字典渲染）。

    E1：按模板可见范围（scope_json）裁剪 —— 部门 / 角色 / 账号任一命中即对当前用户可见。
    """
    rows = db.scalars(
        select(OaForm)
        .where(OaForm.status == "published", OaForm.deleted == 0)
        .order_by(OaForm.sort, OaForm.id)
    ).all()
    groups: dict[str, list[dict]] = {}
    for f in rows:
        scope = _scope_of(f)
        if user is not None and not _scope_allows(db, scope, user):
            continue
        payload = _form_payload(f)
        payload["scope"] = scope
        groups.setdefault(f.category or "", []).append(payload)
    return [{"category": k, "forms": v} for k, v in groups.items()]


def _fmt(v: datetime | None) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%S") if v else ""


def instance_item(db: Session, inst: OaInstance) -> dict:
    pending = ""
    pending_tasks: list[dict] = []
    if inst.status == "running" and inst.flow_instance_id:
        pending = approval_svc.pending_names(db, inst.flow_instance_id)
        task_rows = db.scalars(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == inst.flow_instance_id,
                ApprovalTask.status == "pending",
                ApprovalTask.deleted == 0,
            )
        ).all()
        pending_tasks = [
            {
                "id": t.id,
                "seq": t.seq,
                "nodeName": t.node_name,
                "assigneeId": t.assignee_id,
                "assigneeName": t.assignee_name,
            }
            for t in task_rows
        ]
    return {
        "id": inst.id,
        "displayNo": inst.display_no,
        "formId": inst.form_id,
        "formKey": inst.form_key,
        "formName": inst.form_name,
        "formVersion": inst.form_version,
        "category": inst.category,
        "applicantId": inst.applicant_id,
        "applicantName": inst.applicant_name,
        "status": inst.status,
        "pendingNames": pending,
        "pendingTasks": pending_tasks,
        "flowInstanceId": inst.flow_instance_id or 0,
        "createTime": _fmt(inst.create_time),
        "finishedAt": _fmt(inst.finished_at),
    }


# 实例列表排序白名单（'col:asc|desc'，非法回退 id desc）
_OA_SORT_COLS = {
    "id": OaInstance.id,
    "display_no": OaInstance.display_no,
    "form_name": OaInstance.form_name,
    "category": OaInstance.category,
    "applicant_name": OaInstance.applicant_name,
    "status": OaInstance.status,
    "create_time": OaInstance.create_time,
    "finished_at": OaInstance.finished_at,
}


def _oa_sort_order(raw: str):
    col, desc = OaInstance.id, True
    if ":" in (raw or ""):
        key, _, d = raw.partition(":")
        if key in _OA_SORT_COLS:
            col, desc = _OA_SORT_COLS[key], d != "asc"
    return col.desc() if desc else col.asc()


def my_instances(db: Session, user: User, params: PageParams, status: str = "", sort: str = "", q: str = "") -> dict:
    stmt = select(OaInstance).where(OaInstance.applicant_id == user.id, OaInstance.deleted == 0)
    if status:
        stmt = stmt.where(OaInstance.status == status)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where((OaInstance.display_no.like(like)) | (OaInstance.form_name.like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(_oa_sort_order(sort)).offset((params.page - 1) * params.size).limit(params.size)
    ).all()
    return page_result([instance_item(db, r) for r in rows], total, params.page, params.size)


def instance_status_counts(db: Session, user: User | None = None) -> dict:
    """OA 单据状态页签计数：user 为空=管理端全量，否则=本人申请。"""
    stmt = select(OaInstance.status, func.count()).where(OaInstance.deleted == 0).group_by(OaInstance.status)
    if user is not None:
        stmt = stmt.where(OaInstance.applicant_id == user.id)
    rows = db.execute(stmt).all()
    data = {s: 0 for s in ("running", "approved", "rejected", "withdrawn", "terminated")}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


def _can_view(db: Session, inst: OaInstance, user: User) -> bool:
    if inst.applicant_id == user.id:
        return True
    if "oa:admin:handle" in user.perm_codes or "super" in user.role_codes:
        return True
    if not inst.flow_instance_id:
        return False
    fid = inst.flow_instance_id
    if db.scalar(
        select(ApprovalTask.id).where(
            ApprovalTask.instance_id == fid, ApprovalTask.assignee_id == user.id, ApprovalTask.deleted == 0
        )
    ):
        return True
    if db.scalar(
        select(ApprovalCc.id).where(
            ApprovalCc.instance_id == fid, ApprovalCc.user_id == user.id, ApprovalCc.deleted == 0
        )
    ):
        return True
    return bool(
        db.scalar(
            select(ApprovalRecord.id).where(
                ApprovalRecord.instance_id == fid, ApprovalRecord.operator_id == user.id, ApprovalRecord.deleted == 0
            )
        )
    )


def _field_permission_mask(db: Session, inst: OaInstance, user: User) -> dict[str, str]:
    """当前用户所在待办节点的字段权限掩码 {字段key: editable|viewonly|hidden}。

    非待办人 / 无流程实例 → 空掩码（不限制）。E1 节点字段权限只约束**当前处理人**视图。
    """
    if not inst.flow_instance_id:
        return {}
    task = db.scalar(
        select(ApprovalTask)
        .where(
            ApprovalTask.instance_id == inst.flow_instance_id,
            ApprovalTask.assignee_id == user.id,
            ApprovalTask.status == "pending",
            ApprovalTask.deleted == 0,
        )
        .limit(1)
    )
    if not task:
        return {}
    flow = db.get(ApprovalInstance, inst.flow_instance_id)
    if not flow or not flow.definition_id:
        return {}
    node = db.scalar(
        select(ApprovalNode).where(
            ApprovalNode.definition_id == flow.definition_id,
            ApprovalNode.seq == task.seq,
            ApprovalNode.deleted == 0,
        )
    )
    if not node:
        return {}
    perms = parse_json(node.field_permissions, {}) or {}
    if not isinstance(perms, dict):
        return {}
    return {str(k): str(v) for k, v in perms.items() if v in ("editable", "viewonly", "hidden")}


def instance_detail(db: Session, inst: OaInstance, user: User) -> dict:
    if not _can_view(db, inst, user):
        raise BizException(R.AUTH_FORBIDDEN, http_status=403)
    data = instance_item(db, inst)
    fields = normalized_fields(inst)
    form_data = parse_json(inst.form_data, {})
    # E1：按节点字段权限掩码 —— hidden 字段既不出现在 schema，也不出现在数据里
    mask = _field_permission_mask(db, inst, user)
    if mask:
        hidden = {k for k, v in mask.items() if v == "hidden"}
        if hidden:
            fields = [f for f in fields if f.get("key") not in hidden]
            form_data = {k: v for k, v in (form_data or {}).items() if k not in hidden}
        fields = [
            {**f, "readOnly": True} if mask.get(f.get("key") or "") == "viewonly" else f for f in fields
        ]
    data["schema"] = {"fields": fields}
    data["formData"] = form_data
    data["fieldPermissions"] = mask
    data["timeline"] = (
        approval_svc.instance_timeline(db, inst.flow_instance_id)["records"] if inst.flow_instance_id else []
    )
    return data


# ---------------- 统计 ----------------


def stats(db: Session, with_backlog: bool = False) -> dict:
    """申请量（按模板/状态）、平均审批时长（小时）、在办量、近 6 个月趋势。"""
    base = select(OaInstance).where(OaInstance.deleted == 0)
    rows = db.scalars(base).all()

    by_form: dict[str, dict] = {}
    by_status: dict[str, int] = {}
    durations: list[float] = []
    for r in rows:
        slot = by_form.setdefault(r.form_key, {"formKey": r.form_key, "formName": r.form_name, "count": 0})
        slot["count"] += 1
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.finished_at and r.create_time and r.status in ("approved", "rejected"):
            durations.append((r.finished_at - r.create_time).total_seconds() / 3600)

    today = date.today().replace(day=1)
    months: list[str] = []
    y, m = today.year, today.month
    for _ in range(6):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    counts = {k: 0 for k in months}
    for r in rows:
        if r.create_time:
            key = r.create_time.strftime("%Y-%m")
            if key in counts:
                counts[key] += 1
    trend = [{"month": k, "count": counts[k]} for k in reversed(months)]

    result = {
        "total": len(rows),
        "inFlight": by_status.get("running", 0),
        "byStatus": by_status,
        "byForm": sorted(by_form.values(), key=lambda x: -x["count"]),
        "avgDurationHours": round(sum(durations) / len(durations), 1) if durations else 0,
        "trend": trend,
    }
    if with_backlog:
        # 各模板当前积压待办数（管理员视角）
        pend = db.execute(
            select(ApprovalTask.instance_id, func.count())
            .where(ApprovalTask.status == "pending", ApprovalTask.deleted == 0)
            .group_by(ApprovalTask.instance_id)
        ).all()
        todo_by_flow = {iid: c for iid, c in pend}
        backlog: dict[str, dict] = {}
        for r in rows:
            if r.status != "running":
                continue
            slot = backlog.setdefault(
                r.form_key, {"formKey": r.form_key, "formName": r.form_name, "instances": 0, "pendingTasks": 0}
            )
            slot["instances"] += 1
            slot["pendingTasks"] += todo_by_flow.get(r.flow_instance_id or 0, 0)
        result["backlog"] = sorted(backlog.values(), key=lambda x: -x["instances"])
    return result


# ---------------- 资源控件：全站数据检索（OA 填写人只读） ----------------

# (资源类型, 展示名, 可带出字段 [(key, 标签)])
RESOURCE_DEFS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "customer",
        "客户",
        [
            ("customerNo", "客户编号"),
            ("name", "客户名称"),
            ("customerType", "客户类型"),
            ("grade", "客户等级"),
            ("taxNo", "纳税识别号"),
            ("contactPerson", "联系人"),
            ("contactPhone", "联系电话"),
            ("address", "地址"),
        ],
    ),
    (
        "contract",
        "合同",
        [
            ("contractNo", "合同编号"),
            ("name", "合同名称"),
            ("customerName", "客户名称"),
            ("amount", "合同金额"),
            ("contractType", "合同类型"),
            ("status", "状态"),
        ],
    ),
    (
        "task",
        "检测任务",
        [
            ("taskNo", "任务编号"),
            ("taskName", "任务名称"),
            ("customerName", "客户名称"),
            ("contractNo", "合同编号"),
            ("status", "状态"),
        ],
    ),
    (
        "report",
        "报告",
        [("reportNo", "报告编号"), ("fileName", "文件名"), ("status", "状态")],
    ),
    ("dept", "部门", [("name", "部门名称"), ("code", "部门编码")]),
    (
        "user",
        "用户",
        [("name", "姓名"), ("username", "登录名"), ("deptName", "部门"), ("mobile", "手机"), ("email", "邮箱")],
    ),
    (
        "oa_instance",
        "OA 申请单",
        [
            ("displayNo", "申请编号"),
            ("formName", "表单"),
            ("applicantName", "申请人"),
            ("status", "状态"),
            ("createTime", "申请时间"),
        ],
    ),
]


def resource_meta() -> list[dict]:
    """资源类型 + 可带出字段清单（供设计器配置 mappings）。"""
    return [
        {"type": t, "label": label, "fields": [{"key": k, "label": lab} for k, lab in fields]}
        for t, label, fields in RESOURCE_DEFS
    ]


def _paged(db: Session, stmt, page: int, size: int):
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    return rows, total


def _search_customer(db: Session, q: str, page: int, size: int) -> dict:
    stmt = select(Customer).where(Customer.deleted == 0)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Customer.name.like(like) | Customer.customer_no.like(like) | Customer.tax_no.like(like))
    rows, total = _paged(db, stmt.order_by(Customer.id.desc()), page, size)
    items = [
        {
            "id": c.id,
            "label": c.name,
            "sub": c.customer_no,
            "fields": {
                "customerNo": c.customer_no,
                "name": c.name,
                "customerType": c.customer_type,
                "grade": c.grade,
                "taxNo": c.tax_no,
                "contactPerson": c.contact_person or "",
                "contactPhone": c.contact_phone or "",
                "address": c.address,
            },
        }
        for c in rows
    ]
    return {"items": items, "total": total}


def _search_contract(db: Session, q: str, page: int, size: int) -> dict:
    # 只列已通过的合同（可用状态）
    stmt = select(Contract).where(Contract.deleted == 0, Contract.status == "approved")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            Contract.name.like(like) | Contract.contract_no.like(like) | Contract.customer_name.like(like)
        )
    rows, total = _paged(db, stmt.order_by(Contract.id.desc()), page, size)
    items = [
        {
            "id": c.id,
            "label": c.name,
            "sub": c.contract_no or "",
            "fields": {
                "contractNo": c.contract_no or "",
                "name": c.name,
                "customerName": c.customer_name,
                "amount": float(c.amount) if c.amount is not None else None,
                "contractType": c.contract_type,
                "status": c.status,
            },
        }
        for c in rows
    ]
    return {"items": items, "total": total}


def _search_task(db: Session, q: str, page: int, size: int) -> dict:
    stmt = select(Task).where(Task.deleted == 0)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Task.task_name.like(like) | Task.task_no.like(like) | Task.customer_name.like(like))
    rows, total = _paged(db, stmt.order_by(Task.id.desc()), page, size)
    items = [
        {
            "id": t.id,
            "label": t.task_name,
            "sub": t.task_no or "",
            "fields": {
                "taskNo": t.task_no or "",
                "taskName": t.task_name,
                "customerName": t.customer_name,
                "contractNo": t.contract_no,
                "status": t.status,
            },
        }
        for t in rows
    ]
    return {"items": items, "total": total}


def _search_report(db: Session, q: str, page: int, size: int) -> dict:
    stmt = select(Report).where(Report.deleted == 0)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Report.report_no.like(like) | Report.file_name.like(like))
    rows, total = _paged(db, stmt.order_by(Report.id.desc()), page, size)
    items = [
        {
            "id": r.id,
            "label": r.report_no,
            "sub": r.file_name,
            "fields": {"reportNo": r.report_no, "fileName": r.file_name, "status": r.status},
        }
        for r in rows
    ]
    return {"items": items, "total": total}


def _search_dept(db: Session, q: str, page: int, size: int) -> dict:
    stmt = select(Dept).where(Dept.deleted == 0, Dept.status == "enabled")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Dept.name.like(like) | Dept.code.like(like))
    rows, total = _paged(db, stmt.order_by(Dept.sort, Dept.id), page, size)
    items = [
        {"id": d.id, "label": d.name, "sub": d.code, "fields": {"name": d.name, "code": d.code}} for d in rows
    ]
    return {"items": items, "total": total}


def _search_user(db: Session, q: str, page: int, size: int) -> dict:
    stmt = select(User).where(User.deleted == 0, User.status == "enabled")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(User.name.like(like) | User.username.like(like))
    rows, total = _paged(db, stmt.order_by(User.id), page, size)
    items = [
        {
            "id": u.id,
            "label": u.name or u.username,
            "sub": u.dept_name,
            "fields": {
                "name": u.name,
                "username": u.username,
                "deptName": u.dept_name,
                "mobile": u.mobile,
                "email": u.email,
            },
        }
        for u in rows
    ]
    return {"items": items, "total": total}


def _search_oa_instance(db: Session, user: User, q: str, page: int, size: int) -> dict:
    """只列本人可见的申请单：申请人 / 有待办 / 有已办 / 被抄送。"""
    visible_flow_ids = select(ApprovalTask.instance_id).where(
        ApprovalTask.assignee_id == user.id, ApprovalTask.deleted == 0
    ).union(
        select(ApprovalCc.instance_id).where(ApprovalCc.user_id == user.id, ApprovalCc.deleted == 0),
        select(ApprovalRecord.instance_id).where(ApprovalRecord.operator_id == user.id, ApprovalRecord.deleted == 0),
    )
    stmt = select(OaInstance).where(
        OaInstance.deleted == 0,
        (OaInstance.applicant_id == user.id) | (OaInstance.flow_instance_id.in_(visible_flow_ids)),
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(OaInstance.display_no.like(like) | OaInstance.form_name.like(like))
    rows, total = _paged(db, stmt.order_by(OaInstance.id.desc()), page, size)
    items = [
        {
            "id": i.id,
            "label": i.display_no,
            "sub": i.form_name,
            "fields": {
                "displayNo": i.display_no,
                "formName": i.form_name,
                "applicantName": i.applicant_name,
                "status": i.status,
                "createTime": _fmt(i.create_time),
            },
        }
        for i in rows
    ]
    return {"items": items, "total": total}


def search_resource(db: Session, rtype: str, user: User, q: str, page: int, size: int) -> dict:
    """资源控件通用检索；返回 {items: [{id, label, sub, fields}], total}。"""
    q = q.strip()
    if rtype == "customer":
        return _search_customer(db, q, page, size)
    if rtype == "contract":
        return _search_contract(db, q, page, size)
    if rtype == "task":
        return _search_task(db, q, page, size)
    if rtype == "report":
        return _search_report(db, q, page, size)
    if rtype == "dept":
        return _search_dept(db, q, page, size)
    if rtype == "user":
        return _search_user(db, q, page, size)
    if rtype == "oa_instance":
        return _search_oa_instance(db, user, q, page, size)
    raise BizException(R.GENERIC_PARAM, f"未知资源类型：{rtype}")


# ---------------- 管理端：表单 CRUD / 发布 ----------------


def _flow_version_info(db: Session, def_ids: set[int]) -> dict[int, tuple[int, int, str]]:
    """definition_id → (绑定版本, 同 code 最新启用版本, 流程名)。"""
    if not def_ids:
        return {}
    bound = db.scalars(select(ApprovalDefinition).where(ApprovalDefinition.id.in_(def_ids))).all()
    latest_by_code: dict[str, int] = {}
    for d in db.scalars(
        select(ApprovalDefinition).where(ApprovalDefinition.enabled == 1, ApprovalDefinition.deleted == 0)
    ).all():
        latest_by_code[d.code] = max(latest_by_code.get(d.code, 0), d.flow_version)
    return {
        d.id: (d.flow_version, latest_by_code.get(d.code, d.flow_version), d.name) for d in bound
    }


def list_forms(db: Session) -> list[dict]:
    rows = db.scalars(
        select(OaForm).where(OaForm.deleted == 0).order_by(OaForm.key, OaForm.form_version.desc())
    ).all()
    ver = _flow_version_info(db, {f.flow_definition_id for f in rows if f.flow_definition_id})
    out = []
    for f in rows:
        p = _form_payload(f)
        fv = ver.get(f.flow_definition_id or 0)
        p["flowName"] = fv[2] if fv else None
        p["flowVersion"] = fv[0] if fv else None
        p["flowLatestVersion"] = fv[1] if fv else None
        out.append(p)
    return out


def bind_latest_flow(db: Session, form_id: int, user: User) -> dict:
    """把表单绑定的流程定义切换到同 code 最新启用版本（绑定本身钉版本，不随定义升级自动漂移）。"""
    form = db.get(OaForm, form_id)
    if not form or form.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if not form.flow_definition_id:
        raise BizException(R.OA_INVALID_STATE, "表单未绑定流程")
    d = db.get(ApprovalDefinition, form.flow_definition_id)
    if not d or d.deleted:
        raise BizException(R.OA_INVALID_STATE, "绑定的流程定义不存在")
    latest = db.scalar(
        select(ApprovalDefinition)
        .where(
            ApprovalDefinition.code == d.code,
            ApprovalDefinition.enabled == 1,
            ApprovalDefinition.deleted == 0,
        )
        .order_by(ApprovalDefinition.flow_version.desc(), ApprovalDefinition.id.desc())
        .limit(1)
    )
    if not latest:
        raise BizException(R.OA_INVALID_STATE, "该流程没有启用的版本")
    form.flow_definition_id = latest.id
    form.update_by = user.id
    db.flush()
    p = _form_payload(form)
    p["flowName"] = latest.name
    p["flowVersion"] = latest.flow_version
    p["flowLatestVersion"] = latest.flow_version
    return p


def create_form(db: Session, body, user: User) -> dict:
    if db.scalar(
        select(OaForm).where(OaForm.key == body.key, OaForm.form_version == 1, OaForm.deleted == 0)
    ):
        raise BizException(R.OA_FORM_CONFLICT)
    form = OaForm(
        key=body.key,
        name=body.name,
        form_version=1,
        category=body.category,
        icon=body.icon,
        sort=body.sort,
        description=body.description,
        schema_json=json.dumps({"fields": [f.model_dump(by_alias=True) for f in body.fields]}, ensure_ascii=False),
        scope_json=_scope_json(body.scope),
        flow_definition_id=body.flow_definition_id,
        status="draft",
        create_by=user.id,
    )
    db.add(form)
    db.flush()
    return _form_payload(form)


def _editable_form(db: Session, form_id: int) -> OaForm:
    form = db.get(OaForm, form_id)
    if not form or form.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if form.status == "published":
        raise BizException(R.OA_INVALID_STATE, "已发布表单不可编辑，请新建版本")
    return form


def update_form(db: Session, form_id: int, body, user: User) -> dict:
    form = _editable_form(db, form_id)
    form.name = body.name
    form.category = body.category
    form.icon = body.icon
    form.sort = body.sort
    form.description = body.description
    form.schema_json = json.dumps({"fields": [f.model_dump(by_alias=True) for f in body.fields]}, ensure_ascii=False)
    form.scope_json = _scope_json(body.scope)
    form.flow_definition_id = body.flow_definition_id
    form.update_by = user.id
    db.flush()
    return _form_payload(form)


def new_version(db: Session, form_id: int, user: User) -> dict:
    """从现有版本复制出 form_version+1 草稿（改版入口）。"""
    src = db.get(OaForm, form_id)
    if not src or src.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    latest = db.scalar(
        select(func.max(OaForm.form_version)).where(OaForm.key == src.key, OaForm.deleted == 0)
    ) or src.form_version
    form = OaForm(
        key=src.key,
        name=src.name,
        form_version=latest + 1,
        category=src.category,
        icon=src.icon,
        sort=src.sort,
        description=src.description,
        schema_json=src.schema_json,
        scope_json=src.scope_json,
        flow_definition_id=src.flow_definition_id,
        status="draft",
        create_by=user.id,
    )
    db.add(form)
    db.flush()
    return _form_payload(form)


def publish_form(db: Session, form_id: int, user: User) -> dict:
    form = _editable_form(db, form_id)
    validate_fields(fields_of(form))
    if form.flow_definition_id:
        d = db.get(ApprovalDefinition, form.flow_definition_id)
        if not d or d.deleted or not d.enabled:
            raise BizException(R.OA_SCHEMA_INVALID, "绑定的流程定义不存在或未启用")
        if d.biz_type != "oa":
            raise BizException(R.OA_SCHEMA_INVALID, "只能绑定 biz_type=oa 的流程定义")
    # 同 key 旧版本自动停用，保证目录里同 key 只有一个 published
    for old in db.scalars(
        select(OaForm).where(
            OaForm.key == form.key,
            OaForm.status == "published",
            OaForm.id != form.id,
            OaForm.deleted == 0,
        )
    ):
        old.status = "disabled"
        old.update_time = datetime.now()
    form.status = "published"
    form.published_at = datetime.now()
    form.update_by = user.id
    db.flush()
    return _form_payload(form)


def disable_form(db: Session, form_id: int, user: User) -> dict:
    form = db.get(OaForm, form_id)
    if not form or form.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if form.status != "published":
        raise BizException(R.OA_INVALID_STATE, "仅已发布表单可停用")
    form.status = "disabled"
    form.update_by = user.id
    db.flush()
    return _form_payload(form)


def delete_form(db: Session, form_id: int, user: User | None = None) -> None:
    form = db.get(OaForm, form_id)
    if not form or form.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if form.status != "draft":
        raise BizException(R.OA_INVALID_STATE, "仅草稿可删除")
    used = db.scalar(select(OaInstance.id).where(OaInstance.form_id == form.id, OaInstance.deleted == 0))
    if used:
        raise BizException(R.OA_INVALID_STATE, "已有申请单据，不能删除")
    form.deleted = form.id  # deleted 入唯一键：写 id 保证多条同 key+version 软删行互不冲突
    recycle.track(db, OaForm, form, user=user, module="oa", resource="OaForm")
    form.update_time = datetime.now()


# ---------------- 管理端：异常流程干预 ----------------


def admin_instances(
    db: Session, params: PageParams, status: str = "", keyword: str = "", stuck_days: int = 0, sort: str = ""
) -> dict:
    stmt = select(OaInstance).where(OaInstance.deleted == 0)
    if status:
        stmt = stmt.where(OaInstance.status == status)
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            (OaInstance.display_no.like(like))
            | (OaInstance.form_name.like(like))
            | (OaInstance.applicant_name.like(like))
        )
    if stuck_days > 0:
        threshold = datetime.now().timestamp() - stuck_days * 86400
        stmt = stmt.where(
            OaInstance.status == "running",
            OaInstance.create_time < datetime.fromtimestamp(threshold),
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(_oa_sort_order(sort)).offset((params.page - 1) * params.size).limit(params.size)
    ).all()
    return page_result([instance_item(db, r) for r in rows], total, params.page, params.size)


def _oa_by_id(db: Session, inst_id: int) -> OaInstance:
    inst = db.get(OaInstance, inst_id)
    if not inst or inst.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return inst


def _flow_of(db: Session, inst: OaInstance) -> ApprovalInstance:
    flow = db.get(ApprovalInstance, inst.flow_instance_id) if inst.flow_instance_id else None
    if not flow or flow.deleted:
        raise BizException(R.OA_INVALID_STATE, "该单据无审批实例（直通单不可干预）")
    return flow


def terminate(db: Session, inst_id: int, operator: User, comment: str = "") -> dict:
    """强制结束：作废全部待办，实例 terminated，写时间线，回写 OA 状态。"""
    inst = _oa_by_id(db, inst_id)
    flow = _flow_of(db, inst)
    if flow.status != "running":
        raise BizException(R.APPROVAL_INVALID_STATE, "仅处理中的实例可强制结束")
    engine._cancel_pending(db, flow.id)
    flow.status = "terminated"
    flow.current_node_ids = "[]"
    flow.finished_at = datetime.now()
    engine._record(db, flow, "terminate", operator, comment or "管理员强制结束")
    inst.status = "terminated"
    inst.finished_at = datetime.now()
    inst.update_time = datetime.now()
    db.flush()
    return {"instanceId": flow.id, "status": flow.status}


def reassign(db: Session, inst_id: int, task_id: int, to_user: User, operator: User, comment: str = "") -> dict:
    """改派当前待办审批人（语义同转办，但操作人是管理员，不要求 assignee）。"""
    inst = _oa_by_id(db, inst_id)
    flow = _flow_of(db, inst)
    task = db.get(ApprovalTask, task_id, with_for_update=True)
    if not task or task.deleted or task.instance_id != flow.id or task.status != "pending":
        raise BizException(R.APPROVAL_NO_TODO)
    if flow.status != "running":
        raise BizException(R.APPROVAL_INVALID_STATE)
    task.status = "transferred"
    task.comment = comment or f"管理员改派给：{to_user.name or to_user.username}"
    task.acted_at = datetime.now()
    task.acted_by_id = operator.id
    db.add(
        ApprovalTask(
            instance_id=flow.id,
            seq=task.seq,
            node_name=task.node_name,
            node_type=task.node_type,
            assignee_id=to_user.id,
            assignee_name=to_user.name or to_user.username,
            status="pending",
            task_kind=task.task_kind,
            action_meta=task.action_meta,
        )
    )
    engine._emit_todo(db, flow, to_user, task.node_name, operator.id)
    engine._record(
        db,
        flow,
        "transfer",
        operator,
        task.comment,
        node_name=task.node_name,
        seq=task.seq,
        payload={"toUserId": to_user.id, "admin": True},
    )
    db.flush()
    return {"instanceId": flow.id, "status": flow.status}


def restart(db: Session, inst_id: int, seq: int, operator: User, comment: str = "") -> dict:
    """撤回/退回到指定节点：作废现有待办，按定义从 seq 重建待办，实例回到 running。"""
    inst = _oa_by_id(db, inst_id)
    flow = _flow_of(db, inst)
    definition = db.get(ApprovalDefinition, flow.definition_id) if flow.definition_id else None
    nodes = [n for n in (definition.nodes if definition else []) if n.deleted == 0]
    target = next((n for n in nodes if n.seq == seq), None)
    if not target or target.node_type not in ("approval", "executor"):
        raise BizException(R.GENERIC_PARAM, "目标节点不存在或非审批节点")
    engine._cancel_pending(db, flow.id)
    flow.status = "running"
    flow.finished_at = None
    engine._record(db, flow, "restart", operator, comment or f"管理员退回到节点「{target.node_name or seq}」", seq=seq)
    engine._walk(db, flow, nodes, seq, operator)
    inst.status = "running"
    inst.finished_at = None
    inst.update_time = datetime.now()
    db.flush()
    return {"instanceId": flow.id, "status": flow.status, "currentSeq": seq}


def urge(db: Session, inst_id: int, operator: User, comment: str = "") -> dict:
    """催办：给当前全部待办审批人各写一条站内通知（sys_notify），不改变流程状态。"""
    from app.modules.admin.models import Notify

    inst = _oa_by_id(db, inst_id)
    flow = _flow_of(db, inst)
    if flow.status != "running":
        raise BizException(R.APPROVAL_INVALID_STATE, "仅处理中的单据可催办")
    tasks = db.scalars(
        select(ApprovalTask).where(
            ApprovalTask.instance_id == flow.id,
            ApprovalTask.status == "pending",
            ApprovalTask.deleted == 0,
        )
    ).all()
    if not tasks:
        raise BizException(R.APPROVAL_NO_TODO, "当前无待办审批人")
    title = f"催办：{inst.display_no} {inst.form_name}"
    content = comment.strip() or f"单据已滞留，请尽快处理（当前节点：{tasks[0].node_name or '审批'}）。"
    for t in tasks:
        db.add(
            Notify(
                user_id=t.assignee_id,
                title=title,
                content=content[:500],
                biz_type="oa",
                biz_id=inst.id,
                link="/approval",
            )
        )
    db.flush()
    return {"instanceId": flow.id, "urged": len(tasks)}

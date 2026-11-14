"""AI OA 表单预填：按本人同表单历史申请（最近 3 条）预填当前表单字段草稿。

仅返回草稿（不落库），由人工在发起页确认/修改后随正常发起提交；
资源类控件（file/user/resource）与布局控件不预填（id 类值必须人工重选）；
select/radio 值须 ∈ options、checkbox 须 ⊆ options，非法值服务端直接丢弃。
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.approval.graph import parse_json
from app.modules.auth.models import User
from app.modules.oa.models import OaForm, OaInstance
from app.modules.oa.schemas import FormFieldIn
from app.modules.oa.service import fields_of

PREFILL_PROMPT_VERSION = "v1"
PREFILLABLE_TYPES = ("text", "textarea", "number", "money", "date", "daterange", "select", "radio", "checkbox")
_HISTORY_LIMIT = 3
_VAL_MAX = 500

PREFILL_SYSTEM = (
    "你是表单填写助手。根据用户在同表单上的历史申请记录，为新申请预填字段值，输出严格 JSON："
    '{"data":{"字段key":值,...}}。规则：只输出给定字段清单中的 key；'
    "select/radio 值必须是该字段 options 之一；checkbox 值是 options 子集的数组；"
    "number/money 输出数字；date 输出 YYYY-MM-DD；daterange 输出 [起,止] 数组；"
    "取值以最近一条历史申请为主，缺失字段不要编造。只输出 JSON，不要输出其他内容。"
)


def _prefillable_fields(form: OaForm) -> list[FormFieldIn]:
    return [f for f in fields_of(form) if f.key and f.type in PREFILLABLE_TYPES]


def _history_rows(db: Session, user: User, form: OaForm) -> list[dict]:
    rows = db.scalars(
        select(OaInstance)
        .where(
            OaInstance.applicant_id == user.id,
            OaInstance.form_key == form.key,
            OaInstance.deleted == 0,
        )
        .order_by(OaInstance.id.desc())
        .limit(_HISTORY_LIMIT)
    ).all()
    keys = {f.key for f in _prefillable_fields(form)}
    out = []
    for r in rows:
        data = parse_json(r.form_data, {}) or {}
        slim = {}
        for k in keys:
            v = data.get(k)
            if v is None or v == "":
                continue
            slim[k] = (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))[:_VAL_MAX]
        if slim:
            out.append({"displayNo": r.display_no, "createTime": str(r.create_time or "")[:19], "data": slim})
    return out


def _sanitize(fields: list[FormFieldIn], raw_data: dict) -> tuple[dict, list[str]]:
    """AI 输出按字段元数据校验/归一：非法 key/非法选项值/类型不符一律丢弃。"""
    by_key = {f.key: f for f in fields}
    data: dict = {}
    for k, v in raw_data.items():
        f = by_key.get(k)
        if not f or v is None or v == "":
            continue
        if f.type in ("select", "radio"):
            s = str(v).strip()
            if s and s in (f.options or []):
                data[k] = s
        elif f.type == "checkbox":
            vals = v if isinstance(v, list) else [v]
            picked = [str(x).strip() for x in vals if str(x).strip() in (f.options or [])]
            if picked:
                data[k] = picked
        elif f.type in ("number", "money"):
            try:
                data[k] = float(v)
            except (TypeError, ValueError):
                continue
        elif f.type == "daterange":
            if isinstance(v, list) and len(v) == 2 and all(str(x).strip() for x in v):
                data[k] = [str(x).strip()[:32] for x in v]
        else:  # text/textarea/date
            limit = f.maxlength or 2000
            data[k] = str(v).strip()[:limit]
    return data, list(data.keys())


def parse_prefill_output(fields: list[FormFieldIn], raw: str) -> tuple[dict, list[str]]:
    """AI 输出 → (data, filledKeys)。无法解析抛 BizException(AI_PARSE_FAILED)；空结果合法。"""
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict) or not isinstance(parsed.get("data") or {}, dict):
            raise ValueError("bad shape")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请稍后再试") from exc
    return _sanitize(fields, parsed.get("data") or {})


def ai_prefill(db: Session, user: User, form_id: int) -> dict:
    """OA 预填入口：表单须已发布；无历史申请时直接回空（不调 AI）。只回草稿不落库。"""
    from app.services import ai as ai_svc

    form = db.get(OaForm, form_id)
    if not form or form.deleted or form.status != "published":
        raise BizException(R.OA_FORM_NOT_PUBLISHED)
    fields = _prefillable_fields(form)
    history = _history_rows(db, user, form)
    if not fields or not history:
        return {"data": {}, "filledKeys": [], "historyCount": len(history)}
    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置或表单预填功能已停用")

    ctx = {
        "formName": form.name,
        "fields": [
            {"key": f.key, "label": f.label, "type": f.type, "options": f.options or []}
            for f in fields
        ],
        "history": history,
    }
    messages = [
        {"role": "system", "content": PREFILL_SYSTEM},
        {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db,
            feature="oa_prefill",
            messages=messages,
            user=user,
            biz_type="oa_form",
            biz_id=form.id,
            prompt_version=PREFILL_PROMPT_VERSION,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc
    data, filled = parse_prefill_output(fields, raw)
    return {"data": data, "filledKeys": filled, "historyCount": len(history)}

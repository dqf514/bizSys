"""合同服务：状态机约束 + 审批事件订阅。"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.events import ApprovalCompleted, ApprovalRejected, ApprovalWithdrawn, subscribe
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.contract.models import Contract

EDITABLE = ("draft", "rejected")


def check_editable(c: Contract) -> None:
    if c.status == "approving":
        raise BizException(R.CONTRACT_EDITING_LOCKED)
    if c.status not in EDITABLE:
        raise BizException(R.CONTRACT_INVALID_STATE, f"状态「{c.status}」不允许编辑")


def snapshot(c: Contract) -> dict:
    return {
        "contractNo": c.contract_no or "",
        "name": c.name,
        "customerId": c.customer_id,
        "customerName": c.customer_name,
        "contractType": c.contract_type,
        "amount": float(c.amount) if c.amount is not None else None,
        "status": c.status,
        "handlerName": c.handler_name,
    }


def _handle_completed(event: ApprovalCompleted) -> None:
    if event.biz_type != "contract":
        return
    db: Session = event.db
    c = db.get(Contract, event.biz_id)
    if not c or c.deleted or c.status != "approving":
        return
    c.status = "approved"
    c.flow_instance_id = event.instance_id
    c.update_time = datetime.now()


def _handle_rejected(event: ApprovalRejected) -> None:
    if event.biz_type != "contract":
        return
    db: Session = event.db
    c = db.get(Contract, event.biz_id)
    if not c or c.deleted or c.status != "approving":
        return
    c.status = "rejected"
    c.flow_instance_id = event.instance_id
    c.update_time = datetime.now()


def _handle_withdrawn(event: ApprovalWithdrawn) -> None:
    """撤回后回写 draft（可编辑/可再提交），避免合同卡在 approving。"""
    if event.biz_type != "contract":
        return
    db: Session = event.db
    c = db.get(Contract, event.biz_id)
    if not c or c.deleted or c.status != "approving":
        return
    c.status = "draft"
    c.flow_instance_id = event.instance_id
    c.update_time = datetime.now()


subscribe(ApprovalCompleted, _handle_completed)
subscribe(ApprovalRejected, _handle_rejected)
subscribe(ApprovalWithdrawn, _handle_withdrawn)


def form_snapshot(c: Contract) -> dict:
    return json.loads(json.dumps(snapshot(c), ensure_ascii=False, default=str))


def load_customer_name(db: Session, customer_id: int) -> str:
    from app.modules.crm.models import Customer

    row = db.scalar(select(Customer.name).where(Customer.id == customer_id, Customer.deleted == 0))
    if not row:
        raise BizException(R.GENERIC_NOT_FOUND, "客户不存在")
    return row


# ---------------- AI 合同识别（上传合同文件 → 字段抽取草稿，人工确认后才落库） ----------------

CONTRACT_PARSE_PROMPT_VERSION = "v1"
CONTRACT_PARSE_SYSTEM = (
    "你是合同信息抽取助手。从合同内容中抽取字段，输出严格 JSON："
    '{"name": "合同名称", "customerName": "对方单位/客户名称", "amount": 金额数字(无则0), '
    '"startDate": "YYYY-MM-DD 或空", "endDate": "YYYY-MM-DD 或空", '
    '"payCycle": "付款周期(如 月结/季结/一次性)", "delivery": "交付方式", "sealType": "盖章类型", '
    '"paymentOrg": "付款单位", "contactPerson": "联系人", "contactPhone": "联系电话", '
    '"remark": "一句合同要点概述"}。只输出 JSON，未知字段留空字符串或 0。'
)
PARSE_FIELDS = (
    "name", "customerName", "amount", "startDate", "endDate", "payCycle",
    "delivery", "sealType", "paymentOrg", "contactPerson", "contactPhone", "remark",
)


def _customer_candidates(db: Session, name: str) -> list[dict]:
    """客户名模糊匹配现有往来单位（候选列表人工选，不自动绑定）。"""
    from app.modules.crm.models import Customer

    name = name.strip()
    if not name:
        return []
    rows = list(
        db.scalars(
            select(Customer)
            .where(Customer.deleted == 0, Customer.name.like(f"%{name}%"))
            .order_by(Customer.id)
            .limit(5)
        ).all()
    )
    if not rows and len(name) > 6:
        rows = list(
            db.scalars(
                select(Customer)
                .where(Customer.deleted == 0, Customer.name.like(f"%{name[:6]}%"))
                .order_by(Customer.id)
                .limit(5)
            ).all()
        )
    return [{"id": c.id, "name": c.name} for c in rows]


def ai_parse_contract(db: Session, current: User, filename: str, data: bytes) -> dict:
    """合同文件 → 字段草稿。pdf/docx/txt 走文本提取；jpg/png 走多模态视觉。不落库。"""
    from app.services import ai as ai_svc

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not ai_svc.feature_enabled(db, "contract_ocr"):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置或合同识别功能已停用")
    images = None
    if ext in ai_svc.TEXT_EXTS:
        text = ai_svc.extract_text(filename, data)
        user_msg = f"合同文件 {filename} 的内容如下：\n\n{text}"
    elif ext in ai_svc.IMAGE_EXTS:
        user_msg = "请识别这张合同图片，抽取合同字段。"
        images = [(data, f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}")]
    else:
        raise BizException(
            R.GENERIC_PARAM,
            f"不支持的文件类型：{ext or '无扩展名'}（限 {'/'.join(sorted(ai_svc.TEXT_EXTS | ai_svc.IMAGE_EXTS))}）",
        )
    messages = [
        {"role": "system", "content": CONTRACT_PARSE_SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="contract_ocr", messages=messages, user=current,
            biz_type="contract", prompt_version=CONTRACT_PARSE_PROMPT_VERSION, images=images,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试或手工填写") from exc
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请手工填写") from exc
    fields: dict = {}
    for k in PARSE_FIELDS:
        v = parsed.get(k)
        if k == "amount":
            try:
                fields[k] = float(v or 0)
            except (TypeError, ValueError):
                fields[k] = 0
        else:
            fields[k] = str(v or "").strip()[:500]
    return {
        "fields": fields,
        "customerCandidates": _customer_candidates(db, fields["customerName"]),
        "source": "ai",
    }


# ---------------- AI 合同风险审查（表单字段 + 可选合同原文 → 风险清单，仅展示不落库） ----------------

CONTRACT_RISK_PROMPT_VERSION = "v1"
CONTRACT_RISK_SYSTEM = (
    "你是合同风险审查助手。根据合同表单字段（JSON）"
    "与可能附带的合同原文，做条款风险检查，输出严格 JSON："
    '{"risks":[{"level":"high|mid|low","clause":"条款/方面","issue":"问题描述","suggestion":"修改建议"}],'
    '"missingClauses":["缺失条款名称"],"summary":"总体评价（50字内）"}。'
    "检查维度：付款条款（比例/节点/账期是否明确合理）、违约责任是否对等、金额/日期相互矛盾、"
    "（有原文时）金额大小写一致性；缺失条款参考：验收、保密、争议解决、不可抗力、知识产权。"
    "只输出 JSON，无风险时 risks 给空数组，拿不准的级别给 low。"
)
RISK_LEVELS = ("high", "mid", "low")

# 送审字段白名单（prompt 只放必要字段）
RISK_REVIEW_FIELDS = (
    "name", "customerName", "amount", "startDate", "endDate", "payCycle",
    "delivery", "sealType", "paymentOrg", "remark",
)


def parse_risk_review(raw: str) -> dict:
    """AI 输出 → 风险清单。无法解析抛 BizException(AI_PARSE_FAILED)。"""
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请人工复核条款") from exc

    risks: list[dict] = []
    for r in (parsed.get("risks") or [])[:10]:
        if not isinstance(r, dict):
            continue
        issue = str(r.get("issue") or "").strip()[:300]
        if not issue:
            continue
        level = str(r.get("level") or "low").lower()
        risks.append(
            {
                "level": level if level in RISK_LEVELS else "low",
                "clause": str(r.get("clause") or "").strip()[:100],
                "issue": issue,
                "suggestion": str(r.get("suggestion") or "").strip()[:300],
            }
        )
    missing = [
        str(x).strip()[:50] for x in (parsed.get("missingClauses") or []) if str(x).strip()
    ][:10]
    summary = str(parsed.get("summary") or "").strip()[:300]
    return {"risks": risks, "missingClauses": missing, "summary": summary}


def ai_risk_review(
    db: Session,
    current: User,
    fields: dict,
    text: str = "",
    images: list[tuple[bytes, str]] | None = None,
) -> dict:
    """合同风险审查入口：字段白名单 + 可选原文/图片 → 风险清单草稿（不落库）。"""
    from app.services import ai as ai_svc

    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置或合同风险审查功能已停用")

    safe_fields = {k: fields.get(k) for k in RISK_REVIEW_FIELDS if fields.get(k) not in (None, "")}
    parts = [f"合同表单字段：\n{json.dumps(safe_fields, ensure_ascii=False)}"]
    if text:
        parts.append(f"合同原文（截断）：\n{text[:ai_svc.MAX_EXTRACT_CHARS]}")
    elif not images:
        parts.append("（未提供合同原文，请仅按表单字段做基础审查，并在 missingClauses 中提示补充原文可复核项）")
    messages = [
        {"role": "system", "content": CONTRACT_RISK_SYSTEM},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db,
            feature="contract_risk",
            messages=messages,
            user=current,
            biz_type="contract",
            biz_id=int(fields.get("id") or 0) or None,
            prompt_version=CONTRACT_RISK_PROMPT_VERSION,
            images=images,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试或人工复核") from exc
    result = parse_risk_review(raw)
    result["withText"] = bool(text or images)
    return result

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

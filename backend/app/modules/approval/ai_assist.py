"""AI 审批助手：审批单快照 + 客户历史往来统计（权限内）→ 要点/风险/意见草稿。

仅生成建议，不落库；审批意见由人工引用修改后随正常审批动作提交。
上下文组装按 biz_type 分派，prompt 只放必要字段（快照值截断、历史仅聚合统计）。
"""

import json
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.deps import SUPER_ROLE
from app.core.exceptions import BizException
from app.modules.approval.graph import parse_json
from app.modules.approval.models import ApprovalCc, ApprovalInstance, ApprovalRecord, ApprovalTask
from app.modules.auth.models import User

ASSIST_PROMPT_VERSION = "v1"
ASSIST_LEVELS = ("high", "mid", "low")

ASSIST_SYSTEM = (
    "你是企业审批助手。根据审批单快照与历史往来统计，输出严格 JSON："
    '{"summary":"本单要点摘要（金额/单位/关键字段，80字内）",'
    '"highlights":["要点，最多5条"],'
    '"risks":[{"level":"high|mid|low","text":"风险描述"}]，最多5条，'
    '"opinion":"建议审批意见草稿（客观中立、供审批人引用修改，60字内）"}。'
    "风险参考角度：金额偏离历史均价、账期/付款条件异常、短期重复提交迹象、关键字段缺失；"
    "无风险则 risks 给空数组。只输出 JSON，不要输出其他内容。"
)

_SNAPSHOT_MAX_KEYS = 30
_SNAPSHOT_MAX_VAL = 200


def _can_access_instance(db: Session, inst: ApprovalInstance, user: User) -> bool:
    """实例相关人（发起/待办已办/被抄送）或有 approval:view 权限才可调用助手。"""
    if SUPER_ROLE in (user.role_codes or []) or "approval:view" in set(user.perm_codes or []):
        return True
    if inst.initiator_id == user.id:
        return True
    uid = user.id
    involved = db.scalar(
        select(func.count(ApprovalTask.id)).where(
            ApprovalTask.instance_id == inst.id, ApprovalTask.assignee_id == uid, ApprovalTask.deleted == 0
        )
    )
    if involved:
        return True
    return bool(
        db.scalar(
            select(func.count(ApprovalCc.id)).where(
                ApprovalCc.instance_id == inst.id, ApprovalCc.user_id == uid, ApprovalCc.deleted == 0
            )
        )
    )


def _truncate_snapshot(snap: dict) -> dict:
    """快照值转字符串并截断，防止 prompt 膨胀/泄露无关大字段。"""
    out: dict = {}
    for i, (k, v) in enumerate(snap.items()):
        if i >= _SNAPSHOT_MAX_KEYS:
            break
        if v is None or v == "":
            continue
        s = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        out[str(k)] = s[:_SNAPSHOT_MAX_VAL]
    return out


def _contract_history(db: Session, user: User, inst: ApprovalInstance) -> dict | None:
    """该客户历史合同统计（需 contract:list 权限）；到账合计另需 finance:settlement:list。"""
    if inst.biz_type != "contract":
        return None
    from app.modules.contract.models import Contract

    perms = set(user.perm_codes or [])
    privileged = SUPER_ROLE in (user.role_codes or [])
    if not (privileged or "contract:list" in perms):
        return None
    c = db.get(Contract, inst.biz_id)
    if not c or c.deleted:
        return None
    others = list(
        db.scalars(
            select(Contract).where(
                Contract.customer_id == c.customer_id,
                Contract.deleted == 0,
                Contract.id != c.id,
                Contract.status.in_(("approving", "approved")),
            )
        ).all()
    )
    amounts = [float(x.amount) for x in others if x.amount is not None]
    this_amount = float(c.amount or 0)
    avg = round(sum(amounts) / len(amounts), 2) if amounts else None
    deviation = round((this_amount - avg) / avg * 100, 1) if avg else None
    # 重复提交迹象：近 90 天同客户 ±10% 金额的合同数
    since = date.today() - timedelta(days=90)
    recent_similar = sum(
        1
        for x in others
        if x.create_time
        and x.create_time.date() >= since
        and this_amount > 0
        and x.amount is not None
        and abs(float(x.amount) - this_amount) / this_amount <= 0.1
    )
    out: dict = {
        "customerName": c.customer_name,
        "contractCount": len(others),
        "avgAmount": avg,
        "thisAmount": this_amount,
        "deviationPercent": deviation,
        "recentSimilarCount": recent_similar,
    }
    if privileged or "finance:settlement:list" in perms:
        from app.modules.finance.models import Payment, Settlement

        paid = db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(Settlement, Payment.settlement_id == Settlement.id)
            .where(Settlement.customer_id == c.customer_id, Settlement.deleted == 0, Payment.deleted == 0)
        ).scalar_one()
        out["paidTotal"] = float(paid)
    return out


def build_assist_context(db: Session, inst: ApprovalInstance, user: User) -> dict:
    """组装 prompt 上下文：单据快照（截断）+ 提交说明 + 历史统计（权限内）。"""
    snap = parse_json(inst.form_snapshot, {}) or {}
    submit_comment = ""
    first = db.scalar(
        select(ApprovalRecord)
        .where(ApprovalRecord.instance_id == inst.id, ApprovalRecord.deleted == 0)
        .order_by(ApprovalRecord.id)
        .limit(1)
    )
    if first and first.comment:
        submit_comment = first.comment[:200]
    ctx = {
        "title": inst.title,
        "bizType": inst.biz_type,
        "initiator": inst.initiator_name,
        "submitComment": submit_comment,
        "snapshot": _truncate_snapshot(snap),
    }
    history = _contract_history(db, user, inst)
    if history:
        ctx["customerHistory"] = history
    return ctx


def parse_assist_output(raw: str) -> dict:
    """AI 输出 → 结构化结果。无法解析/全空抛 BizException(AI_PARSE_FAILED)。"""
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请稍后再试") from exc

    summary = str(parsed.get("summary") or "").strip()[:500]
    highlights = [
        str(x).strip()[:200] for x in (parsed.get("highlights") or []) if str(x).strip()
    ][:5]
    risks: list[dict] = []
    for r in (parsed.get("risks") or [])[:5]:
        if not isinstance(r, dict):
            continue
        text = str(r.get("text") or "").strip()[:300]
        if not text:
            continue
        level = str(r.get("level") or "low").lower()
        risks.append({"level": level if level in ASSIST_LEVELS else "low", "text": text})
    opinion = str(parsed.get("opinion") or "").strip()[:500]
    if not (summary or highlights or risks or opinion):
        raise BizException(R.AI_PARSE_FAILED, "AI 输出为空，请稍后再试")
    return {"summary": summary, "highlights": highlights, "risks": risks, "opinion": opinion}


def ai_assist(db: Session, user: User, instance_id: int) -> dict:
    """审批助手入口：实例相关人可调；未配置/停用报 65001/65002。只返回建议，不落库。"""
    from app.services import ai as ai_svc

    inst = db.get(ApprovalInstance, instance_id)
    if not inst or inst.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if not _can_access_instance(db, inst, user):
        raise BizException(R.AUTH_FORBIDDEN)
    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置或审批助手功能已停用")

    ctx = build_assist_context(db, inst, user)
    messages = [
        {"role": "system", "content": ASSIST_SYSTEM},
        {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db,
            feature="approval_assist",
            messages=messages,
            user=user,
            biz_type=inst.biz_type,
            biz_id=inst.biz_id,
            prompt_version=ASSIST_PROMPT_VERSION,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc
    result = parse_assist_output(raw)
    # 回显历史统计，便于审批人核对 AI 风险判断的依据
    if "customerHistory" in ctx:
        result["customerHistory"] = ctx["customerHistory"]
    return result

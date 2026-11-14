"""AI 异常流程分析：滞留节点/审批人状态/组织缺人等确定性信号 + AI 分析与处理建议。

signals 由服务端确定性生成（不依赖 AI 判断）；AI 只产 analysis 与 suggestions 文本，
建议中的转办人选只信服务端按 userName 匹配回来的 userId（防 AI 编造 id）。
催办走独立 urge 端点（非 AI）：人工点击后才给当前待办人写站内通知并落审计。
"""

import json
import statistics
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.approval import engine
from app.modules.approval.graph import parse_json
from app.modules.approval.models import (
    ApprovalDefinition,
    ApprovalInstance,
    ApprovalRecord,
    ApprovalTask,
)
from app.modules.auth.models import User
from app.modules.oa.models import OaInstance
from app.modules.oa.service import _flow_of, _oa_by_id

ANOMALY_PROMPT_VERSION = "v1"
SUGGESTION_TYPES = ("urge", "transfer", "restart", "other")
_STUCK_WARN_HOURS = 24.0

ANOMALY_SYSTEM = (
    "你是流程运维助手。根据滞留审批单的信息与系统检测到的异常信号，输出严格 JSON："
    '{"analysis":"滞留原因分析（结合信号，200字内）",'
    '"suggestions":[{"type":"urge|transfer|restart|other","text":"建议说明（60字内）",'
    '"userName":"转办/加签建议人选姓名（仅 transfer 时需要，须来自给定候选名单）"}]，最多4条}。'
    "只输出 JSON，不要输出其他内容。"
)


def _pending_tasks(db: Session, flow: ApprovalInstance) -> list[ApprovalTask]:
    return list(
        db.scalars(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == flow.id,
                ApprovalTask.status == "pending",
                ApprovalTask.deleted == 0,
            ).order_by(ApprovalTask.id)
        ).all()
    )


def _median_finish_hours(db: Session, form_key: str, exclude_id: int) -> float | None:
    """同表单历史已完成实例的处理总时长中位数（小时，最近 20 条），作滞留参考线。"""
    rows = db.scalars(
        select(OaInstance)
        .where(
            OaInstance.form_key == form_key,
            OaInstance.deleted == 0,
            OaInstance.id != exclude_id,
            OaInstance.status.in_(("approved", "rejected")),
            OaInstance.finished_at.is_not(None),
        )
        .order_by(OaInstance.id.desc())
        .limit(20)
    ).all()
    hours = [
        (r.finished_at - r.create_time).total_seconds() / 3600
        for r in rows
        if r.create_time and r.finished_at and r.finished_at > r.create_time
    ]
    return round(statistics.median(hours), 1) if hours else None


def build_signals(
    db: Session, inst: OaInstance, flow: ApprovalInstance, tasks: list[ApprovalTask]
) -> tuple[dict, list[str]]:
    """确定性信号：审批人账号停用/锁定、滞留时长 vs 历史中位、组织节点解析不到人。"""
    now = datetime.now()
    stuck = {
        "nodeName": tasks[0].node_name if tasks else "",
        "pending": [
            {
                "assigneeId": t.assignee_id,
                "assigneeName": t.assignee_name,
                "hours": round(max(0.0, (now - t.create_time).total_seconds() / 3600), 1)
                if t.create_time else 0.0,
            }
            for t in tasks
        ],
    }
    signals: list[str] = []
    users = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.id.in_([t.assignee_id for t in tasks]))
        ).all()
    } if tasks else {}
    for t in tasks:
        u = users.get(t.assignee_id)
        if u is None or u.deleted:
            signals.append(f"审批人 {t.assignee_name} 账号已删除")
        elif u.status != "enabled":
            signals.append(f"审批人 {t.assignee_name} 账号已{('停用' if u.status == 'disabled' else '锁定')}")
    median = _median_finish_hours(db, inst.form_key, inst.id)
    if stuck["pending"]:
        worst = max(p["hours"] for p in stuck["pending"])
        if median is not None and worst > median:
            signals.append(f"当前节点已滞留 {worst} 小时，超过同表单历史中位处理时长 {median} 小时")
        elif worst >= _STUCK_WARN_HOURS:
            signals.append(f"当前节点已滞留 {worst} 小时")
    # 组织缺人迹象：当前节点定义是组织审批人类型且解析不到人
    definition = db.get(ApprovalDefinition, flow.definition_id) if flow.definition_id else None
    seqs = parse_json(flow.current_node_ids, None) or ([flow.current_seq] if flow.current_seq else [])
    nodes = [n for n in (definition.nodes if definition else []) if n.deleted == 0 and n.seq in seqs]
    for node in nodes:
        if node.approver_type in engine.ORG_APPROVER_TYPES:
            resolved, notes = engine._resolve_org_assignees(db, node, flow.initiator_id)
            if not resolved:
                signals.append(f"节点「{node.node_name}」组织审批人解析不到人：{'；'.join(notes) or '无可用人员'}")
    return stuck, signals


def parse_anomaly_output(db: Session, raw: str) -> dict:
    """AI 输出 → {analysis, suggestions}。userId 只信服务端按姓名匹配；空输出抛 65004。"""
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请稍后再试") from exc
    analysis = str(parsed.get("analysis") or "").strip()[:1000]
    names = {
        str(s.get("userName") or "").strip()
        for s in (parsed.get("suggestions") or [])
        if isinstance(s, dict) and str(s.get("userName") or "").strip()
    }
    name_to_user: dict[str, User] = {}
    if names:
        for u in db.scalars(
            select(User).where(User.status == "enabled", User.deleted == 0)
        ).all():
            if u.name in names or u.username in names:
                name_to_user[u.name] = u
                name_to_user[u.username] = u
    suggestions: list[dict] = []
    for s in (parsed.get("suggestions") or [])[:4]:
        if not isinstance(s, dict):
            continue
        text = str(s.get("text") or "").strip()[:200]
        if not text:
            continue
        stype = str(s.get("type") or "other").strip().lower()
        item: dict = {"type": stype if stype in SUGGESTION_TYPES else "other", "text": text}
        uname = str(s.get("userName") or "").strip()
        if uname and uname in name_to_user:
            item["userId"] = name_to_user[uname].id
            item["userName"] = name_to_user[uname].name or name_to_user[uname].username
        suggestions.append(item)
    if not analysis and not suggestions:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出为空，请稍后再试")
    return {"analysis": analysis, "suggestions": suggestions}


def ai_anomaly(db: Session, user: User, inst_id: int) -> dict:
    """异常分析入口（oa:admin:handle）：仅 running 且有审批实例的单据可分析。"""
    from app.services import ai as ai_svc

    inst = _oa_by_id(db, inst_id)
    flow = _flow_of(db, inst)
    if flow.status != "running":
        raise BizException(R.OA_INVALID_STATE, "仅处理中的单据可做异常分析")
    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置或异常分析功能已停用")

    tasks = _pending_tasks(db, flow)
    stuck, signals = build_signals(db, inst, flow, tasks)
    records = db.scalars(
        select(ApprovalRecord)
        .where(ApprovalRecord.instance_id == flow.id, ApprovalRecord.deleted == 0)
        .order_by(ApprovalRecord.id.desc())
        .limit(5)
    ).all()
    candidates = [
        {"id": u.id, "name": u.name or u.username}
        for u in db.scalars(
            select(User).where(User.status == "enabled", User.deleted == 0).order_by(User.id).limit(50)
        ).all()
    ]
    ctx = {
        "instance": {
            "displayNo": inst.display_no,
            "formName": inst.form_name,
            "applicantName": inst.applicant_name,
            "createTime": str(inst.create_time or "")[:19],
        },
        "stuck": stuck,
        "signals": signals,
        "recentRecords": [
            {"action": r.action, "nodeName": r.node_name, "operatorName": r.operator_name,
             "comment": (r.comment or "")[:100], "at": str(r.at or "")[:19]}
            for r in records
        ],
        "transferCandidates": candidates,
    }
    messages = [
        {"role": "system", "content": ANOMALY_SYSTEM},
        {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db,
            feature="flow_anomaly",
            messages=messages,
            user=user,
            biz_type="oa",
            biz_id=inst.id,
            prompt_version=ANOMALY_PROMPT_VERSION,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc
    result = parse_anomaly_output(db, raw)
    result["stuck"] = stuck
    result["signals"] = signals
    return result

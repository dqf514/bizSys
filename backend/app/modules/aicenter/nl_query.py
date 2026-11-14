"""自然语言问数：AI 仅产出白名单查询意图，后端按预定义聚合模板执行（禁止 AI 生成自由 SQL）。

安全设计：
- AI 输出仅允许 {domain, params, timeRange, subject}；domain 必须命中 DOMAINS 白名单，否则 65004；
- 每个域固定：所需列表权限码、status 参数值域白名单、手写 SQLAlchemy 聚合查询、答案文案与跳转链接；
- params 仅识别 status/customerName，其余键直接丢弃；customerName 只做 LIKE 过滤参数绑定；
- subject=self 由后端解析为当前用户 id（AI 不得输出任何用户标识）；
- 无对应列表权限 → 20002；未配置 AI → 65001；功能停用/配额 → 网关 65002/65003。
"""

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.deps import SUPER_ROLE
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.contract.models import Contract
from app.modules.finance.models import Payment, Settlement
from app.modules.hr.models import HrTimesheet
from app.modules.procurement.models import PurchaseRequest
from app.modules.sales.models import SalesQuotation
from app.modules.task.models import Task
from app.services import ai as ai_svc
from app.services import prompts

TASK_STATUS_CN = {
    "draft": "草稿", "approving": "审批中", "rejected": "已驳回", "in_progress": "进行中",
    "finished": "已完成", "settled": "已结算", "stopped": "已终止",
}
CONTRACT_STATUS_CN = {
    "draft": "草稿", "approving": "审批中", "approved": "已批准", "rejected": "已驳回", "voided": "已作废",
}
SETTLE_STATUS_CN = {"pending": "待开票", "invoicing": "开票审批中", "invoiced": "已开票", "paid": "已到账"}
TIMESHEET_STATUS_CN = {"draft": "草稿", "submitted": "已提交"}
QUOTE_STATUS_CN = {
    "draft": "草稿", "approving": "审批中", "approved": "已批准", "rejected": "已驳回",
    "sent": "已发送", "accepted": "已接受", "declined": "已拒绝", "voided": "已作废",
}


@dataclass(frozen=True)
class Intent:
    domain: str
    status: str
    customer: str
    time_from: date | None
    time_to: date | None
    subject_self: bool


def _money(v: Any) -> float:
    return float(v or 0)


def _fmt_money(v: Any) -> str:
    return f"¥{_money(v):,.2f}"


def _range_desc(intent: Intent) -> str:
    if intent.time_from or intent.time_to:
        return f"{intent.time_from or '…'} 至 {intent.time_to or '…'}，"
    return ""


def _parse_date(v: Any) -> date | None:
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return datetime.strptime(v.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_intent(raw: str, allowed_status: dict[str, tuple[str, ...]]) -> Intent:
    """解析并白名单校验 AI 意图；解析失败/非法域 → 65004（无法理解）。"""
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "无法理解该问题，请换个问法或改用列表筛选") from exc
    if not isinstance(data, dict):
        raise BizException(R.AI_PARSE_FAILED, "无法理解该问题，请换个问法或改用列表筛选")
    domain = data.get("domain")
    if domain not in allowed_status:
        raise BizException(R.AI_PARSE_FAILED, "暂不支持该类问题，可尝试任务量/合同额/应收/结算/工时/采购/报价")
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    status = str(params.get("status") or "").strip()
    if status and status not in allowed_status[domain]:
        status = ""  # 非法状态值降级为不按状态过滤（不执行任何越权语义）
    customer = str(params.get("customerName") or "").strip()[:64]
    tr = data.get("timeRange") if isinstance(data.get("timeRange"), dict) else {}
    time_from, time_to = _parse_date(tr.get("from")), _parse_date(tr.get("to"))
    if time_from and time_to and time_from > time_to:
        time_from, time_to = time_to, time_from
    return Intent(
        domain=domain,
        status=status,
        customer=customer,
        time_from=time_from,
        time_to=time_to,
        subject_self=data.get("subject") == "self",
    )


def _time_conds(col, intent: Intent) -> list:
    conds = []
    if intent.time_from:
        conds.append(col >= intent.time_from)
    if intent.time_to:
        conds.append(col <= datetime.combine(intent.time_to, datetime.max.time()))
    return conds


def _rows_by_status(pairs: list[tuple[str, int]], labels: dict[str, str]) -> list[dict]:
    return [{"label": labels.get(s, s), "value": n} for s, n in pairs]


def _answer(intent: Intent, *, label: str, text: str, rows: list[dict], link: str, criteria: str) -> dict:
    return {
        "domain": intent.domain,
        "domainLabel": label,
        "text": text,
        "rows": rows,
        "link": link,
        "timeRange": {
            "from": intent.time_from.isoformat() if intent.time_from else "",
            "to": intent.time_to.isoformat() if intent.time_to else "",
        },
        "criteria": criteria,
    }


# ---------------- 各域查询模板（手写 SQLAlchemy，固定形态） ----------------


def _run_task_volume(db: Session, user: User, intent: Intent) -> dict:
    conds: list = [Task.deleted == 0]
    if intent.subject_self:
        conds.append(Task.owner_id == user.id)
    if intent.customer:
        conds.append(Task.customer_name.like(f"%{intent.customer}%"))
    if intent.status:
        conds.append(Task.status == intent.status)
    conds += _time_conds(Task.create_time, intent)
    pairs = db.execute(select(Task.status, func.count()).where(*conds).group_by(Task.status)).all()
    total = sum(n for _, n in pairs)
    text = f"{_range_desc(intent)}共 {total} 个任务"
    if pairs and not intent.status:
        text += "：" + "，".join(f"{TASK_STATUS_CN.get(s, s)} {n}" for s, n in pairs)
    return _answer(
        intent, label="任务量", text=text, rows=_rows_by_status(pairs, TASK_STATUS_CN), link="/task/tasks",
        criteria="口径：按任务创建时间过滤；“我”=当前用户作为负责人；含全部未删除任务。",
    )


def _run_contract_amount(db: Session, user: User, intent: Intent) -> dict:
    conds: list = [Contract.deleted == 0]
    if intent.subject_self:
        conds.append(Contract.handler_id == user.id)
    if intent.customer:
        conds.append(Contract.customer_name.like(f"%{intent.customer}%"))
    if intent.status:
        conds.append(Contract.status == intent.status)
    conds += _time_conds(Contract.create_time, intent)
    pairs = db.execute(
        select(Contract.status, func.count(), func.coalesce(func.sum(Contract.amount), 0))
        .where(*conds)
        .group_by(Contract.status)
    ).all()
    total_n = sum(n for _, n, _ in pairs)
    total_amt = sum(_money(a) for _, _, a in pairs)
    text = f"{_range_desc(intent)}共 {total_n} 份合同，金额合计 {_fmt_money(total_amt)}"
    rows = [
        {"label": CONTRACT_STATUS_CN.get(s, s), "value": f"{n} 份 / {_fmt_money(a)}"} for s, n, a in pairs
    ]
    return _answer(
        intent, label="合同额", text=text, rows=rows, link="/contract/contracts",
        criteria="口径：按合同创建时间过滤；金额=合同金额合计；“我”=当前用户作为经办人；含全部未删除合同。",
    )


def _run_receivable(db: Session, user: User, intent: Intent) -> dict:
    """应收未收 = 已开票/已到账状态结算单的结算金额 − 其已登记到账金额。"""
    conds: list = [Settlement.deleted == 0, Settlement.status.in_(("invoiced", "paid"))]
    if intent.customer:
        conds.append(Settlement.customer_name.like(f"%{intent.customer}%"))
    conds += _time_conds(Settlement.create_time, intent)
    settlements = list(db.scalars(select(Settlement).where(*conds)))
    paid_map: dict[int, Decimal] = {}
    if settlements:
        paid_map = dict(
            db.execute(
                select(Payment.settlement_id, func.coalesce(func.sum(Payment.amount), 0))
                .where(Payment.deleted == 0, Payment.settlement_id.in_([s.id for s in settlements]))
                .group_by(Payment.settlement_id)
            ).all()
        )
    outstanding = [
        (s, _money(s.amount) - _money(paid_map.get(s.id)))
        for s in settlements
    ]
    total = sum(v for _, v in outstanding)
    owing = [(s, v) for s, v in outstanding if v > 0.005]
    owing.sort(key=lambda x: x[1], reverse=True)
    text = f"{_range_desc(intent)}应收未收合计 {_fmt_money(total)}（涉及 {len(owing)} 笔结算单）"
    rows = [
        {"label": f"{s.settlement_no} {s.customer_name}".strip(), "value": _fmt_money(v)} for s, v in owing[:10]
    ]
    return _answer(
        intent, label="应收未收", text=text, rows=rows, link="/finance/settlements",
        criteria="口径：已开票/已到账状态结算单的结算金额 − 已登记到账金额；结算单按创建时间过滤。",
    )


def _run_settlement(db: Session, user: User, intent: Intent) -> dict:
    conds: list = [Settlement.deleted == 0]
    if intent.customer:
        conds.append(Settlement.customer_name.like(f"%{intent.customer}%"))
    if intent.status:
        conds.append(Settlement.status == intent.status)
    conds += _time_conds(Settlement.create_time, intent)
    pairs = db.execute(
        select(Settlement.status, func.count(), func.coalesce(func.sum(Settlement.amount), 0))
        .where(*conds)
        .group_by(Settlement.status)
    ).all()
    total_n = sum(n for _, n, _ in pairs)
    total_amt = sum(_money(a) for _, _, a in pairs)
    text = f"{_range_desc(intent)}共 {total_n} 笔结算单，结算金额合计 {_fmt_money(total_amt)}"
    rows = [{"label": SETTLE_STATUS_CN.get(s, s), "value": f"{n} 笔 / {_fmt_money(a)}"} for s, n, a in pairs]
    return _answer(
        intent, label="结算", text=text, rows=rows, link="/finance/settlements",
        criteria="口径：按结算单创建时间过滤；金额=结算金额合计；含全部状态。",
    )


def _run_work_hours(db: Session, user: User, intent: Intent) -> dict:
    """工时域只开放"我的工时"（hr:timesheet:list 即我的列表权限），强制 user_id=当前用户。"""
    conds: list = [HrTimesheet.deleted == 0, HrTimesheet.user_id == user.id]
    if intent.customer:
        conds.append(HrTimesheet.customer_name.like(f"%{intent.customer}%"))
    if intent.status:
        conds.append(HrTimesheet.status == intent.status)
    if intent.time_from:
        conds.append(HrTimesheet.work_date >= intent.time_from)
    if intent.time_to:
        conds.append(HrTimesheet.work_date <= intent.time_to)
    total_hours, entry_count = db.execute(
        select(func.coalesce(func.sum(HrTimesheet.hours), 0), func.count()).where(*conds)
    ).one()
    by_task = db.execute(
        select(HrTimesheet.task_name, func.coalesce(func.sum(HrTimesheet.hours), 0))
        .where(*conds)
        .group_by(HrTimesheet.task_name)
        .order_by(func.sum(HrTimesheet.hours).desc())
        .limit(10)
    ).all()
    text = f"{_range_desc(intent)}我的工时合计 {_money(total_hours):.1f} 小时（{int(entry_count)} 条填报）"
    rows = [{"label": name or "-", "value": f"{_money(h):.1f} h"} for name, h in by_task]
    return _answer(
        intent, label="工时", text=text, rows=rows, link="/hr/timesheets",
        criteria="口径：仅统计本人填报（草稿+已提交，可用状态收窄）；按工作日期过滤。",
    )


def _run_procurement(db: Session, user: User, intent: Intent) -> dict:
    conds: list = [PurchaseRequest.deleted == 0]
    if intent.subject_self:
        conds.append(PurchaseRequest.create_by == user.id)
    if intent.status:
        conds.append(PurchaseRequest.status == intent.status)
    conds += _time_conds(PurchaseRequest.create_time, intent)
    pairs = db.execute(
        select(PurchaseRequest.status, func.count(), func.coalesce(func.sum(PurchaseRequest.budget_amount), 0))
        .where(*conds)
        .group_by(PurchaseRequest.status)
    ).all()
    total_n = sum(n for _, n, _ in pairs)
    total_amt = sum(_money(a) for _, _, a in pairs)
    text = f"{_range_desc(intent)}共 {total_n} 笔采购申请，预算合计 {_fmt_money(total_amt)}"
    rows = [
        {"label": CONTRACT_STATUS_CN.get(s, s), "value": f"{n} 笔 / {_fmt_money(a)}"} for s, n, a in pairs
    ]
    return _answer(
        intent, label="采购申请", text=text, rows=rows, link="/procurement/requests",
        criteria="口径：按申请创建时间过滤；金额=预算金额合计；“我”=当前用户作为创建人。",
    )


def _run_quotation(db: Session, user: User, intent: Intent) -> dict:
    conds: list = [SalesQuotation.deleted == 0]
    if intent.subject_self:
        conds.append(SalesQuotation.create_by == user.id)
    if intent.customer:
        conds.append(SalesQuotation.customer_name.like(f"%{intent.customer}%"))
    if intent.status:
        conds.append(SalesQuotation.status == intent.status)
    conds += _time_conds(SalesQuotation.create_time, intent)
    pairs = db.execute(
        select(SalesQuotation.status, func.count(), func.coalesce(func.sum(SalesQuotation.total_amount), 0))
        .where(*conds)
        .group_by(SalesQuotation.status)
    ).all()
    total_n = sum(n for _, n, _ in pairs)
    total_amt = sum(_money(a) for _, _, a in pairs)
    text = f"{_range_desc(intent)}共 {total_n} 份报价单，金额合计 {_fmt_money(total_amt)}"
    rows = [{"label": QUOTE_STATUS_CN.get(s, s), "value": f"{n} 份 / {_fmt_money(a)}"} for s, n, a in pairs]
    return _answer(
        intent, label="报价", text=text, rows=rows, link="/sales/quotations",
        criteria="口径：按报价单创建时间过滤；金额=报价合计（服务端重算值）；“我”=当前用户作为创建人。",
    )


@dataclass(frozen=True)
class DomainSpec:
    label: str
    perms: tuple[str, ...]
    statuses: tuple[str, ...]
    run: Any


DOMAINS: dict[str, DomainSpec] = {
    "task_volume": DomainSpec("任务量", ("task:list",), tuple(TASK_STATUS_CN), _run_task_volume),
    "contract_amount": DomainSpec("合同额", ("contract:list",), tuple(CONTRACT_STATUS_CN), _run_contract_amount),
    "receivable": DomainSpec("应收未收", ("finance:settlement:list", "finance:payment:list"), (), _run_receivable),
    "settlement": DomainSpec("结算", ("finance:settlement:list",), tuple(SETTLE_STATUS_CN), _run_settlement),
    "work_hours": DomainSpec("工时", ("hr:timesheet:list",), tuple(TIMESHEET_STATUS_CN), _run_work_hours),
    "procurement": DomainSpec("采购申请", ("procurement:request:list",), tuple(CONTRACT_STATUS_CN), _run_procurement),
    "quotation": DomainSpec("报价", ("sales:quote:list",), tuple(QUOTE_STATUS_CN), _run_quotation),
}


def ask(db: Session, user: User, question: str, context: dict | None = None) -> dict:
    """问数主流程：AI 意图解析 → 白名单校验 → 权限校验 → 模板执行 → 答案卡片。"""
    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置，请联系管理员")
    # 功能停用由 gateway_chat 抛 AiFeatureDisabled（65002），与配额 65003 一并透传

    user_msg_parts = [f"今天日期：{date.today().isoformat()}"]
    if context:
        ctx_from, ctx_to = context.get("timeFrom") or "", context.get("timeTo") or ""
        if ctx_from or ctx_to:
            user_msg_parts.append(f"上一轮查询时间范围：{ctx_from or '…'} 至 {ctx_to or '…'}（本轮未提新时间则沿用）")
    user_msg_parts.append(f"问题：{question}")
    messages = [
        {"role": "system", "content": prompts.get("nl_query")["system"]},
        {"role": "user", "content": "\n".join(user_msg_parts)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="nl_query", messages=messages, user=user,
            biz_type="nl_query", prompt_version=prompts.feature_version("nl_query"),
            json_mode=True, max_tokens=800,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc

    intent = parse_intent(raw, {k: v.statuses for k, v in DOMAINS.items()})
    spec = DOMAINS[intent.domain]
    if SUPER_ROLE not in user.role_codes:
        missing = [p for p in spec.perms if p not in user.perm_codes]
        if missing:
            raise BizException(R.AUTH_FORBIDDEN, f"暂无{spec.label}数据的查询权限")
    return spec.run(db, user, intent)

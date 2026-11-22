"""门户对外业务能力（F6 W3）：进度看板 / 报告查阅下载 / 对账单 / 样品交接单。

隔离口径（**三重**）：

1. 按 `partner.customer_id` 过滤 —— 只看本单位的单据；
2. 只暴露"对外口径"的状态（如报告只暴露 `sealed`，不含内部审批意见与审批人）；
3. 报告下载走**一次性下载码**（Redis 存，校验后即焚），链接可转发给同事。

所有查询只读，绝不把内部单据的审批人 / 意见 / 内部备注透出。
"""

import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.core.redis import get_redis
from app.modules.finance.models import Invoice, Payment, Settlement
from app.modules.portal.models import PartnerUser
from app.modules.report.models import Report, ReportFile
from app.modules.task.entrust import STATUS_CN as ENTRUST_STATUS_CN
from app.modules.task.models import Task, TaskEntrust
from app.modules.visitor.models import VisitorSampleHandover, VisitorVisit

# 一次性下载码：portal_dl:{partner_id}:{report_id} → code（30 分钟有效）
DL_KEY = "portal_dl:{partner_id}:{report_id}"
DL_TTL_SEC = 30 * 60

# 报告对外可见状态：仅"签章完成"的正式报告
REPORT_PUBLIC_STATUS = ("sealed",)

TASK_STATUS_CN = {
    "draft": "创建待提交",
    "approving": "立项审批中",
    "rejected": "已驳回",
    "in_progress": "分配执行中",
    "finished": "已完成",
    "settled": "已结算",
    "stopped": "已停止",
}
SETTLEMENT_STATUS_CN = {
    "approving": "结算审批中",
    "rejected": "已驳回",
    "pending": "待开票",
    "invoicing": "开票审批中",
    "invoiced": "已开票",
    "paid": "已到账",
}
INVOICE_STATUS_CN = {"approving": "审批中", "issued": "已开票"}
PAYMENT_STATUS_CN = {
    "draft": "待复核",
    "approving": "复核中",
    "confirmed": "已确认",
    "rejected": "已驳回",
}


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _customer_id(partner: PartnerUser) -> int:
    """自助业务必须先绑定往来单位。"""
    if not partner.customer_id:
        raise BizException(R.CRM_ACCOUNT_NOT_BOUND)
    return partner.customer_id


# ---------------- 进度看板 ----------------


def progress(db: Session, partner: PartnerUser) -> dict:
    """我的项目进度看板：委托 → 任务 → 报告 → 结算 → 开票 → 回款。"""
    cid = _customer_id(partner)

    entrusts = db.scalars(
        select(TaskEntrust)
        .where(TaskEntrust.customer_id == cid, TaskEntrust.deleted == 0)
        .order_by(TaskEntrust.id.desc())
        .limit(50)
    ).all()
    tasks = db.scalars(
        select(Task)
        .where(Task.customer_id == cid, Task.deleted == 0)
        .order_by(Task.id.desc())
        .limit(50)
    ).all()
    settlements = db.scalars(
        select(Settlement)
        .where(Settlement.customer_id == cid, Settlement.deleted == 0)
        .order_by(Settlement.id.desc())
        .limit(50)
    ).all()
    settlement_ids = [s.id for s in settlements]
    invoices = (
        db.scalars(
            select(Invoice)
            .where(Invoice.settlement_id.in_(settlement_ids), Invoice.deleted == 0)
            .order_by(Invoice.id.desc())
        ).all()
        if settlement_ids
        else []
    )
    payments = (
        db.scalars(
            select(Payment)
            .where(Payment.settlement_id.in_(settlement_ids), Payment.deleted == 0)
            .order_by(Payment.id.desc())
        ).all()
        if settlement_ids
        else []
    )
    task_ids = [t.id for t in tasks]
    report_counts: dict[int, int] = {}
    if task_ids:
        rows = db.execute(
            select(Report.task_id, func.count())
            .where(
                Report.task_id.in_(task_ids),
                Report.deleted == 0,
                Report.status.in_(REPORT_PUBLIC_STATUS),
            )
            .group_by(Report.task_id)
        ).all()
        report_counts = {int(r[0]): int(r[1]) for r in rows if r[0]}

    stages: list[dict] = []
    for e in entrusts:
        stages.append(
            {
                "stage": "entrust",
                "stageText": "委托受理",
                "refNo": e.entrust_no or "",
                "title": e.title,
                "status": e.status,
                "statusText": ENTRUST_STATUS_CN.get(e.status, e.status),
                "amount": float(e.amount) if e.amount is not None else None,
                "updatedAt": _t(e.update_time or e.create_time),
            }
        )
    for t in tasks:
        stages.append(
            {
                "stage": "task",
                "stageText": "任务执行",
                "refNo": t.task_no or "",
                "title": t.task_name,
                "status": t.status,
                "statusText": TASK_STATUS_CN.get(t.status, t.status),
                "progress": int(t.progress or 0),
                "reportCount": report_counts.get(t.id, 0),
                "updatedAt": _t(t.update_time or t.create_time),
            }
        )
    for s in settlements:
        stages.append(
            {
                "stage": "settlement",
                "stageText": "结算",
                "refNo": s.settlement_no or "",
                "title": s.customer_name or "",
                "status": s.status,
                "statusText": SETTLEMENT_STATUS_CN.get(s.status, s.status),
                "amount": float(s.amount) if s.amount is not None else None,
                "updatedAt": _t(s.update_time or s.create_time),
            }
        )
    for i in invoices:
        stages.append(
            {
                "stage": "invoice",
                "stageText": "开票",
                "refNo": i.invoice_no or "",
                "title": i.buyer_name or "",
                "status": i.status,
                "statusText": INVOICE_STATUS_CN.get(i.status, i.status),
                "amount": float(i.amount) if i.amount is not None else None,
                "updatedAt": _t(s.update_time or s.create_time),
            }
        )
    for p in payments:
        stages.append(
            {
                "stage": "payment",
                "stageText": "回款",
                "refNo": p.payment_no or "",
                "title": p.payer_name or "",
                "status": p.status,
                "statusText": PAYMENT_STATUS_CN.get(p.status, p.status),
                "amount": float(p.amount) if p.amount is not None else None,
                "updatedAt": _t(s.update_time or s.create_time),
            }
        )

    return {
        "stages": stages,
        "summary": {
            "entrustCount": len(entrusts),
            "taskCount": len(tasks),
            "settledAmount": round(sum(float(s.amount or 0) for s in settlements), 2),
            "invoicedAmount": round(sum(float(i.amount or 0) for i in invoices), 2),
            "paidAmount": round(sum(float(p.amount or 0) for p in payments), 2),
        },
    }


# ---------------- 报告查阅 / 下载 ----------------


def _report_out(r: Report) -> dict:
    return {
        "id": r.id,
        "reportNo": r.report_no or "",
        "fileName": r.file_name or "",
        "status": r.status,
        "statusText": "已签章",
        "taskId": r.task_id,
        "sealedAt": _t(r.seal_time),
        "createTime": _t(r.create_time),
    }


def my_reports(db: Session, partner: PartnerUser) -> list[dict]:
    """本客户任务下、已签章的正式报告（不含内部审批信息）。"""
    cid = _customer_id(partner)
    task_ids = [
        int(t)
        for t in db.scalars(select(Task.id).where(Task.customer_id == cid, Task.deleted == 0)).all()
    ]
    if not task_ids:
        return []
    rows = db.scalars(
        select(Report)
        .where(
            Report.task_id.in_(task_ids),
            Report.deleted == 0,
            Report.status.in_(REPORT_PUBLIC_STATUS),
        )
        .order_by(Report.id.desc())
    ).all()
    return [_report_out(r) for r in rows]


def _load_own_report(db: Session, partner: PartnerUser, report_id: int) -> Report:
    cid = _customer_id(partner)
    r = db.get(Report, report_id)
    if not r or r.deleted or r.status not in REPORT_PUBLIC_STATUS:
        raise BizException(R.GENERIC_NOT_FOUND, "报告不存在")
    task = db.get(Task, r.task_id) if r.task_id else None
    if not task or task.customer_id != cid:
        raise BizException(R.VISITOR_FORBIDDEN, "无权访问该报告")
    return r


def issue_download_code(db: Session, partner: PartnerUser, report_id: int) -> dict:
    """签发一次性下载码（30 分钟有效，可转发给同事）。"""
    r = _load_own_report(db, partner, report_id)
    code = secrets.token_hex(8)
    get_redis().set(
        DL_KEY.format(partner_id=partner.id, report_id=r.id), code, ex=DL_TTL_SEC
    )
    return {"reportId": r.id, "code": code, "expiresIn": DL_TTL_SEC}


def consume_download_code(db: Session, partner: PartnerUser, report_id: int, code: str) -> Report:
    """校验并**消费**下载码（一次性）。"""
    r = _load_own_report(db, partner, report_id)
    key = DL_KEY.format(partner_id=partner.id, report_id=report_id)
    stored = get_redis().get(key)
    if not stored or not code or stored != code:
        raise BizException(R.PORTAL_DOWNLOAD_CODE_INVALID)
    get_redis().delete(key)  # 一次性：校验后即焚
    return r


def report_file(db: Session, r: Report) -> tuple[ReportFile, object]:
    """取报告文件（优先签章后的 PDF）。"""
    from app.modules.report import service as report_svc

    fid = r.pdf_file_id or r.file_id
    f = db.get(ReportFile, fid) if fid else None
    if not f or f.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "文件不存在")
    dest = report_svc.file_path(f)
    if not dest.exists():
        raise BizException(R.GENERIC_NOT_FOUND, "文件已丢失")
    return f, dest


# ---------------- 对账单 ----------------


def billing(db: Session, partner: PartnerUser) -> dict:
    """对账单：结算单 + 开票 + 回款（按本客户过滤）。"""
    cid = _customer_id(partner)
    settlements = db.scalars(
        select(Settlement)
        .where(Settlement.customer_id == cid, Settlement.deleted == 0)
        .order_by(Settlement.id.desc())
    ).all()
    sids = [s.id for s in settlements]
    invoices = (
        db.scalars(select(Invoice).where(Invoice.settlement_id.in_(sids), Invoice.deleted == 0)).all()
        if sids
        else []
    )
    payments = (
        db.scalars(select(Payment).where(Payment.settlement_id.in_(sids), Payment.deleted == 0)).all()
        if sids
        else []
    )
    inv_by_s: dict[int, list[Invoice]] = {}
    for i in invoices:
        inv_by_s.setdefault(i.settlement_id, []).append(i)
    pay_by_s: dict[int, list[Payment]] = {}
    for p in payments:
        pay_by_s.setdefault(p.settlement_id, []).append(p)

    items = []
    for s in settlements:
        invs = inv_by_s.get(s.id, [])
        pays = pay_by_s.get(s.id, [])
        items.append(
            {
                "settlementId": s.id,
                "settlementNo": s.settlement_no or "",
                "taskNo": s.task_no or "",
                "amount": float(s.amount) if s.amount is not None else None,
                "invoiceableAmount": float(s.invoiceable_amount) if s.invoiceable_amount is not None else None,
                "status": s.status,
                "statusText": SETTLEMENT_STATUS_CN.get(s.status, s.status),
                "invoices": [
                    {
                        "invoiceNo": i.invoice_no or "",
                        "amount": float(i.amount) if i.amount is not None else None,
                        "status": i.status,
                        "statusText": INVOICE_STATUS_CN.get(i.status, i.status),
                        "invoiceDate": i.invoice_date.strftime("%Y-%m-%d") if i.invoice_date else "",
                    }
                    for i in invs
                ],
                "payments": [
                    {
                        "paymentNo": p.payment_no or "",
                        "amount": float(p.amount) if p.amount is not None else None,
                        "status": p.status,
                        "statusText": PAYMENT_STATUS_CN.get(p.status, p.status),
                        "paidAt": _t(p.paid_at),
                    }
                    for p in pays
                ],
                "settledAmount": round(sum(float(i.amount or 0) for i in invs), 2),
                "paidAmount": round(sum(float(p.amount or 0) for p in pays), 2),
                "createTime": _t(s.create_time),
            }
        )
    return {
        "items": items,
        "summary": {
            "totalAmount": round(sum(float(s.amount or 0) for s in settlements), 2),
            "invoicedAmount": round(sum(float(i.amount or 0) for i in invoices), 2),
            "paidAmount": round(sum(float(p.amount or 0) for p in payments), 2),
            "pendingAmount": round(
                sum(
                    float(s.amount or 0)
                    - sum(float(p.amount or 0) for p in pay_by_s.get(s.id, []))
                    for s in settlements
                ),
                2,
            ),
        },
    }


# ---------------- 样品 / 样车交接单 ----------------


def handovers(db: Session, partner: PartnerUser) -> list[dict]:
    """样品 / 样车交接单（通过访客单关联本单位）。"""
    cid = _customer_id(partner)
    visit_ids = [
        int(v)
        for v in db.scalars(
            select(VisitorVisit.id).where(
                VisitorVisit.customer_id == cid, VisitorVisit.deleted == 0
            )
        ).all()
    ]
    if not visit_ids:
        return []
    rows = db.scalars(
        select(VisitorSampleHandover)
        .where(
            VisitorSampleHandover.visit_id.in_(visit_ids),
            VisitorSampleHandover.deleted == 0,
        )
        .order_by(VisitorSampleHandover.id.desc())
    ).all()
    return [
        {
            "id": h.id,
            "handoverNo": h.handover_no or "",
            "sampleNo": h.sample_no or "",
            "sampleName": h.sample_name or "",
            "sampleType": h.sample_type,
            "qty": h.qty,
            "handoverUserName": h.handover_user_name or "",
            "receiveUserName": h.receive_user_name or "",
            "handoverAt": _t(h.handover_at),
            "status": h.status,
            "statusText": "已交接" if h.status == "done" else "已归还",
            "visitId": h.visit_id,
        }
        for h in rows
    ]

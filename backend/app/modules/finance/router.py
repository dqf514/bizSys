"""财务路由 /api/v1/finance：结算单 / 发票登记 / 到账登记。"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.admin.models import Notify
from app.modules.approval import service as approval_svc
from app.modules.auth.models import User
from app.modules.finance import schemas as S
from app.modules.finance import service as svc
from app.modules.finance.models import Invoice, Payment, Settlement, SettlementConfirmRecord
from app.modules.task import service as task_svc
from app.modules.task.models import Task
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import next_no

router = APIRouter(prefix="/finance", tags=["finance"], route_class=EnvelopeRoute)

STATUS_CN = {
    "approving": "结算审批中",
    "rejected": "已驳回",
    "pending": "待开票",
    "invoicing": "开票审批中",
    "invoiced": "已开票",
    "paid": "已到账",
}

SETTLEMENT_EXPORT_COLS = [
    {"key": "settlementNo", "label": "结算单号", "width": 20},
    {"key": "taskNo", "label": "任务编号", "width": 20},
    {"key": "customerName", "label": "客户名称", "width": 26},
    {"key": "contractNo", "label": "合同号", "width": 20},
    {"key": "amount", "label": "结算金额(元)", "width": 14},
    {"key": "invoiceableAmount", "label": "可开票金额(元)", "width": 16},
    {"key": "status", "label": "状态", "width": 12},
    {"key": "remark", "label": "备注", "width": 24},
    {"key": "createTime", "label": "创建时间", "width": 19},
]

INVOICE_STATUS_CN = {
    "approving": "审批中",
    "issued": "已开票",
}

INVOICE_EXPORT_COLS = [
    {"key": "invoiceNo", "label": "发票号", "width": 20},
    {"key": "settlementNo", "label": "结算单号", "width": 20},
    {"key": "taskNo", "label": "任务编号", "width": 20},
    {"key": "customerName", "label": "客户名称", "width": 26},
    {"key": "amount", "label": "开票金额(元)", "width": 14},
    {"key": "invoiceDate", "label": "开票日期", "width": 12},
    {"key": "status", "label": "状态", "width": 12},
    {"key": "createBy", "label": "登记人", "width": 12},
    {"key": "createTime", "label": "申请时间", "width": 19},
]

PAYMENT_EXPORT_COLS = [
    {"key": "paymentNo", "label": "到账单号", "width": 20},
    {"key": "settlementNo", "label": "结算单号", "width": 20},
    {"key": "payType", "label": "到账方式", "width": 12},
    {"key": "payerName", "label": "付款方", "width": 24},
    {"key": "payerAccount", "label": "付款账号", "width": 20},
    {"key": "amount", "label": "金额(元)", "width": 14},
    {"key": "bank", "label": "付款银行", "width": 20},
    {"key": "paidAt", "label": "到账日期", "width": 12},
    {"key": "remark", "label": "备注", "width": 24},
    {"key": "createTime", "label": "创建时间", "width": 19},
]


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _d(v) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return v or ""


def _money(v: Decimal | None):
    return float(v) if v is not None else None


def _user_names(db: Session, ids) -> dict[int, str]:
    """create_by 存的是用户 id，展示层统一解析为姓名（批量查询，避免 N+1）。"""
    uid_set = {i for i in ids if i}
    if not uid_set:
        return {}
    return dict(db.execute(select(User.id, User.name).where(User.id.in_(uid_set))).all())


def _settlement_out(s: Settlement, users: dict[int, str]) -> dict:
    return {
        "id": s.id,
        "settlementNo": s.settlement_no,
        "taskId": s.task_id,
        "taskNo": s.task_no,
        "customerName": s.customer_name,
        "contractNo": s.contract_no,
        "contractId": s.contract_id,
        "customerId": s.customer_id,
        "amount": _money(s.amount),
        "invoiceableAmount": _money(s.invoiceable_amount),
        "status": s.status,
        "statusText": STATUS_CN.get(s.status, s.status),
        "remark": s.remark or "",
        "approvalInstanceId": s.approval_instance_id,
        "confirmStatus": s.confirm_status or "",
        "confirmBy": users.get(s.confirm_by, "") if s.confirm_by else "",
        "confirmTime": _t(s.confirm_time),
        "confirmNote": s.confirm_note or "",
        "createBy": users.get(s.create_by, "") if s.create_by else "",
        "createTime": _t(s.create_time),
    }


def _confirm_record_out(r: SettlementConfirmRecord) -> dict:
    return {
        "id": r.id,
        "action": r.action,
        "operatorName": r.operator_name,
        "receiverName": r.receiver_name,
        "note": r.note,
        "createTime": _t(r.create_time),
    }


def _invoice_out(i: Invoice, s: Settlement | None = None, users: dict[int, str] | None = None) -> dict:
    users = users or {}
    return {
        "id": i.id,
        "settlementId": i.settlement_id,
        "settlementNo": s.settlement_no if s else "",
        "invoiceNo": i.invoice_no or "",
        "contractId": s.contract_id if s else None,
        "customerId": s.customer_id if s else None,
        "amount": _money(i.amount),
        "invoiceDate": _d(i.invoice_date),
        "status": i.status,
        "approvalInstanceId": i.approval_instance_id,
        "createBy": users.get(i.create_by, "") if i.create_by else "",
        "createTime": _t(i.create_time),
    }


def _payment_out(p: Payment, s: Settlement | None = None, users: dict[int, str] | None = None) -> dict:
    users = users or {}
    return {
        "id": p.id,
        "paymentNo": p.payment_no,
        "settlementId": p.settlement_id,
        "settlementNo": s.settlement_no if s else "",
        "contractId": s.contract_id if s else None,
        "customerId": s.customer_id if s else None,
        "payType": p.pay_type,
        "payerName": p.payer_name,
        "payerAccount": p.payer_account,
        "amount": _money(p.amount),
        "bank": p.bank,
        "paidAt": _d(p.paid_at),
        "remark": p.remark or "",
        "createBy": users.get(p.create_by, "") if p.create_by else "",
        "createTime": _t(p.create_time),
    }


def _load_settlement(db: Session, sid: int, lock: bool = False) -> Settlement:
    s = db.get(Settlement, sid, with_for_update=lock)
    if not s or s.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return s


# ---------------- 结算单 ----------------


def _settlement_filtered(db: Session, request: Request, page: PageParams):
    stmt = select(Settlement)
    return apply_list_filters(
        stmt,
        Settlement,
        request.query_params,
        db,
        page,
        search_cols=["settlement_no", "task_no", "customer_name", "contract_no"],
        filter_cols={"status", "task_id", "contract_id", "customer_id", "confirm_status"},
        range_cols={"create_time"},
        sort_cols={"update_time", "create_time", "id", "settlement_no", "amount"},
    )


@router.get("/settlements")
def list_settlements(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("finance:settlement:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _settlement_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    users = _user_names(db, {x for s in rows for x in (s.create_by, s.confirm_by)})
    return {"items": [_settlement_out(s, users) for s in rows], "total": total, "page": page, "size": size}


@router.get("/settlements/task-options")
def settlement_task_options(
    q: str = Query("", max_length=64),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_perm("finance:settlement:create")),
    db: Session = Depends(get_db),
):
    """可发起结算的任务：status=finished 且尚无结算单。"""
    stmt = (
        select(Task)
        .where(
            Task.deleted == 0,
            Task.status == "finished",
            ~select(Settlement.id).where(Settlement.task_id == Task.id, Settlement.deleted == 0).exists(),
        )
    )
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Task.task_no.like(like), Task.task_name.like(like), Task.customer_name.like(like)))
    rows = db.scalars(stmt.order_by(Task.update_time.desc()).limit(limit)).all()
    return [
        {"value": t.id, "label": t.task_no, "sub": f"{t.customer_name}/{t.contract_no}".strip("/")} for t in rows
    ]


@router.post("/settlements", status_code=201)
def create_settlement(
    body: S.SettlementIn,
    current: User = Depends(require_perm("finance:settlement:create")),
    db: Session = Depends(get_db),
):
    t = db.get(Task, body.task_id, with_for_update=True)  # 锁任务行：并发建单只放行一个
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "任务不存在")
    if t.create_by != current.id and "super" not in current.role_codes:
        raise BizException(R.FINANCE_NOT_TASK_CREATOR, "仅任务创建人可发起结算")
    if db.scalar(select(Settlement.id).where(Settlement.task_id == t.id, Settlement.deleted == 0)):
        raise BizException(R.FINANCE_SETTLEMENT_EXISTS, "该任务已存在结算单")
    if t.status != "finished":
        raise BizException(R.FINANCE_INVALID_STATE, f"任务状态「{t.status}」不允许发起结算（需已完成）")
    s = Settlement(
        settlement_no=next_no(db, "settlement"),
        task_id=t.id,
        task_no=t.task_no,
        contract_no=t.contract_no,
        customer_name=t.customer_name,
        contract_id=t.contract_id,
        customer_id=t.customer_id,
        amount=body.amount,
        invoiceable_amount=body.invoiceable_amount if body.invoiceable_amount is not None else body.amount,
        status="pending",
        remark=body.remark or None,
        create_by=current.id,
    )
    db.add(s)
    db.flush()
    _submit_settlement_flow(db, s, t, current)
    audit(db, user_id=current.id, module="finance", action="settlement_create", biz_type="settlement", biz_id=s.id)
    db.commit()
    return _settlement_out(s, _user_names(db, {s.create_by, s.confirm_by}))


def _submit_settlement_flow(db: Session, s: Settlement, t: Task, current: User) -> None:
    """结算单创建即发起结算审批；未绑定 settlement 定义时直通（pending + 任务 settled）。"""
    definition = approval_svc.resolve_definition(db, "settlement")
    if not definition:
        s.status = "pending"
        s.version += 1
        s.update_time = datetime.now()
        task_svc.mark_settled(db, t)  # finished → settled
        return
    inst = approval_svc.start(
        db,
        biz_type="settlement",
        biz_id=s.id,
        definition_code=definition.code,
        title=f"{s.settlement_no} 结算审批（{s.customer_name}）",
        initiator=current,
        form_snapshot=svc.form_snapshot(s),
        variables={"amount": float(s.amount), "customer_name": s.customer_name},
    )
    s.status = "approving"
    s.approval_instance_id = inst.id
    s.version += 1
    s.update_time = datetime.now()


@router.post("/settlements/{sid}/submit")
def submit_settlement(
    sid: int,
    current: User = Depends(require_perm("finance:settlement:create")),
    db: Session = Depends(get_db),
):
    """结算审批被驳回/撤回后重新提交（开新实例；未绑定定义直通）。"""
    s = _load_settlement(db, sid, lock=True)
    if s.status != "rejected":
        raise BizException(R.FINANCE_INVALID_STATE, f"状态「{s.status}」不允许重新提交")
    t = db.get(Task, s.task_id)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "任务不存在")
    _submit_settlement_flow(db, s, t, current)
    audit(db, user_id=current.id, module="finance", action="settlement_submit", biz_type="settlement", biz_id=sid)
    db.commit()
    return _settlement_out(s, _user_names(db, {s.create_by, s.confirm_by}))


@router.get("/settlements/export")
def export_settlements(
    request: Request,
    current: User = Depends(require_perm("finance:settlement:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _settlement_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    settlements = db.scalars(stmt).all()
    users = _user_names(db, {x for s in settlements for x in (s.create_by, s.confirm_by)})
    rows = []
    for s in settlements:
        item = _settlement_out(s, users)
        item["status"] = STATUS_CN.get(s.status, s.status)
        rows.append(item)
    payload = export_xlsx_styled(rows, SETTLEMENT_EXPORT_COLS, "settlements")
    audit(
        db,
        user_id=current.id,
        module="finance",
        action="settlement_export",
        detail={"count": len(rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('settlements')}"},
    )


@router.get("/settlements/{sid}")
def get_settlement(
    sid: int,
    user: User = Depends(require_perm("finance:settlement:list")),
    db: Session = Depends(get_db),
):
    s = _load_settlement(db, sid)
    invoices = db.scalars(
        select(Invoice).where(Invoice.settlement_id == sid, Invoice.deleted == 0).order_by(Invoice.id)
    ).all()
    payments = db.scalars(
        select(Payment).where(Payment.settlement_id == sid, Payment.deleted == 0).order_by(Payment.id)
    ).all()
    users = _user_names(
        db, {s.create_by, s.confirm_by} | {i.create_by for i in invoices} | {p.create_by for p in payments}
    )
    data = _settlement_out(s, users)
    data["invoices"] = [_invoice_out(i, s, users) for i in invoices]
    data["payments"] = [_payment_out(p, s, users) for p in payments]
    data["paidAmount"] = _money(sum((p.amount for p in payments), Decimal(0)))
    data["timeline"] = approval_svc.timeline(db, "invoice", sid)["records"]
    records = db.scalars(
        select(SettlementConfirmRecord)
        .where(SettlementConfirmRecord.settlement_id == sid, SettlementConfirmRecord.deleted == 0)
        .order_by(SettlementConfirmRecord.id)
    ).all()
    data["confirmRecords"] = [_confirm_record_out(r) for r in records]
    return data


@router.post("/settlements/{sid}/send-confirm")
def send_settlement_confirm(
    sid: int,
    body: S.SendConfirmIn,
    current: User = Depends(require_perm("finance:settlement:confirm")),
    db: Session = Depends(get_db),
):
    """发送客户确认：站内通知收件人 + 留痕；确认状态 → pending（可重复发送/有异议后重发）。"""
    s = _load_settlement(db, sid, lock=True)
    if s.status != "pending":
        raise BizException(R.FINANCE_INVALID_STATE, f"状态「{s.status}」不允许发送客户确认（需结算审批通过/待开票）")
    receiver = db.get(User, body.receiver_id)
    if not receiver or receiver.deleted or receiver.status != "enabled":
        raise BizException(R.GENERIC_NOT_FOUND, "收件人不存在或已停用")
    db.add(
        SettlementConfirmRecord(
            settlement_id=s.id,
            action="send",
            operator_id=current.id,
            operator_name=current.name or current.username,
            receiver_id=receiver.id,
            receiver_name=receiver.name or receiver.username,
            note=body.note,
            create_by=current.id,
        )
    )
    db.add(
        Notify(
            user_id=receiver.id,
            title=f"结算单待客户确认 {s.settlement_no}",
            content=(
                f"请与客户核对结算单 {s.settlement_no}（{s.customer_name}，金额 {s.amount} 元），"
                f"并在结算单详情回填确认结果。{f'备注：{body.note}' if body.note else ''}"
            ),
            biz_type="settlement",
            biz_id=s.id,
            link="/finance/settlements",
        )
    )
    s.confirm_status = "pending"
    s.update_time = datetime.now()
    audit(
        db,
        user_id=current.id,
        module="finance",
        action="settlement_confirm_send",
        biz_type="settlement",
        biz_id=sid,
        detail={"receiverId": receiver.id, "receiverName": receiver.name or receiver.username, "note": body.note},
    )
    db.commit()
    return _settlement_out(s, _user_names(db, {s.create_by, s.confirm_by}))


@router.post("/settlements/{sid}/confirm")
def confirm_settlement(
    sid: int,
    body: S.ConfirmIn,
    current: User = Depends(require_perm("finance:settlement:confirm")),
    db: Session = Depends(get_db),
):
    """代客标记确认结果（一期由内部人员操作）：confirm 已确认 / object 有异议，说明留痕。"""
    s = _load_settlement(db, sid, lock=True)
    if s.status != "pending":
        raise BizException(R.FINANCE_INVALID_STATE, f"状态「{s.status}」不允许标记客户确认（需待开票）")
    if s.confirm_status not in ("pending", "objected"):
        raise BizException(R.FINANCE_INVALID_STATE, "请先发送客户确认")
    s.confirm_status = "confirmed" if body.action == "confirm" else "objected"
    s.confirm_by = current.id
    s.confirm_time = datetime.now()
    s.confirm_note = body.note
    s.update_time = datetime.now()
    db.add(
        SettlementConfirmRecord(
            settlement_id=s.id,
            action=body.action,
            operator_id=current.id,
            operator_name=current.name or current.username,
            note=body.note,
            create_by=current.id,
        )
    )
    audit(
        db,
        user_id=current.id,
        module="finance",
        action=f"settlement_confirm_{body.action}",
        biz_type="settlement",
        biz_id=sid,
        detail={"note": body.note},
    )
    db.commit()
    return _settlement_out(s, _user_names(db, {s.create_by, s.confirm_by}))


@router.post("/settlements/{sid}/apply-invoice")
def apply_invoice(
    sid: int,
    body: S.ApplyInvoiceIn | None = None,
    current: User = Depends(require_perm("finance:invoice:apply")),
    db: Session = Depends(get_db),
):
    s = _load_settlement(db, sid, lock=True)
    if s.status != "pending":
        raise BizException(R.FINANCE_INVALID_STATE, f"状态「{s.status}」不允许申请开票")
    if s.confirm_status != "confirmed":
        raise BizException(R.FINANCE_INVALID_STATE, "结算单未经客户确认，不能申请开票")
    inst = approval_svc.start(
        db,
        biz_type="invoice",
        biz_id=s.id,
        definition_code="invoice_apply",
        title=f"{s.settlement_no} 开票申请（{s.customer_name}）",
        initiator=current,
        form_snapshot=svc.form_snapshot(s),
        variables={"amount": float(s.amount), "customer_name": s.customer_name},
    )
    s.status = "invoicing"
    s.approval_instance_id = inst.id
    s.version += 1
    s.update_time = datetime.now()
    audit(
        db,
        user_id=current.id,
        module="finance",
        action="invoice_apply",
        biz_type="settlement",
        biz_id=sid,
        detail={"instanceId": inst.id, "comment": body.comment if body else ""},
    )
    db.commit()
    return _settlement_out(s, _user_names(db, {s.create_by, s.confirm_by}))


# ---------------- 发票登记 ----------------


def _rel_filters(model, params) -> list:
    """合同/客户过滤：发票/到账无关联列，经结算单子查询（?contract_id= 与 filters[contract_id]= 均可）。"""
    extra = []
    for key in ("contract_id", "customer_id"):
        raw = params.get(key) or params.get(f"filters[{key}]")
        if raw:
            sub = select(Settlement.id).where(Settlement.deleted == 0, getattr(Settlement, key) == raw)
            extra.append(model.settlement_id.in_(sub))
    return extra


def _invoice_filtered(db: Session, request: Request, page: PageParams):
    stmt = select(Invoice)
    extra = _rel_filters(Invoice, request.query_params)
    q = (request.query_params.get("q") or "").strip()
    if q:  # 发票号 / 关联结算单号 / 客户名
        like = f"%{q}%"
        sub = select(Settlement.id).where(
            Settlement.deleted == 0,
            or_(Settlement.settlement_no.like(like), Settlement.customer_name.like(like)),
        )
        extra.append(or_(Invoice.invoice_no.like(like), Invoice.settlement_id.in_(sub)))
    return apply_list_filters(
        stmt,
        Invoice,
        request.query_params,
        db,
        page,
        filter_cols={"settlement_id"},
        sort_cols={"update_time", "create_time", "id", "amount", "invoice_date"},
        extra_where=extra,
    )


def _settlement_brief_map(db: Session, ids: list[int]) -> dict[int, Settlement]:
    if not ids:
        return {}
    return {s.id: s for s in db.scalars(select(Settlement).where(Settlement.id.in_(ids)))}


def _invoice_list_out(i: Invoice, smap: dict[int, Settlement], users: dict[int, str]) -> dict:
    s = smap.get(i.settlement_id)
    data = _invoice_out(i, s, users)
    data["taskNo"] = s.task_no if s else ""
    data["customerName"] = s.customer_name if s else ""
    data["statusText"] = INVOICE_STATUS_CN.get(i.status, i.status)
    return data


@router.get("/invoices")
def list_invoices(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("finance:invoice:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _invoice_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    smap = _settlement_brief_map(db, [i.settlement_id for i in rows])
    users = _user_names(db, {i.create_by for i in rows})
    return {
        "items": [_invoice_list_out(i, smap, users) for i in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/invoices/export")
def export_invoices(
    request: Request,
    current: User = Depends(require_perm("finance:invoice:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _invoice_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = db.scalars(stmt).all()
    smap = _settlement_brief_map(db, [i.settlement_id for i in rows])
    users = _user_names(db, {i.create_by for i in rows})
    items = []
    for i in rows:
        item = _invoice_list_out(i, smap, users)
        item["status"] = INVOICE_STATUS_CN.get(i.status, i.status)
        items.append(item)
    payload = export_xlsx_styled(items, INVOICE_EXPORT_COLS, "invoices")
    audit(
        db,
        user_id=current.id,
        module="finance",
        action="invoice_export",
        detail={"count": len(items)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('invoices')}"},
    )


@router.put("/invoices/{iid}")
def register_invoice(
    iid: int,
    body: S.InvoiceIn,
    current: User = Depends(require_perm("finance:invoice:edit")),
    db: Session = Depends(get_db),
):
    i = db.get(Invoice, iid)
    if not i or i.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    i.invoice_no = body.invoice_no
    i.amount = body.amount
    i.invoice_date = body.invoice_date
    i.update_by = current.id
    i.update_time = datetime.now()
    audit(db, user_id=current.id, module="finance", action="invoice_register", biz_type="invoice", biz_id=iid)
    db.commit()
    return _invoice_out(i, db.get(Settlement, i.settlement_id), _user_names(db, {i.create_by}))


# ---------------- 到账登记 ----------------


def _payment_filtered(db: Session, request: Request, page: PageParams):
    stmt = select(Payment)
    return apply_list_filters(
        stmt,
        Payment,
        request.query_params,
        db,
        page,
        search_cols=["payment_no", "payer_name", "payer_account"],
        filter_cols={"pay_type", "settlement_id"},
        range_cols={"paid_at", "create_time"},
        sort_cols={"update_time", "create_time", "id", "payment_no", "amount", "paid_at"},
        extra_where=_rel_filters(Payment, request.query_params),
    )


@router.get("/payments")
def list_payments(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("finance:payment:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _payment_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    smap = _settlement_brief_map(db, [p.settlement_id for p in rows])
    users = _user_names(db, {p.create_by for p in rows})
    return {
        "items": [_payment_out(p, smap.get(p.settlement_id), users) for p in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("/payments", status_code=201)
def create_payment(
    body: S.PaymentIn,
    current: User = Depends(require_perm("finance:payment:create")),
    db: Session = Depends(get_db),
):
    s = _load_settlement(db, body.settlement_id, lock=True)  # 锁结算单行：累计到账判断串行化
    if s.status != "invoiced":
        raise BizException(R.FINANCE_INVALID_STATE, f"结算单状态「{s.status}」不允许到账登记（需已开票）")
    p = Payment(
        payment_no=next_no(db, "payment"),
        settlement_id=s.id,
        pay_type=body.pay_type,
        payer_name=body.payer_name,
        payer_account=body.payer_account,
        amount=body.amount,
        bank=body.bank,
        paid_at=body.paid_at,
        remark=body.remark or None,
        create_by=current.id,
    )
    db.add(p)
    db.flush()
    paid_total = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.settlement_id == s.id, Payment.deleted == 0
        )
    )
    if paid_total >= s.amount:
        s.status = "paid"
        s.update_time = datetime.now()
    audit(db, user_id=current.id, module="finance", action="payment_create", biz_type="payment", biz_id=p.id)
    db.commit()
    return _payment_out(p, s, _user_names(db, {p.create_by}))


@router.get("/payments/export")
def export_payments(
    request: Request,
    current: User = Depends(require_perm("finance:payment:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _payment_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = db.scalars(stmt).all()
    smap = _settlement_brief_map(db, [p.settlement_id for p in rows])
    users = _user_names(db, {p.create_by for p in rows})
    payload = export_xlsx_styled([_payment_out(p, smap.get(p.settlement_id), users) for p in rows],
                                 PAYMENT_EXPORT_COLS, "payments")
    audit(
        db,
        user_id=current.id,
        module="finance",
        action="payment_export",
        detail={"count": len(rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('payments')}"},
    )

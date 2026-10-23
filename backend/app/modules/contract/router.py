"""合同路由 /api/v1/contract。"""

import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Form, Query, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.approval import service as approval_svc
from app.modules.auth.models import User
from app.modules.contract import schemas as S
from app.modules.contract import service as svc
from app.modules.contract.models import Contract, ContractAttachment
from app.modules.finance.models import Invoice, Payment, Settlement
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import next_no

router = APIRouter(prefix="/contract", tags=["contract"], route_class=EnvelopeRoute)

STATUS_CN = {
    "draft": "草稿",
    "approving": "审批中",
    "approved": "已通过",
    "rejected": "已驳回",
    "voided": "已作废",
}

ATTACHMENT_CATEGORIES = ("econtract", "other")

EXPORT_COLS = [
    {"key": "contractNo", "label": "合同编号", "width": 20},
    {"key": "name", "label": "合同名称", "width": 36},
    {"key": "customerName", "label": "客户名称", "width": 28},
    {"key": "contractType", "label": "合同类型", "width": 14},
    {"key": "amount", "label": "金额(元)", "width": 14},
    {"key": "startDate", "label": "开始日期", "width": 12},
    {"key": "endDate", "label": "结束日期", "width": 12},
    {"key": "payCycle", "label": "结算周期", "width": 12},
    {"key": "delivery", "label": "交付方式", "width": 12},
    {"key": "handlerName", "label": "经办人", "width": 10},
    {"key": "status", "label": "状态", "width": 10},
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


def _out(c: Contract) -> dict:
    return {
        "id": c.id,
        "contractNo": c.contract_no or "",
        "name": c.name,
        "customerId": c.customer_id,
        "customerName": c.customer_name,
        "contractType": c.contract_type,
        "subjectType": c.subject_type,
        "amount": float(c.amount) if c.amount is not None else None,
        "startDate": _d(c.start_date),
        "endDate": _d(c.end_date),
        "payCycle": c.pay_cycle,
        "delivery": c.delivery,
        "sealType": c.seal_type,
        "handlerId": c.handler_id,
        "handlerName": c.handler_name,
        "frameworkNo": c.framework_no,
        "paymentOrg": c.payment_org,
        "contactPerson": c.contact_person or "",
        "contactPhone": c.contact_phone or "",
        "remark": c.remark or "",
        "status": c.status,
        "statusText": STATUS_CN.get(c.status, c.status),
        "flowInstanceId": c.flow_instance_id,
        "attachments": [
            {"id": a.id, "fileName": a.file_name, "size": a.size, "category": a.category or "other"}
            for a in (c.attachments or [])
            if not a.deleted
        ],
        "version": c.version,
        "createTime": _t(c.create_time),
        "updateTime": _t(c.update_time),
    }


def _check_version(c: Contract, version: int | None) -> None:
    if version is not None and version != c.version:
        raise BizException(R.GENERIC_OPTIMISTIC_LOCK)


def _apply(c: Contract, body: S.ContractIn, customer_name: str) -> None:
    c.name = body.name
    c.customer_id = body.customer_id
    c.customer_name = customer_name
    c.contract_type = body.contract_type
    c.subject_type = body.subject_type
    c.amount = body.amount
    c.start_date = body.start_date
    c.end_date = body.end_date
    c.pay_cycle = body.pay_cycle
    c.delivery = body.delivery
    c.seal_type = body.seal_type
    c.handler_id = body.handler_id
    c.handler_name = body.handler_name
    c.framework_no = body.framework_no
    c.payment_org = body.payment_org
    c.contact_person = body.contact_person
    c.contact_phone = body.contact_phone
    c.remark = body.remark


def _filtered(db: Session, request: Request, page: PageParams):
    stmt = select(Contract)
    return apply_list_filters(
        stmt,
        Contract,
        request.query_params,
        db,
        page,
        search_cols=["name", "contract_no", "customer_name"],
        filter_cols={"status", "customer_id", "contract_type"},
        range_cols={"start_date", "end_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "contract_no", "amount"},
    )


@router.get("/contracts")
def list_contracts(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("contract:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_out(c) for c in rows], "total": total, "page": page, "size": size}


@router.get("/contracts/options")
def contract_options(
    q: str = Query("", max_length=64),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """仅已通过合同（建任务时用）。"""
    stmt = select(Contract).where(Contract.deleted == 0, Contract.status == "approved")
    if q.strip():
        like = f"%{q.strip()}%"
        from sqlalchemy import or_

        stmt = stmt.where(or_(Contract.name.like(like), Contract.contract_no.like(like)))
    rows = db.scalars(stmt.order_by(Contract.update_time.desc()).limit(limit)).all()
    return [
        {
            "id": c.id,
            "label": c.name,
            "sub": c.contract_no,
            "customerId": c.customer_id,
            "customerName": c.customer_name,
            "paymentOrg": c.payment_org,
        }
        for c in rows
    ]


@router.get("/contracts/framework-options")
def framework_contract_options(
    customer_id: int | None = Query(None),
    q: str = Query("", max_length=64),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """已通过的框架合同下拉（编辑合同关联框架号用）；customer_id 限定到该客户。

    选项 id 直接取合同号（framework_no 存的就是框架合同号，兼容存量数据）。
    """
    stmt = select(Contract).where(
        Contract.deleted == 0,
        Contract.status == "approved",
        Contract.contract_type == "framework",
        Contract.contract_no.is_not(None),
    )
    if customer_id:
        stmt = stmt.where(Contract.customer_id == customer_id)
    if q.strip():
        like = f"%{q.strip()}%"
        from sqlalchemy import or_

        stmt = stmt.where(or_(Contract.name.like(like), Contract.contract_no.like(like)))
    rows = db.scalars(stmt.order_by(Contract.update_time.desc()).limit(limit)).all()
    return [
        {
            "id": c.contract_no,
            "label": c.name,
            "sub": c.contract_no,
            "customerId": c.customer_id,
            "customerName": c.customer_name,
        }
        for c in rows
    ]


@router.get("/contracts/{cid}")
def get_contract(
    cid: int,
    user: User = Depends(require_perm("contract:list")),
    db: Session = Depends(get_db),
):
    c = db.get(Contract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    data = _out(c)
    data["timeline"] = approval_svc.timeline(db, "contract", cid)["records"]
    return data


@router.get("/contracts/{cid}/finance-summary")
def contract_finance_summary(
    cid: int,
    user: User = Depends(require_perm("contract:list")),
    db: Session = Depends(get_db),
):
    """合同财务汇总：结算/开票/到账（均按未删除行统计，开票含全部状态）。"""
    c = db.get(Contract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    settlement_count, settled_total = db.execute(
        select(func.count(), func.coalesce(func.sum(Settlement.amount), 0)).where(
            Settlement.contract_id == cid, Settlement.deleted == 0
        )
    ).one()
    settlement_sub = select(Settlement.id).where(Settlement.contract_id == cid, Settlement.deleted == 0)
    invoice_count, invoiced_total = db.execute(
        select(func.count(), func.coalesce(func.sum(Invoice.amount), 0)).where(
            Invoice.settlement_id.in_(settlement_sub), Invoice.deleted == 0
        )
    ).one()
    payment_count, paid_total = db.execute(
        select(func.count(), func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.settlement_id.in_(settlement_sub), Payment.deleted == 0
        )
    ).one()
    return {
        "contractAmount": float(c.amount) if c.amount is not None else None,
        "settledTotal": float(settled_total or 0),
        "invoicedTotal": float(invoiced_total or 0),
        "paidTotal": float(paid_total or 0),
        "settlementCount": settlement_count,
        "invoiceCount": invoice_count,
        "paymentCount": payment_count,
    }


@router.post("/contracts", status_code=201)
def create_contract(
    body: S.ContractIn,
    current: User = Depends(require_perm("contract:create")),
    db: Session = Depends(get_db),
):
    customer_name = svc.load_customer_name(db, body.customer_id)
    # draft 不占正式 HT 编号：提交审批时才由编号规则发放（F3 流程驱动）
    c = Contract(contract_no=None, create_by=current.id, status="draft")
    _apply(c, body, customer_name)
    if not c.handler_id:
        c.handler_id = current.id
        c.handler_name = c.handler_name or current.name or current.username
    db.add(c)
    db.flush()
    audit(db, user_id=current.id, module="contract", action="contract_create", biz_type="contract", biz_id=c.id)
    db.commit()
    return _out(c)


@router.put("/contracts/{cid}")
def update_contract(
    cid: int,
    body: S.ContractIn,
    current: User = Depends(require_perm("contract:edit")),
    db: Session = Depends(get_db),
):
    c = db.get(Contract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(c)
    _check_version(c, body.version)
    customer_name = svc.load_customer_name(db, body.customer_id)
    _apply(c, body, customer_name)
    c.version += 1
    c.update_by = current.id
    c.update_time = datetime.now()
    audit(db, user_id=current.id, module="contract", action="contract_update", biz_type="contract", biz_id=cid)
    db.commit()
    return _out(c)


@router.delete("/contracts/{cid}")
def delete_contract(
    cid: int,
    current: User = Depends(require_perm("contract:delete")),
    db: Session = Depends(get_db),
):
    c = db.get(Contract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if c.status != "draft":
        raise BizException(R.CONTRACT_INVALID_STATE, "仅草稿合同可删除")
    c.deleted = 1
    c.update_time = datetime.now()
    audit(db, user_id=current.id, module="contract", action="contract_delete", biz_type="contract", biz_id=cid)
    db.commit()
    return None


@router.post("/contracts/{cid}/submit")
def submit_contract(
    cid: int,
    body: S.SubmitIn | None = None,
    current: User = Depends(require_perm("contract:submit")),
    db: Session = Depends(get_db),
):
    c = db.get(Contract, cid, with_for_update=True)  # 锁合同行：并发提交审批只放行一个
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if c.status not in ("draft", "rejected"):
        raise BizException(R.CONTRACT_INVALID_STATE, "仅草稿/已驳回合同可提交审批")
    if not c.amount:
        raise BizException(R.GENERIC_PARAM, "合同金额必填，不能提交审批")
    if not c.contract_no:
        # 提交即发放正式编号（按合同类型匹配分类规则，未配置走兜底）；驳回/撤回后重提沿用
        c.contract_no = next_no(db, "contract", category=c.contract_type or None)
        db.flush()
    inst = approval_svc.start(
        db,
        biz_type="contract",
        biz_id=c.id,
        definition_code="contract_approve",
        title=f"{c.contract_no} {c.name}",
        initiator=current,
        form_snapshot=svc.form_snapshot(c),
        variables={
            "amount": float(c.amount),
            "contract_type": c.contract_type,
            "customer_name": c.customer_name,
        },
    )
    c.status = "approving"
    c.flow_instance_id = inst.id
    c.version += 1
    c.update_time = datetime.now()
    audit(
        db,
        user_id=current.id,
        module="contract",
        action="contract_submit",
        biz_type="contract",
        biz_id=cid,
        detail={"instanceId": inst.id, "comment": body.comment if body else ""},
    )
    db.commit()
    return _out(c)


@router.post("/contracts/{cid}/void")
def void_contract(
    cid: int,
    current: User = Depends(require_perm("contract:edit")),
    db: Session = Depends(get_db),
):
    c = db.get(Contract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if c.status == "approving":
        raise BizException(R.CONTRACT_EDITING_LOCKED, "审批中合同不能作废，请先撤回")
    if c.status in ("voided",):
        raise BizException(R.CONTRACT_INVALID_STATE, "合同已作废")
    c.status = "voided"
    c.version += 1
    c.update_time = datetime.now()
    audit(db, user_id=current.id, module="contract", action="contract_void", biz_type="contract", biz_id=cid)
    db.commit()
    return _out(c)


# ---------------- 附件 ----------------


@router.post("/contracts/{cid}/attachments")
def upload_attachment(
    cid: int,
    file: UploadFile,
    category: str = Form("other"),
    current: User = Depends(require_perm("contract:edit")),
    db: Session = Depends(get_db),
):
    c = db.get(Contract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(c)
    if category not in ATTACHMENT_CATEGORIES:
        raise BizException(R.GENERIC_PARAM, f"不支持的附件分类：{category}")
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.upload_ext_set:
        raise BizException(R.GENERIC_PARAM, f"不支持的文件类型：{ext or '无扩展名'}")
    data = file.file.read()
    if not data:
        raise BizException(R.GENERIC_PARAM, "文件为空")
    if len(data) > settings.upload_max_mb * 1024 * 1024:
        raise BizException(R.GENERIC_PARAM, f"文件超过大小上限 {settings.upload_max_mb}MB")
    rel = Path("contract") / f"{uuid.uuid4().hex}"
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    a = ContractAttachment(
        contract_id=cid,
        file_name=file.filename or "file",
        category=category,
        size=len(data),
        content_type=file.content_type or "",
        path=str(rel),
        create_by=current.id,
    )
    db.add(a)
    db.flush()
    c.update_time = datetime.now()
    audit(db, user_id=current.id, module="contract", action="attachment_upload", biz_type="contract", biz_id=cid,
          detail={"file": file.filename, "category": category})
    db.commit()
    return {"id": a.id, "fileName": a.file_name, "size": a.size, "category": a.category}


@router.get("/attachments/{file_id}")
def download_attachment(
    file_id: int,
    user: User = Depends(require_perm("contract:list")),
    db: Session = Depends(get_db),
):
    a = db.get(ContractAttachment, file_id)
    if not a or a.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    dest = Path(settings.upload_dir) / a.path
    if not dest.exists():
        raise BizException(R.GENERIC_NOT_FOUND, "文件已丢失")
    from urllib.parse import quote

    return Response(
        dest.read_bytes(),
        media_type=a.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(a.file_name)}"},
    )


@router.delete("/attachments/{file_id}")
def delete_attachment(
    file_id: int,
    current: User = Depends(require_perm("contract:edit")),
    db: Session = Depends(get_db),
):
    a = db.get(ContractAttachment, file_id)
    if not a or a.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    c = db.get(Contract, a.contract_id)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(c)  # 仅 draft/rejected 合同可删附件
    a.deleted = 1
    c.update_time = datetime.now()
    audit(db, user_id=current.id, module="contract", action="attachment_delete", biz_type="contract",
          biz_id=c.id, detail={"fileId": file_id, "file": a.file_name})
    db.commit()
    return None


# ---------------- 导出 ----------------


@router.post("/contracts/export")
def export_contracts(
    request: Request,
    current: User = Depends(require_perm("contract:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = []
    for c in db.scalars(stmt).all():
        item = _out(c)
        item["status"] = STATUS_CN.get(c.status, c.status)
        rows.append(item)
    payload = export_xlsx_styled(rows, EXPORT_COLS, "contracts")
    audit(
        db,
        user_id=current.id,
        module="contract",
        action="contract_export",
        detail={"count": len(rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('contracts')}"},
    )

"""采购路由 /api/v1/procurement：申请 / 合同（会签）/ 出入库。"""

from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.approval import service as approval_svc
from app.modules.auth.models import User
from app.modules.procurement import schemas as S
from app.modules.procurement import service as svc
from app.modules.procurement.models import (
    PurchaseContract,
    PurchaseRequest,
    PurchaseRequestItem,
    StockOrder,
    StockOrderItem,
)
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import next_no

router = APIRouter(prefix="/procurement", tags=["procurement"], route_class=EnvelopeRoute)

STATUS_CN = {
    "draft": "草稿",
    "approving": "审批中",
    "approved": "已通过",
    "rejected": "已驳回",
    "voided": "已作废",
}
STOCK_STATUS_CN = {"registered": "已登记", "confirmed": "已确认"}
ORDER_TYPE_CN = {"in": "入库", "out": "出库"}
SOURCE_TYPE_CN = {"": "采购", "purchase": "采购", "sample": "样品"}

REQUEST_EXPORT_COLS = [
    {"key": "requestNo", "label": "申请编号", "width": 18},
    {"key": "title", "label": "申请标题", "width": 32},
    {"key": "taskNo", "label": "关联任务", "width": 16},
    {"key": "purchaseMethod", "label": "采购方式", "width": 12},
    {"key": "budgetAmount", "label": "预算金额(元)", "width": 14},
    {"key": "expectDate", "label": "期望到货", "width": 12},
    {"key": "status", "label": "状态", "width": 10},
    {"key": "createTime", "label": "创建时间", "width": 19},
]

CONTRACT_EXPORT_COLS = [
    {"key": "contractNo", "label": "合同编号", "width": 18},
    {"key": "name", "label": "合同名称", "width": 32},
    {"key": "supplierName", "label": "供应商", "width": 28},
    {"key": "requestNo", "label": "来源申请", "width": 16},
    {"key": "amount", "label": "金额(元)", "width": 14},
    {"key": "signDate", "label": "签订日期", "width": 12},
    {"key": "handlerName", "label": "经办人", "width": 10},
    {"key": "status", "label": "状态", "width": 10},
    {"key": "createTime", "label": "创建时间", "width": 19},
]

STOCK_EXPORT_COLS = [
    {"key": "orderNo", "label": "单号", "width": 18},
    {"key": "orderType", "label": "类型", "width": 8},
    {"key": "sourceType", "label": "来源", "width": 8},
    {"key": "sourceRef", "label": "来源单据", "width": 26},
    {"key": "contractNo", "label": "采购合同", "width": 18},
    {"key": "warehouse", "label": "仓库", "width": 12},
    {"key": "orderDate", "label": "出入库日期", "width": 12},
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


def _check_version(obj, version: int | None) -> None:
    if version is not None and version != obj.version:
        raise BizException(R.GENERIC_OPTIMISTIC_LOCK)


# ---------------- 采购申请 ----------------


def _request_out(r: PurchaseRequest) -> dict:
    return {
        "id": r.id,
        "requestNo": r.request_no or "",
        "title": r.title,
        "taskId": r.task_id,
        "taskNo": r.task_no,
        "taskName": r.task_name,
        "purchaseMethod": r.purchase_method,
        "budgetAmount": float(r.budget_amount) if r.budget_amount is not None else None,
        "expectDate": _d(r.expect_date),
        "reason": r.reason or "",
        "remark": r.remark or "",
        "status": r.status,
        "statusText": STATUS_CN.get(r.status, r.status),
        "flowInstanceId": r.flow_instance_id,
        "items": [
            {
                "id": i.id,
                "itemName": i.item_name,
                "spec": i.spec,
                "unit": i.unit,
                "quantity": float(i.quantity),
                "estimatePrice": float(i.estimate_price) if i.estimate_price is not None else None,
                "remark": i.remark,
            }
            for i in (r.items or [])
            if not i.deleted
        ],
        "version": r.version,
        "createTime": _t(r.create_time),
        "updateTime": _t(r.update_time),
    }


def _request_apply(r: PurchaseRequest, body: S.PurchaseRequestIn, db: Session) -> None:
    r.title = body.title
    if body.task_id:
        r.task_no, r.task_name = svc.load_task(db, body.task_id)
        r.task_id = body.task_id
    else:
        r.task_id = None
        r.task_no = ""
        r.task_name = ""
    r.purchase_method = body.purchase_method
    r.budget_amount = body.budget_amount
    r.expect_date = body.expect_date
    r.reason = body.reason
    r.remark = body.remark
    r.items = [
        PurchaseRequestItem(
            item_name=i.item_name,
            spec=i.spec,
            unit=i.unit,
            quantity=i.quantity,
            estimate_price=i.estimate_price,
            remark=i.remark,
        )
        for i in body.items
    ]


def _request_filtered(db: Session, request: Request, page: PageParams):
    stmt = select(PurchaseRequest)
    return apply_list_filters(
        stmt,
        PurchaseRequest,
        request.query_params,
        db,
        page,
        search_cols=["title", "request_no", "task_no", "task_name"],
        filter_cols={"status", "task_id", "purchase_method"},
        range_cols={"expect_date", "create_time"},
        sort_cols={
            "update_time", "create_time", "id", "request_no", "title",
            "budget_amount", "expect_date", "status", "purchase_method",
        },
    )


@router.get("/requests")
def list_requests(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("procurement:request:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _request_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_request_out(r) for r in rows], "total": total, "page": page, "size": size}


@router.get("/requests/counts")
def request_counts(
    user: User = Depends(require_perm("procurement:request:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(PurchaseRequest.status, func.count())
        .where(PurchaseRequest.deleted == 0)
        .group_by(PurchaseRequest.status)
    ).all()
    data = {s: 0 for s in ("draft", "approving", "approved", "rejected", "voided")}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


@router.get("/requests/{rid}")
def get_request(
    rid: int,
    user: User = Depends(require_perm("procurement:request:list")),
    db: Session = Depends(get_db),
):
    r = db.get(PurchaseRequest, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    data = _request_out(r)
    data["timeline"] = approval_svc.timeline(db, "purchase_request", rid)["records"]
    contract = db.scalar(
        select(PurchaseContract).where(PurchaseContract.request_id == rid, PurchaseContract.deleted == 0).limit(1)
    )
    data["contractId"] = contract.id if contract else None
    data["contractNo"] = (contract.contract_no or "") if contract else ""
    data["contractStatus"] = contract.status if contract else ""
    return data


@router.post("/requests", status_code=201)
def create_request(
    body: S.PurchaseRequestIn,
    current: User = Depends(require_perm("procurement:request:create")),
    db: Session = Depends(get_db),
):
    r = PurchaseRequest(request_no=None, create_by=current.id, status="draft")
    _request_apply(r, body, db)
    db.add(r)
    db.flush()
    audit(
        db, user_id=current.id, module="procurement", action="purchase_request_create",
        biz_type="purchase_request", biz_id=r.id,
    )
    db.commit()
    return _request_out(r)


@router.put("/requests/{rid}")
def update_request(
    rid: int,
    body: S.PurchaseRequestIn,
    current: User = Depends(require_perm("procurement:request:edit")),
    db: Session = Depends(get_db),
):
    r = db.get(PurchaseRequest, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(r.status)
    _check_version(r, body.version)
    _request_apply(r, body, db)
    r.version += 1
    r.update_by = current.id
    r.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="procurement", action="purchase_request_update",
        biz_type="purchase_request", biz_id=rid,
    )
    db.commit()
    return _request_out(r)


@router.delete("/requests/{rid}")
def delete_request(
    rid: int,
    current: User = Depends(require_perm("procurement:request:delete")),
    db: Session = Depends(get_db),
):
    r = db.get(PurchaseRequest, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if r.status != "draft":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "仅草稿申请可删除")
    r.deleted = 1
    r.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="procurement", action="purchase_request_delete",
        biz_type="purchase_request", biz_id=rid,
    )
    db.commit()
    return None


@router.post("/requests/{rid}/submit")
def submit_request(
    rid: int,
    body: S.SubmitIn | None = None,
    current: User = Depends(require_perm("procurement:request:submit")),
    db: Session = Depends(get_db),
):
    r = db.get(PurchaseRequest, rid, with_for_update=True)  # 锁行：并发提交审批只放行一个
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if r.status not in ("draft", "rejected"):
        raise BizException(R.PROCUREMENT_INVALID_STATE, "仅草稿/已驳回申请可提交审批")
    if not [i for i in (r.items or []) if not i.deleted]:
        raise BizException(R.GENERIC_PARAM, "采购明细不能为空，不能提交审批")
    if not r.request_no:
        # 提交即发放正式编号；驳回/撤回后重提沿用
        r.request_no = next_no(db, "purchase_request")
        db.flush()
    inst = approval_svc.start(
        db,
        biz_type="purchase_request",
        biz_id=r.id,
        definition_code="purchase_request_approve",
        title=f"{r.request_no} {r.title}",
        initiator=current,
        form_snapshot=svc.form_snapshot(r),
        variables={
            "budget_amount": float(r.budget_amount) if r.budget_amount is not None else 0,
            "purchase_method": r.purchase_method,
            "task_no": r.task_no,
        },
    )
    r.status = "approving"
    r.flow_instance_id = inst.id
    r.version += 1
    r.update_time = datetime.now()
    audit(
        db,
        user_id=current.id,
        module="procurement",
        action="purchase_request_submit",
        biz_type="purchase_request",
        biz_id=rid,
        detail={"instanceId": inst.id, "comment": body.comment if body else ""},
    )
    db.commit()
    return _request_out(r)


@router.post("/requests/{rid}/void")
def void_request(
    rid: int,
    current: User = Depends(require_perm("procurement:request:edit")),
    db: Session = Depends(get_db),
):
    r = db.get(PurchaseRequest, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if r.status == "approving":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "审批中申请不能作废，请先撤回")
    if r.status == "voided":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "申请已作废")
    r.status = "voided"
    r.version += 1
    r.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="procurement", action="purchase_request_void",
        biz_type="purchase_request", biz_id=rid,
    )
    db.commit()
    return _request_out(r)


@router.post("/requests/{rid}/generate-contract", status_code=201)
def generate_contract(
    rid: int,
    body: S.GenerateContractIn,
    current: User = Depends(require_perm("procurement:contract:create")),
    db: Session = Depends(get_db),
):
    """已批准申请 → 采购合同草稿（幂等：一申请一合同，已生成则返回现有合同）。"""
    r = db.get(PurchaseRequest, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if r.status != "approved":
        raise BizException(R.PROCUREMENT_REQUEST_NOT_APPROVED)
    existing = db.scalar(
        select(PurchaseContract).where(PurchaseContract.request_id == rid, PurchaseContract.deleted == 0).limit(1)
    )
    if existing:
        return _contract_out(existing)
    supplier_name = svc.load_supplier_name(db, body.supplier_id)
    c = PurchaseContract(
        contract_no=None,
        name=body.name or f"{r.title}采购合同",
        request_id=r.id,
        request_no=r.request_no or "",
        supplier_id=body.supplier_id,
        supplier_name=supplier_name,
        amount=body.amount if body.amount is not None else r.budget_amount,
        pay_cycle=body.pay_cycle,
        delivery=body.delivery,
        handler_id=current.id,
        handler_name=current.name or current.username,
        remark=body.remark,
        status="draft",
        create_by=current.id,
    )
    db.add(c)
    db.flush()
    audit(
        db,
        user_id=current.id,
        module="procurement",
        action="purchase_contract_generate",
        biz_type="purchase_contract",
        biz_id=c.id,
        detail={"requestId": rid},
    )
    db.commit()
    return _contract_out(c)


@router.post("/requests/export")
def export_requests(
    request: Request,
    current: User = Depends(require_perm("procurement:request:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _request_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = []
    for r in db.scalars(stmt).all():
        item = _request_out(r)
        item["status"] = STATUS_CN.get(r.status, r.status)
        rows.append(item)
    payload = export_xlsx_styled(rows, REQUEST_EXPORT_COLS, "purchase_requests")
    audit(
        db,
        user_id=current.id,
        module="procurement",
        action="purchase_request_export",
        detail={"count": len(rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('purchase_requests')}"},
    )


# ---------------- 采购合同 ----------------


def _contract_out(c: PurchaseContract) -> dict:
    return {
        "id": c.id,
        "contractNo": c.contract_no or "",
        "name": c.name,
        "requestId": c.request_id,
        "requestNo": c.request_no,
        "supplierId": c.supplier_id,
        "supplierName": c.supplier_name,
        "amount": float(c.amount) if c.amount is not None else None,
        "signDate": _d(c.sign_date),
        "startDate": _d(c.start_date),
        "endDate": _d(c.end_date),
        "payCycle": c.pay_cycle,
        "delivery": c.delivery,
        "handlerId": c.handler_id,
        "handlerName": c.handler_name,
        "remark": c.remark or "",
        "status": c.status,
        "statusText": STATUS_CN.get(c.status, c.status),
        "flowInstanceId": c.flow_instance_id,
        "version": c.version,
        "createTime": _t(c.create_time),
        "updateTime": _t(c.update_time),
    }


def _contract_apply(c: PurchaseContract, body: S.PurchaseContractIn, supplier_name: str, db: Session) -> None:
    c.name = body.name
    if body.request_id:
        r = db.get(PurchaseRequest, body.request_id)
        if not r or r.deleted:
            raise BizException(R.GENERIC_NOT_FOUND, "来源采购申请不存在")
        c.request_id = r.id
        c.request_no = r.request_no or ""
    else:
        c.request_id = None
        c.request_no = ""
    c.supplier_id = body.supplier_id
    c.supplier_name = supplier_name
    c.amount = body.amount
    c.sign_date = body.sign_date
    c.start_date = body.start_date
    c.end_date = body.end_date
    c.pay_cycle = body.pay_cycle
    c.delivery = body.delivery
    c.handler_id = body.handler_id
    c.handler_name = body.handler_name
    c.remark = body.remark


def _contract_filtered(db: Session, request: Request, page: PageParams):
    stmt = select(PurchaseContract)
    return apply_list_filters(
        stmt,
        PurchaseContract,
        request.query_params,
        db,
        page,
        search_cols=["name", "contract_no", "supplier_name", "request_no"],
        filter_cols={"status", "supplier_id", "request_id"},
        range_cols={"sign_date", "create_time"},
        sort_cols={
            "update_time", "create_time", "id", "contract_no", "name",
            "supplier_name", "amount", "sign_date", "status",
        },
    )


@router.get("/contracts")
def list_contracts(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("procurement:contract:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _contract_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_contract_out(c) for c in rows], "total": total, "page": page, "size": size}


@router.get("/contracts/counts")
def contract_counts(
    user: User = Depends(require_perm("procurement:contract:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(PurchaseContract.status, func.count())
        .where(PurchaseContract.deleted == 0)
        .group_by(PurchaseContract.status)
    ).all()
    data = {s: 0 for s in ("draft", "approving", "approved", "rejected", "voided")}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


@router.get("/contracts/{cid}")
def get_contract(
    cid: int,
    user: User = Depends(require_perm("procurement:contract:list")),
    db: Session = Depends(get_db),
):
    c = db.get(PurchaseContract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    data = _contract_out(c)
    data["timeline"] = approval_svc.timeline(db, "purchase_contract", cid)["records"]
    orders = db.scalars(
        select(StockOrder)
        .where(StockOrder.contract_id == cid, StockOrder.deleted == 0)
        .order_by(StockOrder.id.desc())
    ).all()
    data["stockOrders"] = [
        {"id": o.id, "orderNo": o.order_no, "orderType": o.order_type, "status": o.status} for o in orders
    ]
    return data


@router.post("/contracts", status_code=201)
def create_contract(
    body: S.PurchaseContractIn,
    current: User = Depends(require_perm("procurement:contract:create")),
    db: Session = Depends(get_db),
):
    supplier_name = svc.load_supplier_name(db, body.supplier_id)
    c = PurchaseContract(contract_no=None, create_by=current.id, status="draft")
    _contract_apply(c, body, supplier_name, db)
    if not c.handler_id:
        c.handler_id = current.id
        c.handler_name = c.handler_name or current.name or current.username
    db.add(c)
    db.flush()
    audit(
        db, user_id=current.id, module="procurement", action="purchase_contract_create",
        biz_type="purchase_contract", biz_id=c.id,
    )
    db.commit()
    return _contract_out(c)


@router.put("/contracts/{cid}")
def update_contract(
    cid: int,
    body: S.PurchaseContractIn,
    current: User = Depends(require_perm("procurement:contract:edit")),
    db: Session = Depends(get_db),
):
    c = db.get(PurchaseContract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(c.status)
    _check_version(c, body.version)
    supplier_name = svc.load_supplier_name(db, body.supplier_id)
    _contract_apply(c, body, supplier_name, db)
    c.version += 1
    c.update_by = current.id
    c.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="procurement", action="purchase_contract_update",
        biz_type="purchase_contract", biz_id=cid,
    )
    db.commit()
    return _contract_out(c)


@router.delete("/contracts/{cid}")
def delete_contract(
    cid: int,
    current: User = Depends(require_perm("procurement:contract:delete")),
    db: Session = Depends(get_db),
):
    c = db.get(PurchaseContract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if c.status != "draft":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "仅草稿合同可删除")
    c.deleted = 1
    c.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="procurement", action="purchase_contract_delete",
        biz_type="purchase_contract", biz_id=cid,
    )
    db.commit()
    return None


@router.post("/contracts/{cid}/submit")
def submit_contract(
    cid: int,
    body: S.SubmitIn | None = None,
    current: User = Depends(require_perm("procurement:contract:submit")),
    db: Session = Depends(get_db),
):
    c = db.get(PurchaseContract, cid, with_for_update=True)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if c.status not in ("draft", "rejected"):
        raise BizException(R.PROCUREMENT_INVALID_STATE, "仅草稿/已驳回合同可提交审批")
    if not c.amount:
        raise BizException(R.GENERIC_PARAM, "合同金额必填，不能提交审批")
    if not c.contract_no:
        c.contract_no = next_no(db, "purchase_contract")
        db.flush()
    inst = approval_svc.start(
        db,
        biz_type="purchase_contract",
        biz_id=c.id,
        definition_code="purchase_contract_approve",
        title=f"{c.contract_no} {c.name}",
        initiator=current,
        form_snapshot=svc.form_snapshot(c),
        variables={
            "amount": float(c.amount),
            "supplier_name": c.supplier_name,
            "request_no": c.request_no,
        },
    )
    c.status = "approving"
    c.flow_instance_id = inst.id
    c.version += 1
    c.update_time = datetime.now()
    audit(
        db,
        user_id=current.id,
        module="procurement",
        action="purchase_contract_submit",
        biz_type="purchase_contract",
        biz_id=cid,
        detail={"instanceId": inst.id, "comment": body.comment if body else ""},
    )
    db.commit()
    return _contract_out(c)


@router.post("/contracts/{cid}/void")
def void_contract(
    cid: int,
    current: User = Depends(require_perm("procurement:contract:edit")),
    db: Session = Depends(get_db),
):
    c = db.get(PurchaseContract, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if c.status == "approving":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "审批中合同不能作废，请先撤回")
    if c.status == "voided":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "合同已作废")
    c.status = "voided"
    c.version += 1
    c.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="procurement", action="purchase_contract_void",
        biz_type="purchase_contract", biz_id=cid,
    )
    db.commit()
    return _contract_out(c)


@router.post("/contracts/export")
def export_contracts(
    request: Request,
    current: User = Depends(require_perm("procurement:contract:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _contract_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = []
    for c in db.scalars(stmt).all():
        item = _contract_out(c)
        item["status"] = STATUS_CN.get(c.status, c.status)
        rows.append(item)
    payload = export_xlsx_styled(rows, CONTRACT_EXPORT_COLS, "purchase_contracts")
    audit(
        db,
        user_id=current.id,
        module="procurement",
        action="purchase_contract_export",
        detail={"count": len(rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('purchase_contracts')}"},
    )


# ---------------- 出入库 ----------------


def _stock_source_info(db: Session, orders: list[StockOrder]) -> dict[int, dict]:
    """order_id -> 样品来源信息（样品编号/名称/VIN + 所属任务）；仅 source_type=sample 的单据。"""
    ids = [o.source_id for o in orders if o.source_type == "sample" and o.source_id]
    if not ids:
        return {}
    from app.modules.task.models import Task, TaskSample

    rows = db.execute(
        select(TaskSample, Task).join(Task, Task.id == TaskSample.task_id).where(TaskSample.id.in_(ids))
    ).all()
    by_sample = {
        s.id: {
            "sampleNo": s.sample_no or "",
            "sampleName": s.name,
            "vin": s.vin or "",
            "taskId": t.id,
            "taskNo": t.task_no or "",
            "taskName": t.task_name,
        }
        for s, t in rows
    }
    return {o.id: by_sample.get(o.source_id, {}) for o in orders if o.source_type == "sample" and o.source_id}


def _stock_out(o: StockOrder, source: dict | None = None) -> dict:
    return {
        "id": o.id,
        "orderNo": o.order_no,
        "orderType": o.order_type,
        "orderTypeText": ORDER_TYPE_CN.get(o.order_type, o.order_type),
        "sourceType": o.source_type or "purchase",
        "sourceTypeText": SOURCE_TYPE_CN.get(o.source_type or "purchase", o.source_type),
        "sourceId": o.source_id,
        "contractId": o.contract_id,
        "contractNo": o.contract_no,
        "contractName": o.contract_name,
        "warehouse": o.warehouse,
        "handlerId": o.handler_id,
        "handlerName": o.handler_name,
        "orderDate": _d(o.order_date),
        "remark": o.remark or "",
        "status": o.status,
        "statusText": STOCK_STATUS_CN.get(o.status, o.status),
        "items": [
            {
                "id": i.id,
                "itemName": i.item_name,
                "spec": i.spec,
                "unit": i.unit,
                "quantity": float(i.quantity),
                "price": float(i.price) if i.price is not None else None,
                "remark": i.remark,
            }
            for i in (o.items or [])
            if not i.deleted
        ],
        "version": o.version,
        "createTime": _t(o.create_time),
        "updateTime": _t(o.update_time),
        **(source or {}),
    }


def _stock_apply(o: StockOrder, body: S.StockOrderIn, db: Session) -> None:
    if body.contract_id:
        c = db.get(PurchaseContract, body.contract_id)
        if not c or c.deleted:
            raise BizException(R.GENERIC_NOT_FOUND, "关联采购合同不存在")
        if c.status != "approved":
            raise BizException(R.PROCUREMENT_INVALID_STATE, "仅已通过的采购合同可登记出入库")
        o.contract_id = c.id
        o.contract_no = c.contract_no or ""
        o.contract_name = c.name
    else:
        o.contract_id = None
        o.contract_no = ""
        o.contract_name = ""
    o.warehouse = body.warehouse
    o.handler_id = body.handler_id
    o.handler_name = body.handler_name
    o.order_date = body.order_date
    o.remark = body.remark
    o.items = [
        StockOrderItem(
            item_name=i.item_name,
            spec=i.spec,
            unit=i.unit,
            quantity=i.quantity,
            price=i.price,
            remark=i.remark,
        )
        for i in body.items
    ]


def _stock_filtered(db: Session, request: Request, page: PageParams):
    stmt = select(StockOrder)
    # 来源筛选：purchase 含历史空值；sample 等其余取值精确匹配（样品单挂在任务样品上）
    src = (request.query_params.get("filters[source_type]") or "").strip()
    extra_where = []
    if src == "purchase":
        extra_where.append(StockOrder.source_type.in_(["", "purchase"]))
    elif src:
        extra_where.append(StockOrder.source_type == src)
    return apply_list_filters(
        stmt,
        StockOrder,
        request.query_params,
        db,
        page,
        search_cols=["order_no", "contract_no", "contract_name"],
        filter_cols={"status", "order_type", "contract_id", "warehouse"},
        range_cols={"order_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "order_no", "order_date", "status", "order_type"},
        extra_where=extra_where,
    )


@router.get("/stock-orders")
def list_stock_orders(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("procurement:stock:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _stock_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    info = _stock_source_info(db, rows)
    return {"items": [_stock_out(o, info.get(o.id)) for o in rows], "total": total, "page": page, "size": size}


@router.get("/stock-orders/counts")
def stock_counts(
    user: User = Depends(require_perm("procurement:stock:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(StockOrder.status, func.count()).where(StockOrder.deleted == 0).group_by(StockOrder.status)
    ).all()
    data = {s: 0 for s in ("registered", "confirmed")}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


@router.get("/stock-orders/{oid}")
def get_stock_order(
    oid: int,
    user: User = Depends(require_perm("procurement:stock:list")),
    db: Session = Depends(get_db),
):
    o = db.get(StockOrder, oid)
    if not o or o.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _stock_out(o, _stock_source_info(db, [o]).get(o.id))


@router.post("/stock-orders", status_code=201)
def create_stock_order(
    body: S.StockOrderIn,
    current: User = Depends(require_perm("procurement:stock:create")),
    db: Session = Depends(get_db),
):
    o = StockOrder(
        order_no=next_no(db, "stock_in" if body.order_type == "in" else "stock_out"),
        order_type=body.order_type,
        status="registered",
        create_by=current.id,
    )
    _stock_apply(o, body, db)
    if not o.handler_id:
        o.handler_id = current.id
        o.handler_name = o.handler_name or current.name or current.username
    db.add(o)
    db.flush()
    audit(
        db, user_id=current.id, module="procurement", action="stock_order_create",
        biz_type="stock_order", biz_id=o.id, detail={"orderType": o.order_type},
    )
    db.commit()
    return _stock_out(o)


@router.put("/stock-orders/{oid}")
def update_stock_order(
    oid: int,
    body: S.StockOrderIn,
    current: User = Depends(require_perm("procurement:stock:edit")),
    db: Session = Depends(get_db),
):
    o = db.get(StockOrder, oid)
    if not o or o.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if o.status != "registered":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "已确认单据只读，不能编辑")
    _check_version(o, body.version)
    if body.order_type != o.order_type:
        raise BizException(R.GENERIC_PARAM, "出入库类型不可修改")
    _stock_apply(o, body, db)
    o.version += 1
    o.update_by = current.id
    o.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="procurement", action="stock_order_update",
        biz_type="stock_order", biz_id=oid,
    )
    db.commit()
    return _stock_out(o)


@router.post("/stock-orders/{oid}/confirm")
def confirm_stock_order(
    oid: int,
    current: User = Depends(require_perm("procurement:stock:confirm")),
    db: Session = Depends(get_db),
):
    o = db.get(StockOrder, oid, with_for_update=True)
    if not o or o.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if o.status != "registered":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "仅已登记单据可确认")
    if o.source_type == svc.SOURCE_SAMPLE and o.source_id:
        # 样品出入库单：确认时回写样品 in_stock 并补写样品流水（同事务，失败整体回滚）
        svc.confirm_sample_stock(db, o, current)
    o.status = "confirmed"
    o.version += 1
    o.update_by = current.id
    o.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="procurement", action="stock_order_confirm",
        biz_type="stock_order", biz_id=oid, detail={"orderNo": o.order_no},
    )
    db.commit()
    return _stock_out(o, _stock_source_info(db, [o]).get(o.id))


@router.delete("/stock-orders/{oid}")
def delete_stock_order(
    oid: int,
    current: User = Depends(require_perm("procurement:stock:delete")),
    db: Session = Depends(get_db),
):
    o = db.get(StockOrder, oid)
    if not o or o.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if o.status != "registered":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "仅已登记单据可删除")
    o.deleted = 1
    o.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="procurement", action="stock_order_delete",
        biz_type="stock_order", biz_id=oid,
    )
    db.commit()
    return None


@router.post("/stock-orders/export")
def export_stock_orders(
    request: Request,
    current: User = Depends(require_perm("procurement:stock:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _stock_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = db.scalars(stmt).all()
    info = _stock_source_info(db, rows)
    payload_rows = []
    for o in rows:
        item = _stock_out(o, info.get(o.id))
        item["status"] = STOCK_STATUS_CN.get(o.status, o.status)
        item["orderType"] = ORDER_TYPE_CN.get(o.order_type, o.order_type)
        item["sourceType"] = SOURCE_TYPE_CN.get(o.source_type or "purchase", o.source_type)
        src = info.get(o.id) or {}
        item["sourceRef"] = (
            f"{src.get('sampleNo', '')} {src.get('sampleName', '')}".strip() if o.source_type == "sample" else ""
        )
        payload_rows.append(item)
    payload = export_xlsx_styled(payload_rows, STOCK_EXPORT_COLS, "stock_orders")
    audit(
        db,
        user_id=current.id,
        module="procurement",
        action="stock_order_export",
        detail={"count": len(rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('stock_orders')}"},
    )

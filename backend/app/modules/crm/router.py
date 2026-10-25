"""CRM 客户路由 /api/v1/crm。"""

from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile
from sqlalchemy import func, or_, select
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
from app.modules.auth.models import User
from app.modules.contract.models import Contract
from app.modules.crm import schemas as S
from app.modules.crm.models import Customer
from app.modules.finance.models import Payment, Settlement
from app.modules.task.models import Task
from app.services.excel import export_xlsx_styled, import_rows, now_filename, template_xlsx
from app.services.numbering import next_no

router = APIRouter(prefix="/crm", tags=["crm"], route_class=EnvelopeRoute)

EXPORT_COLS = [
    {"key": "customerNo", "label": "客户编号", "width": 14},
    {"key": "name", "label": "客户名称", "width": 32},
    {"key": "code", "label": "客户代码", "width": 14},
    {"key": "customerType", "label": "客户类型", "width": 12},
    {"key": "taxNo", "label": "纳税识别号", "width": 22},
    {"key": "grade", "label": "客户等级", "width": 10},
    {"key": "status", "label": "状态", "width": 10},
    {"key": "country", "label": "国家", "width": 10},
    {"key": "province", "label": "省份", "width": 10},
    {"key": "city", "label": "城市", "width": 10},
    {"key": "address", "label": "注册地址", "width": 30},
    {"key": "bankName", "label": "开户行", "width": 20},
    {"key": "bankAccount", "label": "银行账号", "width": 22},
    {"key": "payOrg", "label": "付款单位", "width": 24},
    {"key": "remark", "label": "备注", "width": 24},
    {"key": "createTime", "label": "创建时间", "width": 19},
]

STATUS_CN = {"enabled": "启用", "disabled": "停用"}


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _out(c: Customer) -> dict:
    return {
        "id": c.id,
        "customerNo": c.customer_no,
        "name": c.name,
        "code": c.code,
        "customerType": c.customer_type,
        "taxNo": c.tax_no,
        "grade": c.grade,
        "status": c.status,
        "country": c.country,
        "province": c.province,
        "city": c.city,
        "address": c.address,
        "bankName": c.bank_name,
        "bankAccount": c.bank_account,
        "payOrg": c.pay_org,
        "contactPerson": c.contact_person or "",
        "contactPhone": c.contact_phone or "",
        "licenseFileId": c.license_file_id,
        "remark": c.remark or "",
        "createTime": _t(c.create_time),
        "updateTime": _t(c.update_time),
    }


def _check_tax_no(db: Session, tax_no: str, exclude_id: int | None = None) -> None:
    if not tax_no:
        return
    stmt = select(Customer.id).where(Customer.tax_no == tax_no, Customer.deleted == 0)
    if exclude_id:
        stmt = stmt.where(Customer.id != exclude_id)
    if db.scalar(stmt):
        raise BizException(R.CRM_TAX_NO_DUPLICATE)


def _apply(c: Customer, body: S.CustomerIn) -> None:
    c.name = body.name
    c.code = body.code
    c.customer_type = body.customer_type
    c.tax_no = body.tax_no
    c.grade = body.grade
    c.status = body.status
    c.country = body.country
    c.province = body.province
    c.city = body.city
    c.address = body.address
    c.bank_name = body.bank_name
    c.bank_account = body.bank_account
    c.pay_org = body.pay_org
    c.contact_person = body.contact_person
    c.contact_phone = body.contact_phone
    c.license_file_id = body.license_file_id
    c.remark = body.remark


def _filtered(db: Session, request: Request, page: PageParams):
    stmt = select(Customer)
    return apply_list_filters(
        stmt,
        Customer,
        request.query_params,
        db,
        page,
        search_cols=["name", "customer_no", "tax_no", "code"],
        filter_cols={"status", "customer_type", "grade"},
        range_cols={"create_time"},
        sort_cols={"update_time", "create_time", "id", "customer_no", "name", "customer_type", "grade", "status"},
    )


@router.get("/customers")
def list_customers(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("crm:customer:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_out(c) for c in rows], "total": total, "page": page, "size": size}


@router.get("/customers/counts")
def customer_counts(
    user: User = Depends(require_perm("crm:customer:list")),
    db: Session = Depends(get_db),
):
    """状态页签计数（全部/enabled/disabled）。"""
    rows = db.execute(
        select(Customer.status, func.count()).where(Customer.deleted == 0).group_by(Customer.status)
    ).all()
    data = {"enabled": 0, "disabled": 0}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


@router.get("/customers/options")
def customer_options(
    q: str = Query("", max_length=64),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """远程模糊选择器专用（合同/任务复用）。"""
    stmt = select(Customer).where(Customer.deleted == 0, Customer.status == "enabled")
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Customer.name.like(like), Customer.customer_no.like(like)))
    rows = db.scalars(stmt.order_by(Customer.update_time.desc()).limit(limit)).all()
    return [
        {
            "id": c.id,
            "label": c.name,
            "sub": c.customer_no,
            "payOrg": c.pay_org,
            "taxNo": c.tax_no,
            "contactPerson": c.contact_person or "",
            "contactPhone": c.contact_phone or "",
        }
        for c in rows
    ]


@router.post("/customers", status_code=201)
def create_customer(
    body: S.CustomerIn,
    current: User = Depends(require_perm("crm:customer:create")),
    db: Session = Depends(get_db),
):
    _check_tax_no(db, body.tax_no)
    c = Customer(customer_no=next_no(db, "customer"), create_by=current.id)
    _apply(c, body)
    db.add(c)
    db.flush()
    audit(db, user_id=current.id, module="crm", action="customer_create", biz_type="customer", biz_id=c.id)
    db.commit()
    return _out(c)


@router.put("/customers/{cid}")
def update_customer(
    cid: int,
    body: S.CustomerIn,
    current: User = Depends(require_perm("crm:customer:edit")),
    db: Session = Depends(get_db),
):
    c = db.get(Customer, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    _check_tax_no(db, body.tax_no, exclude_id=cid)
    _apply(c, body)
    c.update_by = current.id
    c.update_time = datetime.now()
    audit(db, user_id=current.id, module="crm", action="customer_update", biz_type="customer", biz_id=cid)
    db.commit()
    return _out(c)


@router.delete("/customers/{cid}")
def delete_customer(
    cid: int,
    current: User = Depends(require_perm("crm:customer:delete")),
    db: Session = Depends(get_db),
):
    c = db.get(Customer, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    used = db.scalar(
        select(Contract.id).where(Contract.customer_id == cid, Contract.deleted == 0).limit(1)
    )
    if used:
        raise BizException(R.GENERIC_PARAM, "该客户已关联合同，不能删除")
    c.deleted = 1
    c.update_time = datetime.now()
    audit(db, user_id=current.id, module="crm", action="customer_delete", biz_type="customer", biz_id=cid)
    db.commit()
    return None


@router.post("/customers/export")
def export_customers(
    request: Request,
    current: User = Depends(require_perm("crm:customer:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = []
    for c in db.scalars(stmt).all():
        item = _out(c)
        item["status"] = STATUS_CN.get(c.status, c.status)
        rows.append(item)
    payload = export_xlsx_styled(rows, EXPORT_COLS, "customers")
    audit(
        db,
        user_id=current.id,
        module="crm",
        action="customer_export",
        detail={"count": len(rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('customers')}"},
    )


@router.get("/customers/template")
def customer_template(
    current: User = Depends(require_perm("crm:customer:import")),
    db: Session = Depends(get_db),
):
    cols = [
        {"key": c["key"], "label": c["label"], "width": c["width"]}
        for c in EXPORT_COLS
        if c["key"] != "createTime"
    ]
    return Response(
        template_xlsx(cols, "customer_template"),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('customer_template')}"},
    )


@router.post("/customers/import")
def import_customers(
    request: Request,
    file: UploadFile,
    current: User = Depends(require_perm("crm:customer:import")),
    db: Session = Depends(get_db),
):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise BizException(R.GENERIC_PARAM, "仅支持 .xlsx 文件")
    data = file.file.read()
    if len(data) > settings.upload_max_mb * 1024 * 1024:
        raise BizException(R.GENERIC_PARAM, f"文件超过大小上限 {settings.upload_max_mb}MB")
    cols = [{"key": c["key"], "label": c["label"]} for c in EXPORT_COLS if c["key"] != "createTime"]

    def require_name(v, row):
        return None if str(v or "").strip() else "客户名称必填"

    ok_rows, errors = import_rows(data, cols, validators={"name": require_name})
    created, skipped = 0, []
    for idx, row in enumerate(ok_rows, start=2):
        tax_no = str(row.get("taxNo") or "").strip()
        try:
            _check_tax_no(db, tax_no)
            c = Customer(customer_no=next_no(db, "customer"), create_by=current.id)
            _apply(
                c,
                S.CustomerIn(
                    name=str(row.get("name") or "").strip(),
                    code=str(row.get("code") or "").strip(),
                    customer_type=str(row.get("customerType") or "").strip(),
                    tax_no=tax_no,
                    grade=str(row.get("grade") or "").strip(),
                    status="enabled",
                    country=str(row.get("country") or "").strip(),
                    province=str(row.get("province") or "").strip(),
                    city=str(row.get("city") or "").strip(),
                    address=str(row.get("address") or "").strip(),
                    bank_name=str(row.get("bankName") or "").strip(),
                    bank_account=str(row.get("bankAccount") or "").strip(),
                    pay_org=str(row.get("payOrg") or "").strip(),
                    remark=str(row.get("remark") or "").strip(),
                ),
            )
            db.add(c)
            db.flush()
            created += 1
        except BizException as e:
            field = "纳税识别号" if e.code == R.CRM_TAX_NO_DUPLICATE else ""
            errors.append({"row": idx, "field": field, "message": e.message})
    audit(
        db,
        user_id=current.id,
        module="crm",
        action="customer_import",
        detail={"created": created, "errors": len(errors)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return {"created": created, "errors": errors, "skipped": skipped}


# 注意：必须放在 /customers/options、/customers/template 等静态 GET 路由之后，避免 {cid} 抢占匹配
@router.get("/customers/{cid}")
def get_customer(
    cid: int,
    user: User = Depends(require_perm("crm:customer:list")),
    db: Session = Depends(get_db),
):
    """客户详情 + 汇总（合同/任务/结算/到账）。"""
    c = db.get(Customer, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    data = _out(c)
    contract_count, contract_total = db.execute(
        select(func.count(), func.coalesce(func.sum(Contract.amount), 0)).where(
            Contract.customer_id == cid, Contract.deleted == 0
        )
    ).one()
    task_count = db.scalar(select(func.count()).where(Task.customer_id == cid, Task.deleted == 0)) or 0
    settled_total = db.scalar(
        select(func.coalesce(func.sum(Settlement.amount), 0)).where(
            Settlement.customer_id == cid, Settlement.deleted == 0
        )
    )
    paid_total = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(Settlement, Settlement.id == Payment.settlement_id)
        .where(Settlement.customer_id == cid, Settlement.deleted == 0, Payment.deleted == 0)
    )
    data["summary"] = {
        "contractCount": contract_count,
        "contractTotal": float(contract_total or 0),
        "taskCount": task_count,
        "settledTotal": float(settled_total or 0),
        "paidTotal": float(paid_total or 0),
    }
    return data

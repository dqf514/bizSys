"""CRM 客户路由 /api/v1/crm。"""

import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request, Response, UploadFile
from sqlalchemy import func, or_, select, update
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
from app.modules.crm.models import Customer, PartnerAttachment, PartnerContact
from app.modules.finance.models import Payment, Settlement
from app.modules.procurement.models import PurchaseContract, PurchaseRequest
from app.modules.task.models import Task
from app.services.excel import export_xlsx_styled, import_rows, now_filename, template_xlsx
from app.services.numbering import next_no

router = APIRouter(prefix="/crm", tags=["crm"], route_class=EnvelopeRoute)

EXPORT_COLS = [
    {"key": "customerNo", "label": "客户编号", "width": 14},
    {"key": "name", "label": "客户名称", "width": 32},
    {"key": "partnerType", "label": "单位类型", "width": 12},
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
PARTNER_TYPE_CN = {"customer": "客户", "supplier": "供应商", "both": "客户+供应商"}


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _out(c: Customer) -> dict:
    return {
        "id": c.id,
        "customerNo": c.customer_no,
        "name": c.name,
        "partnerType": c.partner_type,
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
        "supplyCategory": c.supply_category,
        "supplierRating": c.supplier_rating,
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
    c.partner_type = body.partner_type
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
    c.supply_category = body.supply_category
    c.supplier_rating = body.supplier_rating
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
        filter_cols={"status", "customer_type", "grade", "partner_type"},
        range_cols={"create_time"},
        sort_cols={
            "update_time", "create_time", "id", "customer_no", "name",
            "customer_type", "grade", "status", "partner_type",
        },
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
    partner_type: str = Query("", pattern="^(|customer|supplier|both)$"),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """远程模糊选择器专用（合同/任务/采购复用）。

    partner_type：supplier → 仅供应商（含 both）；customer → 仅客户（含 both）；缺省不过滤。
    """
    stmt = select(Customer).where(Customer.deleted == 0, Customer.status == "enabled")
    if partner_type == "supplier":
        stmt = stmt.where(Customer.partner_type.in_(["supplier", "both"]))
    elif partner_type == "customer":
        stmt = stmt.where(Customer.partner_type.in_(["customer", "both"]))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Customer.name.like(like), Customer.customer_no.like(like)))
    rows = db.scalars(stmt.order_by(Customer.update_time.desc()).limit(limit)).all()
    return [
        {
            "id": c.id,
            "label": c.name,
            "sub": c.customer_no,
            "partnerType": c.partner_type,
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
        item["partnerType"] = PARTNER_TYPE_CN.get(c.partner_type, c.partner_type)
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
        partner_raw = str(row.get("partnerType") or "").strip()
        partner_type = {v: k for k, v in PARTNER_TYPE_CN.items()}.get(partner_raw, partner_raw) or "customer"
        if partner_type not in PARTNER_TYPE_CN:
            partner_type = "customer"
        try:
            _check_tax_no(db, tax_no)
            c = Customer(customer_no=next_no(db, "customer"), create_by=current.id)
            _apply(
                c,
                S.CustomerIn(
                    name=str(row.get("name") or "").strip(),
                    partner_type=partner_type,
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
    # 供应商侧指标（purchaseContractCount/purchaseTotal）；客户类型下为 0
    pur_count, pur_total = db.execute(
        select(func.count(), func.coalesce(func.sum(PurchaseContract.amount), 0)).where(
            PurchaseContract.supplier_id == cid, PurchaseContract.deleted == 0
        )
    ).one()
    data["summary"]["purchaseContractCount"] = pur_count
    data["summary"]["purchaseTotal"] = float(pur_total or 0)
    return data


# ---------------- 联系人 ----------------


def _contact_out(c: PartnerContact) -> dict:
    return {
        "id": c.id,
        "customerId": c.customer_id,
        "name": c.name,
        "position": c.position,
        "phone": c.phone,
        "email": c.email,
        "isPrimary": bool(c.is_primary),
        "remark": c.remark,
        "createTime": _t(c.create_time),
        "updateTime": _t(c.update_time),
    }


def _load_customer(db: Session, cid: int) -> Customer:
    c = db.get(Customer, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return c


def _clear_primary(db: Session, customer_id: int, keep_id: int | None = None) -> None:
    stmt = (
        update(PartnerContact)
        .where(PartnerContact.customer_id == customer_id, PartnerContact.deleted == 0, PartnerContact.is_primary == 1)
        .values(is_primary=0)
    )
    if keep_id:
        stmt = stmt.where(PartnerContact.id != keep_id)
    db.execute(stmt)


@router.get("/customers/{cid}/contacts")
def list_contacts(
    cid: int,
    user: User = Depends(require_perm("crm:customer:list")),
    db: Session = Depends(get_db),
):
    _load_customer(db, cid)
    rows = db.scalars(
        select(PartnerContact)
        .where(PartnerContact.customer_id == cid, PartnerContact.deleted == 0)
        .order_by(PartnerContact.is_primary.desc(), PartnerContact.id.asc())
    ).all()
    return {"items": [_contact_out(c) for c in rows], "total": len(rows)}


@router.post("/customers/{cid}/contacts", status_code=201)
def create_contact(
    cid: int,
    body: S.ContactIn,
    current: User = Depends(require_perm("crm:customer:edit")),
    db: Session = Depends(get_db),
):
    _load_customer(db, cid)
    if body.is_primary:
        _clear_primary(db, cid)
    row = PartnerContact(
        customer_id=cid,
        name=body.name,
        position=body.position,
        phone=body.phone,
        email=body.email,
        is_primary=1 if body.is_primary else 0,
        remark=body.remark,
        create_by=current.id,
    )
    db.add(row)
    db.flush()
    audit(db, user_id=current.id, module="crm", action="partner_contact_create", biz_type="customer", biz_id=cid,
          detail={"contactId": row.id, "name": row.name})
    db.commit()
    return _contact_out(row)


@router.put("/contacts/{ctid}")
def update_contact(
    ctid: int,
    body: S.ContactIn,
    current: User = Depends(require_perm("crm:customer:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(PartnerContact, ctid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if body.is_primary:
        _clear_primary(db, row.customer_id, keep_id=row.id)
    row.name = body.name
    row.position = body.position
    row.phone = body.phone
    row.email = body.email
    row.is_primary = 1 if body.is_primary else 0
    row.remark = body.remark
    row.update_by = current.id
    row.update_time = datetime.now()
    audit(db, user_id=current.id, module="crm", action="partner_contact_update", biz_type="customer",
          biz_id=row.customer_id, detail={"contactId": row.id, "name": row.name})
    db.commit()
    return _contact_out(row)


@router.delete("/contacts/{ctid}")
def delete_contact(
    ctid: int,
    current: User = Depends(require_perm("crm:customer:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(PartnerContact, ctid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    row.deleted = 1
    row.update_time = datetime.now()
    audit(db, user_id=current.id, module="crm", action="partner_contact_delete", biz_type="customer",
          biz_id=row.customer_id, detail={"contactId": ctid, "name": row.name})
    db.commit()
    return None


# ---------------- 附件 ----------------

ATTACHMENT_CATEGORIES = ("license", "qualification", "contract", "other")

# 魔数白名单：防改扩展名伪装（与 settings.upload_ext_set 交集校验）
_MAGIC = {
    "pdf": (b"%PDF-",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "zip": (b"PK\x03\x04",),
    "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
    "doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
}


def _attachment_out(a: PartnerAttachment, uploader: str = "") -> dict:
    return {
        "id": a.id,
        "customerId": a.customer_id,
        "category": a.category,
        "fileName": a.file_name,
        "size": a.size,
        "contentType": a.content_type,
        "remark": a.remark,
        "uploaderName": uploader,
        "createTime": _t(a.create_time),
    }


@router.get("/customers/{cid}/attachments")
def list_attachments(
    cid: int,
    category: str = Query(""),
    user: User = Depends(require_perm("crm:customer:list")),
    db: Session = Depends(get_db),
):
    _load_customer(db, cid)
    stmt = select(PartnerAttachment).where(PartnerAttachment.customer_id == cid, PartnerAttachment.deleted == 0)
    if category:
        stmt = stmt.where(PartnerAttachment.category == category)
    rows = db.scalars(stmt.order_by(PartnerAttachment.id.desc())).all()
    uids = {a.create_by for a in rows if a.create_by}
    users = dict(db.execute(select(User.id, User.name).where(User.id.in_(uids))).all()) if uids else {}
    return {
        "items": [_attachment_out(a, users.get(a.create_by, "")) for a in rows],
        "total": len(rows),
    }


@router.post("/customers/{cid}/attachments", status_code=201)
def upload_partner_attachment(
    cid: int,
    file: UploadFile,
    category: str = Form("other"),
    remark: str = Form(""),
    current: User = Depends(require_perm("crm:customer:edit")),
    db: Session = Depends(get_db),
):
    _load_customer(db, cid)
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
    magic = _MAGIC.get(ext)
    if magic and not any(data.startswith(m) for m in magic):
        raise BizException(R.GENERIC_PARAM, "文件内容与扩展名不符")
    rel = Path("partner") / f"{uuid.uuid4().hex}.{ext}"
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    row = PartnerAttachment(
        customer_id=cid,
        category=category,
        file_name=filename or "file",
        size=len(data),
        content_type=file.content_type or "",
        path=str(rel),
        remark=remark[:500],
        create_by=current.id,
    )
    db.add(row)
    db.flush()
    audit(db, user_id=current.id, module="crm", action="partner_attachment_upload", biz_type="customer", biz_id=cid,
          detail={"fileId": row.id, "file": filename, "category": category})
    db.commit()
    return _attachment_out(row, current.name or current.username)


@router.get("/attachments/{aid}")
def download_partner_attachment(
    aid: int,
    user: User = Depends(require_perm("crm:customer:list")),
    db: Session = Depends(get_db),
):
    a = db.get(PartnerAttachment, aid)
    if not a or a.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    dest = Path(settings.upload_dir) / a.path
    if not dest.exists():
        raise BizException(R.GENERIC_NOT_FOUND, "文件已丢失")
    return Response(
        dest.read_bytes(),
        media_type=a.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(a.file_name)}"},
    )


@router.delete("/attachments/{aid}")
def delete_partner_attachment(
    aid: int,
    current: User = Depends(require_perm("crm:customer:edit")),
    db: Session = Depends(get_db),
):
    a = db.get(PartnerAttachment, aid)
    if not a or a.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    a.deleted = 1
    a.update_time = datetime.now()
    audit(db, user_id=current.id, module="crm", action="partner_attachment_delete", biz_type="customer",
          biz_id=a.customer_id, detail={"fileId": aid, "file": a.file_name})
    db.commit()
    try:
        (Path(settings.upload_dir) / a.path).unlink(missing_ok=True)
    except OSError:
        pass  # 磁盘清理失败不阻断（记录已逻辑删）
    return None


# ---------------- 供应商采购清单 ----------------


@router.get("/customers/{cid}/procurement")
def customer_procurement(
    cid: int,
    user: User = Depends(require_perm("procurement:contract:list")),
    db: Session = Depends(get_db),
):
    """供应商视角采购清单：采购合同（可跳详情）+ 这些合同关联的采购申请。"""
    _load_customer(db, cid)
    contracts = db.scalars(
        select(PurchaseContract)
        .where(PurchaseContract.supplier_id == cid, PurchaseContract.deleted == 0)
        .order_by(PurchaseContract.id.desc())
        .limit(200)
    ).all()
    request_ids = sorted({c.request_id for c in contracts if c.request_id})
    requests = (
        db.scalars(
            select(PurchaseRequest)
            .where(PurchaseRequest.id.in_(request_ids), PurchaseRequest.deleted == 0)
            .order_by(PurchaseRequest.id.desc())
        ).all()
        if request_ids
        else []
    )
    return {
        "contracts": [
            {
                "id": c.id,
                "contractNo": c.contract_no or "",
                "name": c.name,
                "amount": float(c.amount) if c.amount is not None else None,
                "status": c.status,
                "signDate": c.sign_date.strftime("%Y-%m-%d") if c.sign_date else "",
                "createTime": _t(c.create_time),
            }
            for c in contracts
        ],
        "requests": [
            {
                "id": r.id,
                "requestNo": r.request_no or "",
                "title": r.title,
                "status": r.status,
                "createTime": _t(r.create_time),
            }
            for r in requests
        ],
    }

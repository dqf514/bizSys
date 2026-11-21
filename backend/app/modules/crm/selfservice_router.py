"""客户自助体系路由（B2）：客户方人员备案 + 客户自助账号管理，前缀 /api/v1/crm。

与 `crm/router.py` 同前缀分文件挂载（参照 asset 域的 finance_router 做法）。
"""

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
from app.modules.auth.models import User
from app.modules.crm import schemas as S
from app.modules.crm import staff_service
from app.modules.crm.models import Customer, PartnerStaff
from app.modules.portal.models import PartnerUser
from app.modules.portal.selfservice import account_out, review_account, set_account_status
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/crm", tags=["crm"], route_class=EnvelopeRoute)

STAFF_EXPORT_COLS = [
    {"key": "name", "label": "姓名", "width": 14},
    {"key": "customerName", "label": "客户名称", "width": 26},
    {"key": "staffTypeLabel", "label": "人员类型", "width": 14},
    {"key": "position", "label": "职务", "width": 14},
    {"key": "phone", "label": "联系电话", "width": 16},
    {"key": "plateNo", "label": "车牌号", "width": 14},
    {"key": "planVisitDate", "label": "来访日期", "width": 12},
    {"key": "ndaSignedText", "label": "NDA", "width": 8},
    {"key": "statusText", "label": "状态", "width": 10},
    {"key": "sourceText", "label": "来源", "width": 12},
    {"key": "reviewName", "label": "审核人", "width": 12},
    {"key": "createTime", "label": "登记时间", "width": 19},
]


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _d(v) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return v or ""


def _staff_type_labels(db: Session) -> dict:
    from app.modules.task.service import dict_labels

    return dict_labels(db, "partner_staff_type")


def _staff_out(s: PartnerStaff, staff_type_labels: dict | None = None) -> dict:
    labels = staff_type_labels or {}
    return {
        "id": s.id,
        "customerId": s.customer_id,
        "customerName": s.customer_name,
        "name": s.name,
        "gender": s.gender,
        "idNo": s.id_no,
        "position": s.position,
        "phone": s.phone,
        "email": s.email,
        "plateNo": s.plate_no,
        "company": s.company,
        "staffType": s.staff_type,
        "staffTypeLabel": labels.get(s.staff_type, s.staff_type),
        "visitPurpose": s.visit_purpose,
        "planVisitDate": _d(s.plan_visit_date),
        "ndaSigned": bool(s.nda_signed),
        "visitPerm": s.visit_perm or "",
        "source": s.source,
        "sourceText": "客户自助登记" if s.source == "portal" else "内部代登记",
        "applicantName": s.applicant_name,
        "status": s.status,
        "statusText": staff_service.STAFF_STATUS_CN.get(s.status, s.status),
        "reviewBy": s.review_by,
        "reviewName": s.review_name,
        "reviewAt": _t(s.review_at),
        "reviewComment": s.review_comment or "",
        "bizOwnerId": s.biz_owner_id,
        "bizOwnerName": s.biz_owner_name,
        "visitorId": s.visitor_id,
        "remark": s.remark or "",
        "createTime": _t(s.create_time),
        "updateTime": _t(s.update_time),
    }


def _load_staff(db: Session, sid: int) -> PartnerStaff:
    s = db.get(PartnerStaff, sid)
    if not s or s.deleted:
        raise BizException(R.CRM_STAFF_NOT_FOUND)
    return s


def _filtered_staff(db: Session, request: Request, page: PageParams):
    stmt = select(PartnerStaff)
    return apply_list_filters(
        stmt,
        PartnerStaff,
        request.query_params,
        db,
        page,
        search_cols=["name", "customer_name", "phone", "position", "id_no"],
        filter_cols={"status", "staff_type", "source", "customer_id", "biz_owner_id"},
        range_cols={"plan_visit_date", "create_time"},
        sort_cols={"id", "name", "customer_name", "status", "plan_visit_date", "create_time", "staff_type"},
        default_sort=("id", "desc"),
    )


# ---------------- 客户方人员备案 ----------------


@router.get("/partner-staffs")
def list_partner_staff(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("crm:staff:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered_staff(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    labels = _staff_type_labels(db)
    return {
        "items": [_staff_out(s, labels) for s in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/partner-staffs/counts")
def partner_staff_counts(
    user: User = Depends(require_perm("crm:staff:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(PartnerStaff.status, func.count()).where(PartnerStaff.deleted == 0).group_by(PartnerStaff.status)
    ).all()
    data = {s: 0 for s in staff_service.STAFF_STATUS_CN}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/partner-staffs/{sid}")
def get_partner_staff(
    sid: int,
    user: User = Depends(require_perm("crm:staff:list")),
    db: Session = Depends(get_db),
):
    return _staff_out(_load_staff(db, sid), _staff_type_labels(db))


@router.post("/partner-staffs", status_code=201)
def create_partner_staff(
    body: S.PartnerStaffIn,
    current: User = Depends(require_perm("crm:staff:create")),
    db: Session = Depends(get_db),
):
    """内部代登记（客户电话/邮件提供的人员信息补录）。"""
    customer_name = body.customer_name
    if body.customer_id:
        c = db.get(Customer, body.customer_id)
        if not c or c.deleted:
            raise BizException(R.GENERIC_NOT_FOUND, "往来单位不存在")
        customer_name = c.name
    s = staff_service.create_staff(
        db,
        body,
        source="internal",
        customer_id=body.customer_id,
        customer_name=customer_name,
        applicant_account_id=None,
        applicant_name=current.name or current.username,
    )
    audit(
        db, user_id=current.id, module="crm", action="partner_staff_create",
        biz_type="partner_staff", biz_id=s.id, detail={"name": s.name},
    )
    db.commit()
    return _staff_out(s, _staff_type_labels(db))


@router.post("/partner-staffs/{sid}/review")
def review_partner_staff(
    sid: int,
    body: S.PartnerStaffReviewIn,
    current: User = Depends(require_perm("crm:staff:review")),
    db: Session = Depends(get_db),
):
    """客户经理审核：备案通过后抄送业务负责人与访客管理人员，并勾选访客系统权限。"""
    s = _load_staff(db, sid)
    s, notified = staff_service.review_staff(
        db,
        s,
        body.action,
        reviewer_id=current.id,
        reviewer_name=current.name or current.username,
        comment=body.comment,
        biz_owner_id=body.biz_owner_id,
        biz_owner_name=body.biz_owner_name,
        visit_perm=body.visit_perm,
        nda_signed=body.nda_signed,
    )
    audit(
        db, user_id=current.id, module="crm", action=f"partner_staff_{body.action}",
        biz_type="partner_staff", biz_id=sid,
        detail={"status": s.status, "notified": notified, "visitPerm": s.visit_perm},
    )
    db.commit()
    return _staff_out(s, _staff_type_labels(db))


@router.post("/partner-staffs/{sid}/toggle")
def toggle_partner_staff(
    sid: int,
    status: str = Query(..., pattern="^(approved|disabled)$"),
    current: User = Depends(require_perm("crm:staff:edit")),
    db: Session = Depends(get_db),
):
    s = _load_staff(db, sid)
    staff_service.set_staff_status(db, s, status)
    audit(
        db, user_id=current.id, module="crm", action="partner_staff_toggle",
        biz_type="partner_staff", biz_id=sid, detail={"status": status},
    )
    db.commit()
    return _staff_out(s, _staff_type_labels(db))


@router.post("/partner-staffs/export")
def export_partner_staff(
    request: Request,
    current: User = Depends(require_perm("crm:staff:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _filtered_staff(db, request, SimpleNamespace(page=1, size=100_000))
    rows = db.scalars(stmt).all()
    labels = _staff_type_labels(db)
    payload_rows = []
    for s in rows:
        item = _staff_out(s, labels)
        item["ndaSignedText"] = "已签" if s.nda_signed else "未签"
        payload_rows.append(item)
    payload = export_xlsx_styled(payload_rows, STAFF_EXPORT_COLS, "partner_staffs")
    audit(
        db, user_id=current.id, module="crm", action="partner_staff_export",
        detail={"count": len(payload_rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('partner_staffs')}"},
    )


# ---------------- 客户自助账号管理 ----------------


def _filtered_accounts(db: Session, request: Request, page: PageParams):
    stmt = select(PartnerUser).where(PartnerUser.account_type == "customer")
    return apply_list_filters(
        stmt,
        PartnerUser,
        request.query_params,
        db,
        page,
        search_cols=["username", "company_name", "contact_name", "phone", "email"],
        filter_cols={"status", "customer_id", "manager_id"},
        range_cols={"create_time", "last_login_at"},
        sort_cols={"id", "username", "company_name", "status", "create_time", "last_login_at"},
        default_sort=("id", "desc"),
    )


@router.get("/accounts")
def list_customer_accounts(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("crm:account:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered_accounts(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {
        "items": [account_out(p) for p in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/accounts/counts")
def customer_account_counts(
    user: User = Depends(require_perm("crm:account:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(PartnerUser.status, func.count())
        .where(PartnerUser.deleted == 0, PartnerUser.account_type == "customer")
        .group_by(PartnerUser.status)
    ).all()
    data = {"pending": 0, "enabled": 0, "rejected": 0, "disabled": 0}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/accounts/{aid}")
def get_customer_account(
    aid: int,
    user: User = Depends(require_perm("crm:account:list")),
    db: Session = Depends(get_db),
):
    p = db.get(PartnerUser, aid)
    if not p or p.deleted or p.account_type != "customer":
        raise BizException(R.CRM_ACCOUNT_NOT_FOUND)
    return account_out(p)


@router.post("/accounts/{aid}/review")
def review_customer_account(
    aid: int,
    body: S.CustomerAccountReviewIn,
    current: User = Depends(require_perm("crm:account:review")),
    db: Session = Depends(get_db),
):
    """账号审核：启用（绑定往来单位 + 客户经理 + 权限范围）或驳回。"""
    p = db.get(PartnerUser, aid)
    if not p or p.deleted or p.account_type != "customer":
        raise BizException(R.CRM_ACCOUNT_NOT_FOUND)
    review_account(
        db,
        p,
        body.action,
        reviewer_id=current.id,
        reviewer_name=current.name or current.username,
        comment=body.comment,
        customer_id=body.customer_id,
        manager_id=body.manager_id,
        manager_name=body.manager_name,
        perm_scope=body.perm_scope,
        staff_limit=body.staff_limit,
    )
    audit(
        db, user_id=current.id, module="crm", action=f"customer_account_{body.action}",
        biz_type="partner_user", biz_id=aid,
        detail={"username": p.username, "customerId": p.customer_id, "permScope": p.perm_scope},
    )
    db.commit()
    return account_out(p)


@router.post("/accounts/{aid}/toggle")
def toggle_customer_account(
    aid: int,
    status: str = Query(..., pattern="^(enabled|disabled)$"),
    current: User = Depends(require_perm("crm:account:edit")),
    db: Session = Depends(get_db),
):
    p = db.get(PartnerUser, aid)
    if not p or p.deleted or p.account_type != "customer":
        raise BizException(R.CRM_ACCOUNT_NOT_FOUND)
    set_account_status(db, p, status)
    audit(
        db, user_id=current.id, module="crm", action="customer_account_toggle",
        biz_type="partner_user", biz_id=aid, detail={"status": status},
    )
    db.commit()
    return account_out(p)

"""客户自助服务（B2）：门户侧在线委托下单 + 外来试验人员登记备案。

门户账号（`partner_user`）与内部员工（`sys_user`）是**两套独立认证**：
门户 token（aud=portal）与内部 access token 互不通用，权限范围由 `perm_scope` 控制：
- `tender` 招投标（供应商场景，默认）
- `entrust` 在线委托（客户场景）
- `staff` 外来人员备案（客户场景）

所有门户接口只暴露"本单位自己的"数据：合同、委托单、人员备案均按 `partner.customer_id` 过滤。
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.contract.models import Contract
from app.modules.crm.models import PartnerStaff
from app.modules.portal.models import PartnerUser
from app.modules.task import entrust as entrust_svc
from app.modules.task.models import TaskEntrust

SCOPE_TENDER = "tender"
SCOPE_ENTRUST = "entrust"
SCOPE_STAFF = "staff"


def has_scope(p: PartnerUser, scope: str) -> bool:
    return scope in (p.perm_scope or "").split(",")


def require_scope(p: PartnerUser, scope: str) -> None:
    if not has_scope(p, scope):
        raise BizException(R.PORTAL_SCOPE_DENIED, f"当前账号未开通「{scope}」权限范围")


def require_customer(p: PartnerUser) -> int:
    """客户自助功能必须先绑定往来单位（由客户经理在账号审核时绑定）。"""
    if not p.customer_id:
        raise BizException(R.CRM_ACCOUNT_NOT_BOUND)
    return p.customer_id


# ---------------- 我的合同 ----------------


def _contract_out(c: Contract) -> dict:
    return {
        "id": c.id,
        "contractNo": c.contract_no or "",
        "name": c.name,
        "contractType": c.contract_type,
        "amount": float(c.amount) if c.amount is not None else None,
        "startDate": c.start_date.strftime("%Y-%m-%d") if c.start_date else "",
        "endDate": c.end_date.strftime("%Y-%m-%d") if c.end_date else "",
    }


def my_contracts(db: Session, partner: PartnerUser) -> list[dict]:
    customer_id = require_customer(partner)
    rows = db.scalars(
        select(Contract)
        .where(
            Contract.customer_id == customer_id,
            Contract.deleted == 0,
            Contract.status == "approved",
        )
        .order_by(Contract.id.desc())
    ).all()
    return [_contract_out(c) for c in rows]


# ---------------- 在线委托 ----------------


def _entrust_out(e: TaskEntrust) -> dict:
    return {
        "id": e.id,
        "entrustNo": e.entrust_no or "",
        "title": e.title,
        "entrustType": e.entrust_type,
        "contractId": e.contract_id,
        "contractNo": e.contract_no,
        "customerName": e.customer_name,
        "requirement": e.requirement or "",
        "sampleDesc": e.sample_desc or "",
        "planStartDate": e.plan_start_date.strftime("%Y-%m-%d") if e.plan_start_date else "",
        "planEndDate": e.plan_end_date.strftime("%Y-%m-%d") if e.plan_end_date else "",
        "priority": e.priority,
        "status": e.status,
        "statusText": entrust_svc.STATUS_CN.get(e.status, e.status),
        "reviewComment": e.review_comment or "",
        "taskNo": e.task_no,
        "itemCount": len([i for i in e.items if not i.deleted]),
        "createTime": e.create_time.strftime("%Y-%m-%d %H:%M:%S") if e.create_time else "",
    }


def create_entrust(db: Session, partner: PartnerUser, body) -> dict:
    """客户在线提交委托（基于已审批合同）。"""
    require_scope(partner, SCOPE_ENTRUST)
    customer_id = require_customer(partner)
    contract = entrust_svc.load_contract(db, body.contract_id)
    if contract and contract.customer_id != customer_id:
        raise BizException(R.TASK_ENTRUST_CONTRACT_INVALID, "只能基于本单位的合同提交委托")
    e = entrust_svc.create_entrust(
        db,
        body,
        source="portal",
        applicant_type="portal",
        applicant_id=partner.id,
        applicant_name=partner.contact_name or partner.username,
        applicant_phone=partner.phone,
        customer_id=customer_id,
        customer_name=partner.company_name,
    )
    audit(
        db, user_id=None, module="portal", action="entrust_create",
        biz_type="entrust", biz_id=e.id, detail={"partner": partner.username, "title": e.title},
    )
    db.commit()
    return _entrust_out(e)


def my_entrusts(db: Session, partner: PartnerUser) -> list[dict]:
    customer_id = require_customer(partner)
    rows = db.scalars(
        select(TaskEntrust)
        .where(
            TaskEntrust.customer_id == customer_id,
            TaskEntrust.source == "portal",
            TaskEntrust.deleted == 0,
        )
        .order_by(TaskEntrust.id.desc())
    ).all()
    return [_entrust_out(e) for e in rows]


def cancel_entrust(db: Session, partner: PartnerUser, entrust_id: int) -> dict:
    """客户撤回尚未受理的委托。"""
    customer_id = require_customer(partner)
    e = db.get(TaskEntrust, entrust_id)
    if not e or e.deleted or e.customer_id != customer_id or e.source != "portal":
        raise BizException(R.TASK_ENTRUST_NOT_FOUND)
    entrust_svc.transition(db, e, "cancel")
    audit(db, user_id=None, module="portal", action="entrust_cancel",
          biz_type="entrust", biz_id=e.id, detail={"partner": partner.username})
    db.commit()
    return _entrust_out(e)


# ---------------- 外来人员登记备案 ----------------

STAFF_STATUS_CN = {"pending": "待审核", "approved": "已备案", "rejected": "已驳回", "disabled": "已停用"}


def _staff_out(s: PartnerStaff) -> dict:
    return {
        "id": s.id,
        "customerName": s.customer_name,
        "name": s.name,
        "gender": s.gender,
        "position": s.position,
        "phone": s.phone,
        "email": s.email,
        "plateNo": s.plate_no,
        "company": s.company,
        "staffType": s.staff_type,
        "visitPurpose": s.visit_purpose,
        "planVisitDate": s.plan_visit_date.strftime("%Y-%m-%d") if s.plan_visit_date else "",
        "ndaSigned": bool(s.nda_signed),
        "status": s.status,
        "statusText": STAFF_STATUS_CN.get(s.status, s.status),
        "reviewComment": s.review_comment or "",
        "createTime": s.create_time.strftime("%Y-%m-%d %H:%M:%S") if s.create_time else "",
    }


def register_staff(db: Session, partner: PartnerUser, body) -> dict:
    """客户自助登记外来试验人员 / 跟踪支持人员（待客户经理审核）。"""
    require_scope(partner, SCOPE_STAFF)
    customer_id = require_customer(partner)
    used = db.scalar(
        select(func.count())
        .select_from(PartnerStaff)
        .where(
            PartnerStaff.applicant_account_id == partner.id,
            PartnerStaff.deleted == 0,
            PartnerStaff.status != "disabled",
        )
    ) or 0
    limit = partner.staff_limit if partner.staff_limit and partner.staff_limit > 0 else 5
    if used >= limit:
        raise BizException(R.GENERIC_PARAM, f"登记人数已达上限（{limit} 人），请联系客户经理调整")
    staff = PartnerStaff(
        customer_id=customer_id,
        customer_name=partner.company_name,
        name=body.name,
        gender=body.gender,
        id_no=body.id_no,
        position=body.position,
        phone=body.phone,
        email=body.email,
        plate_no=body.plate_no,
        company=partner.company_name,
        staff_type=body.staff_type,
        visit_purpose=body.visit_purpose,
        plan_visit_date=body.plan_visit_date,
        nda_signed=1 if body.nda_signed else 0,
        source="portal",
        applicant_account_id=partner.id,
        applicant_name=partner.contact_name or partner.username,
        status="pending",
    )
    db.add(staff)
    db.flush()
    audit(
        db, user_id=None, module="portal", action="partner_staff_register",
        biz_type="partner_staff", biz_id=staff.id,
        detail={"partner": partner.username, "name": staff.name},
    )
    db.commit()
    return _staff_out(staff)


def my_staff(db: Session, partner: PartnerUser) -> list[dict]:
    customer_id = require_customer(partner)
    rows = db.scalars(
        select(PartnerStaff)
        .where(
            PartnerStaff.customer_id == customer_id,
            PartnerStaff.source == "portal",
            PartnerStaff.deleted == 0,
        )
        .order_by(PartnerStaff.id.desc())
    ).all()
    return [_staff_out(s) for s in rows]


# ---------------- 账号审核（内部侧调用） ----------------


def account_out(p: PartnerUser) -> dict:
    return {
        "id": p.id,
        "username": p.username,
        "companyName": p.company_name,
        "contactName": p.contact_name,
        "phone": p.phone,
        "email": p.email,
        "status": p.status,
        "accountType": p.account_type,
        "permScope": p.perm_scope or "",
        "permScopeList": [s for s in (p.perm_scope or "").split(",") if s],
        "customerId": p.customer_id,
        "managerId": p.manager_id,
        "managerName": p.manager_name,
        "staffLimit": p.staff_limit,
        "reviewBy": p.review_by,
        "reviewName": p.review_name,
        "reviewAt": p.review_at.strftime("%Y-%m-%d %H:%M:%S") if p.review_at else "",
        "reviewComment": p.review_comment or "",
        "lastLoginAt": p.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if p.last_login_at else "",
        "createTime": p.create_time.strftime("%Y-%m-%d %H:%M:%S") if p.create_time else "",
    }


def review_account(
    db: Session,
    p: PartnerUser,
    action: str,
    reviewer_id: int | None,
    reviewer_name: str,
    comment: str = "",
    customer_id: int | None = None,
    manager_id: int | None = None,
    manager_name: str = "",
    perm_scope: str | None = None,
    staff_limit: int | None = None,
) -> PartnerUser:
    """账号审核：启用（绑定往来单位与客户经理、授权权限范围）或驳回。"""
    if action == "approve":
        if p.status == "enabled":
            raise BizException(R.CRM_ACCOUNT_INVALID_STATE, "账号已启用")
        p.status = "enabled"
    elif action == "reject":
        if p.status not in ("pending", "rejected"):
            raise BizException(R.CRM_ACCOUNT_INVALID_STATE, "仅待审核账号可驳回")
        p.status = "rejected"
    else:
        raise BizException(R.GENERIC_PARAM, f"未知审核动作：{action}")

    if customer_id is not None:
        p.customer_id = customer_id
    if manager_id is not None:
        p.manager_id = manager_id
        p.manager_name = manager_name
    if perm_scope:
        p.perm_scope = perm_scope
    if staff_limit is not None and staff_limit >= 0:
        p.staff_limit = staff_limit
    p.review_by = reviewer_id
    p.review_name = reviewer_name
    p.review_at = datetime.now()
    p.review_comment = comment
    p.update_time = datetime.now()
    db.flush()
    return p


def set_account_status(db: Session, p: PartnerUser, status: str) -> PartnerUser:
    if status not in ("enabled", "disabled"):
        raise BizException(R.GENERIC_PARAM, "账号状态只能是启用或停用")
    p.status = status
    p.update_time = datetime.now()
    db.flush()
    return p

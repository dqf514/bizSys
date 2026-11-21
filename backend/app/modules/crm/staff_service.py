"""客户方人员档案（B2）：外来试验人员 / 跟踪支持人员登记备案的审核与抄送。

流程（行业惯例：访客主数据由客户侧先行登记，试验室侧审核后生效）：
    客户门户自助登记 → 客户经理审核 → 抄送业务负责人（对接人员）与访客管理人员
    → 勾选访客系统权限（可进入区域 + NDA 状态）→ 访客系统据此预登记访客档案与通行凭证（B3）。
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.common import notify as notify_svc
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.crm.models import PartnerStaff

# 访客管理人员权限点（B3 落地后自动生效；当前无人持有时跳过抄送）
VISITOR_ADMIN_PERM = "visitor:visit:list"

STAFF_STATUS_CN = {"pending": "待审核", "approved": "已备案", "rejected": "已驳回", "disabled": "已停用"}


def create_staff(
    db: Session,
    body,
    *,
    source: str = "internal",
    customer_id: int | None = None,
    customer_name: str = "",
    applicant_account_id: int | None = None,
    applicant_name: str = "",
) -> PartnerStaff:
    """登记客户方人员（内部代登记 / 门户自助登记）。"""
    staff = PartnerStaff(
        customer_id=customer_id,
        customer_name=customer_name,
        name=body.name,
        gender=body.gender,
        id_no=body.id_no,
        position=body.position,
        phone=body.phone,
        email=body.email,
        plate_no=body.plate_no,
        company=body.company or customer_name,
        staff_type=body.staff_type,
        visit_purpose=body.visit_purpose,
        plan_visit_date=body.plan_visit_date,
        nda_signed=1 if body.nda_signed else 0,
        source=source,
        applicant_account_id=applicant_account_id,
        applicant_name=applicant_name,
        status="pending",
    )
    db.add(staff)
    db.flush()
    return staff


def review_staff(
    db: Session,
    staff: PartnerStaff,
    action: str,
    reviewer_id: int | None,
    reviewer_name: str,
    comment: str = "",
    biz_owner_id: int | None = None,
    biz_owner_name: str = "",
    visit_perm: str | None = None,
    nda_signed: bool | None = None,
) -> tuple[PartnerStaff, int]:
    """审核（approve/reject）。approve 时勾选访客系统权限并抄送业务负责人与访客管理人员。

    返回 (人员档案, 抄送通知条数)。
    """
    if staff.status not in ("pending", "rejected"):
        raise BizException(R.CRM_STAFF_INVALID_STATE, "仅待审核的备案可审核")
    if action == "approve":
        staff.status = "approved"
    elif action == "reject":
        staff.status = "rejected"
    else:
        raise BizException(R.GENERIC_PARAM, f"未知审核动作：{action}")

    if visit_perm is not None:
        staff.visit_perm = visit_perm
    if nda_signed is not None:
        staff.nda_signed = 1 if nda_signed else 0
    if biz_owner_id:
        staff.biz_owner_id = biz_owner_id
        staff.biz_owner_name = biz_owner_name
    staff.review_by = reviewer_id
    staff.review_name = reviewer_name
    staff.review_at = datetime.now()
    staff.review_comment = comment
    staff.update_time = datetime.now()
    db.flush()

    notified = 0
    if action == "approve":
        notified = notify_approved(db, staff, operator_id=reviewer_id)
    return staff, notified


def notify_approved(db: Session, staff: PartnerStaff, operator_id: int | None = None) -> int:
    """抄送业务负责人与访客管理人员（内容含"已勾选访客系统权限"）。"""
    targets: list[int] = []
    if staff.biz_owner_id:
        targets.append(staff.biz_owner_id)
    visitor_admins = notify_svc.users_with_perm(db, VISITOR_ADMIN_PERM)
    targets.extend(visitor_admins)
    if not targets:
        return 0
    return notify_svc.notify(
        db,
        targets,
        title=f"客户人员备案审核通过：{staff.name}",
        content=(
            f"{staff.customer_name} · {staff.name}（{staff.staff_type or '外部人员'}）"
            f"，来访日期 {staff.plan_visit_date or '待定'}，已勾选访客系统权限"
        ),
        biz_type="partner_staff",
        biz_id=staff.id,
        link=f"/crm/partner-staffs?id={staff.id}",
        exclude_user_id=operator_id,
    )


def set_staff_status(db: Session, staff: PartnerStaff, status: str) -> PartnerStaff:
    if status not in ("approved", "disabled"):
        raise BizException(R.GENERIC_PARAM, "人员状态只能是已备案或已停用")
    if staff.status not in ("approved", "disabled"):
        raise BizException(R.CRM_STAFF_INVALID_STATE, "仅已备案人员可启用或停用")
    staff.status = status
    staff.update_time = datetime.now()
    db.flush()
    return staff

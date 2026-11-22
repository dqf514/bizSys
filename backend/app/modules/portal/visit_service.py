"""门户访客预约（F6）：合作方在门户提交来访申请 → 内部审批 → 通行凭证 → 自助签到/签离。

与内部访客域的关系：

- 数据落在同一张 `vis_visit` 表（`source=portal`，`partner_user_id` 标记提交账号）；
- 审批走**通用审批引擎**（`approval/registry.py::submit_flow`，biz_type=`visitor_visit`），
  审批链可在「流程设置」里设计（节点可按表单变量动态指定被访人）；
- 凭证下发 / 签到签出 / 合规审计全部**复用访客域的服务层**（`visitor/service.py`），
  保证与内部登记口径完全一致。

隔离口径：门户只暴露**本账号提交**的访客单（`partner_user_id`），不暴露他人预约。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.approval.engine import FlowInitiator
from app.modules.approval.models import ApprovalInstance, ApprovalTask
from app.modules.auth.models import User
from app.modules.portal.models import PartnerUser
from app.modules.portal.selfservice import SCOPE_VISIT, require_scope
from app.modules.visitor import service as vsvc
from app.modules.visitor.models import VisitorCredential, VisitorVisit, VisitorZone
from app.services.numbering import next_no

BIZ_TYPE = "visitor_visit"


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


# ---------------- 选项数据 ----------------


def host_options(db: Session, q: str = "") -> list[dict]:
    """被访人候选（内部员工）：只暴露姓名 / 部门 / 工号，不暴露手机号与邮箱。"""
    stmt = select(User).where(User.deleted == 0, User.status == "enabled")
    keyword = (q or "").strip()
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(User.name.like(like) | User.username.like(like) | User.dept_name.like(like))
    rows = db.scalars(stmt.order_by(User.dept_name, User.name).limit(50)).all()
    return [
        {
            "id": u.id,
            "name": u.name or u.username,
            "deptName": u.dept_name or "",
            "employeeNo": u.employee_no or "",
        }
        for u in rows
    ]


def zone_options(db: Session) -> list[dict]:
    """可申请区域（仅启用）。"""
    rows = db.scalars(
        select(VisitorZone)
        .where(VisitorZone.deleted == 0, VisitorZone.status == "enabled")
        .order_by(VisitorZone.id)
    ).all()
    return [
        {
            "id": z.id,
            "name": z.name,
            "zoneType": z.zone_type,
            "zoneTypeText": vsvc.ZONE_TYPE_CN.get(z.zone_type, z.zone_type),
            "securityLevel": z.security_level,
            "needNda": bool(z.need_nda),
            "needExtraApproval": bool(z.need_extra_approval),
            "needEscort": bool(z.need_escort),
        }
        for z in rows
    ]


# ---------------- 提交预约 ----------------


def _load_host(db: Session, host_user_id: int) -> User:
    host = db.get(User, host_user_id)
    if not host or host.deleted or host.status != "enabled":
        raise BizException(R.GENERIC_PARAM, "被访人不存在或已停用")
    return host


def _load_zones(db: Session, zone_ids: list[int]) -> list[VisitorZone]:
    if not zone_ids:
        raise BizException(R.GENERIC_PARAM, "请至少选择一个来访区域")
    rows = db.scalars(
        select(VisitorZone).where(
            VisitorZone.id.in_(zone_ids), VisitorZone.deleted == 0, VisitorZone.status == "enabled"
        )
    ).all()
    if len(rows) != len(set(zone_ids)):
        raise BizException(R.VISITOR_ZONE_NOT_FOUND, "存在不可申请的区域")
    return list(rows)


def create_visit(db: Session, partner: PartnerUser, body, ip: str = "") -> dict:
    """门户提交访客预约 → 发起审批流程。"""
    require_scope(partner, SCOPE_VISIT)
    host = _load_host(db, body.host_user_id)
    zones = _load_zones(db, body.zone_ids)

    # 敏感区域必须先确认保密协议
    if any(z.need_nda for z in zones) and not body.nda_signed:
        raise BizException(R.VISITOR_NDA_REQUIRED, "该区域要求先签署保密协议")

    zone_ids = ",".join(str(z.id) for z in zones)
    levels = vsvc.required_levels(db, [z.id for z in zones])
    security_level = max((z.security_level or 1) for z in zones)

    visit = VisitorVisit(
        visit_no="",
        visitor_name=body.visitor_name,
        visitor_company=body.visitor_company or partner.company_name,
        visitor_type=body.visitor_type or "customer",
        id_no=body.id_no,
        phone=body.phone or partner.phone,
        plate_no=body.plate_no,
        host_user_id=host.id,
        host_name=host.name or host.username,
        host_dept_id=host.dept_id,
        host_dept_name=host.dept_name or "",
        purpose=body.purpose,
        source="portal",
        zone_ids=zone_ids,
        escort_names=body.escort_names,
        plan_start=body.plan_start,
        plan_end=body.plan_end,
        status="pending",
        required_levels=",".join(levels),
        partner_user_id=partner.id,
        customer_id=partner.customer_id,
        customer_name=partner.company_name,
        remark=body.remark,
    )
    db.add(visit)
    db.flush()
    visit.visit_no = next_no(db, "visit")

    audit(
        db, user_id=None, module="portal", action="visit_create",
        biz_type="visitor_visit", biz_id=visit.id,
        detail={"partner": partner.username, "visitor": visit.visitor_name, "host": visit.host_name}, ip=ip,
    )

    from app.modules.approval import registry

    if registry.flow_enabled(db, BIZ_TYPE):
        registry.submit_flow(
            db,
            BIZ_TYPE,
            visit.id,
            title=f"访客预约 {visit.visit_no} · {visit.visitor_name}",
            initiator=FlowInitiator(0, f"合作方·{partner.company_name}"),
            variables={
                "hostUserId": host.id,
                "hostDeptId": host.dept_id or 0,
                "hostName": visit.host_name,
                "securityLevel": security_level,
                "zoneIds": zone_ids,
                "customerId": partner.customer_id or 0,
            },
            form_snapshot={
                "visitNo": visit.visit_no,
                "visitorName": visit.visitor_name,
                "visitorCompany": visit.visitor_company,
                "hostName": visit.host_name,
                "hostDeptName": visit.host_dept_name,
                "purpose": visit.purpose,
                "planStart": _t(visit.plan_start),
                "planEnd": _t(visit.plan_end),
                "zoneNames": ",".join(z.name for z in zones),
            },
        )
    # 流程停用时保持 pending —— 落回访客域内人工审批链（host → zone）

    db.commit()
    return visit_out(db, visit)


# ---------------- 查询 ----------------


def _own_visit(db: Session, partner: PartnerUser, visit_id: int) -> VisitorVisit:
    visit = db.get(VisitorVisit, visit_id)
    if not visit or visit.deleted:
        raise BizException(R.VISITOR_NOT_FOUND)
    if visit.partner_user_id != partner.id:
        raise BizException(R.VISITOR_FORBIDDEN, "无权访问该访客记录")
    return visit


def visit_out(db: Session, visit: VisitorVisit) -> dict:
    """门户口径的访客单输出（不含内部审批人 / 意见等敏感字段以外的内容）。"""
    zones = vsvc.load_zones(db, vsvc._split_ids(visit.zone_ids))
    cred = db.get(VisitorCredential, visit.credential_id) if visit.credential_id else None
    return {
        "id": visit.id,
        "visitNo": visit.visit_no,
        "visitorName": visit.visitor_name,
        "visitorCompany": visit.visitor_company,
        "visitorType": visit.visitor_type,
        "idNo": visit.id_no,
        "phone": visit.phone,
        "plateNo": visit.plate_no,
        "hostUserId": visit.host_user_id,
        "hostName": visit.host_name,
        "hostDeptName": visit.host_dept_name,
        "purpose": visit.purpose,
        "zoneIds": visit.zone_ids,
        "zoneNames": ",".join(z.name for z in zones),
        "escortNames": visit.escort_names,
        "planStart": _t(visit.plan_start),
        "planEnd": _t(visit.plan_end),
        "checkinAt": _t(visit.checkin_at),
        "checkoutAt": _t(visit.checkout_at),
        "status": visit.status,
        "statusText": vsvc.VISIT_STATUS_CN.get(visit.status, visit.status),
        "credentialNo": visit.credential_no,
        "credentialStatus": cred.status if cred else "",
        "credentialValidFrom": _t(cred.valid_from) if cred else "",
        "credentialValidTo": _t(cred.valid_to) if cred else "",
        "ndaSigned": bool(visit.nda_id),
        "remark": visit.remark or "",
        "flowInstanceId": visit.flow_instance_id,
        "createTime": _t(visit.create_time),
    }


def timeline(db: Session, visit: VisitorVisit) -> list[dict]:
    """审批时间线（只暴露节点名与结论，不暴露内部审批人姓名以外的信息）。"""
    if not visit.flow_instance_id:
        return []
    inst = db.get(ApprovalInstance, visit.flow_instance_id)
    if not inst or inst.deleted:
        return []
    pending = db.scalars(
        select(ApprovalTask).where(
            ApprovalTask.instance_id == inst.id,
            ApprovalTask.status == "pending",
            ApprovalTask.deleted == 0,
        )
    ).all()
    pending_nodes = sorted({t.node_name for t in pending if t.node_name})
    out = []
    for r in inst.records:
        out.append(
            {
                "action": r.action,
                "nodeName": r.node_name,
                "comment": r.comment or "",
                "at": _t(r.at),
            }
        )
    out.append(
        {
            "action": "current",
            "nodeName": "、".join(pending_nodes),
            "comment": "",
            "at": "",
        }
    )
    return out


def visit_detail(db: Session, partner: PartnerUser, visit_id: int) -> dict:
    visit = _own_visit(db, partner, visit_id)
    data = visit_out(db, visit)
    data["timeline"] = timeline(db, visit)
    return data


def my_visits(db: Session, partner: PartnerUser) -> list[dict]:
    rows = db.scalars(
        select(VisitorVisit)
        .where(VisitorVisit.partner_user_id == partner.id, VisitorVisit.deleted == 0)
        .order_by(VisitorVisit.id.desc())
    ).all()
    return [visit_out(db, v) for v in rows]


# ---------------- 取消 / 凭证 / 签到签离 ----------------


def cancel_visit(db: Session, partner: PartnerUser, visit_id: int, remark: str = "") -> dict:
    visit = _own_visit(db, partner, visit_id)
    if visit.status not in ("pending", "approving"):
        raise BizException(R.VISITOR_INVALID_STATE, "当前状态不允许取消")
    visit.status = "cancelled"
    if remark:
        visit.remark = (visit.remark + "\n" if visit.remark else "") + f"[取消] {remark}"
    vsvc.revoke_credential(db, visit)
    audit(
        db, user_id=None, module="portal", action="visit_cancel",
        biz_type="visitor_visit", biz_id=visit.id, detail={"partner": partner.username},
    )
    db.commit()
    return visit_out(db, visit)


def credential_info(db: Session, partner: PartnerUser, visit_id: int) -> dict:
    """通行凭证信息（仅本人；审批通过后才有凭证）。"""
    visit = _own_visit(db, partner, visit_id)
    if not visit.credential_id:
        raise BizException(R.VISITOR_CREDENTIAL_INVALID, "尚未下发通行凭证")
    cred = db.get(VisitorCredential, visit.credential_id)
    if not cred or cred.deleted:
        raise BizException(R.VISITOR_CREDENTIAL_INVALID, "通行凭证不存在")
    if cred.status == "expired":
        raise BizException(R.VISITOR_CREDENTIAL_EXPIRED)
    zones = vsvc.load_zones(db, vsvc._split_ids(cred.zone_ids))
    return {
        "credentialNo": cred.credential_no,
        "visitorName": cred.visitor_name,
        "status": cred.status,
        "validFrom": _t(cred.valid_from),
        "validTo": _t(cred.valid_to),
        "zoneNames": ",".join(z.name for z in zones),
        "code": cred.code,
        "visitId": visit.id,
    }


def pass_info(db: Session, visit_id: int, code: str) -> dict:
    """公开的「通行证」页数据：凭证码即持有者凭证（微信转发链接用）。

    只暴露访客姓名 / 有效期 / 授权区域，不含任何内部信息。
    """
    visit = db.get(VisitorVisit, visit_id)
    if not visit or visit.deleted or not visit.credential_id or not code:
        raise BizException(R.VISITOR_NOT_FOUND)
    cred = db.get(VisitorCredential, visit.credential_id)
    if not cred or cred.deleted or cred.code != code:
        raise BizException(R.VISITOR_CREDENTIAL_INVALID)
    zones = vsvc.load_zones(db, vsvc._split_ids(cred.zone_ids))
    return {
        "visitNo": visit.visit_no,
        "visitorName": visit.visitor_name,
        "hostName": visit.host_name,
        "credentialNo": cred.credential_no,
        "status": cred.status,
        "validFrom": _t(cred.valid_from),
        "validTo": _t(cred.valid_to),
        "zoneNames": ",".join(z.name for z in zones),
        "checkinAt": _t(visit.checkin_at),
    }


def check_in(db: Session, partner: PartnerUser, visit_id: int, method: str, device_id: str) -> dict:
    """访客自助签到（扫码）。拒绝放行同样留痕（告警 + 审计日志）。"""
    visit = _own_visit(db, partner, visit_id)
    try:
        vsvc.check_in(db, visit, method, device_id, visit.credential_no, f"合作方·{partner.company_name}")
    except BizException:
        db.commit()  # 拒绝放行也要落审计（合规要求），先提交再抛错
        raise
    audit(
        db, user_id=None, module="portal", action="visit_checkin",
        biz_type="visitor_visit", biz_id=visit.id, detail={"method": method, "partner": partner.username},
    )
    db.commit()
    return visit_out(db, visit)


def check_out(db: Session, partner: PartnerUser, visit_id: int, method: str, device_id: str) -> dict:
    """访客自助签离。"""
    visit = _own_visit(db, partner, visit_id)
    vsvc.check_out(db, visit, method, device_id, f"合作方·{partner.company_name}")
    audit(
        db, user_id=None, module="portal", action="visit_checkout",
        biz_type="visitor_visit", biz_id=visit.id, detail={"partner": partner.username},
    )
    db.commit()
    return visit_out(db, visit)

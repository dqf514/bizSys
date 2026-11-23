"""访客与安全域（B3）路由，前缀 /api/v1/visitor。

合规审计日志（vis_access_log）**只提供查询与导出**，不提供任何 update / delete 接口。
"""

from datetime import datetime, timedelta
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
from app.modules.visitor import schemas as S
from app.modules.visitor import service as svc
from app.modules.visitor.models import (
    VisitorAccessLog,
    VisitorAlert,
    VisitorApproval,
    VisitorBlacklist,
    VisitorCredential,
    VisitorNda,
    VisitorSampleHandover,
    VisitorVisit,
    VisitorZone,
)
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import next_no

router = APIRouter(prefix="/visitor", tags=["visitor"], route_class=EnvelopeRoute)

VISIT_EXPORT_COLS = [
    {"key": "visitNo", "label": "访客单号", "width": 18},
    {"key": "visitorName", "label": "访客姓名", "width": 12},
    {"key": "visitorCompany", "label": "访客单位", "width": 24},
    {"key": "visitorTypeText", "label": "访客类型", "width": 12},
    {"key": "hostName", "label": "被访人", "width": 12},
    {"key": "hostDeptName", "label": "被访部门", "width": 14},
    {"key": "zoneNames", "label": "授权区域", "width": 26},
    {"key": "purpose", "label": "来访事由", "width": 24},
    {"key": "planStart", "label": "计划进入", "width": 19},
    {"key": "planEnd", "label": "计划离开", "width": 19},
    {"key": "checkinAt", "label": "签入时间", "width": 19},
    {"key": "checkoutAt", "label": "签出时间", "width": 19},
    {"key": "statusText", "label": "状态", "width": 10},
]

LOG_EXPORT_COLS = [
    {"key": "happenedAt", "label": "事件时间", "width": 19},
    {"key": "visitorName", "label": "访客", "width": 12},
    {"key": "credentialNo", "label": "凭证编号", "width": 18},
    {"key": "zoneName", "label": "区域", "width": 16},
    {"key": "eventType", "label": "事件", "width": 14},
    {"key": "method", "label": "核验方式", "width": 12},
    {"key": "result", "label": "结果", "width": 8},
    {"key": "deviceId", "label": "设备号", "width": 14},
    {"key": "operatorName", "label": "操作人", "width": 12},
    {"key": "detail", "label": "明细", "width": 30},
]


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _out_visit(db: Session, v: VisitorVisit) -> dict:
    zones = svc.load_zones(db, svc._split_ids(v.zone_ids))
    return {
        "id": v.id,
        "visitNo": v.visit_no,
        "visitorName": v.visitor_name,
        "visitorCompany": v.visitor_company,
        "visitorType": v.visitor_type,
        "visitorTypeText": svc.VISITOR_TYPE_CN.get(v.visitor_type, v.visitor_type),
        "idNo": v.id_no,
        "phone": v.phone,
        "plateNo": v.plate_no,
        "hostUserId": v.host_user_id,
        "hostName": v.host_name,
        "hostDeptId": v.host_dept_id,
        "hostDeptName": v.host_dept_name,
        "purpose": v.purpose,
        "source": v.source,
        "sourceText": svc.VISIT_SOURCE_CN.get(v.source, v.source),
        "zoneIds": v.zone_ids,
        "zoneNames": ",".join(z.name for z in zones),
        "escortNames": v.escort_names,
        "planStart": _t(v.plan_start),
        "planEnd": _t(v.plan_end),
        "checkinAt": _t(v.checkin_at),
        "checkoutAt": _t(v.checkout_at),
        "status": v.status,
        "statusText": svc.VISIT_STATUS_CN.get(v.status, v.status),
        "requiredLevels": v.required_levels,
        "approvedLevels": v.approved_levels,
        "ndaId": v.nda_id,
        "credentialId": v.credential_id,
        "credentialNo": v.credential_no,
        "staffId": v.staff_id,
        "customerId": v.customer_id,
        "customerName": v.customer_name,
        "remark": v.remark or "",
        "version": v.version,
        "createTime": _t(v.create_time),
        "updateTime": _t(v.update_time),
    }


def _out_zone(z: VisitorZone) -> dict:
    return {
        "id": z.id,
        "code": z.code,
        "name": z.name,
        "zoneType": z.zone_type,
        "zoneTypeText": svc.ZONE_TYPE_CN.get(z.zone_type, z.zone_type),
        "securityLevel": z.security_level,
        "needExtraApproval": bool(z.need_extra_approval),
        "needEscort": bool(z.need_escort),
        "needNda": bool(z.need_nda),
        "needDualPerson": bool(z.need_dual_person),
        "cameraControl": bool(z.camera_control),
        "deviceBinding": z.device_binding,
        "capacity": z.capacity,
        "status": z.status,
        "remark": z.remark or "",
        "createTime": _t(z.create_time),
    }


def _load_visit(db: Session, vid: int) -> VisitorVisit:
    v = db.get(VisitorVisit, vid)
    if not v or v.deleted:
        raise BizException(R.VISITOR_NOT_FOUND)
    return v


def _load_zone(db: Session, zid: int) -> VisitorZone:
    z = db.get(VisitorZone, zid)
    if not z or z.deleted:
        raise BizException(R.VISITOR_ZONE_NOT_FOUND)
    return z


# ---------------- 区域管理 ----------------


@router.get("/zones")
def list_zones(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("visitor:zone:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(VisitorZone),
        VisitorZone,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["code", "name", "remark"],
        filter_cols={"status", "zone_type", "security_level"},
        sort_cols={"id", "code", "name", "zone_type", "security_level", "create_time"},
        default_sort=("id", "asc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_out_zone(z) for z in rows], "total": total, "page": page, "size": size}


@router.get("/zones/counts")
def zone_counts(
    user: User = Depends(require_perm("visitor:zone:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(VisitorZone.status, func.count()).where(VisitorZone.deleted == 0).group_by(VisitorZone.status)
    ).all()
    data = {"enabled": 0, "disabled": 0}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.post("/zones", status_code=201)
def create_zone(
    body: S.ZoneIn,
    current: User = Depends(require_perm("visitor:zone:edit")),
    db: Session = Depends(get_db),
):
    exists = db.scalar(select(VisitorZone).where(VisitorZone.code == body.code, VisitorZone.deleted == 0))
    if exists:
        raise BizException(R.VISITOR_DUPLICATE, "区域编码已存在")
    z = VisitorZone(
        code=body.code,
        name=body.name,
        zone_type=body.zone_type,
        security_level=body.security_level,
        need_extra_approval=int(body.need_extra_approval),
        need_escort=int(body.need_escort),
        need_nda=int(body.need_nda),
        need_dual_person=int(body.need_dual_person),
        camera_control=int(body.camera_control),
        device_binding=body.device_binding,
        capacity=body.capacity,
        status=body.status,
        remark=body.remark,
    )
    db.add(z)
    db.flush()
    audit(
        db, user_id=current.id, module="visitor", action="zone_create",
        biz_type="visitor_zone", biz_id=z.id, detail={"code": z.code},
    )
    db.commit()
    return _out_zone(z)


@router.put("/zones/{zid}")
def update_zone(
    zid: int,
    body: S.ZoneIn,
    current: User = Depends(require_perm("visitor:zone:edit")),
    db: Session = Depends(get_db),
):
    z = _load_zone(db, zid)
    z.code = body.code
    z.name = body.name
    z.zone_type = body.zone_type
    z.security_level = body.security_level
    z.need_extra_approval = int(body.need_extra_approval)
    z.need_escort = int(body.need_escort)
    z.need_nda = int(body.need_nda)
    z.need_dual_person = int(body.need_dual_person)
    z.camera_control = int(body.camera_control)
    z.device_binding = body.device_binding
    z.capacity = body.capacity
    z.status = body.status
    z.remark = body.remark
    audit(
        db, user_id=current.id, module="visitor", action="zone_update",
        biz_type="visitor_zone", biz_id=z.id, detail={"code": z.code},
    )
    db.commit()
    return _out_zone(z)


@router.post("/zones/{zid}/toggle")
def toggle_zone(
    zid: int,
    status: str = Query(..., pattern="^(enabled|disabled)$"),
    current: User = Depends(require_perm("visitor:zone:edit")),
    db: Session = Depends(get_db),
):
    z = _load_zone(db, zid)
    z.status = status
    audit(
        db, user_id=current.id, module="visitor", action="zone_toggle",
        biz_type="visitor_zone", biz_id=z.id, detail={"status": status},
    )
    db.commit()
    return _out_zone(z)


@router.delete("/zones/{zid}")
def delete_zone(
    zid: int,
    current: User = Depends(require_perm("visitor:zone:edit")),
    db: Session = Depends(get_db),
):
    """逻辑删除：仍有在办访客单引用该区域时禁止删除。"""
    z = _load_zone(db, zid)
    active = db.scalars(
        select(VisitorVisit).where(
            VisitorVisit.deleted == 0,
            VisitorVisit.status.in_(("pending", "approved", "visiting")),
        )
    ).all()
    if any(str(z.id) in (v.zone_ids or "").split(",") for v in active):
        raise BizException(R.VISITOR_INVALID_STATE, "该区域仍有在办访客单，不能删除")
    z.deleted = 1
    audit(
        db, user_id=current.id, module="visitor", action="zone_delete",
        biz_type="visitor_zone", biz_id=z.id, detail={"code": z.code},
    )
    db.commit()
    return {"id": zid}


# ---------------- 访客登记 ----------------


def _filtered_visits(db: Session, request: Request, page: PageParams):
    stmt = select(VisitorVisit)
    return apply_list_filters(
        stmt,
        VisitorVisit,
        request.query_params,
        db,
        page,
        search_cols=["visit_no", "visitor_name", "visitor_company", "phone", "id_no", "plate_no", "host_name"],
        filter_cols={"status", "visitor_type", "source", "host_user_id", "host_dept_id", "customer_id"},
        range_cols={"plan_start", "plan_end", "checkin_at", "create_time"},
        sort_cols={"id", "visit_no", "visitor_name", "status", "plan_start", "plan_end", "create_time"},
        default_sort=("id", "desc"),
    )


@router.get("/visits")
def list_visits(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("visitor:visit:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered_visits(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_out_visit(db, v) for v in rows], "total": total, "page": page, "size": size}


@router.get("/visits/counts")
def visit_counts(
    user: User = Depends(require_perm("visitor:visit:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(VisitorVisit.status, func.count()).where(VisitorVisit.deleted == 0).group_by(VisitorVisit.status)
    ).all()
    data = {s: 0 for s in svc.VISIT_STATUSES}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/visits/stats")
def visit_stats(
    user: User = Depends(require_perm("visitor:visit:list")),
    db: Session = Depends(get_db),
):
    return svc.visitor_stats(db)


@router.get("/visits/{vid}")
def get_visit(
    vid: int,
    user: User = Depends(require_perm("visitor:visit:list")),
    db: Session = Depends(get_db),
):
    v = _load_visit(db, vid)
    data = _out_visit(db, v)
    approvals = db.scalars(
        select(VisitorApproval)
        .where(VisitorApproval.visit_id == vid, VisitorApproval.deleted == 0)
        .order_by(VisitorApproval.id.asc())
    ).all()
    data["approvals"] = [
        {
            "id": a.id,
            "level": a.level,
            "levelText": svc.APPROVAL_LEVEL_CN.get(a.level, a.level),
            "approverName": a.approver_name,
            "action": a.action,
            "comment": a.comment,
            "decidedAt": _t(a.decided_at),
        }
        for a in approvals
    ]
    handover = db.scalars(
        select(VisitorSampleHandover).where(VisitorSampleHandover.visit_id == vid, VisitorSampleHandover.deleted == 0)
    ).all()
    data["handovers"] = [
        {
            "id": h.id,
            "handoverNo": h.handover_no,
            "sampleNo": h.sample_no,
            "sampleName": h.sample_name,
            "handoverUserName": h.handover_user_name,
            "receiveUserName": h.receive_user_name,
            "handoverAt": _t(h.handover_at),
        }
        for h in handover
    ]
    return data


@router.post("/visits", status_code=201)
def create_visit(
    body: S.VisitIn,
    current: User = Depends(require_perm("visitor:visit:create")),
    db: Session = Depends(get_db),
):
    """多渠道统一登记入口（网页 / 微信 / 小程序 / 员工邀请 / 前台现场）。"""
    levels = svc.required_levels(db, svc._split_ids(body.zone_ids))
    v = VisitorVisit(
        visit_no="",
        visitor_name=body.visitor_name,
        visitor_company=body.visitor_company,
        visitor_type=body.visitor_type,
        id_no=body.id_no,
        phone=body.phone,
        plate_no=body.plate_no,
        host_user_id=body.host_user_id,
        host_name=body.host_name,
        host_dept_id=body.host_dept_id,
        host_dept_name=body.host_dept_name,
        purpose=body.purpose,
        source=body.source,
        zone_ids=body.zone_ids,
        escort_names=body.escort_names,
        plan_start=body.plan_start,
        plan_end=body.plan_end,
        status="pending",
        required_levels=",".join(levels),
        staff_id=body.staff_id,
        customer_id=body.customer_id,
        customer_name=body.customer_name,
        remark=body.remark,
    )
    db.add(v)
    db.flush()
    v.visit_no = next_no(db, "visit")
    audit(
        db, user_id=current.id, module="visitor", action="visit_create",
        biz_type="visitor_visit", biz_id=v.id, detail={"visitor": v.visitor_name, "source": v.source},
    )
    db.commit()
    return _out_visit(db, v)


@router.post("/visits/{vid}/approve")
def approve_visit(
    vid: int,
    body: S.VisitApprovalIn,
    current: User = Depends(require_perm("visitor:visit:review")),
    db: Session = Depends(get_db),
):
    """逐级审批（被访人 / 部门 / 敏感区域）。

    F6：访客单接入通用审批引擎后，人工直通端点被拦截（70005），
    只能通过「提交审批」走流程；流程总开关关闭时才恢复域内审批链。
    """
    v = _load_visit(db, vid)
    if v.flow_instance_id:
        from app.modules.approval import registry

        if registry.flow_enabled(db, "visitor_visit"):
            raise BizException(
                R.APPROVAL_INVALID_STATE,
                "访客预约已启用审批流程，请在审批中心处理",
            )
    svc.approve_visit(
        db,
        v,
        body.level,
        body.action,
        body.comment,
        current.id,
        current.name or current.username,
    )
    audit(
        db, user_id=current.id, module="visitor", action=f"visit_{body.action}",
        biz_type="visitor_visit", biz_id=vid, detail={"status": v.status, "comment": body.comment},
    )
    db.commit()
    return _out_visit(db, v)


@router.post("/visits/{vid}/checkin")
def check_in(
    vid: int,
    body: S.VisitCheckIn,
    current: User = Depends(require_perm("visitor:visit:checkin")),
    db: Session = Depends(get_db),
):
    v = _load_visit(db, vid)
    try:
        svc.check_in(db, v, body.method, body.device_id, body.credential_no, current.name or current.username)
    except BizException:
        # 拒绝放行也要留痕（黑名单命中 / 越权 / 超时窗），先提交再抛错
        db.commit()
        raise
    audit(
        db, user_id=current.id, module="visitor", action="visit_checkin",
        biz_type="visitor_visit", biz_id=vid, detail={"method": body.method},
    )
    db.commit()
    return _out_visit(db, v)


@router.post("/visits/{vid}/checkout")
def check_out(
    vid: int,
    body: S.VisitCheckIn,
    current: User = Depends(require_perm("visitor:visit:checkin")),
    db: Session = Depends(get_db),
):
    v = _load_visit(db, vid)
    svc.check_out(db, v, body.method, body.device_id, current.name or current.username)
    audit(
        db, user_id=current.id, module="visitor", action="visit_checkout",
        biz_type="visitor_visit", biz_id=vid,
    )
    db.commit()
    return _out_visit(db, v)


@router.post("/visits/{vid}/cancel")
def cancel_visit(
    vid: int,
    current: User = Depends(require_perm("visitor:visit:review")),
    db: Session = Depends(get_db),
):
    v = _load_visit(db, vid)
    if v.status not in ("pending", "approved"):
        raise BizException(R.VISITOR_INVALID_STATE, "当前状态不允许取消")
    v.status = "cancelled"
    svc.revoke_credential(db, v)
    audit(
        db, user_id=current.id, module="visitor", action="visit_cancel",
        biz_type="visitor_visit", biz_id=vid,
    )
    db.commit()
    return _out_visit(db, v)


@router.post("/visits/export")
def export_visits(
    request: Request,
    current: User = Depends(require_perm("visitor:visit:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _filtered_visits(db, request, SimpleNamespace(page=1, size=100_000))
    rows = db.scalars(stmt).all()
    payload_rows = [_out_visit(db, v) for v in rows]
    payload = export_xlsx_styled(payload_rows, VISIT_EXPORT_COLS, "visitor_visits")
    audit(
        db, user_id=current.id, module="visitor", action="visit_export",
        detail={"count": len(payload_rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('visitor_visits')}"},
    )


# ---------------- 通行凭证 ----------------


@router.get("/credentials")
def list_credentials(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("visitor:credential:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(VisitorCredential),
        VisitorCredential,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["credential_no", "visitor_name"],
        filter_cols={"status", "credential_type", "visit_id"},
        range_cols={"valid_from", "valid_to"},
        sort_cols={"id", "credential_no", "status", "valid_from", "valid_to"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    items = [
        {
            "id": c.id,
            "credentialNo": c.credential_no,
            "visitId": c.visit_id,
            "visitorName": c.visitor_name,
            "credentialType": c.credential_type,
            "credentialTypeText": svc.CREDENTIAL_TYPE_CN.get(c.credential_type, c.credential_type),
            "zoneIds": c.zone_ids,
            "zoneNames": svc.zone_names(db, svc._split_ids(c.zone_ids)),
            "validFrom": _t(c.valid_from),
            "validTo": _t(c.valid_to),
            "status": c.status,
            "code": c.code,
            "usedAt": _t(c.used_at),
            "usedCount": c.used_count,
            "createTime": _t(c.create_time),
        }
        for c in rows
    ]
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/credentials/verify")
def verify_credential(
    body: S.CredentialVerifyIn,
    current: User = Depends(require_perm("visitor:credential:verify")),
    db: Session = Depends(get_db),
):
    """门禁 / 闸机 / 梯控核验（放行与否 + 审计留痕）。"""
    result = svc.verify_credential(db, body.credential_no, body.zone_id, body.method, body.device_id, body.direction)
    audit(
        db, user_id=current.id, module="visitor", action="credential_verify",
        biz_type="visitor_credential", biz_id=None,
        detail={"credentialNo": body.credential_no, "pass": result["pass"]},
    )
    db.commit()
    return result


@router.post("/credentials/{cid}/revoke")
def revoke_credential(
    cid: int,
    current: User = Depends(require_perm("visitor:credential:edit")),
    db: Session = Depends(get_db),
):
    c = db.get(VisitorCredential, cid)
    if not c or c.deleted:
        raise BizException(R.VISITOR_CREDENTIAL_INVALID, "凭证不存在")
    c.status = "revoked"
    audit(
        db, user_id=current.id, module="visitor", action="credential_revoke",
        biz_type="visitor_credential", biz_id=cid, detail={"credentialNo": c.credential_no},
    )
    db.commit()
    return {"id": cid, "status": c.status}


# ---------------- 合规审计（只读） ----------------


@router.get("/access-logs")
def list_access_logs(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("visitor:audit:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(VisitorAccessLog),
        VisitorAccessLog,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["visitor_name", "credential_no", "zone_name", "device_id", "detail"],
        filter_cols={"event_type", "result", "method", "visit_id", "zone_id"},
        range_cols={"happened_at", "create_time"},
        sort_cols={"id", "happened_at", "event_type", "result"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    items = [
        {
            "id": r.id,
            "visitId": r.visit_id,
            "credentialNo": r.credential_no,
            "visitorName": r.visitor_name,
            "zoneId": r.zone_id,
            "zoneName": r.zone_name,
            "direction": r.direction,
            "eventType": r.event_type,
            "method": r.method,
            "result": r.result,
            "deviceId": r.device_id,
            "operatorName": r.operator_name,
            "happenedAt": _t(r.happened_at),
            "detail": r.detail,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/access-logs/summary")
def access_log_summary(
    request: Request,
    days: int = Query(7, ge=1, le=180),
    user: User = Depends(require_perm("visitor:audit:report")),
    db: Session = Depends(get_db),
):
    """应急报表：按天 / 区域 / 事件类型聚合。"""
    since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    since = since - timedelta(days=days - 1)
    rows = db.execute(
        select(
            func.date_format(VisitorAccessLog.happened_at, "%Y-%m-%d").label("d"),
            VisitorAccessLog.event_type,
            VisitorAccessLog.result,
            func.count(),
        )
        .where(VisitorAccessLog.happened_at >= since)
        .group_by("d", VisitorAccessLog.event_type, VisitorAccessLog.result)
    ).all()
    byDay: dict[str, int] = {}
    byEvent: dict[str, int] = {}
    denied = 0
    for d, event_type, result, n in rows:
        byDay[d] = byDay.get(d, 0) + n
        byEvent[event_type] = byEvent.get(event_type, 0) + n
        if result == "deny":
            denied += n
    return {
        "days": days,
        "since": since.strftime("%Y-%m-%d"),
        "total": sum(byDay.values()),
        "denied": denied,
        "byDay": byDay,
        "byEvent": byEvent,
    }


@router.post("/access-logs/export")
def export_access_logs(
    request: Request,
    current: User = Depends(require_perm("visitor:audit:export")),
    db: Session = Depends(get_db),
):
    """应急报表导出（审计日志只读导出，保留期 ≥180 天）。"""
    stmt, _ = apply_list_filters(
        select(VisitorAccessLog),
        VisitorAccessLog,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=["visitor_name", "credential_no", "zone_name", "device_id", "detail"],
        filter_cols={"event_type", "result", "method", "visit_id", "zone_id"},
        range_cols={"happened_at", "create_time"},
        sort_cols={"id", "happened_at"},
        default_sort=("id", "asc"),
    )
    rows = db.scalars(stmt).all()
    payload_rows = [
        {
            "happenedAt": _t(r.happened_at),
            "visitorName": r.visitor_name,
            "credentialNo": r.credential_no,
            "zoneName": r.zone_name,
            "eventType": r.event_type,
            "method": r.method,
            "result": r.result,
            "deviceId": r.device_id,
            "operatorName": r.operator_name,
            "detail": r.detail,
        }
        for r in rows
    ]
    payload = export_xlsx_styled(payload_rows, LOG_EXPORT_COLS, "visitor_access_logs")
    audit(
        db, user_id=current.id, module="visitor", action="access_log_export",
        detail={"count": len(payload_rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('visitor_access_logs')}"},
    )


# ---------------- 预警 ----------------


@router.get("/alerts")
def list_alerts(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("visitor:alert:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(VisitorAlert),
        VisitorAlert,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["message", "zone_name"],
        filter_cols={"alert_type", "status", "level", "visit_id"},
        range_cols={"occurred_at", "create_time"},
        sort_cols={"id", "alert_type", "status", "level", "occurred_at"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    items = [
        {
            "id": a.id,
            "visitId": a.visit_id,
            "alertType": a.alert_type,
            "alertTypeText": svc.ALERT_TYPE_CN.get(a.alert_type, a.alert_type),
            "level": a.level,
            "zoneId": a.zone_id,
            "zoneName": a.zone_name,
            "message": a.message,
            "occurredAt": _t(a.occurred_at),
            "status": a.status,
            "handledByName": a.handled_by_name,
            "handledAt": _t(a.handled_at),
            "handleRemark": a.handle_remark or "",
        }
        for a in rows
    ]
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/alerts/counts")
def alert_counts(
    user: User = Depends(require_perm("visitor:alert:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(VisitorAlert.status, func.count()).where(VisitorAlert.deleted == 0).group_by(VisitorAlert.status)
    ).all()
    data = {"open": 0, "handled": 0, "ignored": 0}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.post("/alerts/scan")
def scan_overdue(
    current: User = Depends(require_perm("visitor:alert:handle")),
    db: Session = Depends(get_db),
):
    """滞留扫描（可由定时任务或门禁回写触发）。"""
    n = svc.scan_overdue(db)
    audit(db, user_id=current.id, module="visitor", action="overdue_scan", detail={"count": n})
    db.commit()
    return {"scanned": n}


@router.post("/alerts/{aid}/handle")
def handle_alert(
    aid: int,
    body: S.AlertHandleIn,
    current: User = Depends(require_perm("visitor:alert:handle")),
    db: Session = Depends(get_db),
):
    a = db.get(VisitorAlert, aid)
    if not a or a.deleted:
        raise BizException(R.VISITOR_NOT_FOUND, "预警不存在")
    a.status = body.status
    a.handle_remark = body.handle_remark
    a.handled_by = current.id
    a.handled_by_name = current.name or current.username
    a.handled_at = datetime.now()
    audit(
        db, user_id=current.id, module="visitor", action="alert_handle",
        biz_type="visitor_alert", biz_id=aid, detail={"status": body.status},
    )
    db.commit()
    return {"id": aid, "status": a.status}


# ---------------- NDA ----------------


def _out_nda(n: VisitorNda) -> dict:
    return {
        "id": n.id,
        "ndaNo": n.nda_no,
        "title": n.title,
        "template": n.template,
        "visitorName": n.visitor_name,
        "visitorCompany": n.visitor_company,
        "signerTitle": n.signer_title,
        "idNo": n.id_no,
        "signedAt": _t(n.signed_at),
        "evidenceHash": n.evidence_hash,
        "signedById": n.signed_by_id,
        "signedByName": n.signed_by_name or "",
        "signedIp": n.signed_ip or "",
        "signAlg": n.sign_alg or "",
        "signVersion": n.sign_version or "",
        "validFrom": _t(n.valid_from),
        "validTo": _t(n.valid_to),
        "status": n.status,
        "visitId": n.visit_id,
        "staffId": n.staff_id,
        "remark": n.remark or "",
        "createTime": _t(n.create_time),
    }


@router.get("/nda")
def list_nda(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("visitor:nda:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(VisitorNda),
        VisitorNda,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["nda_no", "visitor_name", "visitor_company", "title"],
        filter_cols={"status", "template", "visit_id", "staff_id"},
        range_cols={"signed_at", "create_time"},
        sort_cols={"id", "nda_no", "visitor_name", "signed_at", "status"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_out_nda(n) for n in rows], "total": total, "page": page, "size": size}


@router.get("/nda/counts")
def nda_counts(
    user: User = Depends(require_perm("visitor:nda:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(VisitorNda.status, func.count()).where(VisitorNda.deleted == 0).group_by(VisitorNda.status)
    ).all()
    data = {"signed": 0, "expired": 0, "revoked": 0}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.post("/nda", status_code=201)
def sign_nda(
    body: S.NdaIn,
    current: User = Depends(require_perm("visitor:nda:sign")),
    db: Session = Depends(get_db),
):
    nda = svc.sign_nda(db, body, current.name or current.username, signed_by_id=current.id)
    audit(
        db, user_id=current.id, module="visitor", action="nda_sign",
        biz_type="visitor_nda", biz_id=nda.id,
        detail={
            "visitor": nda.visitor_name,
            "hash": nda.evidence_hash[:16],
            "alg": nda.sign_alg,
            "signedIp": nda.signed_ip,
        },
    )
    db.commit()
    return _out_nda(nda)


@router.get("/nda/{nid}/verify")
def verify_nda(
    nid: int,
    user: User = Depends(require_perm("visitor:nda:list")),
    db: Session = Depends(get_db),
):
    """NDA 验签（B9 合规 2.4）：签名与内容一致性 + 存量行口径说明。"""
    n = db.get(VisitorNda, nid)
    if not n or n.deleted:
        raise BizException(R.VISITOR_NOT_FOUND, "NDA 不存在")
    result = svc.verify_nda_signature(n)
    if not result["valid"] and result["verdict"] == "invalid":
        audit(
            db, user_id=user.id, module="visitor", action="nda_verify",
            biz_type="visitor_nda", biz_id=nid,
            detail={"verdict": result["verdict"], "reason": result["reason"]},
            strict=False,
        )
        db.commit()
    return {"id": n.id, "ndaNo": n.nda_no, **result}


@router.post("/nda/{nid}/revoke")
def revoke_nda(
    nid: int,
    current: User = Depends(require_perm("visitor:nda:sign")),
    db: Session = Depends(get_db),
):
    n = db.get(VisitorNda, nid)
    if not n or n.deleted:
        raise BizException(R.VISITOR_NOT_FOUND, "NDA 不存在")
    n.status = "revoked"
    audit(
        db, user_id=current.id, module="visitor", action="nda_revoke",
        biz_type="visitor_nda", biz_id=nid,
    )
    db.commit()
    return _out_nda(n)


# ---------------- 黑名单 ----------------


def _out_black(b: VisitorBlacklist) -> dict:
    return {
        "id": b.id,
        "visitorName": b.visitor_name,
        "idNo": b.id_no,
        "phone": b.phone,
        "company": b.company,
        "reason": b.reason,
        "effectiveFrom": _t(b.effective_from),
        "effectiveTo": _t(b.effective_to),
        "source": b.source,
        "status": b.status,
        "remark": b.remark or "",
        "createTime": _t(b.create_time),
    }


@router.get("/blacklist")
def list_blacklist(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("visitor:blacklist:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(VisitorBlacklist),
        VisitorBlacklist,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["visitor_name", "id_no", "phone", "company", "reason"],
        filter_cols={"status", "source"},
        range_cols={"effective_from", "effective_to", "create_time"},
        sort_cols={"id", "visitor_name", "status", "create_time"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_out_black(b) for b in rows], "total": total, "page": page, "size": size}


@router.get("/blacklist/counts")
def blacklist_counts(
    user: User = Depends(require_perm("visitor:blacklist:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(VisitorBlacklist.status, func.count())
        .where(VisitorBlacklist.deleted == 0)
        .group_by(VisitorBlacklist.status)
    ).all()
    data = {"enabled": 0, "disabled": 0}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.post("/blacklist", status_code=201)
def create_blacklist(
    body: S.BlacklistIn,
    current: User = Depends(require_perm("visitor:blacklist:edit")),
    db: Session = Depends(get_db),
):
    b = VisitorBlacklist(
        visitor_name=body.visitor_name,
        id_no=body.id_no,
        phone=body.phone,
        company=body.company,
        reason=body.reason,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        source=body.source,
        status=body.status,
        remark=body.remark,
    )
    db.add(b)
    db.flush()
    audit(
        db, user_id=current.id, module="visitor", action="blacklist_create",
        biz_type="visitor_blacklist", biz_id=b.id, detail={"name": b.visitor_name},
    )
    db.commit()
    return _out_black(b)


@router.put("/blacklist/{bid}")
def update_blacklist(
    bid: int,
    body: S.BlacklistIn,
    current: User = Depends(require_perm("visitor:blacklist:edit")),
    db: Session = Depends(get_db),
):
    b = db.get(VisitorBlacklist, bid)
    if not b or b.deleted:
        raise BizException(R.VISITOR_NOT_FOUND, "黑名单记录不存在")
    b.visitor_name = body.visitor_name
    b.id_no = body.id_no
    b.phone = body.phone
    b.company = body.company
    b.reason = body.reason
    b.effective_from = body.effective_from
    b.effective_to = body.effective_to
    b.source = body.source
    b.status = body.status
    b.remark = body.remark
    audit(
        db, user_id=current.id, module="visitor", action="blacklist_update",
        biz_type="visitor_blacklist", biz_id=bid,
    )
    db.commit()
    return _out_black(b)


@router.post("/blacklist/{bid}/toggle")
def toggle_blacklist(
    bid: int,
    status: str = Query(..., pattern="^(enabled|disabled)$"),
    current: User = Depends(require_perm("visitor:blacklist:edit")),
    db: Session = Depends(get_db),
):
    b = db.get(VisitorBlacklist, bid)
    if not b or b.deleted:
        raise BizException(R.VISITOR_NOT_FOUND, "黑名单记录不存在")
    b.status = status
    audit(
        db, user_id=current.id, module="visitor", action="blacklist_toggle",
        biz_type="visitor_blacklist", biz_id=bid, detail={"status": status},
    )
    db.commit()
    return _out_black(b)


# ---------------- 样品 / 样车交接 ----------------


@router.get("/handovers")
def list_handovers(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("visitor:handover:list")),
    db: Session = Depends(get_db),
):
    """交接记录查询（可按样品编号 / 条码反查）。"""
    stmt, total = apply_list_filters(
        select(VisitorSampleHandover),
        VisitorSampleHandover,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["handover_no", "sample_no", "sample_name", "barcode", "handover_user_name"],
        filter_cols={"visit_id", "sample_type", "status"},
        range_cols={"handover_at", "create_time"},
        sort_cols={"id", "handover_no", "sample_no", "handover_at"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    items = [
        {
            "id": h.id,
            "handoverNo": h.handover_no,
            "visitId": h.visit_id,
            "sampleNo": h.sample_no,
            "sampleName": h.sample_name,
            "barcode": h.barcode,
            "sampleType": h.sample_type,
            "qty": h.qty,
            "handoverUserName": h.handover_user_name,
            "receiveUserName": h.receive_user_name,
            "handoverAt": _t(h.handover_at),
            "status": h.status,
            "remark": h.remark or "",
        }
        for h in rows
    ]
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/handovers", status_code=201)
def create_handover(
    body: S.HandoverIn,
    current: User = Depends(require_perm("visitor:handover:create")),
    db: Session = Depends(get_db),
):
    """样品 / 样车交接登记（与访客单联动，可反查）。"""
    visit = db.get(VisitorVisit, body.visit_id) if body.visit_id else None
    if body.visit_id and (not visit or visit.deleted):
        raise BizException(R.VISITOR_NOT_FOUND)
    row = svc.create_handover(db, body, visit)
    audit(
        db, user_id=current.id, module="visitor", action="handover_create",
        biz_type="visitor_handover", biz_id=row.id,
        detail={"sampleNo": row.sample_no, "visitId": row.visit_id},
    )
    db.commit()
    return {
        "id": row.id,
        "handoverNo": row.handover_no,
        "visitId": row.visit_id,
        "sampleNo": row.sample_no,
        "sampleName": row.sample_name,
        "barcode": row.barcode,
        "sampleType": row.sample_type,
        "qty": row.qty,
        "handoverUserName": row.handover_user_name,
        "receiveUserName": row.receive_user_name,
        "handoverAt": _t(row.handover_at),
        "status": row.status,
        "remark": row.remark or "",
    }

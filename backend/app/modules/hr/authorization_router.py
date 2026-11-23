"""人员授权台账路由 /api/v1/hr（B9-C3 / HR L2 授权管理）。

与 `hr/router.py`（工时填报）同前缀，按「同前缀分文件」惯例拆开。

权限码：
- hr:authorization:list       列表 / 详情 / 轨迹 / 时点回放 / 选项
- hr:authorization:create     新建
- hr:authorization:edit       编辑
- hr:authorization:submit     提交审批
- hr:authorization:activate   生效 / 暂停 / 恢复
- hr:authorization:revoke     撤销 / 过期
- hr:authorization:export     导出
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.approval import registry
from app.modules.auth.models import User
from app.modules.hr import authorization as auth_svc
from app.modules.hr import schemas as S
from app.modules.hr.models import HrAuthorization
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import next_no

router = APIRouter(prefix="/hr", tags=["hr"], route_class=EnvelopeRoute)

AUTH_STATUS_CN = {
    "draft": "草稿",
    "approving": "审批中",
    "confirmed": "已确认",
    "active": "生效中",
    "suspended": "已暂停",
    "expired": "已过期",
    "revoked": "已撤销",
    "rejected": "已驳回",
}

AUTH_TYPE_CN = {
    "test_item": "检测项目",
    "device": "设备操作",
    "report_role": "报告角色",
    "signer": "授权签字",
}

AUTH_ROLE_CN = {
    "preparer": "编制",
    "reviewer": "复核",
    "approver": "批准",
    "signer": "签字",
}

AUTH_EXPORT_COLS = [
    {"key": "authNo", "label": "授权编号", "width": 18},
    {"key": "userName", "label": "被授权人", "width": 14},
    {"key": "deptName", "label": "部门", "width": 16},
    {"key": "authTypeText", "label": "授权类型", "width": 14},
    {"key": "roleCodeText", "label": "角色", "width": 10},
    {"key": "scopeMethod", "label": "检测方法", "width": 18},
    {"key": "scopeDeviceName", "label": "设备", "width": 18},
    {"key": "scopeDomain", "label": "业务域", "width": 16},
    {"key": "validFrom", "label": "生效时间", "width": 19},
    {"key": "validTo", "label": "失效时间", "width": 19},
    {"key": "statusText", "label": "状态", "width": 10},
    {"key": "approverName", "label": "批准人", "width": 14},
    {"key": "lastReason", "label": "最近原因", "width": 26},
]

_SEARCH_COLS = ["auth_no", "user_name", "scope_method", "scope_device_name", "scope_domain", "remark"]
_FILTER_COLS = {
    "status": HrAuthorization.status,
    "auth_type": HrAuthorization.auth_type,
    "role_code": HrAuthorization.role_code,
    "user_id": HrAuthorization.user_id,
    "dept_id": HrAuthorization.dept_id,
    "scope_method": HrAuthorization.scope_method,
    "scope_domain": HrAuthorization.scope_domain,
}
_RANGE_COLS = {"valid_from": HrAuthorization.valid_from, "valid_to": HrAuthorization.valid_to}
_SORT_COLS = {
    "id": HrAuthorization.id,
    "auth_no": HrAuthorization.auth_no,
    "user_name": HrAuthorization.user_name,
    "auth_type": HrAuthorization.auth_type,
    "status": HrAuthorization.status,
    "valid_from": HrAuthorization.valid_from,
    "valid_to": HrAuthorization.valid_to,
    "create_time": HrAuthorization.create_time,
}


def _load_auth(db: Session, aid: int) -> HrAuthorization:
    a = db.get(HrAuthorization, aid)
    if not a or a.deleted:
        raise BizException(R.HR_AUTH_NOT_FOUND, "授权记录不存在")
    return a


def _user_name(db: Session, user_id: int) -> str:
    u = db.get(User, user_id)
    return (u.name or u.username) if u else ""


def _auth_out(a: HrAuthorization) -> dict:
    data = auth_svc.out(a)
    data["statusText"] = AUTH_STATUS_CN.get(a.status, a.status)
    data["authTypeText"] = AUTH_TYPE_CN.get(a.auth_type, a.auth_type)
    data["roleCodeText"] = AUTH_ROLE_CN.get(a.role_code, a.role_code)
    return data


def _query(request: Request, db: Session):
    """导出用：与列表同一套过滤口径，但不限制条数。"""
    from types import SimpleNamespace

    return apply_list_filters(
        select(HrAuthorization),
        HrAuthorization,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=_SEARCH_COLS,
        filter_cols=_FILTER_COLS,
        range_cols=_RANGE_COLS,
        sort_cols=_SORT_COLS,
        default_sort=("id", "desc"),
    )


# ---------------- 列表 / 详情 ----------------


@router.get("/authorizations")
def list_authorizations(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("hr:authorization:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(HrAuthorization),
        HrAuthorization,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=_SEARCH_COLS,
        filter_cols=_FILTER_COLS,
        range_cols=_RANGE_COLS,
        sort_cols=_SORT_COLS,
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_auth_out(a) for a in rows], "total": total, "page": page, "size": size}


@router.get("/authorizations/counts")
def authorization_counts(
    current: User = Depends(require_perm("hr:authorization:list")),
    db: Session = Depends(get_db),
):
    """状态页签计数（含 all；前端 all 永远最左）。"""
    rows = db.execute(
        select(HrAuthorization.status, func.count())
        .where(HrAuthorization.deleted == 0)
        .group_by(HrAuthorization.status)
    ).all()
    data = {s: 0 for s in AUTH_STATUS_CN}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/authorizations/export")
def export_authorizations(
    request: Request,
    current: User = Depends(require_perm("hr:authorization:export")),
    db: Session = Depends(get_db),
):
    """授权台账导出（与列表同一套过滤口径）。"""
    stmt, _ = _query(request, db)
    rows = list(db.scalars(stmt).all())
    payload = export_xlsx_styled([_auth_out(a) for a in rows], AUTH_EXPORT_COLS, "hr_authorizations")
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_authorization_export",
        biz_type="hr_authorization",
        detail={"count": len(rows)},
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('hr_authorizations')}"},
    )


@router.get("/authorizations/options/users")
def authorization_user_options(
    q: str = Query("", max_length=64),
    current: User = Depends(require_perm("hr:authorization:list")),
    db: Session = Depends(get_db),
):
    """被授权人远程检索（姓名 / 账号）。"""
    kw = q.strip()
    stmt = select(User).where(User.deleted == 0)
    if kw:
        like = f"%{kw}%"
        stmt = stmt.where(User.name.like(like) | User.username.like(like))
    rows = db.scalars(stmt.order_by(User.id).limit(50)).all()
    return [{"value": u.id, "label": u.name or u.username, "sub": u.username} for u in rows]


@router.get("/authorizations/{aid}")
def get_authorization(
    aid: int,
    current: User = Depends(require_perm("hr:authorization:list")),
    db: Session = Depends(get_db),
):
    a = _load_auth(db, aid)
    data = _auth_out(a)
    data["timeline"] = auth_svc.timeline(db, aid)
    return data


@router.get("/authorizations/{aid}/timeline")
def authorization_timeline(
    aid: int,
    current: User = Depends(require_perm("hr:authorization:list")),
    db: Session = Depends(get_db),
):
    """授权变更轨迹（只追加，倒序）。"""
    _load_auth(db, aid)
    return {"items": auth_svc.timeline(db, aid)}


@router.get("/authorizations/{aid}/state-at")
def authorization_state_at(
    aid: int,
    at: datetime = Query(...),
    current: User = Depends(require_perm("hr:authorization:list")),
    db: Session = Depends(get_db),
):
    """回放某历史时点的授权状态（HR docx：可回溯任一历史时点）。"""
    _load_auth(db, aid)
    return auth_svc.state_at(db, aid, at)


# ---------------- 维护 ----------------


@router.post("/authorizations", status_code=201)
def create_authorization(
    body: S.AuthorizationIn,
    current: User = Depends(require_perm("hr:authorization:create")),
    db: Session = Depends(get_db),
):
    """新建授权（草稿）。授权须经审批确认后方可生效。"""
    a = HrAuthorization(
        auth_no=next_no(db, "hr_authorization"),
        user_id=body.user_id,
        user_name=_user_name(db, body.user_id),
        auth_type=body.auth_type,
        role_code=body.role_code,
        scope_method=body.scope_method,
        scope_params=body.scope_params,
        scope_device_id=body.scope_device_id,
        scope_device_name=body.scope_device_name,
        scope_domain=body.scope_domain,
        scope_json="",
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        status=auth_svc.STATUS_DRAFT,
        applicant_id=current.id,
        applicant_name=current.name or "",
        remark=body.remark,
        create_by=current.id,
    )
    db.add(a)
    db.flush()
    auth_svc.write_event(
        db,
        a,
        event_type="create",
        from_status="",
        to_status=auth_svc.STATUS_DRAFT,
        operator_id=current.id,
        operator_name=current.name or "",
        reason="创建授权申请",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_authorization_create",
        biz_type="hr_authorization",
        biz_id=a.id,
        field_name="status",
        old_value="",
        new_value=a.status,
        detail={"authNo": a.auth_no, "userId": a.user_id, "authType": a.auth_type},
        strict=True,
    )
    db.commit()
    return _auth_out(a)


@router.put("/authorizations/{aid}")
def update_authorization(
    aid: int,
    body: S.AuthorizationIn,
    current: User = Depends(require_perm("hr:authorization:edit")),
    db: Session = Depends(get_db),
):
    """编辑授权（仅草稿 / 驳回态可改）。"""
    a = _load_auth(db, aid)
    if a.status not in (auth_svc.STATUS_DRAFT, auth_svc.STATUS_REJECTED):
        raise BizException(R.HR_AUTH_INVALID_STATE, f"状态「{a.status}」不允许编辑授权")
    a.user_id = body.user_id
    a.user_name = _user_name(db, body.user_id)
    a.auth_type = body.auth_type
    a.role_code = body.role_code
    a.scope_method = body.scope_method
    a.scope_params = body.scope_params
    a.scope_device_id = body.scope_device_id
    a.scope_device_name = body.scope_device_name
    a.scope_domain = body.scope_domain
    a.valid_from = body.valid_from
    a.valid_to = body.valid_to
    a.remark = body.remark
    a.update_by = current.id
    a.update_time = datetime.now()
    db.flush()
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_authorization_update",
        biz_type="hr_authorization",
        biz_id=a.id,
        field_name="scope",
        old_value="",
        new_value=a.scope_method,
        detail={"authNo": a.auth_no, "authType": a.auth_type},
        strict=True,
    )
    db.commit()
    return _auth_out(a)


@router.post("/authorizations/{aid}/submit")
def submit_authorization(
    aid: int,
    body: S.AuthorizationSubmitIn | None = None,
    current: User = Depends(require_perm("hr:authorization:submit")),
    db: Session = Depends(get_db),
):
    """提交授权审批（不允许人工直通：未配置流程定义直接报错）。"""
    a = _load_auth(db, aid)
    if a.status not in (auth_svc.STATUS_DRAFT, auth_svc.STATUS_REJECTED):
        raise BizException(R.HR_AUTH_INVALID_STATE, f"状态「{a.status}」不允许提交审批")
    instance, _row = registry.submit_flow(
        db,
        "hr_authorization",
        aid,
        title=f"人员授权 {a.auth_no}",
        initiator=current,
        variables={"authNo": a.auth_no, "userName": a.user_name, "authType": a.auth_type},
        form_snapshot=auth_svc.snapshot(a),
    )
    if instance:
        a.flow_instance_id = instance.id
    auth_svc.write_event(
        db,
        a,
        event_type="submit",
        from_status=auth_svc.STATUS_DRAFT,
        to_status=auth_svc.STATUS_APPROVING,
        operator_id=current.id,
        operator_name=current.name or "",
        reason=(body.comment if body else "") or "提交授权审批",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_authorization_submit",
        biz_type="hr_authorization",
        biz_id=aid,
        field_name="status",
        old_value=auth_svc.STATUS_DRAFT,
        new_value=auth_svc.STATUS_APPROVING,
        detail={"authNo": a.auth_no, "instanceId": instance.id if instance else 0},
        strict=True,
    )
    db.commit()
    return _auth_out(a)


def _action(db: Session, aid: int, to_status: str, event_type: str, reason: str, current: User) -> dict:
    a = _load_auth(db, aid)
    auth_svc.transition(
        db,
        a,
        to_status,
        event_type=event_type,
        operator_id=current.id,
        operator_name=current.name or "",
        reason=reason,
    )
    db.commit()
    return _auth_out(a)


@router.post("/authorizations/{aid}/activate")
def activate_authorization(
    aid: int,
    body: S.AuthorizationActionIn | None = None,
    current: User = Depends(require_perm("hr:authorization:activate")),
    db: Session = Depends(get_db),
):
    """授权生效（confirmed → active）。"""
    return _action(
        db,
        aid,
        auth_svc.STATUS_ACTIVE,
        "activate",
        (body.reason if body else "") or "授权生效",
        current,
    )


@router.post("/authorizations/{aid}/suspend")
def suspend_authorization(
    aid: int,
    body: S.AuthorizationActionIn,
    current: User = Depends(require_perm("hr:authorization:activate")),
    db: Session = Depends(get_db),
):
    """暂停授权（原因必填）。"""
    return _action(db, aid, auth_svc.STATUS_SUSPENDED, "suspend", body.reason, current)


@router.post("/authorizations/{aid}/resume")
def resume_authorization(
    aid: int,
    body: S.AuthorizationActionIn | None = None,
    current: User = Depends(require_perm("hr:authorization:activate")),
    db: Session = Depends(get_db),
):
    """恢复授权（suspended → active）。"""
    return _action(
        db,
        aid,
        auth_svc.STATUS_ACTIVE,
        "resume",
        (body.reason if body else "") or "恢复授权",
        current,
    )


@router.post("/authorizations/{aid}/revoke")
def revoke_authorization(
    aid: int,
    body: S.AuthorizationActionIn,
    current: User = Depends(require_perm("hr:authorization:revoke")),
    db: Session = Depends(get_db),
):
    """撤销授权（原因必填；撤销立即生效）。"""
    return _action(db, aid, auth_svc.STATUS_REVOKED, "revoke", body.reason, current)


@router.post("/authorizations/{aid}/expire")
def expire_authorization(
    aid: int,
    body: S.AuthorizationActionIn,
    current: User = Depends(require_perm("hr:authorization:revoke")),
    db: Session = Depends(get_db),
):
    """授权过期（原因必填）。"""
    return _action(db, aid, auth_svc.STATUS_EXPIRED, "expire", body.reason, current)

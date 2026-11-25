"""人事事务与代理人路由 /api/v1/hr（B10-1 / HR L1）。

与 `hr/router.py`（工时）、`hr/authorization_router.py`（授权台账）、
`hr/org_router.py`（组织架构）、`hr/employee_router.py`（员工主数据）同前缀，
按「同前缀分文件」惯例拆开。

**审批通过 ≠ 生效**：人事事务必须先提交审批（`hr:employment:submit`），
审批通过后由 HR 显式点「生效」（`hr:employment:effect`）才执行副作用 ——
离职需在**离职当日**回收权限。

权限码：
- hr:employment:list    列表 / 计数 / 详情 / 轨迹
- hr:employment:create  新建
- hr:employment:edit    编辑
- hr:employment:submit  提交审批 / 撤回
- hr:employment:effect  生效（执行副作用）
- hr:delegate:list      代理列表
- hr:delegate:edit      代理维护
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common import recycle
from app.common.audit import record
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams, page_result
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.approval import engine, registry
from app.modules.auth.models import User
from app.modules.hr import employment as emp_svc
from app.modules.hr import schemas as S
from app.modules.hr.constants import DELEGATE_SCOPE_CN
from app.modules.hr.models import HrDelegate, HrEmployee, HrEmployment
from app.services.numbering import next_no

router = APIRouter(prefix="/hr", tags=["hr"], route_class=EnvelopeRoute)

EMPLOYMENT_STATUS_CN = {
    "draft": "草稿",
    "approving": "审批中",
    "approved": "已通过",
    "effective": "已生效",
    "rejected": "已驳回",
}

_SEARCH_COLS = ["emp_no", "user_name", "reason", "remark", "dept_name", "new_dept_name"]
_FILTER_COLS = {
    "status": HrEmployment.status,
    "event_type": HrEmployment.event_type,
    "employee_id": HrEmployment.employee_id,
    "user_id": HrEmployment.user_id,
    "applicant_id": HrEmployment.applicant_id,
}
_RANGE_COLS = {"effective_date": HrEmployment.effective_date}
_SORT_COLS = {
    "id": HrEmployment.id,
    "emp_no": HrEmployment.emp_no,
    "event_type": HrEmployment.event_type,
    "status": HrEmployment.status,
    "effective_date": HrEmployment.effective_date,
    "create_time": HrEmployment.create_time,
}

_DELEGATE_SEARCH_COLS = ["principal_name", "agent_name", "reason", "remark"]
_DELEGATE_FILTER_COLS = {
    "status": HrDelegate.status,
    "scope": HrDelegate.scope,
    "principal_id": HrDelegate.principal_id,
    "agent_id": HrDelegate.agent_id,
    "position_id": HrDelegate.position_id,
}
_DELEGATE_RANGE_COLS = {"effective_from": HrDelegate.effective_from, "effective_to": HrDelegate.effective_to}
_DELEGATE_SORT_COLS = {
    "id": HrDelegate.id,
    "principal_id": HrDelegate.principal_id,
    "agent_id": HrDelegate.agent_id,
    "scope": HrDelegate.scope,
    "status": HrDelegate.status,
    "effective_from": HrDelegate.effective_from,
    "create_time": HrDelegate.create_time,
}


def _load_employment(db: Session, eid: int) -> HrEmployment:
    row = db.get(HrEmployment, eid)
    if not row or row.deleted:
        raise BizException(R.HR_EMPLOYMENT_NOT_FOUND, "人事事务单据不存在")
    return row


def _employment_out(row: HrEmployment) -> dict:
    data = emp_svc.out(row)
    data["statusText"] = EMPLOYMENT_STATUS_CN.get(row.status, row.status)
    return data


def _delegate_out(d: HrDelegate) -> dict:
    return {
        "id": d.id,
        "principalId": d.principal_id,
        "principalName": d.principal_name,
        "agentId": d.agent_id,
        "agentName": d.agent_name,
        "scope": d.scope,
        "scopeText": DELEGATE_SCOPE_CN.get(d.scope, d.scope),
        "positionId": d.position_id,
        "authId": d.auth_id,
        "reason": d.reason,
        "effectiveFrom": d.effective_from.isoformat() if d.effective_from else "",
        "effectiveTo": d.effective_to.isoformat() if d.effective_to else "",
        "status": d.status,
        "autoTakeover": d.auto_takeover,
        "remark": d.remark,
        "createTime": d.create_time.isoformat() if d.create_time else "",
    }


def _user_name(db: Session, user_id: int | None) -> str:
    if not user_id:
        return ""
    u = db.get(User, user_id)
    return (u.name or u.username) if u else ""


# ---------------- 人事事务：列表 / 计数 / 详情 ----------------


@router.get("/employments")
def list_employments(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("hr:employment:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(HrEmployment),
        HrEmployment,
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
    return page_result([_employment_out(r) for r in rows], total, page, size)


@router.get("/employments/counts")
def employment_counts(
    current: User = Depends(require_perm("hr:employment:list")),
    db: Session = Depends(get_db),
):
    """状态页签计数（含 all；前端 all 永远最左）。"""
    rows = db.execute(
        select(HrEmployment.status, func.count())
        .where(HrEmployment.deleted == 0)
        .group_by(HrEmployment.status)
    ).all()
    data = {s: 0 for s in EMPLOYMENT_STATUS_CN}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/employments/{eid}")
def get_employment(
    eid: int,
    current: User = Depends(require_perm("hr:employment:list")),
    db: Session = Depends(get_db),
):
    """人事事务详情（含变更轨迹）。"""
    row = _load_employment(db, eid)
    data = _employment_out(row)
    data["timeline"] = emp_svc.timeline(db, eid)
    emp = db.get(HrEmployee, row.employee_id)
    data["employee"] = {
        "id": emp.id,
        "employeeNo": emp.employee_no,
        "name": emp.name,
        "employStatus": emp.employ_status,
        "userId": emp.user_id or 0,
    } if emp else None
    return data


@router.get("/employments/{eid}/timeline")
def employment_timeline(
    eid: int,
    current: User = Depends(require_perm("hr:employment:list")),
    db: Session = Depends(get_db),
):
    """人事事务变更轨迹（只追加，倒序）。"""
    _load_employment(db, eid)
    return {"items": emp_svc.timeline(db, eid)}


# ---------------- 人事事务：维护 ----------------


@router.post("/employments", status_code=201)
def create_employment(
    body: S.EmploymentIn,
    current: User = Depends(require_perm("hr:employment:create")),
    db: Session = Depends(get_db),
):
    """新建人事事务单（草稿）。

    入职单可同时勾选「开账号」并填初始密码 / 角色 —— 生效时据此建号
    （密码以密文落库，明文只在生效响应里出现一次）。
    """
    emp = db.get(HrEmployee, body.employee_id)
    if not emp or emp.deleted:
        raise BizException(R.HR_EMP_NOT_FOUND, "员工档案不存在")
    if body.create_account and body.event_type != "onboard":
        raise BizException(R.HR_EMPLOYMENT_INVALID_STATE, "只有入职事务可以开账号")
    if body.create_account and not (body.password or "").strip() and not emp.user_id:
        raise BizException(R.GENERIC_PARAM, "开账号时初始密码必填")

    row = HrEmployment(
        emp_no=next_no(db, "hr_employment"),
        event_type=body.event_type,
        employee_id=body.employee_id,
        user_id=emp.user_id,
        user_name=emp.name,
        dept_id=emp.dept_id,
        dept_name=emp_svc.dept_name_of(db, emp.dept_id),
        position_id=emp.position_id,
        position_name=emp_svc.position_name_of(db, emp.position_id),
        new_dept_id=body.new_dept_id,
        new_dept_name=emp_svc.dept_name_of(db, body.new_dept_id),
        new_position_id=body.new_position_id,
        new_position_name=emp_svc.position_name_of(db, body.new_position_id),
        effective_date=body.effective_date,
        reason=body.reason,
        status=emp_svc.STATUS_DRAFT,
        applicant_id=current.id,
        applicant_name=current.name or current.username,
        remark=body.remark,
        create_account=1 if body.create_account else 0,
        account_username=body.username,
        account_password=emp_svc.encrypt_account_password(body.password),
        account_roles=",".join(str(r) for r in body.role_ids),
        create_by=current.id,
    )
    db.add(row)
    db.flush()
    emp_svc.write_event(
        db,
        row,
        event_type="create",
        from_status="",
        to_status=emp_svc.STATUS_DRAFT,
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason=body.reason or "创建人事事务单",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employment_create",
        biz_type="hr_employment",
        biz_id=row.id,
        field_name="status",
        old_value="",
        new_value=row.status,
        detail={"empNo": row.emp_no, "eventType": row.event_type, "employeeId": emp.id},
        strict=True,
    )
    db.commit()
    return _employment_out(row)


@router.put("/employments/{eid}")
def update_employment(
    eid: int,
    body: S.EmploymentIn,
    current: User = Depends(require_perm("hr:employment:edit")),
    db: Session = Depends(get_db),
):
    """编辑人事事务单（仅草稿 / 驳回态可改）。"""
    row = _load_employment(db, eid)
    if row.status not in (emp_svc.STATUS_DRAFT, emp_svc.STATUS_REJECTED):
        raise BizException(
            R.HR_EMPLOYMENT_INVALID_STATE,
            f"状态「{row.status}」不允许编辑人事事务",
        )
    emp = db.get(HrEmployee, body.employee_id)
    if not emp or emp.deleted:
        raise BizException(R.HR_EMP_NOT_FOUND, "员工档案不存在")

    from_status = row.status
    row.event_type = body.event_type
    row.employee_id = body.employee_id
    row.user_id = emp.user_id
    row.user_name = emp.name
    row.dept_id = emp.dept_id
    row.dept_name = emp_svc.dept_name_of(db, emp.dept_id)
    row.position_id = emp.position_id
    row.position_name = emp_svc.position_name_of(db, emp.position_id)
    row.new_dept_id = body.new_dept_id
    row.new_dept_name = emp_svc.dept_name_of(db, body.new_dept_id)
    row.new_position_id = body.new_position_id
    row.new_position_name = emp_svc.position_name_of(db, body.new_position_id)
    row.effective_date = body.effective_date
    row.reason = body.reason
    row.remark = body.remark
    row.create_account = 1 if body.create_account else 0
    row.account_username = body.username
    row.account_password = emp_svc.encrypt_account_password(body.password)
    row.account_roles = ",".join(str(r) for r in body.role_ids)
    row.update_by = current.id
    row.update_time = datetime.now()
    db.flush()
    emp_svc.write_event(
        db,
        row,
        event_type="update",
        from_status=from_status,
        to_status=row.status,
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason=body.reason or "编辑人事事务单",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employment_update",
        biz_type="hr_employment",
        biz_id=row.id,
        field_name="status",
        old_value=from_status,
        new_value=row.status,
        detail={"empNo": row.emp_no, "eventType": row.event_type},
        strict=True,
    )
    db.commit()
    return _employment_out(row)


@router.post("/employments/{eid}/submit")
def submit_employment(
    eid: int,
    body: S.EmploymentActionIn | None = None,
    current: User = Depends(require_perm("hr:employment:submit")),
    db: Session = Depends(get_db),
):
    """提交人事事务审批（不允许人工直通：未配置流程定义直接报错）。"""
    row = _load_employment(db, eid)
    if row.status not in (emp_svc.STATUS_DRAFT, emp_svc.STATUS_REJECTED):
        raise BizException(
            R.HR_EMPLOYMENT_INVALID_STATE,
            f"状态「{row.status}」不允许提交审批",
        )
    instance, _row = registry.submit_flow(
        db,
        "hr_employment",
        eid,
        title=f"人事事务 {row.emp_no}",
        initiator=current,
        variables={
            "empNo": row.emp_no,
            "eventType": row.event_type,
            "userName": row.user_name,
        },
        form_snapshot=emp_svc.snapshot(row),
    )
    if instance:
        row.flow_instance_id = instance.id
    emp_svc.write_event(
        db,
        row,
        event_type="submit",
        from_status=emp_svc.STATUS_DRAFT,
        to_status=emp_svc.STATUS_APPROVING,
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason=(body.comment if body else "") or "提交人事事务审批",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employment_submit",
        biz_type="hr_employment",
        biz_id=eid,
        field_name="status",
        old_value=emp_svc.STATUS_DRAFT,
        new_value=emp_svc.STATUS_APPROVING,
        detail={"empNo": row.emp_no, "instanceId": instance.id if instance else 0},
        strict=True,
    )
    db.commit()
    return _employment_out(row)


@router.post("/employments/{eid}/withdraw")
def withdraw_employment(
    eid: int,
    body: S.EmploymentActionIn | None = None,
    current: User = Depends(require_perm("hr:employment:submit")),
    db: Session = Depends(get_db),
):
    """撤回人事事务审批（仅发起人，且无人处理时）。"""
    row = _load_employment(db, eid)
    if row.status != emp_svc.STATUS_APPROVING:
        raise BizException(
            R.HR_EMPLOYMENT_INVALID_STATE,
            f"状态「{row.status}」不允许撤回",
        )
    if not row.flow_instance_id:
        raise BizException(R.HR_EMPLOYMENT_INVALID_STATE, "该单据没有审批实例，无法撤回")
    engine.withdraw(db, row.flow_instance_id, current, (body.comment if body else "") or "发起人撤回")
    db.flush()
    emp_svc.write_event(
        db,
        row,
        event_type="withdraw",
        from_status=emp_svc.STATUS_APPROVING,
        to_status=emp_svc.STATUS_DRAFT,
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason=(body.comment if body else "") or "发起人撤回",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employment_withdraw",
        biz_type="hr_employment",
        biz_id=eid,
        field_name="status",
        old_value=emp_svc.STATUS_APPROVING,
        new_value=emp_svc.STATUS_DRAFT,
        detail={"empNo": row.emp_no},
        strict=True,
    )
    db.commit()
    return _employment_out(row)


@router.post("/employments/{eid}/effect")
def effect_employment(
    eid: int,
    current: User = Depends(require_perm("hr:employment:effect")),
    db: Session = Depends(get_db),
):
    """**生效**：执行人事事务的副作用（建号 / 调岗 / 离职清权 / 返聘）。

    副作用清单见 `app/modules/hr/employment.py::effect_employment`。
    """
    row = _load_employment(db, eid)
    result = emp_svc.effect_employment(
        db,
        row,
        operator_id=current.id,
        operator_name=current.name or current.username,
    )
    db.commit()
    data = _employment_out(row)
    data["effect"] = result
    return data


# ---------------- 代理人（AB 角 / 临时代理） ----------------


@router.get("/delegates")
def list_delegates(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("hr:delegate:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(HrDelegate),
        HrDelegate,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=_DELEGATE_SEARCH_COLS,
        filter_cols=_DELEGATE_FILTER_COLS,
        range_cols=_DELEGATE_RANGE_COLS,
        sort_cols=_DELEGATE_SORT_COLS,
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return page_result([_delegate_out(d) for d in rows], total, page, size)


def _validate_delegate(db: Session, body: S.DelegateIn) -> tuple[User, User]:
    if body.principal_id == body.agent_id:
        raise BizException(R.HR_DELEGATE_INVALID_STATE, "委托人与代理人不能是同一人")
    principal = db.get(User, body.principal_id)
    agent = db.get(User, body.agent_id)
    if not principal or principal.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "委托人不存在")
    if not agent or agent.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "代理人不存在")
    if body.scope == "position" and not body.position_id:
        raise BizException(R.HR_DELEGATE_INVALID_STATE, "岗位范围的代理必须指定岗位")
    return principal, agent


@router.post("/delegates", status_code=201)
def create_delegate(
    body: S.DelegateIn,
    current: User = Depends(require_perm("hr:delegate:edit")),
    db: Session = Depends(get_db),
):
    """新建代理记录（**不借账号** —— 代理只是授权与职责的临时转授）。"""
    principal, agent = _validate_delegate(db, body)
    d = HrDelegate(
        principal_id=principal.id,
        principal_name=principal.name or principal.username,
        agent_id=agent.id,
        agent_name=agent.name or agent.username,
        scope=body.scope,
        position_id=body.position_id,
        auth_id=body.auth_id,
        reason=body.reason,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        status="enabled",
        auto_takeover=1 if body.auto_takeover else 0,
        remark=body.remark,
        create_by=current.id,
    )
    db.add(d)
    db.flush()
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_delegate_create",
        biz_type="hr_delegate",
        biz_id=d.id,
        field_name="status",
        old_value="",
        new_value=d.status,
        detail={"principal": d.principal_name, "agent": d.agent_name, "scope": d.scope},
        strict=True,
    )
    db.commit()
    return _delegate_out(d)


@router.put("/delegates/{did}")
def update_delegate(
    did: int,
    body: S.DelegateIn,
    current: User = Depends(require_perm("hr:delegate:edit")),
    db: Session = Depends(get_db),
):
    """编辑代理记录。"""
    d = db.get(HrDelegate, did)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "代理记录不存在")
    if d.status == "expired":
        raise BizException(R.HR_DELEGATE_INVALID_STATE, "已失效的代理记录不可编辑")
    principal, agent = _validate_delegate(db, body)
    d.principal_id = principal.id
    d.principal_name = principal.name or principal.username
    d.agent_id = agent.id
    d.agent_name = agent.name or agent.username
    d.scope = body.scope
    d.position_id = body.position_id
    d.auth_id = body.auth_id
    d.reason = body.reason
    d.effective_from = body.effective_from
    d.effective_to = body.effective_to
    d.auto_takeover = 1 if body.auto_takeover else 0
    d.remark = body.remark
    d.update_by = current.id
    d.update_time = datetime.now()
    db.flush()
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_delegate_update",
        biz_type="hr_delegate",
        biz_id=d.id,
        field_name="scope",
        old_value="",
        new_value=d.scope,
        detail={"principal": d.principal_name, "agent": d.agent_name},
        strict=True,
    )
    db.commit()
    return _delegate_out(d)


@router.delete("/delegates/{did}")
def delete_delegate(
    did: int,
    current: User = Depends(require_perm("hr:delegate:edit")),
    db: Session = Depends(get_db),
):
    """撤销代理（逻辑删除）。"""
    d = db.get(HrDelegate, did)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "代理记录不存在")
    recycle.soft_delete(
        db, HrDelegate, d, user=current, module="hr", resource="HrDelegate",
        restore_fields={"status": d.status},
    )
    d.status = "revoked"
    d.update_by = current.id
    d.update_time = datetime.now()
    db.flush()
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_delegate_delete",
        biz_type="hr_delegate",
        biz_id=did,
        field_name="status",
        old_value=d.status,
        new_value="revoked",
        detail={"principal": d.principal_name, "agent": d.agent_name},
        strict=True,
    )
    db.commit()
    return None

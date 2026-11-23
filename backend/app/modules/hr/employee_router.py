"""员工主数据路由 /api/v1/hr（B10-1 / HR L1 员工一人一档）。

与 `hr/router.py`（工时）、`hr/authorization_router.py`（授权台账）、
`hr/org_router.py`（组织架构）同前缀，按「同前缀分文件」惯例拆开。

**敏感信息**：`id_no` 明文**唯一出口**是 `GET /hr/employees/{id}/id-no`，
且每次访问都写 `sys_audit_log`（谁在何时查看了谁的证件号 —— ALCOA 可归因）。

权限码：
- hr:staff:list      列表 / 计数 / 选项 / 详情 / 轨迹
- hr:staff:create    新建
- hr:staff:edit      编辑 / 删除 / 名单管控
- hr:staff:export    导出
- hr:staff:idno      查看证件号明文
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams, page_result
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.admin.models import Dept
from app.modules.auth.models import User
from app.modules.hr import employee as emp_svc
from app.modules.hr import org as org_svc
from app.modules.hr import schemas as S
from app.modules.hr.constants import EMPLOY_STATUSES
from app.modules.hr.models import (
    HrAuthorization,
    HrDelegate,
    HrEmployee,
    HrEmployment,
    HrEmploymentEvent,
    HrOrgChange,
)
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/hr", tags=["hr"], route_class=EnvelopeRoute)

EMP_STATUS_CN = {"enabled": "启用", "disabled": "停用"}

EMPLOYEE_EXPORT_COLS = [
    {"key": "employeeNo", "label": "工号", "width": 14},
    {"key": "name", "label": "姓名", "width": 14},
    {"key": "employTypeText", "label": "雇佣类型", "width": 12},
    {"key": "employStatusText", "label": "在职状态", "width": 12},
    {"key": "deptName", "label": "部门", "width": 20},
    {"key": "positionName", "label": "岗位", "width": 20},
    {"key": "gender", "label": "性别", "width": 8},
    {"key": "mobile", "label": "手机号", "width": 16},
    {"key": "email", "label": "邮箱", "width": 26},
    {"key": "hireDate", "label": "入职日期", "width": 14},
    {"key": "contractEnd", "label": "合同到期", "width": 14},
    {"key": "idNo", "label": "证件号", "width": 22},
    {"key": "remark", "label": "备注", "width": 24},
]

_SEARCH_COLS = ["employee_no", "name", "mobile", "email", "contract_no", "remark"]
_FILTER_COLS = {
    "status": HrEmployee.status,
    "employ_status": HrEmployee.employ_status,
    "employ_type": HrEmployee.employ_type,
    "dept_id": HrEmployee.dept_id,
    "position_id": HrEmployee.position_id,
    "user_id": HrEmployee.user_id,
    "education": HrEmployee.education,
}
_RANGE_COLS = {
    "hire_date": HrEmployee.hire_date,
    "leave_date": HrEmployee.leave_date,
    "contract_start": HrEmployee.contract_start,
    "contract_end": HrEmployee.contract_end,
}
_SORT_COLS = {
    "id": HrEmployee.id,
    "employee_no": HrEmployee.employee_no,
    "name": HrEmployee.name,
    "employ_status": HrEmployee.employ_status,
    "employ_type": HrEmployee.employ_type,
    "hire_date": HrEmployee.hire_date,
    "status": HrEmployee.status,
    "create_time": HrEmployee.create_time,
}


def _load_employee(db: Session, eid: int) -> HrEmployee:
    e = db.get(HrEmployee, eid)
    if not e or e.deleted:
        raise BizException(R.HR_EMP_NOT_FOUND, "员工档案不存在")
    return e


def _employee_out(db: Session, e: HrEmployee) -> dict:
    data = emp_svc.employee_out(db, e)
    data["statusText"] = EMP_STATUS_CN.get(e.status, e.status)
    data["controls"] = [emp_svc.control_out(c) for c in emp_svc.active_controls(db, e.id)]
    return data


def _all_query(request: Request, db: Session):
    """导出用：与列表同一套过滤口径，但不限制条数。"""
    from types import SimpleNamespace

    return apply_list_filters(
        select(HrEmployee),
        HrEmployee,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=_SEARCH_COLS,
        filter_cols=_FILTER_COLS,
        range_cols=_RANGE_COLS,
        sort_cols=_SORT_COLS,
        default_sort=("id", "desc"),
    )


def _timeline(db: Session, e: HrEmployee) -> list[dict]:
    """员工档案轨迹：人事事务变更 + 组织变更快照（合并倒序）。"""
    items: list[dict] = []
    emp_ids = db.scalars(
        select(HrEmployment.id).where(HrEmployment.employee_id == e.id, HrEmployment.deleted == 0)
    ).all()
    if emp_ids:
        rows = db.scalars(
            select(HrEmploymentEvent)
            .where(HrEmploymentEvent.employment_id.in_(emp_ids))
            .order_by(HrEmploymentEvent.id.desc())
        ).all()
        for r in rows:
            items.append(
                {
                    "kind": "employment",
                    "id": r.id,
                    "empNo": r.emp_no,
                    "eventType": r.event_type,
                    "fromStatus": r.from_status,
                    "toStatus": r.to_status,
                    "operatorId": r.operator_id,
                    "operatorName": r.operator_name,
                    "reason": r.reason,
                    "effectiveAt": r.effective_at.isoformat() if r.effective_at else "",
                }
            )
    org_rows = db.scalars(
        select(HrOrgChange)
        .where(HrOrgChange.object_type == "employee", HrOrgChange.object_id == e.id)
        .order_by(HrOrgChange.id.desc())
    ).all()
    for r in org_rows:
        items.append(
            {
                "kind": "org",
                "id": r.id,
                "empNo": "",
                "eventType": r.change_type,
                "fromStatus": "",
                "toStatus": "",
                "operatorId": r.operator_id,
                "operatorName": r.operator_name,
                "reason": r.reason,
                "effectiveAt": r.effective_at.isoformat() if r.effective_at else "",
            }
        )
    items.sort(key=lambda x: (x["effectiveAt"], x["id"]), reverse=True)
    return items


# ---------------- 列表 / 计数 / 选项 ----------------


@router.get("/employees")
def list_employees(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("hr:staff:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(HrEmployee),
        HrEmployee,
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
    return page_result([_employee_out(db, e) for e in rows], total, page, size)


@router.get("/employees/counts")
def employee_counts(
    current: User = Depends(require_perm("hr:staff:list")),
    db: Session = Depends(get_db),
):
    """状态页签计数（含 all；前端 all 永远最左）。"""
    rows = db.execute(
        select(HrEmployee.employ_status, func.count())
        .where(HrEmployee.deleted == 0)
        .group_by(HrEmployee.employ_status)
    ).all()
    data = {s: 0 for s in EMPLOY_STATUSES}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/employees/options")
def employee_options(
    current: User = Depends(require_perm("hr:staff:list")),
    db: Session = Depends(get_db),
):
    """员工下拉选项（在职人员 / 全部）—— 人事事务表单用。"""
    rows = db.scalars(
        select(HrEmployee).where(HrEmployee.deleted == 0).order_by(HrEmployee.employee_no)
    ).all()
    dept_names = {d.id: d.name for d in db.scalars(select(Dept).where(Dept.deleted == 0)).all()}
    return {
        "all": [
            {
                "value": e.id,
                "label": f"{e.name}（{e.employee_no}）",
                "sub": e.employee_no,
                "employStatus": e.employ_status,
                "deptName": dept_names.get(e.dept_id, ""),
                "userId": e.user_id or 0,
            }
            for e in rows
        ],
        "active": [
            {
                "value": e.id,
                "label": f"{e.name}（{e.employee_no}）",
                "sub": e.employee_no,
                "employStatus": e.employ_status,
                "deptName": dept_names.get(e.dept_id, ""),
                "userId": e.user_id or 0,
            }
            for e in rows
            if e.employ_status not in ("resigned", "retired")
        ],
    }


@router.get("/employees/export")
def export_employees(
    request: Request,
    current: User = Depends(require_perm("hr:staff:export")),
    db: Session = Depends(get_db),
):
    """员工档案导出（与列表同一套过滤口径；证件号仍为掩码）。"""
    stmt, _ = _all_query(request, db)
    rows = list(db.scalars(stmt).all())
    items = [_employee_out(db, e) for e in rows]
    payload = export_xlsx_styled(items, EMPLOYEE_EXPORT_COLS, "hr_employees")
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employee_export",
        biz_type="hr_employee",
        detail={"count": len(items)},
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('hr_employees')}"},
    )


# ---------------- 详情 / 明文 / 轨迹 ----------------


@router.get("/employees/{eid}")
def get_employee(
    eid: int,
    current: User = Depends(require_perm("hr:staff:list")),
    db: Session = Depends(get_db),
):
    """员工档案详情：档案 + 任职 + 授权 + 代理 + 人事事务轨迹。"""
    e = _load_employee(db, eid)
    data = _employee_out(db, e)
    data["memberships"] = emp_svc.employee_memberships(db, e)
    data["timeline"] = _timeline(db, e)

    if e.user_id:
        auths = db.scalars(
            select(HrAuthorization)
            .where(HrAuthorization.user_id == e.user_id, HrAuthorization.deleted == 0)
            .order_by(HrAuthorization.id.desc())
        ).all()
        data["authorizations"] = [
            {
                "id": a.id,
                "authNo": a.auth_no,
                "authType": a.auth_type,
                "roleCode": a.role_code,
                "scopeMethod": a.scope_method,
                "status": a.status,
                "validFrom": a.valid_from.isoformat() if a.valid_from else "",
                "validTo": a.valid_to.isoformat() if a.valid_to else "",
            }
            for a in auths
        ]
        delegates = db.scalars(
            select(HrDelegate).where(
                HrDelegate.deleted == 0,
                (HrDelegate.principal_id == e.user_id) | (HrDelegate.agent_id == e.user_id),
            )
        ).all()
        data["delegates"] = [
            {
                "id": d.id,
                "principalId": d.principal_id,
                "principalName": d.principal_name,
                "agentId": d.agent_id,
                "agentName": d.agent_name,
                "scope": d.scope,
                "positionId": d.position_id,
                "status": d.status,
                "autoTakeover": d.auto_takeover,
                "reason": d.reason,
            }
            for d in delegates
        ]
    else:
        data["authorizations"] = []
        data["delegates"] = []

    employments = db.scalars(
        select(HrEmployment)
        .where(HrEmployment.employee_id == eid, HrEmployment.deleted == 0)
        .order_by(HrEmployment.id.desc())
    ).all()
    data["employments"] = [
        {
            "id": m.id,
            "empNo": m.emp_no,
            "eventType": m.event_type,
            "status": m.status,
            "effectiveDate": m.effective_date.isoformat() if m.effective_date else "",
            "reason": m.reason,
        }
        for m in employments
    ]
    return data


@router.get("/employees/{eid}/id-no")
def get_employee_id_no(
    eid: int,
    current: User = Depends(require_perm("hr:staff:idno")),
    db: Session = Depends(get_db),
):
    """证件号明文 —— **唯一出口**，每次访问写审计日志（ALCOA 可归因）。"""
    e = _load_employee(db, eid)
    plain = emp_svc.decrypt_id_no(e.id_no)
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employee_idno_view",
        biz_type="hr_employee",
        biz_id=e.id,
        field_name="id_no",
        old_value="",
        new_value=emp_svc.mask_id_no(plain),
        detail={"employeeNo": e.employee_no, "name": e.name},
        strict=True,
    )
    db.commit()
    return {"idNo": plain, "masked": emp_svc.mask_id_no(plain)}


@router.get("/employees/{eid}/timeline")
def employee_timeline(
    eid: int,
    current: User = Depends(require_perm("hr:staff:list")),
    db: Session = Depends(get_db),
):
    """员工档案轨迹（人事事务变更 + 组织变更快照，倒序）。"""
    e = _load_employee(db, eid)
    return {"items": _timeline(db, e)}


# ---------------- 维护 ----------------


@router.post("/employees", status_code=201)
def create_employee(
    body: S.EmployeeIn,
    current: User = Depends(require_perm("hr:staff:create")),
    db: Session = Depends(get_db),
):
    """新建员工档案（可先建档、后开账号 —— `user_id` 为空）。"""
    emp_svc.check_employee_conflicts(
        db,
        employee_no=body.employee_no,
        id_no=body.id_no,
        employ_type=body.employ_type,
        position_id=body.position_id,
        user_id=body.user_id,
    )
    data = body.model_dump()
    data["id_no"] = emp_svc.encrypt_id_no(data.get("id_no", ""))
    e = HrEmployee(**data, create_by=current.id)
    db.add(e)
    db.flush()
    emp_svc.sync_user_redundant(db, e)
    org_svc.write_org_change(
        db,
        object_type="employee",
        object_id=e.id,
        object_name=e.name,
        change_type="create",
        before=None,
        after=_employee_out(db, e),
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason="新建员工档案",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employee_create",
        biz_type="hr_employee",
        biz_id=e.id,
        field_name="employee_no",
        old_value="",
        new_value=e.employee_no,
        detail={"name": e.name, "employType": e.employ_type},
        strict=True,
    )
    db.commit()
    return _employee_out(db, e)


@router.put("/employees/{eid}")
def update_employee(
    eid: int,
    body: S.EmployeeIn,
    current: User = Depends(require_perm("hr:staff:edit")),
    db: Session = Depends(get_db),
):
    """编辑员工档案。证件号留空表示**不修改**（避免列表页回显掩码覆盖真实值）。"""
    e = _load_employee(db, eid)
    before = _employee_out(db, e)
    emp_svc.check_employee_conflicts(
        db,
        employee_no=body.employee_no,
        id_no=body.id_no,
        employ_type=body.employ_type,
        position_id=body.position_id,
        user_id=body.user_id,
        exclude_id=eid,
    )
    data = body.model_dump()
    if not (data.get("id_no") or "").strip():
        data["id_no"] = e.id_no
    else:
        data["id_no"] = emp_svc.encrypt_id_no(data["id_no"])
    new_user_id = data.pop("user_id", None)
    for k, v in data.items():
        setattr(e, k, v)
    if new_user_id != e.user_id:
        emp_svc.link_user(db, e, new_user_id)
    else:
        e.user_id = new_user_id
    e.update_by = current.id
    e.update_time = datetime.now()
    db.flush()
    emp_svc.sync_user_redundant(db, e)
    after = _employee_out(db, e)
    org_svc.write_org_change(
        db,
        object_type="employee",
        object_id=e.id,
        object_name=e.name,
        change_type="update",
        before=before,
        after=after,
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason=body.remark or "编辑员工档案",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employee_update",
        biz_type="hr_employee",
        biz_id=e.id,
        field_name="employ_status",
        old_value=before.get("employStatus", ""),
        new_value=after.get("employStatus", ""),
        detail={"employeeNo": e.employee_no, "name": e.name},
        strict=True,
    )
    db.commit()
    return _employee_out(db, e)


@router.delete("/employees/{eid}")
def delete_employee(
    eid: int,
    current: User = Depends(require_perm("hr:staff:edit")),
    db: Session = Depends(get_db),
):
    """删除员工档案（逻辑删除）。

    有**未完结的人事事务**（草稿 / 审批中）时拒绝删除 —— 否则会留下指向空档案的单据。
    """
    e = _load_employee(db, eid)
    pending = db.scalar(
        select(HrEmployment.id).where(
            HrEmployment.employee_id == eid,
            HrEmployment.status.in_(("draft", "approving")),
            HrEmployment.deleted == 0,
        )
    )
    if pending:
        raise BizException(R.HR_EMP_INVALID_STATE, "该员工存在未完结的人事事务，无法删除")

    before = _employee_out(db, e)
    emp_svc.link_user(db, e, None)
    e.deleted = 1
    e.update_by = current.id
    e.update_time = datetime.now()
    db.flush()
    org_svc.write_org_change(
        db,
        object_type="employee",
        object_id=e.id,
        object_name=e.name,
        change_type="delete",
        before=before,
        after=None,
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason="删除员工档案",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employee_delete",
        biz_type="hr_employee",
        biz_id=eid,
        field_name="status",
        old_value=before.get("status", ""),
        new_value="deleted",
        detail={"employeeNo": e.employee_no, "name": e.name},
        strict=True,
    )
    db.commit()
    return None


@router.post("/employees/{eid}/control")
def create_employee_control(
    eid: int,
    body: S.EmployeeControlIn,
    current: User = Depends(require_perm("hr:staff:edit")),
    db: Session = Depends(get_db),
):
    """名单管控（黑名单 / 白名单）。

    同一员工同一名单类型只有一条记录，重复写入改为更新（原因 / 有效期 / 状态）。
    """
    e = _load_employee(db, eid)
    row = emp_svc.write_control(
        db,
        e,
        control_type=body.control_type,
        reason=body.reason,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        status=body.status,
        remark=body.remark,
        operator_id=current.id,
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_employee_control",
        biz_type="hr_employee",
        biz_id=eid,
        field_name="control_type",
        old_value="",
        new_value=body.control_type,
        detail={"employeeNo": e.employee_no, "reason": body.reason},
        strict=True,
    )
    db.commit()
    return emp_svc.control_out(row)

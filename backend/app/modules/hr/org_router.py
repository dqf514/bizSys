"""组织架构路由 /api/v1/hr（B10-1 / HR L1 组织架构）。

与 `hr/router.py`（工时填报）、`hr/authorization_router.py`（授权台账）同前缀，
按「同前缀分文件」惯例拆开。

**写入口边界**：部门（`sys_dept`）的增删改**仍统一走 `admin/router.py` 的
`/admin/depts`**（全站唯一部门写入口，HR 组织架构页复用），本文件只负责
**岗位**与**组织变更轨迹** —— 避免两套部门写入口造成双轨漂移。

权限码：
- hr:org:list         组织变更轨迹 / 组织下拉选项
- hr:position:list    岗位列表 / 计数
- hr:position:create  新建岗位
- hr:position:edit    编辑 / 删除岗位
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select, update
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
from app.modules.auth.models import User
from app.modules.hr import org as org_svc
from app.modules.hr import schemas as S
from app.modules.hr.models import HrDelegate, HrEmployee, HrOrgChange, HrPosition
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/hr", tags=["hr"], route_class=EnvelopeRoute)

POSITION_STATUS_CN = {"enabled": "启用", "disabled": "停用"}

CHANGE_TYPE_CN = {
    "create": "新建",
    "update": "修改",
    "move": "调整归属",
    "disable": "停用",
    "enable": "启用",
    "delete": "删除",
}

OBJECT_TYPE_CN = {"dept": "部门", "position": "岗位", "employee": "员工"}

POSITION_EXPORT_COLS = [
    {"key": "code", "label": "岗位编码", "width": 16},
    {"key": "name", "label": "岗位名称", "width": 22},
    {"key": "deptName", "label": "所属部门", "width": 20},
    {"key": "siteName", "label": "所属场所", "width": 18},
    {"key": "positionTypeText", "label": "岗位类型", "width": 12},
    {"key": "keyRoleText", "label": "关键岗位标记", "width": 16},
    {"key": "reportToName", "label": "汇报岗位", "width": 18},
    {"key": "primaryUserName", "label": "A 角", "width": 14},
    {"key": "backupUserName", "label": "B 角", "width": 14},
    {"key": "status", "label": "状态", "width": 8},
    {"key": "remark", "label": "备注", "width": 26},
]

_SEARCH_COLS = ["code", "name", "duty", "requirement", "remark"]
_FILTER_COLS = {
    "status": HrPosition.status,
    "position_type": HrPosition.position_type,
    "key_role": HrPosition.key_role,
    "dept_id": HrPosition.dept_id,
    "site_id": HrPosition.site_id,
}
_SORT_COLS = {
    "id": HrPosition.id,
    "code": HrPosition.code,
    "name": HrPosition.name,
    "position_type": HrPosition.position_type,
    "key_role": HrPosition.key_role,
    "status": HrPosition.status,
    "create_time": HrPosition.create_time,
}

_CHANGE_SEARCH_COLS = ["object_name", "reason", "operator_name"]
_CHANGE_FILTER_COLS = {
    "object_type": HrOrgChange.object_type,
    "object_id": HrOrgChange.object_id,
    "change_type": HrOrgChange.change_type,
    "operator_id": HrOrgChange.operator_id,
}
_CHANGE_RANGE_COLS = {"effective_at": HrOrgChange.effective_at}
_CHANGE_SORT_COLS = {
    "id": HrOrgChange.id,
    "object_type": HrOrgChange.object_type,
    "object_id": HrOrgChange.object_id,
    "change_type": HrOrgChange.change_type,
    "effective_at": HrOrgChange.effective_at,
    "create_time": HrOrgChange.create_time,
}


def _load_position(db: Session, pid: int) -> HrPosition:
    p = db.get(HrPosition, pid)
    if not p or p.deleted:
        raise BizException(R.HR_POSITION_NOT_FOUND, "岗位不存在")
    return p


def _position_out(db: Session, p: HrPosition) -> dict:
    data = org_svc.position_out(db, p)
    data["statusText"] = POSITION_STATUS_CN.get(p.status, p.status)
    return data


def _change_out(c: HrOrgChange) -> dict:
    def _parse(raw: str) -> dict:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {}

    return {
        "id": c.id,
        "objectType": c.object_type,
        "objectTypeText": OBJECT_TYPE_CN.get(c.object_type, c.object_type),
        "objectId": c.object_id,
        "objectName": c.object_name,
        "changeType": c.change_type,
        "changeTypeText": CHANGE_TYPE_CN.get(c.change_type, c.change_type),
        "before": _parse(c.before_json),
        "after": _parse(c.after_json),
        "operatorId": c.operator_id,
        "operatorName": c.operator_name,
        "effectiveAt": c.effective_at.isoformat() if c.effective_at else "",
        "reason": c.reason,
        "createTime": c.create_time.isoformat() if c.create_time else "",
    }


def _all_query(request: Request, db: Session):
    """导出用：与列表同一套过滤口径，但不限制条数。"""
    from types import SimpleNamespace

    return apply_list_filters(
        select(HrPosition),
        HrPosition,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=_SEARCH_COLS,
        filter_cols=_FILTER_COLS,
        sort_cols=_SORT_COLS,
        default_sort=("id", "desc"),
    )


# ---------------- 岗位 ----------------


@router.get("/org/positions")
def list_positions(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("hr:position:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(HrPosition),
        HrPosition,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=_SEARCH_COLS,
        filter_cols=_FILTER_COLS,
        sort_cols=_SORT_COLS,
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return page_result([_position_out(db, p) for p in rows], total, page, size)


@router.get("/org/positions/counts")
def position_counts(
    current: User = Depends(require_perm("hr:position:list")),
    db: Session = Depends(get_db),
):
    """状态页签计数（含 all；前端 all 永远最左）。"""
    rows = db.execute(
        select(HrPosition.status, func.count())
        .where(HrPosition.deleted == 0)
        .group_by(HrPosition.status)
    ).all()
    data = {s: 0 for s in POSITION_STATUS_CN}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/org/positions/export")
def export_positions(
    request: Request,
    current: User = Depends(require_perm("hr:position:list")),
    db: Session = Depends(get_db),
):
    """岗位导出（与列表同一套过滤口径）。"""
    stmt, _ = _all_query(request, db)
    rows = list(db.scalars(stmt).all())
    items = [_position_out(db, p) for p in rows]
    payload = export_xlsx_styled(items, POSITION_EXPORT_COLS, "hr_positions")
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_position_export",
        biz_type="hr_position",
        detail={"count": len(items)},
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('hr_positions')}"},
    )


@router.post("/org/positions", status_code=201)
def create_position(
    body: S.PositionIn,
    current: User = Depends(require_perm("hr:position:create")),
    db: Session = Depends(get_db),
):
    """新建岗位（含岗位职责 / 任职要求 / 关键岗位标记 / A、B 角）。"""
    exists = db.scalar(
        select(HrPosition.id).where(HrPosition.code == body.code, HrPosition.deleted == 0)
    )
    if exists:
        raise BizException(R.HR_ORG_INVALID_STATE, f"岗位编码已存在：{body.code}")
    if body.primary_user_id and body.primary_user_id == body.backup_user_id:
        raise BizException(R.HR_ORG_INVALID_STATE, "A 角与 B 角不能是同一人")

    p = HrPosition(**body.model_dump(), create_by=current.id)
    db.add(p)
    db.flush()
    org_svc.write_org_change(
        db,
        object_type="position",
        object_id=p.id,
        object_name=p.name,
        change_type="create",
        before=None,
        after=_position_out(db, p),
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason="新建岗位",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_position_create",
        biz_type="hr_position",
        biz_id=p.id,
        field_name="code",
        old_value="",
        new_value=p.code,
        detail={"name": p.name, "keyRole": p.key_role},
        strict=True,
    )
    db.commit()
    return _position_out(db, p)


@router.put("/org/positions/{pid}")
def update_position(
    pid: int,
    body: S.PositionIn,
    current: User = Depends(require_perm("hr:position:edit")),
    db: Session = Depends(get_db),
):
    """编辑岗位（每次改动留一份 before/after 快照，可回溯历史版本）。"""
    p = _load_position(db, pid)
    dup = db.scalar(
        select(HrPosition.id).where(
            HrPosition.code == body.code, HrPosition.id != pid, HrPosition.deleted == 0
        )
    )
    if dup:
        raise BizException(R.HR_ORG_INVALID_STATE, f"岗位编码已存在：{body.code}")
    if body.primary_user_id and body.primary_user_id == body.backup_user_id:
        raise BizException(R.HR_ORG_INVALID_STATE, "A 角与 B 角不能是同一人")

    before = _position_out(db, p)
    data = body.model_dump()
    for k, v in data.items():
        setattr(p, k, v)
    p.update_by = current.id
    p.update_time = datetime.now()
    db.flush()
    after = _position_out(db, p)
    org_svc.write_org_change(
        db,
        object_type="position",
        object_id=p.id,
        object_name=p.name,
        change_type="update",
        before=before,
        after=after,
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason=body.remark or "编辑岗位",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_position_update",
        biz_type="hr_position",
        biz_id=p.id,
        field_name="key_role",
        old_value=before.get("keyRole", ""),
        new_value=after.get("keyRole", ""),
        detail={"code": p.code, "name": p.name},
        strict=True,
    )
    db.commit()
    return _position_out(db, p)


@router.delete("/org/positions/{pid}")
def delete_position(
    pid: int,
    current: User = Depends(require_perm("hr:position:edit")),
    db: Session = Depends(get_db),
):
    """删除岗位（逻辑删除）。

    同时清理引用：员工的在岗岗位、岗位的汇报关系、代理记录 —— 避免留下悬空引用。
    """
    p = _load_position(db, pid)
    before = _position_out(db, p)

    db.execute(
        update(HrEmployee)
        .where(HrEmployee.position_id == pid, HrEmployee.deleted == 0)
        .values(position_id=None)
    )
    db.execute(
        update(HrPosition)
        .where(HrPosition.report_to_id == pid, HrPosition.id != pid, HrPosition.deleted == 0)
        .values(report_to_id=None)
    )
    db.execute(
        update(HrDelegate)
        .where(HrDelegate.position_id == pid, HrDelegate.deleted == 0)
        .values(position_id=None)
    )

    recycle.soft_delete(db, HrPosition, p, user=current, module="hr", resource="HrPosition")
    p.update_by = current.id
    p.update_time = datetime.now()
    db.flush()
    org_svc.write_org_change(
        db,
        object_type="position",
        object_id=p.id,
        object_name=p.name,
        change_type="delete",
        before=before,
        after=None,
        operator_id=current.id,
        operator_name=current.name or current.username,
        reason="删除岗位",
    )
    record(
        db,
        user_id=current.id,
        module="hr",
        action="hr_position_delete",
        biz_type="hr_position",
        biz_id=pid,
        field_name="status",
        old_value="enabled",
        new_value="deleted",
        detail={"code": before.get("code", ""), "name": before.get("name", "")},
        strict=True,
    )
    db.commit()
    return None


# ---------------- 组织变更轨迹 / 选项 ----------------


@router.get("/org/changes")
def list_org_changes(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("hr:org:list")),
    db: Session = Depends(get_db),
):
    """组织变更轨迹（只追加，倒序）。可回溯任一时点的组织形态。"""
    stmt, total = apply_list_filters(
        select(HrOrgChange),
        HrOrgChange,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=_CHANGE_SEARCH_COLS,
        filter_cols=_CHANGE_FILTER_COLS,
        range_cols=_CHANGE_RANGE_COLS,
        sort_cols=_CHANGE_SORT_COLS,
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return page_result([_change_out(c) for c in rows], total, page, size)


@router.get("/org/options")
def org_options(
    current: User = Depends(require_perm("hr:org:list")),
    db: Session = Depends(get_db),
):
    """组织下拉选项：场所 / 部门 / 岗位 / 关键岗位 / 枚举字典。"""
    return org_svc.org_options(db)

"""组织架构纯逻辑层（B10-1 / HR docx 2.1）。

职责：
- 部门 / 岗位的**出参序列化**（camelCase，含中文标签与统计数）；
- **组织变更快照**（`hr_org_change`，只追加）—— 部门与岗位的每次增删改都留
  before/after，可回溯任一时点的组织形态（docx「多层级 + 历史版本」）；
- 组织下拉选项（场所 / 部门 / 岗位 / 关键岗位）。

**不依赖 router**：路由层负责鉴权与事务，本模块只做纯逻辑与轨迹写入。
"""

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.admin.models import Dept, UserDept
from app.modules.auth.models import User
from app.modules.hr.constants import (
    DEPT_TYPE_CN,
    DEPT_TYPES,
    KEY_ROLE_CN,
    KEY_ROLES,
    POSITION_TYPE_CN,
    POSITION_TYPES,
)
from app.modules.hr.models import HrOrgChange, HrPosition

__all__ = [
    "DEPT_TYPES",
    "DEPT_TYPE_CN",
    "POSITION_TYPES",
    "POSITION_TYPE_CN",
    "KEY_ROLES",
    "KEY_ROLE_CN",
    "user_names",
    "site_of_dept",
    "dept_counts",
    "dept_out",
    "position_out",
    "write_org_change",
    "org_options",
]


def _now() -> datetime:
    return datetime.now()


def user_names(db: Session, ids: list[int]) -> dict[int, str]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(ids))).all()
    return {u.id: (u.name or u.username) for u in rows}


def site_of_dept(db: Session, dept_id: int | None) -> int | None:
    """所属场所：沿部门树向上找到第一个 `dept_type='site'` 的节点。

    没有显式场所时回退到树根（保证「多场所」口径下总有一个归属）。
    """
    cur = dept_id
    seen: set[int] = set()
    root: int | None = None
    while cur and cur not in seen:
        seen.add(cur)
        d = db.get(Dept, cur)
        if not d or d.deleted:
            break
        if root is None:
            root = d.id
        if d.dept_type == "site" or d.site_code:
            return d.id
        cur = d.parent_id
    return root


def dept_counts(db: Session) -> tuple[dict[int, int], dict[int, int]]:
    """(部门人数, 部门岗位数) 统计 —— 部门树上直接展示规模。"""
    member_rows = db.execute(
        select(UserDept.dept_id, func.count(UserDept.id)).where(UserDept.deleted == 0).group_by(UserDept.dept_id)
    ).all()
    position_rows = db.execute(
        select(HrPosition.dept_id, func.count(HrPosition.id))
        .where(HrPosition.deleted == 0)
        .group_by(HrPosition.dept_id)
    ).all()
    return (
        {int(r[0]): int(r[1]) for r in member_rows if r[0] is not None},
        {int(r[0]): int(r[1]) for r in position_rows if r[0] is not None},
    )


def dept_out(
    db: Session,
    d: Dept,
    member_counts: dict[int, int] | None = None,
    position_counts: dict[int, int] | None = None,
    manager_names: dict[int, str] | None = None,
) -> dict:
    """部门出参（camelCase）。"""
    if manager_names is None:
        manager_names = user_names(db, [d.manager_id] if d.manager_id else [])
    return {
        "id": d.id,
        "parentId": d.parent_id,
        "name": d.name,
        "code": d.code,
        "sort": d.sort,
        "status": d.status,
        "deptType": d.dept_type,
        "deptTypeText": DEPT_TYPE_CN.get(d.dept_type, d.dept_type),
        "siteCode": d.site_code,
        "address": d.address,
        "managerId": d.manager_id,
        "managerName": manager_names.get(d.manager_id, "") if d.manager_id else "",
        "effectiveFrom": d.effective_from.isoformat() if d.effective_from else "",
        "effectiveTo": d.effective_to.isoformat() if d.effective_to else "",
        "memberCount": (member_counts or {}).get(d.id, 0),
        "positionCount": (position_counts or {}).get(d.id, 0),
        "createTime": d.create_time.isoformat() if d.create_time else "",
    }


def position_out(db: Session, p: HrPosition, names: dict[int, str] | None = None) -> dict:
    """岗位出参（camelCase）。"""
    if names is None:
        names = user_names(db, [p.primary_user_id, p.backup_user_id])
    dept = db.get(Dept, p.dept_id) if p.dept_id else None
    site = db.get(Dept, p.site_id) if p.site_id else None
    report_to = db.get(HrPosition, p.report_to_id) if p.report_to_id else None
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "deptId": p.dept_id,
        "deptName": dept.name if dept else "",
        "siteId": p.site_id,
        "siteName": site.name if site else "",
        "positionType": p.position_type,
        "positionTypeText": POSITION_TYPE_CN.get(p.position_type, p.position_type),
        "duty": p.duty,
        "requirement": p.requirement,
        "reportToId": p.report_to_id,
        "reportToName": report_to.name if report_to else "",
        "keyRole": p.key_role,
        "keyRoleText": KEY_ROLE_CN.get(p.key_role, p.key_role),
        "primaryUserId": p.primary_user_id,
        "primaryUserName": names.get(p.primary_user_id, "") if p.primary_user_id else "",
        "backupUserId": p.backup_user_id,
        "backupUserName": names.get(p.backup_user_id, "") if p.backup_user_id else "",
        "status": p.status,
        "remark": p.remark,
        "createTime": p.create_time.isoformat() if p.create_time else "",
    }


def write_org_change(
    db: Session,
    *,
    object_type: str,
    object_id: int,
    object_name: str,
    change_type: str,
    before: dict | None,
    after: dict | None,
    operator_id: int | None = None,
    operator_name: str = "",
    reason: str = "",
) -> None:
    """写一条组织变更快照（`hr_org_change`，只追加）。

    只 `db.flush()`，不 commit —— 事务边界在 router。
    """
    db.add(
        HrOrgChange(
            object_type=object_type,
            object_id=object_id,
            object_name=object_name,
            change_type=change_type,
            before_json=json.dumps(before, ensure_ascii=False, default=str) if before else "",
            after_json=json.dumps(after, ensure_ascii=False, default=str) if after else "",
            operator_id=operator_id,
            operator_name=operator_name,
            effective_at=_now(),
            reason=reason or "",
        )
    )
    db.flush()


def org_options(db: Session) -> dict:
    """组织下拉选项：场所 / 部门 / 岗位 / 关键岗位。

    前端组织架构页与人事事务表单共用同一份选项，避免各页各写一套。
    """
    depts = db.scalars(select(Dept).where(Dept.deleted == 0).order_by(Dept.sort, Dept.id)).all()
    positions = db.scalars(
        select(HrPosition).where(HrPosition.deleted == 0).order_by(HrPosition.code, HrPosition.id)
    ).all()
    names = user_names(
        db,
        [p.primary_user_id for p in positions] + [p.backup_user_id for p in positions],
    )
    return {
        "sites": [
            {"value": d.id, "label": d.name, "siteCode": d.site_code, "deptType": d.dept_type}
            for d in depts
            if d.dept_type == "site" or d.site_code
        ],
        "depts": [
            {"value": d.id, "label": d.name, "parentId": d.parent_id, "deptType": d.dept_type}
            for d in depts
        ],
        "positions": [
            {
                "value": p.id,
                "label": p.name,
                "code": p.code,
                "deptId": p.dept_id,
                "keyRole": p.key_role,
                "primaryUserId": p.primary_user_id,
                "primaryUserName": names.get(p.primary_user_id, "") if p.primary_user_id else "",
                "backupUserId": p.backup_user_id,
                "backupUserName": names.get(p.backup_user_id, "") if p.backup_user_id else "",
            }
            for p in positions
        ],
        "keyPositions": [
            {
                "value": p.id,
                "label": p.name,
                "keyRole": p.key_role,
                "keyRoleText": KEY_ROLE_CN.get(p.key_role, p.key_role),
                "primaryUserId": p.primary_user_id,
                "primaryUserName": names.get(p.primary_user_id, "") if p.primary_user_id else "",
                "backupUserId": p.backup_user_id,
                "backupUserName": names.get(p.backup_user_id, "") if p.backup_user_id else "",
            }
            for p in positions
            if p.key_role
        ],
        "deptTypes": [{"value": k, "label": v} for k, v in DEPT_TYPE_CN.items()],
        "positionTypes": [{"value": k, "label": v} for k, v in POSITION_TYPE_CN.items()],
        "keyRoles": [{"value": k, "label": v} for k, v in KEY_ROLE_CN.items()],
    }

"""企业微信组织 / 人员 / 标签的**全模拟**种子（E1）。

数据源：`app/seeds/data/wecom_{org,tags,people}.json`（由 `scripts/parse_wecom_doc.py`
从《企业微信审批与组织数据技术文档.html》解析并**脱敏**而来 —— 姓名替换为
`模拟员工NN`、账号 `mockNNN`，手机号 / 邮箱 / 企微 vid 在解析阶段即丢弃）。

落位（复用现有表，**不新建组织表**）：

| 企微概念 | bizSys | 键 |
| --- | --- | --- |
| 11 个部门 | `sys_dept` | `code = WC01…WC11`，`parent_id` 按文档树 |
| 23 个标签 | `sys_role` | `code = wc_tag_01…wc_tag_23`（**只作审批人来源，不挂菜单**） |
| 40 名成员 | `sys_user` | `username = mock001…mock040`，密码 `Mock@123456` |
| 成员→部门 | `sys_user_dept` | 每人每条部门路径一条任职，首条 `is_primary=1` |
| 成员→标签 | `sys_user_role` | 标签角色 + 基础角色 `biz_user` |
| 岗位职务 | `hr_position` | 按 title 去重，`code = WCP001…` |
| 员工档案 | `hr_employee` | `employee_no = MOCK001…`，`id_no` 空 |

**隐私红线**：本模块**禁止**写入真实姓名 / 手机号 / 邮箱 / 证件号 / 企微 ID。
所有标识一律取自脱敏后的 JSON；`hr_employee.id_no`、`mobile`、`email` 一律留空。

`sys_dept` 仍是全站唯一部门表（写入口 `POST/PUT /admin/depts`）；本模块只做**只读种子**。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.admin.models import Dept, Role, UserDept, UserRole
from app.modules.auth.models import User
from app.modules.hr.models import HrEmployee, HrPosition

DATA_DIR = Path(__file__).parent / "data"

#: 模拟账号统一口令（仅供演示；上线前请重置）
MOCK_PASSWORD = "Mock@123456"

#: 标签角色 code 前缀（标签 → 角色的唯一通道）
TAG_ROLE_PREFIX = "wc_tag_"

#: 模拟人员的基础角色（给 OA 申请等常规入口的可见性；标签角色本身不挂菜单）
BASE_ROLE_CODE = "biz_user"


# --------------------------------------------------------------------------- 数据


def _load(name: str) -> Any:
    path = DATA_DIR / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def org_data() -> list[dict]:
    return _load("wecom_org.json")


def tag_data() -> list[dict]:
    return _load("wecom_tags.json")


def people_data() -> list[dict]:
    return _load("wecom_people.json")


def tag_role_code(tag_name: str) -> str:
    """标签名 → 角色 code（稳定：直接用标签名派生，便于流程包 JSON 可读）。"""
    name = (tag_name or "").strip()
    return f"{TAG_ROLE_PREFIX}{name}" if name else ""


def _dept_path_key(path: str) -> str:
    """部门路径归一化：人员文件用 `/`，组织文件用 ` / `。"""
    return " / ".join(p.strip() for p in path.split("/") if p.strip())


# --------------------------------------------------------------------------- 落库


def import_org(db: Session) -> dict:
    """幂等导入模拟组织 / 人员 / 标签。返回统计摘要。"""
    from app.modules.admin import org as org_mod  # noqa: PLC0415 避免种子与模块加载循环

    orgs = org_data()
    tags = tag_data()
    people = people_data()

    # —— 1. 部门（先建行，再按 parent_name 连父子）——
    dept_by_name: dict[str, Dept] = {}
    for idx, o in enumerate(orgs, start=1):
        code = f"WC{idx:02d}"
        row = db.scalar(select(Dept).where(Dept.code == code, Dept.deleted == 0))
        if row is None:
            row = Dept(name=o.get("name", code), code=code)
            db.add(row)
            db.flush()
        level = int(o.get("level") or 1)
        row.name = o.get("name", row.name)
        row.dept_type = {1: "company", 2: "division"}.get(level, "dept")
        row.status = "enabled"
        row.sort = idx
        dept_by_name[row.name] = row
    for o in orgs:
        row = dept_by_name.get(o.get("name", ""))
        parent = dept_by_name.get(o.get("parent_name", "") or "")
        if row is not None:
            row.parent_id = parent.id if parent is not None and parent.id != row.id else None
    db.flush()

    # 部门路径：按父子链自上而下拼（源文档的 path 列格式不规整，不直接采用）
    parent_of: dict[str, str] = {o.get("name", ""): o.get("parent_name", "") or "" for o in orgs}

    def _chain(name: str) -> list[str]:
        parts = [name]
        cur = parent_of.get(name, "")
        guard = 0
        while cur and cur in parent_of and guard < 10:
            parts.append(cur)
            cur = parent_of.get(cur, "")
            guard += 1
        return list(reversed(parts))

    dept_by_path: dict[str, Dept] = {}
    for o in orgs:
        row = dept_by_name.get(o.get("name", ""))
        if row is None:
            continue
        dept_by_path[" / ".join(_chain(row.name))] = row

    # —— 2. 标签角色（只挂名字与备注，不挂菜单 → 仅作审批人来源）——
    tag_roles: dict[str, Role] = {}
    for t in tags:
        code = tag_role_code(t.get("name", ""))
        if not code:
            continue
        role = db.scalar(select(Role).where(Role.code == code, Role.deleted == 0))
        if role is None:
            role = Role(code=code, name=t.get("name", code))
            db.add(role)
            db.flush()
        role.name = t.get("name", role.name)
        role.data_scope = "all"
        role.status = "enabled"
        role.remark = f"企业微信标签：{t.get('name', '')}（模拟）"
        tag_roles[t.get("name", "")] = role
    db.flush()

    # 清理历史版本遗留的序号式标签角色（wc_tag_01…）—— 标签 code 改为按名派生后作废
    valid_codes = {r.code for r in tag_roles.values()}
    for stale in db.scalars(select(Role).where(Role.code.like(f"{TAG_ROLE_PREFIX}%"), Role.deleted == 0)).all():
        if stale.code in valid_codes or not stale.code[len(TAG_ROLE_PREFIX) :].isdigit():
            continue
        for link in db.scalars(select(UserRole).where(UserRole.role_id == stale.id, UserRole.deleted == 0)).all():
            link.deleted = 1
        stale.deleted = 1
        stale.status = "disabled"
    db.flush()

    base_role = db.scalar(select(Role).where(Role.code == BASE_ROLE_CODE, Role.deleted == 0))

    # —— 3. 人员账号 ——
    user_by_name: dict[str, User] = {}
    users: dict[str, User] = {}
    for p in people:
        username = p.get("account") or f"mock{int(p.get('seq') or 0):03d}"
        row = db.scalar(select(User).where(User.username == username, User.deleted == 0))
        if row is None:
            row = User(
                username=username,
                password_hash=hash_password(MOCK_PASSWORD),
                name=p.get("name", username),
                status="enabled",
            )
            db.add(row)
            db.flush()
        resigned = "离职" in (p.get("status") or "")
        row.name = p.get("name", row.name)
        row.status = "disabled" if resigned else "enabled"
        row.employee_no = f"MOCK{int(p.get('seq') or 0):03d}"
        row.mobile = ""
        row.email = ""
        row.hire_date = None
        users[username] = row
        user_by_name[p.get("name", "")] = row
    db.flush()

    # —— 4. 任职（sys_user_dept）——
    leader_of: dict[str, str] = {}
    for o in orgs:
        if o.get("leader"):
            leader_of[o.get("name", "")] = o["leader"]

    for p in people:
        username = p.get("account")
        user = users.get(username or "")
        if user is None:
            continue
        paths = p.get("dept_paths") or []
        primary_done = False
        for path in paths:
            dept = dept_by_path.get(_dept_path_key(path))
            if dept is None:
                continue
            row = db.scalar(
                select(UserDept).where(
                    UserDept.user_id == user.id, UserDept.dept_id == dept.id, UserDept.deleted == 0
                )
            )
            if row is None:
                row = UserDept(user_id=user.id, dept_id=dept.id)
                db.add(row)
                db.flush()
            row.is_primary = 0 if primary_done else 1
            row.is_leader = 1 if leader_of.get(dept.name) == p.get("name") else 0
            if row.is_primary:
                primary_done = True
                user.dept_id = dept.id
                user.dept_name = dept.name
    db.flush()

    # —— 5. 标签角色 + 基础角色（sys_user_role）——
    for p in people:
        user = users.get(p.get("account") or "")
        if user is None:
            continue
        wanted: list[Role] = []
        for tag_name in p.get("tags") or []:
            role = tag_roles.get(tag_name)
            if role is not None:
                wanted.append(role)
        if base_role is not None:
            wanted.append(base_role)
        for role in wanted:
            row = db.scalar(
                select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id, UserRole.deleted == 0)
            )
            if row is None:
                db.add(UserRole(user_id=user.id, role_id=role.id))
    db.flush()

    # —— 6. 岗位（hr_position，按 title 去重）——
    positions: dict[str, HrPosition] = {}
    seq = 0
    for p in people:
        title = (p.get("title") or "").strip()
        if not title or title == "—":
            continue
        if title in positions:
            continue
        seq += 1
        code = f"WCP{seq:03d}"
        pos = db.scalar(select(HrPosition).where(HrPosition.code == code, HrPosition.deleted == 0))
        if pos is None:
            pos = HrPosition(code=code, name=title)
            db.add(pos)
            db.flush()
        pos.name = title
        pos.position_type = "staff"
        pos.status = "enabled"
        pos.remark = "企业微信岗位职务（模拟）"
        user = users.get(p.get("account") or "")
        if user is not None:
            pos.dept_id = user.dept_id
            pos.primary_user_id = user.id
        positions[title] = pos
    db.flush()

    # —— 7. 员工档案（hr_employee）——
    for p in people:
        user = users.get(p.get("account") or "")
        if user is None:
            continue
        emp_no = f"MOCK{int(p.get('seq') or 0):03d}"
        emp = db.scalar(select(HrEmployee).where(HrEmployee.employee_no == emp_no, HrEmployee.deleted == 0))
        if emp is None:
            emp = HrEmployee(employee_no=emp_no, name=p.get("name", emp_no))
            db.add(emp)
            db.flush()
        resigned = "离职" in (p.get("status") or "")
        position = positions.get((p.get("title") or "").strip())
        emp.name = p.get("name", emp.name)
        emp.user_id = user.id
        emp.gender = p.get("gender") or ""
        emp.dept_id = user.dept_id
        emp.position_id = position.id if position is not None else None
        emp.employ_status = "resigned" if resigned else "regular"
        emp.status = "disabled" if resigned else "enabled"
        # 隐私：证件号 / 手机 / 邮箱一律留空
        emp.id_no = ""
        emp.mobile = ""
        emp.email = ""
        emp.emergency_contact = ""
        emp.emergency_mobile = ""
    db.flush()

    # —— 8. 部门负责人回写（dept.manager_id ↔ 任职表 is_leader）——
    for o in orgs:
        dept = dept_by_name.get(o.get("name", ""))
        if dept is None:
            continue
        leader = user_by_name.get(o.get("leader") or "")
        manager_id = leader.id if leader is not None else None
        org_mod.apply_dept_manager(db, dept, manager_id)
    db.flush()

    return {
        "depts": len(dept_by_name),
        "tag_roles": len(tag_roles),
        "users": len(users),
        "positions": len(positions),
    }

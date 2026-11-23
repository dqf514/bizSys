"""组织任职解析：主部门、部门负责人、逐级负责人链。

供审批引擎（DEPT_LEADER / PARENT_DEPT_LEADER / SUPERVISOR_CHAIN）与部门管理复用。
解析语义对齐 TPCworkflow services/assignee_resolver.py + org_service.py：
- 主部门：sys_user_dept 中 is_primary=1 的任职；无任职时回退 user.dept_id（旧字段兼容）；
- 负责人：该部门 is_leader=1 且用户 enabled 的任职；
- 逐级链：从发起人主部门起沿 parent_id 向上，逐级收集负责人，支持级数上限。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.admin.models import Dept, UserDept
from app.modules.auth.models import User


def primary_dept_id(db: Session, user_id: int) -> int | None:
    """用户主部门：任职表优先，回退 user.dept_id。"""
    did = db.scalar(
        select(UserDept.dept_id).where(
            UserDept.user_id == user_id, UserDept.is_primary == 1, UserDept.deleted == 0
        ).limit(1)
    )
    if did:
        return did
    u = db.get(User, user_id)
    return u.dept_id if u else None


def _enabled_users(db: Session, ids: list[int]) -> dict[int, User]:
    if not ids:
        return {}
    rows = db.scalars(
        select(User).where(User.id.in_(ids), User.status == "enabled", User.deleted == 0)
    ).all()
    return {u.id: u for u in rows}


def dept_leader_ids(db: Session, dept_id: int, exclude_user_id: int = 0) -> list[int]:
    """部门负责人（enabled 用户），可按发起人排除（避免自审）。"""
    ids = db.scalars(
        select(UserDept.user_id).where(
            UserDept.dept_id == dept_id, UserDept.is_leader == 1, UserDept.deleted == 0
        )
    ).all()
    users = _enabled_users(db, [i for i in ids if i != exclude_user_id])
    return [i for i in ids if i != exclude_user_id and i in users]


def leader_chain(
    db: Session, dept_id: int, levels: int = 0, exclude_user_id: int = 0
) -> tuple[list[int], list[str]]:
    """逐级负责人链：从 dept_id 起沿部门树向上；levels<=0 表示一直到根部门。

    返回 (有序去重的负责人用户 ID 列表, 跳过说明列表)。某级无负责人时跳过该级并记录说明。
    """
    chain: list[int] = []
    notes: list[str] = []
    cur: int | None = dept_id
    depth = 0
    guard = 0
    while cur and guard < 50:
        guard += 1
        dept = db.get(Dept, cur)
        if not dept or dept.deleted:
            break
        depth += 1
        leaders = dept_leader_ids(db, cur, exclude_user_id=exclude_user_id)
        if leaders:
            for uid in leaders:
                if uid not in chain:
                    chain.append(uid)
        else:
            notes.append(f"第{depth}级「{dept.name}」无负责人，已跳过")
        if levels > 0 and depth >= levels:
            break
        cur = dept.parent_id
    return chain, notes


def sync_primary_membership(db: Session, user: User) -> None:
    """把 user.dept_id 同步为主部门任职（用户创建/更新、部门成员维护后调用）。

    - user.dept_id 非空：对应任职 is_primary=1，其余任职 is_primary=0；无任职则补建。
    - user.dept_id 为空：仅清除主部门标记，不删任职。
    """
    rows = list(
        db.scalars(select(UserDept).where(UserDept.user_id == user.id, UserDept.deleted == 0)).all()
    )
    target = user.dept_id
    for r in rows:
        r.is_primary = 1 if (target and r.dept_id == target) else 0
    if target and not any(r.dept_id == target for r in rows):
        db.add(UserDept(user_id=user.id, dept_id=target, is_primary=1))
    db.flush()


def apply_dept_manager(db: Session, dept: Dept, manager_id: int | None) -> None:
    """设置部门负责人（B10-1 组织架构）。

    `dept.manager_id` 是**权威写入方**；这里把它与任职表的 `is_leader` 标记双向同步：

    - manager_id 为空 → 清除本部门全部任职的 is_leader；
    - manager_id 非空 → 该用户在本科室的任职 is_leader=1，本部门其余任职 is_leader=0；
      若该用户还没有本科室的任职则补建（非主部门标记）。

    审批引擎的 `DEPT_LEADER` 解析读的是任职表的 is_leader，因此两处必须一致。
    """
    rows = list(db.scalars(select(UserDept).where(UserDept.dept_id == dept.id, UserDept.deleted == 0)).all())
    if not manager_id:
        for r in rows:
            r.is_leader = 0
        dept.manager_id = None
        db.flush()
        return
    for r in rows:
        r.is_leader = 1 if r.user_id == manager_id else 0
    if not any(r.user_id == manager_id for r in rows):
        db.add(UserDept(user_id=manager_id, dept_id=dept.id, is_primary=0, is_leader=1))
    dept.manager_id = manager_id
    db.flush()


def sync_dept_manager_from_members(db: Session, dept: Dept) -> None:
    """从任职表的 is_leader 标记反推 `dept.manager_id`（部门成员维护后调用）。

    部门只有一个负责人：取 is_leader=1 的第一个任职；没有则清空。
    """
    rows = list(db.scalars(select(UserDept).where(UserDept.dept_id == dept.id, UserDept.deleted == 0)).all())
    leader = next((r.user_id for r in rows if r.is_leader == 1), None)
    dept.manager_id = leader
    db.flush()

"""系统管理业务：菜单树、角色授权、偏好、账号创建等。"""

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.core.security import hash_password
from app.modules.admin.models import Menu, Role, RoleMenu, UserPref, UserRole
from app.modules.admin.org import sync_primary_membership
from app.modules.auth.models import User


def _menu_node(m: Menu) -> dict:
    return {
        "id": m.id,
        "parentId": m.parent_id,
        "name": m.name,
        "titleKey": m.title_key,
        "path": m.path,
        "componentKey": m.component_key,
        "icon": m.icon,
        "permission": m.permission,
        "menuType": m.menu_type,
        "sort": m.sort,
        "visible": m.visible,
    }


def menu_tree_all(db: Session, include_buttons: bool = False) -> list[dict]:
    menus = db.scalars(select(Menu).where(Menu.deleted == 0).order_by(Menu.sort, Menu.id)).all()
    if not include_buttons:
        menus = [m for m in menus if m.menu_type != "button"]
    return _build_tree(menus)


def menu_tree_for_user(db: Session, user: User) -> list[dict]:
    """按用户角色过滤后的可见菜单树（dir/menu，不含按钮）。

    角色通常只挂叶子菜单（按钮/页面），目录节点未必勾选；
    这里自动补齐被授权菜单的全部祖先目录，保证树形分组完整，
    避免叶子节点因找不到父级而被提升为根节点、平铺展示。
    """
    if "super" in user.role_codes:
        menus = db.scalars(
            select(Menu).where(Menu.deleted == 0, Menu.visible == 1).order_by(Menu.sort, Menu.id)
        ).all()
        return _build_tree([m for m in menus if m.menu_type != "button"])
    menu_ids = set(
        db.scalars(
            select(RoleMenu.menu_id)
            .join(Role, Role.id == RoleMenu.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user.id,
                Role.status == "enabled",
                Role.deleted == 0,
                RoleMenu.deleted == 0,
            )
        ).all()
    )
    if not menu_ids:
        return []
    all_menus = db.scalars(
        select(Menu).where(Menu.deleted == 0, Menu.visible == 1).order_by(Menu.sort, Menu.id)
    ).all()
    by_id = {m.id: m for m in all_menus}
    keep = set(menu_ids)
    for mid in menu_ids:
        node = by_id.get(mid)
        while node and node.parent_id and node.parent_id not in keep:
            keep.add(node.parent_id)
            node = by_id.get(node.parent_id)
    menus = [m for m in all_menus if m.id in keep and m.menu_type != "button"]
    return _build_tree(menus)


def all_menu_paths(db: Session) -> list[str]:
    """全部菜单路由路径（不过滤权限）：前端据此区分 404（路径不存在）与 403（无权限）。"""
    rows = db.scalars(
        select(Menu.path).where(Menu.deleted == 0, Menu.menu_type == "menu", Menu.path.isnot(None), Menu.path != "")
    ).all()
    return sorted(set(rows))


def _build_tree(menus: list[Menu]) -> list[dict]:
    nodes = {m.id: {**_menu_node(m), "children": []} for m in menus}
    roots = []
    for m in menus:
        node = nodes[m.id]
        parent = nodes.get(m.parent_id) if m.parent_id else None
        if parent is not None and parent is not node:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


def set_role_menus(db: Session, role_id: int, menu_ids: list[int]) -> None:
    db.execute(delete(RoleMenu).where(RoleMenu.role_id == role_id))
    for mid in menu_ids:
        db.add(RoleMenu(role_id=role_id, menu_id=mid))


def role_menu_ids(db: Session, role_id: int) -> list[int]:
    return list(db.scalars(select(RoleMenu.menu_id).where(RoleMenu.role_id == role_id, RoleMenu.deleted == 0)).all())


def set_user_roles(db: Session, user_id: int, role_ids: list[int]) -> None:
    db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    for rid in role_ids:
        db.add(UserRole(user_id=user_id, role_id=rid))


def user_role_ids(db: Session, user_id: int) -> list[int]:
    return list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id, UserRole.deleted == 0)).all())


def create_user_account(
    db: Session,
    *,
    username: str,
    name: str,
    password: str,
    dept_id: int | None = None,
    dept_name: str = "",
    mobile: str = "",
    email: str = "",
    role_ids: list[int] | None = None,
    employee_no: str = "",
    hire_date: date | None = None,
    status: str = "enabled",
    operator_id: int | None = None,
) -> User:
    """创建系统账号（`admin/router.py::create_user` 与 HR 入职生效共用）。

    **只 flush 不 commit** —— 事务边界在调用方（人事生效必须与档案变更同事务）。

    登录名重复直接抛 `ADMIN_USERNAME_EXISTS`，由调用方决定转成什么业务错误。
    """
    if db.scalar(select(User).where(User.username == username, User.deleted == 0)):
        raise BizException(R.ADMIN_USERNAME_EXISTS, f"登录名已存在：{username}")
    u = User(
        username=username,
        password_hash=hash_password(password),
        name=name,
        dept_id=dept_id,
        dept_name=dept_name,
        mobile=mobile,
        email=email,
        status=status,
        employee_no=employee_no,
        hire_date=hire_date,
        create_by=operator_id,
    )
    db.add(u)
    db.flush()
    sync_primary_membership(db, u)
    set_user_roles(db, u.id, role_ids or [])
    db.flush()
    return u


def upsert_prefs(db: Session, user_id: int, prefs: dict[str, str]) -> None:
    for k, v in prefs.items():
        row = db.scalar(
            select(UserPref).where(UserPref.user_id == user_id, UserPref.pref_key == k, UserPref.deleted == 0)
        )
        if row:
            row.pref_value = v
        else:
            db.add(UserPref(user_id=user_id, pref_key=k, pref_value=v))

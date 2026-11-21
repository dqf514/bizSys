"""站内通知（抄送）通用助手。

跨域场景（客户委托受理抄送业务负责人、人员备案抄送访客管理人员等）统一走这里：
按权限点找收件人 → 写 `sys_notify` → 审计留痕由调用方负责。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.admin.models import Menu, Notify, Role, RoleMenu, UserRole
from app.modules.auth.models import User


def users_with_perm(db: Session, perm: str) -> list[int]:
    """拥有指定权限点的启用用户 id（超管角色一并算上）。"""
    if not perm:
        return []
    rows = db.execute(
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .join(RoleMenu, RoleMenu.role_id == Role.id)
        .join(Menu, Menu.id == RoleMenu.menu_id)
        .where(
            Menu.permission == perm,
            Menu.deleted == 0,
            Role.deleted == 0,
            Role.status == "enabled",
            User.deleted == 0,
            User.status == "enabled",
        )
    ).all()
    ids = [r[0] for r in rows]
    # 超管（role_code=super）绕过权限点，直接补齐
    super_ids = db.execute(
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            Role.code == "super",
            Role.deleted == 0,
            User.deleted == 0,
            User.status == "enabled",
        )
    ).all()
    ids.extend(r[0] for r in super_ids)
    return list(dict.fromkeys(ids))


def notify(
    db: Session,
    user_ids: list[int],
    title: str,
    content: str,
    biz_type: str = "",
    biz_id: int | None = None,
    link: str = "",
    exclude_user_id: int | None = None,
) -> int:
    """写站内通知，返回实际写入条数（去重并剔除操作者本人）。"""
    targets = [u for u in dict.fromkeys(user_ids) if u and u != exclude_user_id]
    for uid in targets:
        db.add(
            Notify(
                user_id=uid,
                title=title,
                content=content,
                biz_type=biz_type,
                biz_id=biz_id,
                link=link,
            )
        )
    db.flush()
    return len(targets)

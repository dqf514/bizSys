"""系统管理：角色/菜单/字典/编号规则/审计/偏好。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class Role(BaseModel):
    __tablename__ = "sys_role"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="角色编码")
    name: Mapped[str] = mapped_column(String(64), comment="角色名")
    data_scope: Mapped[str] = mapped_column(String(16), default="all", comment="all/dept/self")
    status: Mapped[str] = mapped_column(String(16), default="enabled")
    remark: Mapped[str] = mapped_column(String(255), default="")

    menus = relationship("Menu", secondary="sys_role_menu", viewonly=True, lazy="selectin")


class Menu(BaseModel):
    __tablename__ = "sys_menu"

    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(64), comment="路由名/组件键")
    title_key: Mapped[str] = mapped_column(String(128), default="", comment="i18n 键")
    path: Mapped[str] = mapped_column(String(255), default="")
    component_key: Mapped[str] = mapped_column(String(128), default="", comment="前端组件键")
    icon: Mapped[str] = mapped_column(String(64), default="")
    permission: Mapped[str] = mapped_column(String(64), default="", index=True, comment="权限码")
    menu_type: Mapped[str] = mapped_column(String(16), default="menu", comment="dir/menu/button")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[int] = mapped_column(Integer, default=1)


class UserRole(BaseModel):
    __tablename__ = "sys_user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id"), index=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_role.id"), index=True)


class RoleMenu(BaseModel):
    __tablename__ = "sys_role_menu"
    __table_args__ = (UniqueConstraint("role_id", "menu_id"),)

    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_role.id"), index=True)
    menu_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_menu.id"), index=True)


class DictType(BaseModel):
    __tablename__ = "sys_dict_type"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    remark: Mapped[str] = mapped_column(String(255), default="")

    items = relationship(
        "DictItem",
        primaryjoin="DictType.code == foreign(DictItem.dict_type_code)",
        lazy="selectin",
        viewonly=True,
    )


class DictItem(BaseModel):
    __tablename__ = "sys_dict_item"
    __table_args__ = (UniqueConstraint("dict_type_code", "value"),)

    dict_type_code: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(128), comment="中文标签")
    label_en: Mapped[str] = mapped_column(String(128), default="", comment="英文标签")
    value: Mapped[str] = mapped_column(String(64))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="enabled")
    extra: Mapped[str] = mapped_column(String(255), default="")


class NumberRule(BaseModel):
    __tablename__ = "sys_number_rule"

    biz_type: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="task/sample/...")
    prefix: Mapped[str] = mapped_column(String(16), default="", comment="前缀")
    date_format: Mapped[str] = mapped_column(String(16), default="", comment="yyyyMMdd 等，空=不带日期")
    seq_len: Mapped[int] = mapped_column(Integer, default=4)
    reset_cycle: Mapped[str] = mapped_column(String(8), default="none", comment="none/daily/monthly")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    example: Mapped[str] = mapped_column(String(64), default="", comment="预览样例")


class NumberSeq(BaseModel):
    """Redis INCR 双写兜底（防 Redis 丢序列）。"""

    __tablename__ = "sys_number_seq"
    __table_args__ = (UniqueConstraint("rule_id", "period_key"),)

    rule_id: Mapped[int] = mapped_column(BigInteger)
    period_key: Mapped[str] = mapped_column(String(16), comment="20261009 / 202610 / -")
    value: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(BaseModel):
    __tablename__ = "sys_audit_log"

    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(32))
    biz_type: Mapped[str] = mapped_column(String(32), default="", index=True)
    biz_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(32), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")


# audit.record 里的别名
SysAuditLog = AuditLog


class LoginLog(BaseModel):
    __tablename__ = "sys_login_log"

    username: Mapped[str] = mapped_column(String(64), index=True)
    success: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(128), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    ua: Mapped[str] = mapped_column(String(255), default="")


class UserPref(BaseModel):
    __tablename__ = "sys_user_pref"
    __table_args__ = (UniqueConstraint("user_id", "pref_key"),)

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    pref_key: Mapped[str] = mapped_column(String(32))
    pref_value: Mapped[str] = mapped_column(String(255), default="")


class Dept(BaseModel):
    """部门/业务板块。"""

    __tablename__ = "sys_dept"

    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(32), default="", unique=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="enabled")


class Notify(BaseModel):
    """站内通知/待办提醒。"""

    __tablename__ = "sys_notify"

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    biz_type: Mapped[str] = mapped_column(String(32), default="")
    biz_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    link: Mapped[str] = mapped_column(String(255), default="")
    read_flag: Mapped[int] = mapped_column(Integer, default=0, index=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

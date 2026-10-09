"""用户账号。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class User(BaseModel):
    __tablename__ = "sys_user"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="登录名")
    password_hash: Mapped[str] = mapped_column(String(128), comment="bcrypt")
    name: Mapped[str] = mapped_column(String(64), default="", comment="姓名")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="部门/业务板块")
    dept_name: Mapped[str] = mapped_column(String(128), default="", comment="部门名冗余")
    mobile: Mapped[str] = mapped_column(String(32), default="", comment="手机")
    email: Mapped[str] = mapped_column(String(128), default="", comment="邮箱")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True, comment="enabled/disabled/locked")
    wecom_userid: Mapped[str] = mapped_column(String(64), default="", comment="企微预留")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    roles = relationship("Role", secondary="sys_user_role", viewonly=True, lazy="selectin")

    @property
    def role_codes(self) -> list[str]:
        return [r.code for r in self.roles]

    @property
    def perm_codes(self) -> list[str]:
        perms: set[str] = set()
        for role in self.roles:
            for menu in role.menus:
                if menu.permission:
                    perms.add(menu.permission)
        return sorted(perms)

"""用户账号。"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, String
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
    # ---- 批次B 个人档案：组织字段（管理员维护，本人只读）；avatar 为 uploads 相对路径 ----
    employee_no: Mapped[str] = mapped_column(String(32), default="", comment="工号（组织统一管理）")
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="入职日期")
    job_level: Mapped[str] = mapped_column(String(32), default="", comment="职级（预留，对接 HR 系统）")
    avatar: Mapped[str] = mapped_column(String(255), default="", comment="头像文件相对路径")

    roles = relationship("Role", secondary="sys_user_role", viewonly=True, lazy="selectin")

    @property
    def _active_roles(self) -> list:
        """仅启用且未删除的角色参与授权（与菜单树过滤行为一致，见 admin/service.menu_tree_for_user）。"""
        return [r for r in self.roles if r.deleted == 0 and r.status == "enabled"]

    @property
    def role_codes(self) -> list[str]:
        return [r.code for r in self._active_roles]

    @property
    def perm_codes(self) -> list[str]:
        perms: set[str] = set()
        for role in self._active_roles:
            for menu in role.menus:
                if menu.permission:
                    perms.add(menu.permission)
        return sorted(perms)


class UserEmergencyContact(BaseModel):
    """紧急联系人（用户自助维护，多条）。"""

    __tablename__ = "user_emergency_contact"

    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属用户")
    name: Mapped[str] = mapped_column(String(64), comment="姓名")
    relation: Mapped[str] = mapped_column(String(32), default="", comment="关系")
    phone: Mapped[str] = mapped_column(String(32), default="", comment="电话")
    remark: Mapped[str] = mapped_column(String(255), default="", comment="备注")


class UserBankAccount(BaseModel):
    """银行卡（用户自助维护，多条）。

    卡号接口默认脱敏（仅后 4 位），完整查看/增删改均需 step-up 二次验证；
    审计日志只记录后 4 位，不落完整卡号明文。
    """

    __tablename__ = "user_bank_account"

    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属用户")
    bank_name: Mapped[str] = mapped_column(String(64), comment="开户行")
    card_no: Mapped[str] = mapped_column(String(32), comment="卡号")
    holder_name: Mapped[str] = mapped_column(String(64), default="", comment="持卡人")

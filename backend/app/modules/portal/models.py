"""合作方门户账号：独立于内部 sys_user 的认证体系。"""

from datetime import datetime

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class PartnerUser(BaseModel):
    """门户合作方账号。状态机：pending（注册待审）→ enabled / rejected；enabled → disabled。

    注册后必须内部审核通过（enabled）才能登录；customer_id 绑定往来单位后，
    定标生成采购合同时以该往来单位为供应商。
    """

    __tablename__ = "partner_user"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    company_name: Mapped[str] = mapped_column(String(255), index=True, comment="公司名")
    contact_name: Mapped[str] = mapped_column(String(64), default="", comment="联系人")
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    account_type: Mapped[str] = mapped_column(
        String(16), default="supplier", index=True, comment="customer 客户自助 / supplier 供应商投标"
    )
    perm_scope: Mapped[str] = mapped_column(
        String(64), default="tender", comment="权限范围（逗号分隔）：tender 招投标 / entrust 在线委托 / staff 人员备案"
    )
    manager_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="归属客户经理 sys_user.id"
    )
    manager_name: Mapped[str] = mapped_column(String(64), default="")
    staff_limit: Mapped[int] = mapped_column(Integer, default=5, comment="可登记的外来人员名额上限")
    customer_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="绑定往来单位 crm_customer.id"
    )
    review_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    review_name: Mapped[str] = mapped_column(String(64), default="")
    review_at: Mapped[datetime | None] = mapped_column(nullable=True)
    review_comment: Mapped[str] = mapped_column(String(500), default="")
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)

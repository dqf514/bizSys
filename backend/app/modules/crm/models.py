"""CRM 客户表。"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class Customer(BaseModel):
    __tablename__ = "crm_customer"

    customer_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="客户编号 CCxxxxx")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="客户名称")
    code: Mapped[str] = mapped_column(String(64), default="", comment="客户代码")
    customer_type: Mapped[str] = mapped_column(String(32), default="", comment="字典 customer_type")
    tax_no: Mapped[str] = mapped_column(String(64), default="", index=True, comment="纳税识别号")
    grade: Mapped[str] = mapped_column(String(16), default="", comment="字典 customer_grade")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True)
    country: Mapped[str] = mapped_column(String(64), default="")
    province: Mapped[str] = mapped_column(String(64), default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    bank_name: Mapped[str] = mapped_column(String(128), default="", comment="开户行")
    bank_account: Mapped[str] = mapped_column(String(64), default="", comment="银行账号")
    pay_org: Mapped[str] = mapped_column(String(128), default="", comment="付款单位")
    contact_person: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="联系人")
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="联系电话")
    license_file_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="营业执照附件ID")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

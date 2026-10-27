"""CRM 客户表。"""

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class Customer(BaseModel):
    """往来单位：客户/供应商统一档案（partner_type 区分，默认 customer）。"""

    __tablename__ = "crm_customer"

    customer_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="客户编号 CCxxxxx")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="客户名称")
    partner_type: Mapped[str] = mapped_column(
        String(16), default="customer", index=True, comment="customer/supplier/both"
    )
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
    supply_category: Mapped[str] = mapped_column(String(32), default="", comment="字典 supply_category（供应商）")
    supplier_rating: Mapped[str] = mapped_column(String(8), default="", comment="复用字典 customer_grade（供应商评级）")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class PartnerContact(BaseModel):
    """往来单位联系人。is_primary 每单位最多一个（置主时同事务清除其他）。"""

    __tablename__ = "crm_partner_contact"

    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crm_customer.id"), index=True)
    name: Mapped[str] = mapped_column(String(64), comment="姓名")
    position: Mapped[str] = mapped_column(String(64), default="", comment="职务")
    phone: Mapped[str] = mapped_column(String(32), default="", comment="电话")
    email: Mapped[str] = mapped_column(String(128), default="", comment="邮箱")
    is_primary: Mapped[int] = mapped_column(default=0, comment="主要联系人 0/1")
    remark: Mapped[str] = mapped_column(String(500), default="")


class PartnerAttachment(BaseModel):
    """往来单位附件（营业执照/资质证明等集中管理，字典 partner_attachment_category）。"""

    __tablename__ = "crm_partner_attachment"

    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("crm_customer.id"), index=True)
    category: Mapped[str] = mapped_column(String(32), default="other", comment="字典 partner_attachment_category")
    file_name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    content_type: Mapped[str] = mapped_column(String(128), default="")
    path: Mapped[str] = mapped_column(String(255), comment="相对 upload_dir 的路径")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="说明")

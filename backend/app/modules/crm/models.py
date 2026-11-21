"""CRM 客户表。"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, String, Text
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


class PartnerStaff(BaseModel):
    """客户方人员档案（B2 外来试验人员 / 跟踪支持人员登记备案）。

    客户通过门户自助登记 → 客户经理审核 → 抄送业务负责人与访客管理人员，
    审核通过后即可作为访客主数据（B3 访客系统据此预登记访客档案与通行凭证）。
    状态机：pending → approved / rejected；approved → disabled。
    """

    __tablename__ = "crm_partner_staff"

    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    name: Mapped[str] = mapped_column(String(64), index=True, comment="姓名")
    gender: Mapped[str] = mapped_column(String(8), default="", comment="male/female")
    id_no: Mapped[str] = mapped_column(String(64), default="", comment="证件号（一人一号，通行凭证依据）")
    position: Mapped[str] = mapped_column(String(64), default="", comment="职务")
    phone: Mapped[str] = mapped_column(String(32), default="", index=True)
    email: Mapped[str] = mapped_column(String(128), default="")
    plate_no: Mapped[str] = mapped_column(String(32), default="", comment="车牌号（车牌凭证）")
    company: Mapped[str] = mapped_column(String(255), default="", comment="所属单位（默认客户名）")
    staff_type: Mapped[str] = mapped_column(
        String(32), default="", index=True, comment="字典 partner_staff_type：试验人员/支持人员/见证专家/厂商工程师"
    )
    visit_purpose: Mapped[str] = mapped_column(String(255), default="", comment="来访事由")
    plan_visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    nda_signed: Mapped[int] = mapped_column(Integer, default=0, comment="是否已签 NDA（未签不放行）")
    visit_perm: Mapped[str] = mapped_column(String(255), default="", comment="可进入区域 id 列表（逗号分隔）")
    source: Mapped[str] = mapped_column(
        String(16), default="portal", index=True, comment="portal 客户自助 / internal 代登记"
    )
    applicant_account_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    applicant_name: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    review_by: Mapped[int | None] = mapped_column(BigInteger)
    review_name: Mapped[str] = mapped_column(String(64), default="")
    review_at: Mapped[datetime | None] = mapped_column(nullable=True)
    review_comment: Mapped[str] = mapped_column(String(500), default="")
    biz_owner_id: Mapped[int | None] = mapped_column(BigInteger, index=True, comment="业务负责人（审核后抄送）")
    biz_owner_name: Mapped[str] = mapped_column(String(64), default="")
    notify_visitor_admin: Mapped[int] = mapped_column(
        Integer, default=1, comment="是否抄送访客管理人员并勾选访客系统权限"
    )
    visitor_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="访客档案 id（B3 预登记）"
    )
    remark: Mapped[str] = mapped_column(String(500), default="")

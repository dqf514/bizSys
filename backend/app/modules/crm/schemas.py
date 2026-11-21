"""CRM 入参模型。"""

from pydantic import Field

from app.core.schemas import CamelModel, OptionalDate


class CustomerIn(CamelModel):
    name: str = Field(..., min_length=1, max_length=128)
    partner_type: str = Field("customer", pattern="^(customer|supplier|both)$")
    code: str = Field("", max_length=64)
    customer_type: str = Field("", max_length=32)
    tax_no: str = Field("", max_length=64)
    grade: str = Field("", max_length=16)
    status: str = Field("enabled", pattern="^(enabled|disabled)$")
    country: str = Field("", max_length=64)
    province: str = Field("", max_length=64)
    city: str = Field("", max_length=64)
    address: str = Field("", max_length=255)
    bank_name: str = Field("", max_length=128)
    bank_account: str = Field("", max_length=64)
    pay_org: str = Field("", max_length=128)
    contact_person: str = Field("", max_length=64)
    contact_phone: str = Field("", max_length=32)
    license_file_id: str | None = None
    supply_category: str = Field("", max_length=32)
    supplier_rating: str = Field("", max_length=8)
    remark: str = Field("", max_length=2000)


class ContactIn(CamelModel):
    name: str = Field(..., min_length=1, max_length=64)
    position: str = Field("", max_length=64)
    phone: str = Field("", max_length=32)
    email: str = Field("", max_length=128)
    is_primary: bool = False
    remark: str = Field("", max_length=500)


class PartnerStaffIn(CamelModel):
    """客户方人员档案（B2 外来试验人员 / 跟踪支持人员）。"""

    name: str = Field(..., min_length=1, max_length=64)
    customer_id: int | None = None
    customer_name: str = Field("", max_length=128)
    gender: str = Field("", max_length=8)
    id_no: str = Field("", max_length=64)
    position: str = Field("", max_length=64)
    phone: str = Field("", max_length=32)
    email: str = Field("", max_length=128)
    plate_no: str = Field("", max_length=32)
    company: str = Field("", max_length=255)
    staff_type: str = Field("", max_length=32)
    visit_purpose: str = Field("", max_length=255)
    plan_visit_date: OptionalDate = None
    nda_signed: bool = False
    remark: str = Field("", max_length=500)


class PartnerStaffReviewIn(CamelModel):
    """客户方人员备案审核：approve/reject，可同时勾选访客系统权限与业务负责人。"""

    action: str = Field(..., pattern="^(approve|reject)$")
    comment: str = Field("", max_length=500)
    biz_owner_id: int | None = None
    biz_owner_name: str = Field("", max_length=64)
    visit_perm: str | None = Field(default=None, max_length=255)
    nda_signed: bool | None = None


class CustomerAccountReviewIn(CamelModel):
    """客户自助账号审核：approve/reject，审核通过时绑定往来单位与客户经理。"""

    action: str = Field(..., pattern="^(approve|reject)$")
    comment: str = Field("", max_length=500)
    customer_id: int | None = None
    manager_id: int | None = None
    manager_name: str = Field("", max_length=64)
    perm_scope: str | None = Field(default=None, max_length=64)
    staff_limit: int | None = Field(default=None, ge=0, le=200)

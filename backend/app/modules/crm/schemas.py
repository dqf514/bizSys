"""CRM 入参模型。"""

from pydantic import Field

from app.core.schemas import CamelModel


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

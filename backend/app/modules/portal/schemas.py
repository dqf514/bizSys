"""门户入参模型。"""

from pydantic import Field

from app.core.schemas import CamelModel


class PortalRegisterIn(CamelModel):
    username: str = Field(min_length=4, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=64)
    company_name: str = Field(min_length=2, max_length=255)
    contact_name: str = Field(default="", max_length=64)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=128)


class PortalLoginIn(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class PartnerReviewIn(CamelModel):
    approve: bool
    comment: str = Field(default="", max_length=500)
    customer_id: int | None = None  # 审核通过时可一并绑定往来单位

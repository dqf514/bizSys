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


class PartnerCreateIn(CamelModel):
    """管理侧新建门户账号：直接启用，可指定绑定往来单位；密码策略同注册（≥8 位）。"""

    username: str = Field(min_length=4, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=64)
    company_name: str = Field(min_length=2, max_length=255)
    contact_name: str = Field(default="", max_length=64)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=128)
    customer_id: int | None = None


class PartnerUpdateIn(CamelModel):
    """编辑资料；customer_id 出现在 payload 中即改绑/解绑（null=解绑），缺省不动。"""

    company_name: str = Field(min_length=2, max_length=255)
    contact_name: str = Field(default="", max_length=64)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=128)
    customer_id: int | None = None


class PartnerPasswordResetIn(CamelModel):
    """重置门户账号密码：缺省由服务端生成一次性随机密码（响应仅展示一次）。"""

    password: str | None = Field(default=None, min_length=8, max_length=64)

"""销售系统接口 Schemas（报价模板 + 报价单 + AI 生成）。"""

from datetime import date
from decimal import Decimal

from pydantic import Field, field_validator

from app.core.schemas import CamelModel

# 明细列白名单（模板 itemColumns 的 key）
ITEM_COLUMN_KEYS = ("spec", "unit", "remark")


class ItemColumnIn(CamelModel):
    key: str = Field(pattern=r"^(spec|unit|remark)$")
    label: str = Field(default="", max_length=32)  # 列头自定义（空=默认文案）
    visible: bool = True


class LayoutIn(CamelModel):
    """模板版式：公司抬头/报价说明/付款条款/页脚/默认有效期天数/明细列配置。"""

    header_html: str = Field(default="", max_length=4000)
    intro_html: str = Field(default="", max_length=8000)
    terms_html: str = Field(default="", max_length=8000)
    footer_html: str = Field(default="", max_length=4000)
    valid_days: int = Field(default=30, ge=0, le=3650)
    item_columns: list[ItemColumnIn] = Field(default_factory=list)


class TemplateIn(CamelModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=128)
    sort: int = Field(default=0, ge=0, le=9999)
    layout: LayoutIn = Field(default_factory=LayoutIn)


class QuotationItemIn(CamelModel):
    name: str = Field(min_length=1, max_length=255)
    spec: str = Field(default="", max_length=255)
    unit: str = Field(default="", max_length=16)
    qty: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    remark: str = Field(default="", max_length=255)


class QuotationIn(CamelModel):
    """报价单新建/编辑入参；金额由服务端按明细重算，前端提交合计仅供参考不入库。"""

    title: str = Field(min_length=1, max_length=255)
    customer_id: int
    contact_name: str = Field(default="", max_length=64)
    contact_phone: str = Field(default="", max_length=32)
    contact_email: str = Field(default="", max_length=128)
    template_id: int | None = None
    requirement: str = Field(default="", max_length=4000)
    intro_html: str = Field(default="", max_length=8000)
    terms_html: str = Field(default="", max_length=8000)
    tax_rate: Decimal = Field(default=Decimal("6"), ge=0, le=100)
    valid_until: date | None = None
    auto_send: bool = False
    ai_meta: str = Field(default="", max_length=2000)  # AI 生成来源/回退原因 JSON（前端透传）
    items: list[QuotationItemIn] = Field(default_factory=list, max_length=200)

    @field_validator("contact_email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        if v and ("@" not in v or " " in v):
            raise ValueError("联系人邮箱格式不正确")
        return v


class AiGenerateIn(CamelModel):
    """AI 生成入参：可挂已有草稿（quotationId）或未保存的即时生成（customerId+templateId+requirement）。"""

    quotation_id: int | None = None
    customer_id: int | None = None
    template_id: int | None = None
    requirement: str = Field(min_length=1, max_length=4000)


class SendIn(CamelModel):
    channel: str = Field(pattern=r"^(email|print|download)$")
    recipient: str = Field(default="", max_length=255)  # email 通道必填（默认联系人邮箱）


class FeedbackIn(CamelModel):
    action: str = Field(pattern=r"^(accept|decline)$")
    note: str = Field(default="", max_length=500)


class SubmitIn(CamelModel):
    comment: str = Field(default="", max_length=500)

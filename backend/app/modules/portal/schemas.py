"""门户入参模型。"""

from datetime import datetime

from pydantic import Field

from app.core.schemas import CamelModel, OptionalDate


class PortalRegisterIn(CamelModel):
    username: str = Field(min_length=4, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=64)
    company_name: str = Field(min_length=2, max_length=255)
    contact_name: str = Field(default="", max_length=64)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=128)
    # B2 客户自助：账号类型（supplier 供应商投标 / customer 客户自助下单）
    company_type: str = Field(default="supplier", pattern="^(customer|supplier)$")


class PortalLoginIn(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class PortalRefreshIn(CamelModel):
    """门户 token 刷新（F6）：refresh token 一次性轮换。"""

    refresh_token: str = Field(min_length=1, max_length=1024)


class PortalAccountUpdateIn(CamelModel):
    """门户自助改资料（**不含** customer_id —— 改绑往来单位必须走内部审核）。"""

    company_name: str = Field(min_length=2, max_length=255)
    contact_name: str = Field(default="", max_length=64)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=128)


class PortalPasswordIn(CamelModel):
    """门户自助改密码（需原密码）。"""

    old_password: str = Field(default="", max_length=64)
    new_password: str = Field(min_length=8, max_length=64)


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


class PortalStaffIn(CamelModel):
    """门户侧外来试验人员登记备案（B2）。"""

    name: str = Field(min_length=1, max_length=64)
    gender: str = Field(default="", max_length=8)
    id_no: str = Field(default="", max_length=64)
    position: str = Field(default="", max_length=64)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=128)
    plate_no: str = Field(default="", max_length=32)
    staff_type: str = Field(default="", max_length=32)
    visit_purpose: str = Field(default="", max_length=255)
    plan_visit_date: OptionalDate = None
    nda_signed: bool = False


class PortalVisitIn(CamelModel):
    """门户侧访客预约（F6）：合作方提交来访申请 → 内部审批 → 通行凭证 → 自助签到。"""

    visitor_name: str = Field(min_length=1, max_length=64)
    visitor_company: str = Field(default="", max_length=128)
    visitor_type: str = Field(default="customer", max_length=32)
    id_no: str = Field(default="", max_length=64)
    phone: str = Field(default="", max_length=32)
    plate_no: str = Field(default="", max_length=32)
    host_user_id: int = Field(..., ge=1, description="被访人（内部员工）id")
    zone_ids: list[int] = Field(default_factory=list, description="申请进入的区域 id 列表")
    purpose: str = Field(default="", max_length=255)
    plan_start: datetime | None = None
    plan_end: datetime | None = None
    escort_names: str = Field(default="", max_length=255)
    nda_signed: bool = Field(default=False, description="已确认签署保密协议（敏感区域必填）")
    remark: str = Field(default="", max_length=500)


class PortalVisitCancelIn(CamelModel):
    remark: str = Field(default="", max_length=255)


class PortalVisitCheckIn(CamelModel):
    method: str = Field(default="qrcode", max_length=16)
    device_id: str = Field(default="", max_length=64)

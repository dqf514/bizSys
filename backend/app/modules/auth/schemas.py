"""鉴权接口入参/出参。"""

from pydantic import BaseModel, Field

from app.core.schemas import CamelModel


class LoginIn(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(CamelModel):
    refresh_token: str


class PasswordIn(CamelModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    dept_id: int | None = None
    dept_name: str = ""
    email: str = ""
    mobile: str = ""
    roles: list[str] = []
    perms: list[str] = []
    prefs: dict[str, str] = {}

    model_config = {"from_attributes": True}


class LoginOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    user: UserOut


class MeOut(UserOut):
    menus: list = []


# ---------------- 批次B 个人档案 ----------------


class StepUpIn(CamelModel):
    """二次身份验证。当前仅 method=password；method 预留 sms/email（验证码登录复用同一 step-up 通道）。"""

    password: str = Field(min_length=1, max_length=128)
    method: str = Field(default="password", max_length=16)


class ProfilePatchIn(CamelModel):
    """自助可编辑字段：电话/邮箱（变更需 step-up）。

    邮箱/电话作为后期邮箱验证码/短信验证码登录的标识预留，故做格式与唯一性校验。
    """

    mobile: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=128)


class ContactIn(CamelModel):
    name: str = Field(min_length=1, max_length=64)
    relation: str = Field(default="", max_length=32)
    phone: str = Field(default="", max_length=32)
    remark: str = Field(default="", max_length=255)


class BankAccountIn(CamelModel):
    bank_name: str = Field(min_length=1, max_length=64)
    card_no: str = Field(min_length=8, max_length=30, pattern=r"^\d+$")
    holder_name: str = Field(min_length=1, max_length=64)

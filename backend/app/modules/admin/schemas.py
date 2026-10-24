"""系统管理接口 Schemas。"""

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import CamelModel, OptionalDate


class UserIn(CamelModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(default="", max_length=128)
    name: str = ""
    dept_id: int | None = None
    dept_name: str = ""
    mobile: str = ""
    email: str = ""
    status: str = "enabled"
    role_ids: list[int] = []
    # 批次B 组织字段（管理员维护，本人只读；职级预留对接 HR 系统）
    employee_no: str = Field(default="", max_length=32)
    hire_date: OptionalDate = None
    job_level: str = Field(default="", max_length=32)


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    dept_id: int | None = None
    dept_name: str = ""
    mobile: str = ""
    email: str = ""
    status: str
    roles: list[str] = []
    create_time: str = ""

    model_config = {"from_attributes": True}


class RoleIn(CamelModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    data_scope: str = "all"
    status: str = "enabled"
    remark: str = ""

    @field_validator("data_scope")
    @classmethod
    def _scope_known(cls, v: str) -> str:
        if v not in ("all", "dept", "self"):
            raise ValueError(f"未知数据范围：{v}")
        return v

    @field_validator("status")
    @classmethod
    def _status_known(cls, v: str) -> str:
        if v not in ("enabled", "disabled"):
            raise ValueError(f"未知状态：{v}")
        return v


class RoleOut(BaseModel):
    id: int
    code: str
    name: str
    data_scope: str
    status: str
    remark: str = ""
    menu_ids: list[int] = []

    model_config = {"from_attributes": True}


class MenuIn(CamelModel):
    parent_id: int | None = None
    name: str = Field(min_length=1, max_length=64)
    title_key: str = ""
    path: str = ""
    component_key: str = ""
    icon: str = ""
    permission: str = ""
    menu_type: str = "menu"
    sort: int = 0
    visible: int = 1


class DictTypeIn(CamelModel):
    code: str = Field(min_length=2, max_length=64)
    name: str
    remark: str = ""


class DictItemIn(CamelModel):
    dict_type_code: str
    label: str
    label_en: str = ""
    value: str
    sort: int = 0
    status: str = "enabled"
    extra: str = ""


class NumberRuleIn(CamelModel):
    biz_type: str = Field(min_length=2, max_length=32)
    category_key: str = Field("", max_length=64)
    prefix: str = ""
    date_format: str = Field("", max_length=16)
    year_digits: int = Field(0)
    month_digits: int = Field(0)
    day_digits: int = Field(0)
    seq_len: int = Field(4, ge=1, le=10)
    seq_start: int = Field(1, ge=0)
    separator: str = Field("", max_length=4)
    reset_cycle: str = "none"
    enabled: int = 1
    example: str = ""

    @field_validator("year_digits")
    @classmethod
    def _year_digits(cls, v: int) -> int:
        if v not in (0, 2, 4):
            raise ValueError("year_digits 仅支持 0/2/4")
        return v

    @field_validator("month_digits", "day_digits")
    @classmethod
    def _md_digits(cls, v: int) -> int:
        if v not in (0, 2):
            raise ValueError("month_digits/day_digits 仅支持 0/2")
        return v

    @field_validator("reset_cycle")
    @classmethod
    def _reset_cycle(cls, v: str) -> str:
        if v not in ("none", "daily", "monthly", "yearly"):
            raise ValueError("reset_cycle 仅支持 none/daily/monthly/yearly")
        return v


class NumberRulePreviewIn(NumberRuleIn):
    biz_type: str = Field("_preview", min_length=2, max_length=32)


class NumberSeqResetIn(CamelModel):
    value: int = Field(0, ge=0)


class PrefIn(CamelModel):
    prefs: dict[str, str] = {}


class RoleMenusIn(CamelModel):
    menu_ids: list[int] = []


class ResetPasswordIn(CamelModel):
    password: str = Field(min_length=8, max_length=128)


class DeptIn(CamelModel):
    parent_id: int | None = None
    name: str
    code: str = ""
    sort: int = 0
    status: str = "enabled"


class DeptMemberIn(CamelModel):
    """部门任职成员：is_primary=1 时同步为该用户主部门（user.dept_id 冗余同步）。"""

    user_id: int
    is_primary: int = 0
    is_leader: int = 0


class DeptMembersIn(CamelModel):
    members: list[DeptMemberIn] = []

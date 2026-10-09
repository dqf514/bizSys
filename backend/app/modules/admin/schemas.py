"""系统管理接口 Schemas。"""

from pydantic import BaseModel, Field


class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(default="", max_length=128)
    name: str = ""
    dept_id: int | None = None
    dept_name: str = ""
    mobile: str = ""
    email: str = ""
    status: str = "enabled"
    role_ids: list[int] = []


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


class RoleIn(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    data_scope: str = "all"
    status: str = "enabled"
    remark: str = ""


class RoleOut(BaseModel):
    id: int
    code: str
    name: str
    data_scope: str
    status: str
    remark: str = ""
    menu_ids: list[int] = []

    model_config = {"from_attributes": True}


class MenuIn(BaseModel):
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


class DictTypeIn(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str
    remark: str = ""


class DictItemIn(BaseModel):
    dict_type_code: str
    label: str
    label_en: str = ""
    value: str
    sort: int = 0
    status: str = "enabled"
    extra: str = ""


class NumberRuleIn(BaseModel):
    biz_type: str = Field(min_length=2, max_length=32)
    prefix: str = ""
    date_format: str = ""
    seq_len: int = Field(4, ge=1, le=10)
    reset_cycle: str = "none"
    enabled: int = 1
    example: str = ""


class PrefIn(BaseModel):
    prefs: dict[str, str] = {}


class RoleMenusIn(BaseModel):
    menu_ids: list[int] = []


class ResetPasswordIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class DeptIn(BaseModel):
    parent_id: int | None = None
    name: str
    code: str = ""
    sort: int = 0
    status: str = "enabled"

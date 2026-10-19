"""OA 模块接口 Schemas。"""

from pydantic import Field, field_validator

from app.core.schemas import CamelModel

FIELD_TYPES = (
    "text",
    "textarea",
    "number",
    "money",
    "date",
    "daterange",
    "select",
    "radio",
    "checkbox",
    "file",
    "user",
)
# 可作为流程变量注入 instance.variables 的标量类型（条件分支用）
EXPOSABLE_TYPES = ("text", "number", "money", "date", "select", "radio", "user")
OPTION_TYPES = ("select", "radio", "checkbox")


class FormFieldIn(CamelModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    label: str = Field(min_length=1, max_length=64)
    type: str
    required: bool = False
    options: list[str] = []
    placeholder: str = ""
    maxlength: int | None = Field(None, ge=1, le=5000)
    expose_variable: bool = False

    @field_validator("type")
    @classmethod
    def _type_known(cls, v: str) -> str:
        if v not in FIELD_TYPES:
            raise ValueError(f"未知字段类型：{v}")
        return v


class FormIn(CamelModel):
    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(default="", max_length=32)
    icon: str = Field(default="", max_length=64)
    sort: int = 0
    description: str = Field(default="", max_length=512)
    fields: list[FormFieldIn] = []
    flow_definition_id: int | None = None


class ApplyIn(CamelModel):
    form_id: int
    data: dict = {}


class TerminateIn(CamelModel):
    comment: str = Field(default="", max_length=500)


class ReassignIn(CamelModel):
    task_id: int
    to_user_id: int
    comment: str = Field(default="", max_length=500)


class RestartIn(CamelModel):
    seq: int = Field(ge=1)
    comment: str = Field(default="", max_length=500)

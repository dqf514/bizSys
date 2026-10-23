"""OA 模块接口 Schemas。"""

from typing import Any

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
    # 批次4 扩展：全站数据选择 + 布局控件
    "resource",
    "divider",
    "text_block",
)
# 可作为流程变量注入 instance.variables 的标量类型（条件分支用）
EXPOSABLE_TYPES = ("text", "number", "money", "date", "select", "radio", "user")
OPTION_TYPES = ("select", "radio", "checkbox")
# 布局控件：不占数据位（key 允许为空）
LAYOUT_TYPES = ("divider", "text_block")
# 全站资源控件可选资源类型
RESOURCE_TYPES = ("customer", "contract", "task", "report", "dept", "user", "oa_instance")

CONDITION_OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "contains", "empty", "not_empty")


class ConditionRule(CamelModel):
    """单条条件：{field: 控件key, op: 比较符, value: 比较值（empty/not_empty 忽略）}。"""

    field: str = Field(min_length=1, max_length=64)
    op: str = "eq"
    value: str = Field(default="", max_length=255)

    @field_validator("op")
    @classmethod
    def _op_known(cls, v: str) -> str:
        if v not in CONDITION_OPS:
            raise ValueError(f"未知比较符：{v}")
        return v


class ConditionGroup(CamelModel):
    """条件组：rules 按 logic（and/or）组合。"""

    logic: str = "and"
    rules: list[ConditionRule] = []

    @field_validator("logic")
    @classmethod
    def _logic_known(cls, v: str) -> str:
        if v not in ("and", "or"):
            raise ValueError(f"未知组合逻辑：{v}")
        return v


class FieldMapping(CamelModel):
    """资源控件带出映射：{from: 资源字段key, to: 本表单控件key}。"""

    from_key: str = Field(min_length=1, max_length=64, alias="from")
    to: str = Field(min_length=1, max_length=64)


class FormFieldIn(CamelModel):
    key: str = Field(default="", max_length=64, pattern=r"^([a-zA-Z_][a-zA-Z0-9_]*)?$")
    label: str = Field(min_length=1, max_length=64)
    type: str
    required: bool = False
    options: list[str] = []
    placeholder: str = ""
    maxlength: int | None = Field(None, ge=1, le=5000)
    expose_variable: bool = False
    # ---- 批次4 扩展（全部可选，存量 schema 向后兼容） ----
    span: int | None = Field(None, ge=1, le=24)  # 栅格宽度（12=半行 / 24=整行）
    description: str = Field(default="", max_length=255)  # 控件说明
    default_value: Any = None
    show_when: ConditionGroup | None = None  # 条件显示：不满足则隐藏（提交时忽略）
    required_when: ConditionGroup | None = None  # 条件必填：满足时按必填校验
    readonly_when: ConditionGroup | None = None  # 条件只读：满足时禁用编辑（前端约束）
    options_source: str = "manual"  # manual 手工选项 / dict 字典数据源
    dict_type: str = Field(default="", max_length=64)
    cascade: dict | None = None  # 级联过滤：{parent: 父控件key, map: {父值: [可选选项]}}
    resource: str = Field(default="", max_length=32)  # type=resource 时的资源类型
    mappings: list[FieldMapping] = []  # 资源选中后的带出字段映射

    @field_validator("type")
    @classmethod
    def _type_known(cls, v: str) -> str:
        if v not in FIELD_TYPES:
            raise ValueError(f"未知字段类型：{v}")
        return v

    @field_validator("options_source")
    @classmethod
    def _source_known(cls, v: str) -> str:
        if v not in ("manual", "dict"):
            raise ValueError(f"未知选项数据源：{v}")
        return v

    @field_validator("resource")
    @classmethod
    def _resource_known(cls, v: str) -> str:
        if v and v not in RESOURCE_TYPES:
            raise ValueError(f"未知资源类型：{v}")
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

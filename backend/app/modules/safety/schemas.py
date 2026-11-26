"""安全巡检域（B8 / CSV 24）入参模型。"""

import json
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.core.schemas import CamelModel, OptionalDate

PLAN_TYPES = "^(daily|weekly|monthly|special)$"
PLAN_STATUSES = "^(active|paused|finished)$"
INSPECTION_RESULTS = "^(normal|abnormal)$"
INSPECTION_STATUSES = "^(draft|submitted|closed)$"
HAZARD_LEVELS = "^(low|medium|high|critical)$"
HAZARD_STATUSES = "^(open|rectifying|verified|closed)$"
HAZARD_SOURCES = "^(inspection|manual)$"


def _dump_json(value: Any) -> str:
    """把 list / dict 规整成 JSON 字符串；已是字符串则原样透传（允许前端直接传 JSON 文本）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


class PlanIn(CamelModel):
    """巡检计划维护。"""

    plan_no: str = Field("", max_length=32, description="计划编号，留空由后端生成")
    name: str = Field(..., min_length=1, max_length=128, description="计划名称")
    plan_type: str = Field("daily", pattern=PLAN_TYPES, description="daily/weekly/monthly/special")
    target_area: str = Field("", max_length=128, description="巡检区域 / 对象")
    check_items: Any = Field("", description="巡检项清单（字符串数组或 JSON 数组文本）")
    cycle_days: int = Field(1, ge=1, le=365, description="周期天数")
    next_date: OptionalDate = None
    owner_id: int | None = None
    owner_name: str = Field("", max_length=64)
    dept_id: int | None = None
    dept_name: str = Field("", max_length=128)
    status: str = Field("active", pattern=PLAN_STATUSES)
    remark: str = Field("", max_length=500)

    @field_validator("check_items", mode="before")
    @classmethod
    def _norm_check_items(cls, v: Any) -> str:
        return _dump_json(v)


class InspectionIn(CamelModel):
    """巡检记录登记（逐项结果）。"""

    record_no: str = Field("", max_length=32, description="记录编号，留空由后端生成")
    plan_id: int | None = None
    plan_name: str = Field("", max_length=128)
    area: str = Field("", max_length=128)
    inspect_date: OptionalDate = None
    inspector_id: int | None = None
    inspector_name: str = Field("", max_length=64)
    result: str = Field("normal", pattern=INSPECTION_RESULTS)
    abnormal_count: int = Field(0, ge=0, le=999)
    items_json: Any = Field("", description="逐项结果（数组或 JSON 数组文本）")
    status: str = Field("draft", pattern=INSPECTION_STATUSES)
    summary: str = Field("", max_length=500)
    remark: str = Field("", max_length=500)

    @field_validator("items_json", mode="before")
    @classmethod
    def _norm_items_json(cls, v: Any) -> str:
        return _dump_json(v)


class HazardIn(CamelModel):
    """隐患登记 / 修改。"""

    hazard_no: str = Field("", max_length=32, description="隐患编号，留空由后端取号")
    inspection_id: int | None = None
    record_no: str = Field("", max_length=32)
    source: str = Field("manual", pattern=HAZARD_SOURCES)
    description: str = Field(..., min_length=1, max_length=500)
    level: str = Field("medium", pattern=HAZARD_LEVELS)
    status: str = Field("open", pattern=HAZARD_STATUSES)
    responsible_id: int | None = None
    responsible_name: str = Field("", max_length=64)
    deadline: OptionalDate = None
    found_at: datetime | None = None
    measure: str = Field("", max_length=500)
    remark: str = Field("", max_length=255)


class RectifyIn(CamelModel):
    """隐患整改（措施必填）。"""

    measure: str = Field(..., min_length=1, max_length=500, description="整改措施")


class VerifyIn(CamelModel):
    """隐患验证结论。"""

    verify_result: str = Field("", max_length=500, description="验证结论")
    pass_: bool = Field(False, alias="pass", description="是否验证通过")

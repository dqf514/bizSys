"""智能排程入参模型（B5 CSV 22）。"""

from datetime import datetime

from pydantic import Field

from app.core.schemas import CamelModel, OptionalDate


class AutoScheduleIn(CamelModel):
    """自动排期请求。"""

    name: str = Field("", max_length=128)
    base_date: OptionalDate = None
    task_ids: list[int] = Field(default_factory=list)
    project_id: int | None = None
    date_from: OptionalDate = None
    date_to: OptionalDate = None
    remark: str = Field("", max_length=500)


class ScheduleIn(CamelModel):
    """排程行调整（人工可改资源 / 时间 / 数量）。"""

    resource_type: str = Field("", max_length=16)
    resource_id: int | None = None
    resource_code: str = Field("", max_length=64)
    resource_name: str = Field("", max_length=128)
    quantity: float = 0
    unit: str = Field("", max_length=16)
    plan_start: datetime | None = None
    plan_end: datetime | None = None
    status: str = Field("", max_length=16)
    remark: str = Field("", max_length=500)
    version: int | None = None


class PlanIn(CamelModel):
    name: str = Field("", max_length=128)
    plan_date: OptionalDate = None
    remark: str = Field("", max_length=500)

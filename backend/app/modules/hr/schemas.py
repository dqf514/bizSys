"""人事行政模块接口 Schemas。"""

from datetime import date
from decimal import Decimal

from pydantic import Field, field_validator

from app.core.schemas import CamelModel


class TimesheetIn(CamelModel):
    """工时填报/编辑入参：submit=true 表示保存并直接提交。"""

    task_id: int
    work_date: date
    hours: Decimal = Field(gt=0, le=24)
    content: str = Field(min_length=1, max_length=500)
    remark: str = Field(default="", max_length=500)
    submit: bool = False

    @field_validator("hours")
    @classmethod
    def _half_step(cls, v: Decimal) -> Decimal:
        if v * 2 != int(v * 2):
            raise ValueError("工时须以 0.5 小时为步进")
        return v


class TimesheetPrefillIn(CamelModel):
    """AI 工时预填入参：按任务+日期生成草稿（不落库）。"""

    task_id: int
    work_date: date

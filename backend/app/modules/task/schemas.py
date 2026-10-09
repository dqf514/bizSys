"""任务入参模型。"""

from datetime import date

from pydantic import Field

from app.core.schemas import CamelModel


class ItemIn(CamelModel):
    id: int | None = None
    item_code: str = Field("", max_length=32)
    name: str = Field("", max_length=128)
    std: str = Field("", max_length=128)
    dept: str = Field("", max_length=64)
    inspector: str = Field("", max_length=64)
    qty: int = Field(1, ge=0)
    settle_type: str = Field("", max_length=32)
    need_report: int = 0
    report_no: str = Field("", max_length=32)
    report_status: str = Field("", max_length=16)


class SampleIn(CamelModel):
    id: int | None = None
    name: str = Field("", max_length=128)
    model: str = Field("", max_length=64)
    vin: str = Field("", max_length=64)
    vehicle_type: str = Field("", max_length=64)
    sample_date: date | None = None
    in_stock: str = Field("in", pattern="^(in|out)$")


class TaskIn(CamelModel):
    task_name: str = Field(..., min_length=1, max_length=255)
    task_type: str = Field("", max_length=32)
    contract_id: int | None = None
    content: str = Field("", max_length=4000)
    receiver: str = Field("", max_length=64)
    receiver_unit: str = Field("", max_length=128)
    biz_block: str = Field("", max_length=32)
    dept_id: int | None = None
    dept_name: str = Field("", max_length=64)
    owner_id: int | None = None
    owner_name: str = Field("", max_length=64)
    party_system: str = Field("", max_length=64)
    plan_finish_date: date | None = None
    version: int | None = None
    items: list[ItemIn] = Field(default_factory=list)
    samples: list[SampleIn] = Field(default_factory=list)

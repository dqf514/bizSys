"""任务入参模型。"""

from pydantic import Field

from app.core.schemas import CamelModel, OptionalDate


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
    sample_date: OptionalDate = None
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
    plan_finish_date: OptionalDate = None
    version: int | None = None
    items: list[ItemIn] = Field(default_factory=list)
    samples: list[SampleIn] = Field(default_factory=list)


class ProgressIn(CamelModel):
    """进度记录（人工确认后落库；AI 分析结果由前端透传 source=ai）。"""

    percent: int = Field(..., ge=0, le=100)
    note: str = Field("", max_length=2000)
    image_path: str = Field("", max_length=255)
    source: str = Field("manual", pattern="^(ai|manual)$")


class EntrustItemIn(CamelModel):
    """委托明细行（受理后转任务条目）。"""

    id: int | None = None
    item_code: str = Field("", max_length=32)
    name: str = Field("", max_length=128)
    std: str = Field("", max_length=128)
    qty: int = Field(1, ge=0)
    need_report: int = 1
    report_type: str = Field("", max_length=32)
    remark: str = Field("", max_length=255)


class EntrustIn(CamelModel):
    """在线任务委托单（客户自助下单 / 业务经理代提交）。"""

    title: str = Field(..., min_length=1, max_length=255)
    entrust_type: str = Field("", pattern="^(sim|model|test|outsource)$")
    contract_id: int | None = None
    requirement: str = Field("", max_length=4000)
    sample_desc: str = Field("", max_length=500)
    plan_start_date: OptionalDate = None
    plan_end_date: OptionalDate = None
    priority: str = Field("normal", pattern="^(normal|urgent)$")
    amount: float | None = None
    remark: str = Field("", max_length=500)
    items: list[EntrustItemIn] = Field(default_factory=list)


class EntrustReviewIn(CamelModel):
    """受理 / 驳回：受理时可指定业务负责人（抄送）。"""

    action: str = Field(..., pattern="^(accept|reject)$")
    comment: str = Field("", max_length=500)
    biz_owner_id: int | None = None
    biz_owner_name: str = Field("", max_length=64)
    handler_id: int | None = None
    handler_name: str = Field("", max_length=64)


class EntrustDispatchIn(CamelModel):
    """受理后生成任务草稿：指定负责人与执行部门。"""

    owner_id: int | None = None
    owner_name: str = Field("", max_length=64)
    dept_id: int | None = None
    dept_name: str = Field("", max_length=64)
    plan_finish_date: OptionalDate = None
    comment: str = Field("", max_length=500)

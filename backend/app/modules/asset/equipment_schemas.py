"""B6 设备台账 / 能耗 / 预警入参模型（camelCase 别名，见 `app/core/schemas.py::CamelModel`）。"""

from pydantic import Field

from app.core.schemas import CamelModel, OptionalDate

EQUIPMENT_STATUS_PATTERN = "^(idle|running|maintenance|fault|scrapped)$"
EQUIPMENT_CATEGORY_PATTERN = "^(wind_tunnel|cfd|machining|test|other)$"
SHIFT_PATTERN = "^(morning|day|night)$"
METRIC_SOURCE_PATTERN = "^(manual|schedule)$"
ALERT_RULE_PATTERN = "^(maintain_overdue|energy_abnormal|low_utilization|fault|status_abnormal)$"
ALERT_LEVEL_PATTERN = "^(info|warning|critical)$"


class EquipmentIn(CamelModel):
    equipment_no: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=128)
    category: str = Field("other", pattern=EQUIPMENT_CATEGORY_PATTERN)
    model: str = Field("", max_length=64)
    spec: str = Field("", max_length=255)
    workshop: str = Field("", max_length=64)
    location: str = Field("", max_length=128)
    vendor_id: int | None = None
    purchase_date: OptionalDate = None
    commission_date: OptionalDate = None
    original_value: float = Field(0, ge=0, le=999999999999.99)
    status: str = Field("idle", pattern=EQUIPMENT_STATUS_PATTERN)
    owner_id: int | None = None
    owner_name: str = Field("", max_length=64)
    dept_id: int | None = None
    maintain_cycle_days: int = Field(0, ge=0, le=3650)
    last_maintain_date: OptionalDate = None
    next_maintain_date: OptionalDate = None
    run_hours: float = Field(0, ge=0, le=9999999999.99)
    remark: str = Field("", max_length=500)
    version: int | None = None


class EquipmentMetricIn(CamelModel):
    equipment_id: int
    stat_date: OptionalDate = None
    shift: str = Field("day", pattern=SHIFT_PATTERN)
    run_hours: float = Field(0, ge=0, le=9999999999.99)
    downtime_hours: float = Field(0, ge=0, le=9999999999.99)
    energy: float = Field(0, ge=0, le=9999999999.99)
    output_qty: float = Field(0, ge=0, le=9999999999.99)
    source: str = Field("manual", pattern=METRIC_SOURCE_PATTERN)
    remark: str = Field("", max_length=255)


class EquipmentAlertIn(CamelModel):
    equipment_id: int
    rule_type: str = Field(..., pattern=ALERT_RULE_PATTERN)
    level: str = Field("warning", pattern=ALERT_LEVEL_PATTERN)
    title: str = Field("", max_length=128)
    content: str = Field("", max_length=500)
    remark: str = Field("", max_length=255)


class EquipmentAlertHandleIn(CamelModel):
    """预警处理：状态只允许 processing / closed（非法值由服务端抛业务异常，不做 pattern 拦截）。"""

    status: str = Field(..., max_length=16)
    handle_result: str = Field("", max_length=500)


__all__ = [
    "EquipmentIn",
    "EquipmentMetricIn",
    "EquipmentAlertIn",
    "EquipmentAlertHandleIn",
]

"""数据维护入参。"""

import re
from datetime import datetime

from pydantic import Field, field_validator

from app.core.schemas import CamelModel


class BackupSettingsIn(CamelModel):
    enabled: bool | None = None
    time: str | None = None
    retention: int | None = Field(None, ge=1, le=90)
    dir: str | None = Field(None, max_length=255)

    @field_validator("time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("时间格式须为 HH:MM")
        return v


class MaintenanceSettingsIn(CamelModel):
    backup: BackupSettingsIn | None = None
    show_demo_accounts: bool | None = None


class PurgeIn(CamelModel):
    password: str = Field(..., min_length=1, max_length=128)
    confirm: str = Field(..., min_length=1, max_length=32)
    force_backup_skip: bool = False


class RetimeIn(CamelModel):
    """记录时间修正：biz_type 白名单内的单据时间字段改值，原因必填（留痕审计）。"""

    biz_type: str = Field(..., min_length=1, max_length=32)
    id: int = Field(..., ge=1)
    field: str = Field(..., min_length=1, max_length=32)
    value: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(..., min_length=1, max_length=255)

    @field_validator("value")
    @classmethod
    def _check_value(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError("时间格式须为 YYYY-MM-DD HH:MM:SS（服务器本地时区）") from None
        return v

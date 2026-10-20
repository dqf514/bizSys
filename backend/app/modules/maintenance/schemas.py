"""数据维护入参。"""

import re

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

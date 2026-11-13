"""AI 中心入参。"""

from pydantic import BaseModel, Field


class AiQuotaIn(BaseModel):
    userDailyCalls: int = Field(0, ge=0, le=100000)
    userDailyTokens: int = Field(0, ge=0, le=100_000_000)
    globalDailyTokens: int = Field(0, ge=0, le=100_000_000)


class AiCenterSettingsIn(BaseModel):
    features: dict[str, bool] | None = None
    quota: AiQuotaIn | None = None

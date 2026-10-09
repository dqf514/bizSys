"""系统设置接口 Schemas。"""

from pydantic import Field

from app.core.schemas import CamelModel


class WecomIn(CamelModel):
    enabled: bool = False
    corp_id: str = Field(default="", max_length=64)
    agent_id: str = Field(default="", max_length=32)
    secret: str = Field(default="", max_length=128)  # 空串 = 不修改
    callback_url: str = Field(default="", max_length=255)


class SettingsIn(CamelModel):
    site_name: str | None = Field(default=None, max_length=128)
    wecom: WecomIn | None = None


class WecomCallbackIn(CamelModel):
    code: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=64)

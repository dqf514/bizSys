"""AI 中心入参。"""

from pydantic import BaseModel, Field


class AiQuotaIn(BaseModel):
    userDailyCalls: int = Field(0, ge=0, le=100000)
    userDailyTokens: int = Field(0, ge=0, le=100_000_000)
    globalDailyTokens: int = Field(0, ge=0, le=100_000_000)


class AiCenterSettingsIn(BaseModel):
    features: dict[str, bool] | None = None
    quota: AiQuotaIn | None = None


class NlQueryContext(BaseModel):
    """对话式追问上下文：回传上一轮的域与时间范围，AI 可只补时间。"""

    domain: str = ""
    timeFrom: str = ""
    timeTo: str = ""


class NlQueryIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=200)
    context: NlQueryContext | None = None


class AssistantIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    menus: list[dict] = Field(default_factory=list, max_length=100)


class KnowledgeEntryIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    category: str = Field("", max_length=64)
    content: str = Field("", max_length=20000)


class KnowledgeAskIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=200)


class DigestPushIn(BaseModel):
    """推送内容回传 GET 摘要结果，避免重复 AI 调用。"""

    summary: str = Field(..., min_length=1, max_length=2000)
    highlights: list[str] = Field(default_factory=list, max_length=10)

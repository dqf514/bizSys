"""报告入参模型。"""

from typing import Literal

from pydantic import Field

from app.core.schemas import CamelModel


class SubmitIn(CamelModel):
    comment: str = Field("", max_length=255)


class SealIn(CamelModel):
    comment: str = Field("", max_length=255)


class RemarkIn(CamelModel):
    remark: str = Field("", max_length=4000)


class AssistIn(CamelModel):
    kind: Literal["conclusion", "proofread", "completeness"]


class ConclusionIn(CamelModel):
    conclusion: str = Field("", max_length=4000)

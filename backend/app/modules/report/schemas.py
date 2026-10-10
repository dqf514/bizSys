"""报告入参模型。"""

from pydantic import Field

from app.core.schemas import CamelModel


class SubmitIn(CamelModel):
    comment: str = Field("", max_length=255)


class SealIn(CamelModel):
    comment: str = Field("", max_length=255)

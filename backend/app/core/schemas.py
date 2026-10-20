"""请求体基类：camelCase / snake_case 双向兼容（契约 api-contract.md 用 camel）。"""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def _none_if_empty(v):
    """前端日期控件清空后回传空串：宽容解析为 None（草稿不强校验日期）。"""
    return None if v == "" else v


OptionalDate = Annotated[date | None, BeforeValidator(_none_if_empty)]

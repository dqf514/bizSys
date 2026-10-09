"""请求体基类：camelCase / snake_case 双向兼容（契约 api-contract.md 用 camel）。"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

"""回收站入参（camelCase 别名）。"""

from pydantic import Field

from app.core.schemas import CamelModel


class RecycleSettingIn(CamelModel):
    """保留期设置（天）：保留期内禁止彻底删除。"""

    retention_days: int = Field(180, ge=1, le=3650, description="保留天数")

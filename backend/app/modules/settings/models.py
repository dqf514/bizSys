"""系统配置表：key-value 存储（敏感值加密，见 core/crypto）。"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class SysConfig(BaseModel):
    __tablename__ = "sys_config"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="配置键")
    value: Mapped[str] = mapped_column(Text, default="", comment="配置值（敏感项 AES-GCM 加密存储）")
    remark: Mapped[str] = mapped_column(String(255), default="", comment="说明")

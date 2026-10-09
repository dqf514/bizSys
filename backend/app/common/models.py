"""全表通用基类：id / 审计四列 / 乐观锁 / 逻辑删除。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BaseModel(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    create_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="创建人")
    update_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    update_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="更新人")
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=True, comment="乐观锁版本")
    deleted: Mapped[int] = mapped_column(Integer, default=0, nullable=True, comment="逻辑删除 0/1")

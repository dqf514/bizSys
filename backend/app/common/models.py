"""全表通用基类：id / 审计四列 / 乐观锁 / 逻辑删除。

另含 `AppendOnlyModel` —— 合规审计日志的只追加基类（无 deleted / version / update_*）。
"""

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
    deleted: Mapped[int] = mapped_column(Integer, default=0, comment="逻辑删除 0/1")


class AppendOnlyModel(Base):
    """只追加基类 —— 合规审计日志（审计追踪 / 访客通行 / 授权变更轨迹）。

    刻意**不继承** `BaseModel`：没有 `deleted` / `version` / `update_*`，
    从数据模型层面保证"日志不可删改"；接口层同样不提供 update / delete。

    注意：`create_time` 仍是秒精度默认。审计链（sys_audit_log）需要在毫秒级
    复现同一时间戳才能重算哈希，因此 AuditLog 单独用 DATETIME(3) 覆盖。
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="写入时间")

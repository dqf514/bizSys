"""回收站登记表：`sys_recycle_bin`（全站软删记录的登记表）。

只登记「谁在什么时候删了哪张表的哪一行」，业务数据本身仍在原表里（`deleted=1`）。
这样**不用给 116 张业务表加列**（也绕开了 `AppendOnlyModel` 表没有 `deleted` 的问题）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class RecycleBin(BaseModel):
    """回收站条目（状态：recycled 待处理 / restored 已恢复 / purged 已彻底删除）。"""

    __tablename__ = "sys_recycle_bin"
    __table_args__ = (
        Index("ix_sys_recycle_bin_status_deleted", "status", "deleted_at"),
        Index("ix_sys_recycle_bin_module", "module"),
    )

    module: Mapped[str] = mapped_column(String(32), default="", comment="业务域（如 asset/knowledge）")
    table_name: Mapped[str] = mapped_column(String(64), default="", comment="原表名")
    resource: Mapped[str] = mapped_column(String(64), default="", comment="模型名")
    resource_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True, comment="原记录主键")
    title: Mapped[str] = mapped_column(String(255), default="", comment="冗余标题（列表展示）")
    deleted_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="删除人用户 id")
    deleted_by_name: Mapped[str] = mapped_column(String(64), default="", comment="删除人姓名")
    deleted_at: Mapped[datetime] = mapped_column(DateTime, index=True, comment="删除时间")
    purge_after: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="可彻底删除时间（删除时间+保留期）"
    )
    status: Mapped[str] = mapped_column(String(16), default="recycled", index=True, comment="recycled/restored/purged")
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="彻底删除时间")
    purged_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="彻底删除人")
    restore_fields: Mapped[str] = mapped_column(Text, default="", comment="恢复时要回填的字段（JSON）")
    meta: Mapped[str] = mapped_column(Text, default="", comment="附加信息（JSON，含级联软删子行）")

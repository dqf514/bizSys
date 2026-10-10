"""报告 2 表：rpt_file（文件实体）/ rpt_report（报告单）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class ReportFile(BaseModel):
    """报告文件实体：原件与转换后的 PDF 各占一行（存 uploads/report/）。"""

    __tablename__ = "rpt_file"

    file_name: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    size: Mapped[int] = mapped_column(BigInteger, default=0, comment="字节数")
    content_type: Mapped[str] = mapped_column(String(128), default="")
    path: Mapped[str] = mapped_column(String(255), comment="相对 upload_dir 的路径")


class Report(BaseModel):
    """报告：uploaded 已上传待审 → approving 审批中 → approved 批准通过 → sealed 签章完成；rejected 已驳回。"""

    __tablename__ = "rpt_report"
    __table_args__ = (Index("ix_rpt_report_status_update_time", "status", "update_time"),)

    report_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="报告编号 BG...（取自条目）")
    task_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="task_task.id")
    task_item_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="task_item.id（一条目一未删报告）")
    file_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="原件 rpt_file.id")
    file_name: Mapped[str] = mapped_column(String(255), default="", comment="原件文件名冗余")
    status: Mapped[str] = mapped_column(
        String(16), default="uploaded", index=True, comment="uploaded/approving/approved/rejected/sealed"
    )
    pdf_file_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="转换后 PDF rpt_file.id")
    seal_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="签章人")
    seal_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="签章时间")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_instance_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="最近一次签批审批实例"
    )

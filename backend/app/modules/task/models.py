"""任务 4 表：task_task / task_item / task_sample / task_sample_flow。"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class Task(BaseModel):
    """状态机：draft → assigning → assigned → in_progress → finished → closed；终态 stopped。"""

    __tablename__ = "task_task"

    task_no: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True, comment="任务编号 RW...（提交审批时发放，草稿不占号）"
    )
    task_name: Mapped[str] = mapped_column(String(255), index=True)
    task_type: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 task_type")
    contract_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    contract_no: Mapped[str] = mapped_column(String(32), default="", comment="合同号冗余")
    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(128), default="", comment="客户名冗余")
    biz_block: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 biz_block")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(64), default="")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="负责人")
    owner_name: Mapped[str] = mapped_column(String(64), default="")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="试验/工作内容")
    party_system: Mapped[str] = mapped_column(String(64), default="", comment="外部系统")
    receiver: Mapped[str] = mapped_column(String(64), default="", comment="接样人")
    receiver_unit: Mapped[str] = mapped_column(String(128), default="", comment="受检单位")
    plan_finish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    flow_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    items = relationship(
        "TaskItem", foreign_keys="TaskItem.task_id", cascade="all, delete-orphan", lazy="selectin"
    )
    samples = relationship(
        "TaskSample", foreign_keys="TaskSample.task_id", cascade="all, delete-orphan", lazy="selectin"
    )


class TaskItem(BaseModel):
    """任务子条目（报告挂 need_report）。"""

    __tablename__ = "task_item"

    task_id: Mapped[int] = mapped_column(ForeignKey("task_task.id"), index=True)
    item_code: Mapped[str] = mapped_column(String(32), default="", comment="条目编号")
    name: Mapped[str] = mapped_column(String(128), default="")
    std: Mapped[str] = mapped_column(String(128), default="", comment="依据标准")
    dept: Mapped[str] = mapped_column(String(64), default="", comment="试验室")
    inspector: Mapped[str] = mapped_column(String(64), default="", comment="试验人")
    qty: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    settle_type: Mapped[str] = mapped_column(String(32), default="", comment="结算方式")
    need_report: Mapped[int] = mapped_column(Integer, default=0)
    report_no: Mapped[str] = mapped_column(String(32), default="", comment="报告编号 BG...")
    report_status: Mapped[str] = mapped_column(String(16), default="", comment="报告状态")


class TaskSample(BaseModel):
    """样品：编号=任务号-01；in_stock: in/out。"""

    __tablename__ = "task_sample"

    task_id: Mapped[int] = mapped_column(ForeignKey("task_task.id"), index=True)
    sample_no: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True, comment="编号=任务号-01（随任务提交发放）"
    )
    name: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(64), default="", comment="型号")
    vin: Mapped[str] = mapped_column(String(64), default="")
    vehicle_type: Mapped[str] = mapped_column(String(64), default="", comment="车型")
    sample_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    in_stock: Mapped[str] = mapped_column(String(8), default="in", comment="in=在库 out=出库")


class TaskSampleFlow(BaseModel):
    """样品出入库流水。"""

    __tablename__ = "task_sample_flow"

    sample_id: Mapped[int] = mapped_column(BigInteger, index=True)
    task_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(8), comment="in/out")
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    remark: Mapped[str] = mapped_column(String(255), default="")

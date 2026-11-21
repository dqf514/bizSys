"""智能排程域（B5 CSV 22）模型。

排程落点：方案（prd_plan，一次自动排期生成的可发布批次）+ 排程行（prd_schedule，
一个任务在一组资源上的时段占用）。

约束来源：任务上的「人 / 机 / 料 / 环」分配（task_assignment）与设备台账、
样车档案、存货库存 —— 排程求解时按资源维度做时段冲突检测。
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class ProdPlan(BaseModel):
    """排程方案：一次自动排期生成的批次，人工调整后发布。

    状态机：draft（草稿，可调）→ published（已发布，占用资源）→ confirmed（已确认开工）
    ；draft / published 可 cancelled。
    """

    __tablename__ = "prd_plan"

    plan_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="方案号 PL...")
    name: Mapped[str] = mapped_column(String(128), default="", comment="方案名称")
    plan_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="排期基准日")
    status: Mapped[str] = mapped_column(
        String(16), default="draft", index=True, comment="draft/published/confirmed/cancelled"
    )
    auto_generated: Mapped[int] = mapped_column(Integer, default=0, comment="是否自动生成")
    task_count: Mapped[int] = mapped_column(Integer, default=0, comment="排程任务数")
    conflict_count: Mapped[int] = mapped_column(Integer, default=0, comment="冲突行数")
    generated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    generated_by_name: Mapped[str] = mapped_column(String(64), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by_name: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")
    schedules = relationship(
        "ProdSchedule", foreign_keys="ProdSchedule.plan_id", cascade="all, delete-orphan", lazy="selectin"
    )


class ProdSchedule(BaseModel):
    """排程行：任务 × 资源 × 时段。

    `resource_type` 取值：equipment 设备 · person 人员 · vehicle 样车 · material 物料。
    同一资源在同一时段的占用不允许重叠 —— 发布时按 (resource_type, resource_id) 做冲突检测。
    """

    __tablename__ = "prd_schedule"

    schedule_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="排程编号 SC...")
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("prd_plan.id"), index=True)
    plan_no_text: Mapped[str] = mapped_column(String(32), default="", comment="方案号冗余")
    task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    task_no: Mapped[str] = mapped_column(String(32), default="", index=True)
    task_name: Mapped[str] = mapped_column(String(128), default="")
    project_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    project_no: Mapped[str] = mapped_column(String(32), default="")
    resource_type: Mapped[str] = mapped_column(String(16), default="equipment", index=True)
    resource_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    resource_code: Mapped[str] = mapped_column(String(64), default="")
    resource_name: Mapped[str] = mapped_column(String(128), default="")
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="占用数量")
    unit: Mapped[str] = mapped_column(String(16), default="")
    plan_start: Mapped[datetime] = mapped_column(DateTime, index=True, comment="计划开始")
    plan_end: Mapped[datetime] = mapped_column(DateTime, index=True, comment="计划结束")
    duration_hours: Mapped[float] = mapped_column(Numeric(10, 2), default=0, comment="时长（小时）")
    priority: Mapped[int] = mapped_column(Integer, default=5, comment="优先级 1(最高)~9(最低)")
    seq: Mapped[int] = mapped_column(Integer, default=0, comment="方案内顺序")
    status: Mapped[str] = mapped_column(
        String(16), default="scheduled", index=True, comment="scheduled/published/confirmed/done/conflict/cancelled"
    )
    source: Mapped[str] = mapped_column(String(8), default="auto", comment="auto 自动 / manual 人工调整")
    conflict_reason: Mapped[str] = mapped_column(String(255), default="", comment="冲突原因")
    remark: Mapped[str] = mapped_column(String(500), default="")

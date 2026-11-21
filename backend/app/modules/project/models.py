"""项目管理域（B5 CSV 31）模型。

项目（prj_project）+ 项目任务（prj_project_task）。项目任务可以挂接已有业务任务
（task_task.id），也可以是纯项目内节点（里程碑 / 阶段）。甘特图数据由项目任务
的起止日期与进度直接推导。
"""

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class Project(BaseModel):
    """项目：大型项目全生命周期。

    状态机：draft 立项 → planning 策划（排程中）→ executing 执行中 →
    accepting 验收中 → closed 已结项；draft / planning / executing 可 cancelled。
    """

    __tablename__ = "prj_project"

    project_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="项目编号 PJ...")
    name: Mapped[str] = mapped_column(String(255), index=True, comment="项目名称")
    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    contract_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    contract_no: Mapped[str] = mapped_column(String(32), default="")
    manager_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="项目经理")
    manager_name: Mapped[str] = mapped_column(String(64), default="")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(64), default="")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="计划开始")
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="计划完成")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="整体进度百分比")
    budget_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="预算金额")
    actual_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="实际发生额")
    description: Mapped[str] = mapped_column(Text, default="", comment="项目说明")
    remark: Mapped[str] = mapped_column(String(500), default="")
    tasks = relationship(
        "ProjectTask", foreign_keys="ProjectTask.project_id", cascade="all, delete-orphan", lazy="selectin"
    )


class ProjectTask(BaseModel):
    """项目任务（甘特行）：可挂接业务任务，也可作为项目内阶段 / 里程碑。"""

    __tablename__ = "prj_project_task"

    project_id: Mapped[int] = mapped_column(ForeignKey("prj_project.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="关联 task_task.id")
    task_no: Mapped[str] = mapped_column(String(32), default="", index=True)
    task_name: Mapped[str] = mapped_column(String(255), default="")
    seq: Mapped[int] = mapped_column(Integer, default=1, comment="序号 / 排序")
    group_code: Mapped[str] = mapped_column(
        String(32), default="", index=True, comment="任务分组：sim/model/test/outsource"
    )
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    owner_name: Mapped[str] = mapped_column(String(64), default="")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="进度百分比")
    milestone: Mapped[int] = mapped_column(Integer, default=0, comment="是否里程碑")
    weight: Mapped[float] = mapped_column(Numeric(8, 2), default=0, comment="权重（进度加权）")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, comment="pending/doing/done/delayed")
    depends_on: Mapped[str] = mapped_column(String(255), default="", comment="前置项目任务 id，逗号分隔")
    source: Mapped[str] = mapped_column(String(8), default="manual", comment="auto 自动生成 / manual 手工")
    remark: Mapped[str] = mapped_column(String(500), default="")

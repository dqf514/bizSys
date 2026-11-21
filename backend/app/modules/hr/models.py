"""人事行政（HR）：工时填报 hr_timesheet。

- 一条 = 某用户某天某任务一条工时；同用户+日期+任务唯一（deleted 入唯一键，软删行写行 id 不阻塞重建）；
- 填报必须挂"进行中且关联合同"的任务；任务编号/名称、合同、客户快照落行，统计不依赖任务后续变更；
- 状态机（F5 接入审批）：draft（可改/删/提交）→ approving（审批中）→ approved（已批准，计入成本）
  / rejected（已驳回，可改后重提）；未绑定工时审批流程时提交直通为 submitted（同样计入成本）。
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class HrTimesheet(BaseModel):
    """工时填报行：每日按任务填报一次，允许多条不同任务。"""

    __tablename__ = "hr_timesheet"
    __table_args__ = (
        UniqueConstraint("user_id", "work_date", "task_id", "deleted", name="uq_hr_timesheet_user_date_task"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="填报人 sys_user.id")
    user_name: Mapped[str] = mapped_column(String(64), default="", comment="填报人姓名冗余")
    work_date: Mapped[date] = mapped_column(Date, index=True, comment="工作日期（不允许未来日期）")
    task_id: Mapped[int] = mapped_column(ForeignKey("task_task.id"), index=True, comment="关联任务 task_task.id")
    task_no: Mapped[str] = mapped_column(String(32), default="", comment="任务编号快照")
    task_name: Mapped[str] = mapped_column(String(255), default="", comment="任务名称快照")
    contract_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="关联合同快照")
    contract_no: Mapped[str] = mapped_column(String(32), default="", comment="合同号快照")
    customer_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="客户快照")
    customer_name: Mapped[str] = mapped_column(String(128), default="", comment="客户名快照")
    hours: Mapped[Decimal] = mapped_column(Numeric(4, 1), comment="工时小时数（0.5 步进，≤24）")
    content: Mapped[str] = mapped_column(String(500), default="", comment="工作内容")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    status: Mapped[str] = mapped_column(
        String(16), default="draft", index=True, comment="draft/approving/approved/rejected/submitted"
    )
    flow_instance_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="工时审批实例 approval_instance.id"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近提交时间")

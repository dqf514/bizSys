"""人事行政（HR）：工时填报 hr_timesheet。

- 一条 = 某用户某天某任务一条工时；同用户+日期+任务唯一（deleted 入唯一键，软删行写行 id 不阻塞重建）；
- 填报必须挂"进行中且关联合同"的任务；任务编号/名称、合同、客户快照落行，统计不依赖任务后续变更；
- 状态机（F5 接入审批）：draft（可改/删/提交）→ approving（审批中）→ approved（已批准，计入成本）
  / rejected（已驳回，可改后重提）；未绑定工时审批流程时提交直通为 submitted（同样计入成本）。
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import AppendOnlyModel, BaseModel


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


class HrAuthorization(BaseModel):
    """人员授权台账（B9-C3 / HR L2 授权管理 / 合规 3.1「人员能力」）。

    一行 = 某人在某段时间、某范围内、以某个角色获得的授权。
    检测机构的核心控制点：**未授权不得操作对应检测活动**（HR docx 3.4/3.5）。

    维度四列显式建模（可索引、可过滤），`scope_json` 只是展示用快照兜底，
    **不做过滤依据**（过滤永远走显式列，避免"快照里恰好有值"这种隐性授权）。
    """

    __tablename__ = "hr_authorization"
    __table_args__ = (
        Index("ix_hr_authorization_user_type_status", "user_id", "auth_type", "status"),
        Index("ix_hr_authorization_type_status", "auth_type", "status"),
        Index("ix_hr_authorization_status_valid_to", "status", "valid_to"),
    )

    auth_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="授权编号 AU...")
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="被授权人 sys_user.id")
    user_name: Mapped[str] = mapped_column(String(64), default="", comment="被授权人姓名")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="部门 id")
    dept_name: Mapped[str] = mapped_column(String(64), default="", comment="部门名称")
    auth_type: Mapped[str] = mapped_column(
        String(32), index=True, comment="授权类型 test_item检测项目/device设备操作/report_role报告角色/signer授权签字"
    )
    role_code: Mapped[str] = mapped_column(
        String(32), default="", comment="角色 preparer编制/reviewer复核/approver批准/signer签字"
    )
    # —— 授权范围四维（留空 = 该维度不限）——
    scope_method: Mapped[str] = mapped_column(String(64), default="", comment="检测方法/标准")
    scope_params: Mapped[str] = mapped_column(String(255), default="", comment="方法参数（逗号分隔）")
    scope_device_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="设备 id")
    scope_device_name: Mapped[str] = mapped_column(String(64), default="", comment="设备名称")
    scope_domain: Mapped[str] = mapped_column(String(64), default="", comment="业务域/专业域")
    scope_json: Mapped[str] = mapped_column(Text, default="", comment="范围快照（展示兜底，不做过滤依据）")
    # —— 有效期与状态 ——
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="生效时间")
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="失效时间")
    status: Mapped[str] = mapped_column(
        String(16),
        default="draft",
        index=True,
        comment="draft/approving/confirmed/active/suspended/expired/revoked/rejected",
    )
    # —— 申请与审批 ——
    applicant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="申请人 id")
    applicant_name: Mapped[str] = mapped_column(String(64), default="", comment="申请人姓名")
    approver_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="批准人 id")
    approver_name: Mapped[str] = mapped_column(String(64), default="", comment="批准人姓名")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="批准时间")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="生效时间")
    flow_instance_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="审批实例 approval_instance.id"
    )
    last_reason: Mapped[str] = mapped_column(String(500), default="", comment="最近一次状态变更原因")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")


class HrAuthorizationEvent(AppendOnlyModel):
    """授权变更轨迹（**只追加**）—— 可回溯任一历史时点的授权状态。

    合规 4.4 的同类要求：授权台账的"谁在何时把什么授权改成什么"本身就是证据，
    因此这张表不提供任何 update / delete 接口（继承 `AppendOnlyModel`，无 deleted 列）。
    """

    __tablename__ = "hr_authorization_event"
    __table_args__ = (
        Index("ix_hr_authorization_event_auth_id_at", "authorization_id", "effective_at"),
        Index("ix_hr_authorization_event_auth_no", "auth_no"),
    )

    authorization_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="授权 id")
    auth_no: Mapped[str] = mapped_column(String(32), default="", comment="授权编号快照")
    event_type: Mapped[str] = mapped_column(
        String(32), default="", comment="事件类型 create/submit/approve/activate/suspend/resume/revoke/expire"
    )
    from_status: Mapped[str] = mapped_column(String(16), default="", comment="变更前状态")
    to_status: Mapped[str] = mapped_column(String(16), default="", comment="变更后状态")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="操作人 id")
    operator_name: Mapped[str] = mapped_column(String(64), default="", comment="操作人姓名")
    reason: Mapped[str] = mapped_column(String(500), default="", comment="变更原因")
    effective_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=3),
        nullable=True,
        index=True,
        comment="生效时间（毫秒精度：同一秒内的多次变更要能区分先后）",
    )
    snapshot: Mapped[str] = mapped_column(Text, default="", comment="变更时点的授权快照 JSON")

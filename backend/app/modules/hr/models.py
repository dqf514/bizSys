"""人事行政（HR）：工时填报 hr_timesheet + 组织架构/员工主数据/人事事务（B10-1）。

- 一条 = 某用户某天某任务一条工时；同用户+日期+任务唯一（deleted 入唯一键，软删行写行 id 不阻塞重建）；
- 填报必须挂"进行中且关联合同"的任务；任务编号/名称、合同、客户快照落行，统计不依赖任务后续变更；
- 状态机（F5 接入审批）：draft（可改/删/提交）→ approving（审批中）→ approved（已批准，计入成本）
  / rejected（已驳回，可改后重提）；未绑定工时审批流程时提交直通为 submitted（同样计入成本）。

B10-1 新增（HR L1 基础人事，对应 HR docx 2.1–2.3）：
- `hr_position`：岗位说明书 + 关键岗位标记 + A/B 角；
- `hr_employee`：员工一人一档（与 sys_user 1:1 关联但分域存放；证件号 AES-GCM 密文）；
- `hr_employee_control`：黑白名单（违规人员 / 行业禁入）；
- `hr_employment` / `hr_employment_event`：人事事务单据 + 只追加变更轨迹；
- `hr_delegate`：代理人（AB 角 / 临时代理，不借账号）；
- `hr_org_change`：只追加组织变更快照（历史版本留存）。
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
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


# ============================================================================
# B10-1 HR L1：组织架构 / 员工主数据 / 人事事务
# ============================================================================


class HrPosition(BaseModel):
    """岗位（组织架构的"岗位说明书"载体）。

    HR docx 2.1：岗位职责、任职要求、汇报关系、**关键权限标识**（技术负责人 /
    质量负责人 / 授权签字人 / 监督员 / 样品管理员 / 设备管理员）。

    `primary_user_id` / `backup_user_id` 是岗位的 **A/B 角**：关键岗位必须两人，
    主岗离岗时由 B 角顶岗（**不借账号**，见 `hr_delegate`）。
    """

    __tablename__ = "hr_position"
    __table_args__ = (
        Index("ix_hr_position_dept_status", "dept_id", "status"),
        Index("ix_hr_position_key_role_status", "key_role", "status"),
        Index("ix_hr_position_site_status", "site_id", "status"),
    )

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="岗位编码")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="岗位名称")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="所属部门 sys_dept.id")
    site_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="所属场所 sys_dept.id")
    position_type: Mapped[str] = mapped_column(
        String(16), default="staff", index=True, comment="岗位类型 staff普通岗/manager管理岗/key关键岗位"
    )
    duty: Mapped[str] = mapped_column(Text, default="", comment="岗位职责")
    requirement: Mapped[str] = mapped_column(Text, default="", comment="任职要求")
    report_to_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="汇报岗位 hr_position.id"
    )
    key_role: Mapped[str] = mapped_column(
        String(32),
        default="",
        index=True,
        comment="关键岗位标记 tech_leader技术负责人/qa_leader质量负责人/signer授权签字人/"
        "supervisor监督员/sample_manager样品管理员/device_manager设备管理员",
    )
    primary_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="A 角 sys_user.id"
    )
    backup_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="B 角 sys_user.id"
    )
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True, comment="enabled/disabled")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")


class HrEmployee(BaseModel):
    """员工主数据（一人一档基础）。

    与 `sys_user`（账号 / 权限）**1:1 关联但分域存放**：HR 基础信息、技术能力、
    薪酬考勤分域（HR docx 2.2 的数据隔离原则）。`user_id` 为空 = 已建档未开账号。

    `id_no`（证件号）以 **AES-GCM 密文**（`enc:` 前缀）落库，域分隔密钥见
    `app/core/crypto.py::encrypt_text_domain("hr-employee-idno", ...)`；
    出参一律掩码，明文只有 `GET /hr/employees/{id}/id-no` 一条出口且访问留痕。
    """

    __tablename__ = "hr_employee"
    __table_args__ = (
        Index("ix_hr_employee_status_dept", "employ_status", "dept_id"),
        Index("ix_hr_employee_user", "user_id"),
    )

    employee_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="工号")
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="关联账号 sys_user.id")
    name: Mapped[str] = mapped_column(String(64), index=True, comment="姓名")
    id_no: Mapped[str] = mapped_column(String(255), default="", comment="证件号（AES-GCM 密文 enc: 前缀）")
    id_type: Mapped[str] = mapped_column(
        String(16), default="id_card", comment="证件类型 id_card身份证/passport护照/other其他"
    )
    gender: Mapped[str] = mapped_column(String(8), default="", comment="性别")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="出生日期")
    education: Mapped[str] = mapped_column(String(32), default="", index=True, comment="学历")
    major: Mapped[str] = mapped_column(String(64), default="", comment="专业")
    mobile: Mapped[str] = mapped_column(String(32), default="", index=True, comment="手机号")
    email: Mapped[str] = mapped_column(String(128), default="", comment="邮箱")
    # —— 雇佣关系 ——
    employ_type: Mapped[str] = mapped_column(
        String(16), default="labor", index=True, comment="雇佣类型 labor劳动合同/engage聘用/part_time兼职/intern实习"
    )
    employ_status: Mapped[str] = mapped_column(
        String(16),
        default="probation",
        index=True,
        comment="在职状态 probation试用/regular正式/idle待岗/resigned离职/retired退休",
    )
    # —— 任职 ——
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="所属部门 sys_dept.id")
    position_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="岗位 hr_position.id"
    )
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True, comment="入职日期")
    leave_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="离职日期")
    contract_no: Mapped[str] = mapped_column(String(64), default="", comment="劳动合同编号")
    contract_start: Mapped[date | None] = mapped_column(Date, nullable=True, comment="合同起始")
    contract_end: Mapped[date | None] = mapped_column(Date, nullable=True, comment="合同到期")
    emergency_contact: Mapped[str] = mapped_column(String(64), default="", comment="紧急联系人")
    emergency_mobile: Mapped[str] = mapped_column(String(32), default="", comment="紧急联系电话")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True, comment="档案状态 enabled/disabled")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")


class HrEmployeeControl(BaseModel):
    """员工名单管控（HR docx 2.2 黑白名单）。

    黑名单 = 违规人员 / 行业禁入（入职、返聘一律拒绝）；白名单 = 特殊放行说明。
    """

    __tablename__ = "hr_employee_control"
    __table_args__ = (
        UniqueConstraint("employee_id", "control_type", "deleted", name="uq_hr_emp_control_type"),
    )

    employee_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="员工 hr_employee.id")
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="关联账号 sys_user.id")
    control_type: Mapped[str] = mapped_column(
        String(16), index=True, comment="名单类型 blacklist黑名单/whitelist白名单"
    )
    reason: Mapped[str] = mapped_column(String(500), default="", comment="原因")
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True, comment="生效日期")
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, comment="失效日期")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True, comment="enabled/disabled")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")


class HrEmployment(BaseModel):
    """人事事务单据（入职 / 调岗 / 离职 / 返聘）。

    状态机：`draft → approving → approved → effective`；`rejected`（可改后重提）；
    `withdrawn` 回到 `draft`。

    **审批通过 ≠ 生效**：离职单需要"择时生效"（离职当日回收权限），
    因此副作用统一由 `POST /hr/employments/{id}/effect` 触发
    （`hr/employment.py::effect_employment`）。
    """

    __tablename__ = "hr_employment"
    __table_args__ = (
        Index("ix_hr_employment_event_status", "event_type", "status"),
        Index("ix_hr_employment_employee", "employee_id"),
    )

    emp_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="人事事务单号 EM...")
    event_type: Mapped[str] = mapped_column(
        String(16), index=True, comment="事务类型 onboard入职/transfer调岗/resign离职/rehire返聘"
    )
    employee_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="员工 hr_employee.id")
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="关联账号 sys_user.id")
    user_name: Mapped[str] = mapped_column(String(64), default="", comment="员工姓名快照")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="原部门")
    dept_name: Mapped[str] = mapped_column(String(64), default="", comment="原部门名称")
    new_dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="新部门")
    new_dept_name: Mapped[str] = mapped_column(String(64), default="", comment="新部门名称")
    position_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="原岗位")
    position_name: Mapped[str] = mapped_column(String(64), default="", comment="原岗位名称")
    new_position_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="新岗位")
    new_position_name: Mapped[str] = mapped_column(String(64), default="", comment="新岗位名称")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True, comment="生效日期")
    reason: Mapped[str] = mapped_column(String(500), default="", comment="事由")
    status: Mapped[str] = mapped_column(
        String(16), default="draft", index=True, comment="draft/approving/approved/effective/rejected"
    )
    flow_instance_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="审批实例 approval_instance.id"
    )
    applicant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="申请人 id")
    applicant_name: Mapped[str] = mapped_column(String(64), default="", comment="申请人姓名")
    approver_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="批准人 id")
    approver_name: Mapped[str] = mapped_column(String(64), default="", comment="批准人姓名")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="批准时间")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")


class HrEmploymentEvent(AppendOnlyModel):
    """人事事务变更轨迹（**只追加**）—— 可回溯任一历史时点的人事状态。

    与 `hr_authorization_event` 同构：继承 `AppendOnlyModel`，没有 deleted /
    version / update_* 列，接口层不提供 update / delete。
    """

    __tablename__ = "hr_employment_event"
    __table_args__ = (
        Index("ix_hr_emp_event_emp_id_at", "employment_id", "effective_at"),
        Index("ix_hr_emp_event_emp_no", "emp_no"),
    )

    employment_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="人事事务 id")
    emp_no: Mapped[str] = mapped_column(String(32), default="", comment="单号快照")
    event_type: Mapped[str] = mapped_column(
        String(32), default="", comment="事件类型 create/submit/approve/reject/effect/withdraw"
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
    snapshot: Mapped[str] = mapped_column(Text, default="", comment="变更时点的人事事务快照 JSON")


class HrDelegate(BaseModel):
    """代理人配置（关键岗位 A/B 角 / 临时代理）。

    HR docx 2.3：「代理人配置（关键岗位 AB 角，离岗自动接管，**不借账号**）」。
    代理只是**授权与职责的临时转授记录**，不会创建第二个系统账号；
    委托人离职生效时自动失效（`auto_takeover=1` 的记录由 B 角接管）。
    """

    __tablename__ = "hr_delegate"
    __table_args__ = (
        Index("ix_hr_delegate_principal", "principal_id", "status"),
        Index("ix_hr_delegate_agent", "agent_id", "status"),
    )

    principal_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="委托人 sys_user.id")
    principal_name: Mapped[str] = mapped_column(String(64), default="", comment="委托人姓名")
    agent_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="代理人 sys_user.id")
    agent_name: Mapped[str] = mapped_column(String(64), default="", comment="代理人姓名")
    scope: Mapped[str] = mapped_column(
        String(32), default="position", index=True, comment="代理范围 position岗位AB角/auth授权/task任务"
    )
    position_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="关联岗位 hr_position.id"
    )
    auth_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="关联授权 hr_authorization.id"
    )
    reason: Mapped[str] = mapped_column(String(500), default="", comment="事由")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True, comment="生效时间")
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True, comment="失效时间")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True, comment="enabled/expired/revoked")
    auto_takeover: Mapped[int] = mapped_column(Integer, default=0, comment="委托人离岗自动接管标记")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")


class HrOrgChange(AppendOnlyModel):
    """组织变更轨迹（**只追加**）—— 部门 / 岗位的历史版本留存。

    HR docx 2.1 要求组织架构「多层级 + 历史版本」；这里每次部门 / 岗位的
    增删改都留一份 before/after 快照，可回溯任一时点的组织形态。
    """

    __tablename__ = "hr_org_change"
    __table_args__ = (
        Index("ix_hr_org_change_obj", "object_type", "object_id", "effective_at"),
    )

    object_type: Mapped[str] = mapped_column(
        String(16), index=True, comment="对象类型 dept部门/position岗位/employee员工"
    )
    object_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="对象 id")
    object_name: Mapped[str] = mapped_column(String(128), default="", comment="对象名称快照")
    change_type: Mapped[str] = mapped_column(
        String(32), default="", comment="变更类型 create/update/move/disable/enable"
    )
    before_json: Mapped[str] = mapped_column(Text, default="", comment="变更前快照 JSON")
    after_json: Mapped[str] = mapped_column(Text, default="", comment="变更后快照 JSON")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="操作人 id")
    operator_name: Mapped[str] = mapped_column(String(64), default="", comment="操作人姓名")
    effective_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=3), nullable=True, index=True, comment="生效时间（毫秒精度）"
    )
    reason: Mapped[str] = mapped_column(String(500), default="", comment="变更原因")

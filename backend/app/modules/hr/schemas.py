"""人事行政模块接口 Schemas。"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator

from app.core.schemas import CamelModel
from app.modules.hr.authorization import AUTH_TYPES, ROLE_CODES
from app.modules.hr.constants import (
    CONTROL_TYPES,
    DELEGATE_SCOPES,
    EMPLOY_STATUSES,
    EMPLOY_TYPES,
    EVENT_TYPES,
    KEY_ROLES,
    POSITION_TYPES,
)


class TimesheetIn(CamelModel):
    """工时填报/编辑入参：submit=true 表示保存并直接提交。"""

    task_id: int
    work_date: date
    hours: Decimal = Field(gt=0, le=24)
    content: str = Field(min_length=1, max_length=500)
    remark: str = Field(default="", max_length=500)
    submit: bool = False

    @field_validator("hours")
    @classmethod
    def _half_step(cls, v: Decimal) -> Decimal:
        if v * 2 != int(v * 2):
            raise ValueError("工时须以 0.5 小时为步进")
        return v


class TimesheetPrefillIn(CamelModel):
    """AI 工时预填入参：按任务+日期生成草稿（不落库）。"""

    task_id: int
    work_date: date


class AuthorizationIn(CamelModel):
    """人员授权新建/编辑入参。"""

    user_id: int
    auth_type: str = Field("test_item", max_length=32)
    role_code: str = Field("", max_length=32)
    scope_method: str = Field("", max_length=64)
    scope_params: str = Field("", max_length=255)
    scope_device_id: int | None = None
    scope_device_name: str = Field("", max_length=64)
    scope_domain: str = Field("", max_length=64)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    remark: str = Field("", max_length=500)

    @field_validator("auth_type")
    @classmethod
    def _auth_type(cls, v: str) -> str:
        if v not in AUTH_TYPES:
            raise ValueError(f"授权类型必须是 {', '.join(AUTH_TYPES)} 之一")
        return v

    @field_validator("role_code")
    @classmethod
    def _role_code(cls, v: str) -> str:
        if v and v not in ROLE_CODES:
            raise ValueError(f"角色必须是 {', '.join(ROLE_CODES)} 之一")
        return v


class AuthorizationActionIn(CamelModel):
    """授权状态动作入参（激活 / 暂停 / 恢复 / 撤销 / 过期）：原因必填由服务端按动作判定。"""

    reason: str = Field("", max_length=500)


class AuthorizationSubmitIn(CamelModel):
    """提交授权审批入参。"""

    comment: str = Field("", max_length=500)


# ============================================================================
# B10-1 HR L1：组织架构 / 员工主数据 / 人事事务
# ============================================================================


class PositionIn(CamelModel):
    """岗位新建/编辑入参（B10-1 组织架构）。"""

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    dept_id: int | None = None
    site_id: int | None = None
    position_type: str = Field("staff", max_length=16)
    duty: str = Field("", max_length=4000)
    requirement: str = Field("", max_length=4000)
    report_to_id: int | None = None
    key_role: str = Field("", max_length=32)
    primary_user_id: int | None = None
    backup_user_id: int | None = None
    status: str = Field("enabled", max_length=16)
    remark: str = Field("", max_length=500)

    @field_validator("position_type")
    @classmethod
    def _position_type(cls, v: str) -> str:
        if v not in POSITION_TYPES:
            raise ValueError(f"岗位类型必须是 {', '.join(POSITION_TYPES)} 之一")
        return v

    @field_validator("key_role")
    @classmethod
    def _key_role(cls, v: str) -> str:
        if v and v not in KEY_ROLES:
            raise ValueError(f"关键岗位标记必须是 {', '.join(KEY_ROLES)} 之一")
        return v


class EmployeeIn(CamelModel):
    """员工主数据新建/编辑入参（B10-1）。

    `id_no` 明文入参，服务端加密落库（`enc:` 前缀）；出参一律掩码。
    """

    employee_no: str = Field(min_length=1, max_length=32)
    user_id: int | None = None
    name: str = Field(min_length=1, max_length=64)
    id_no: str = Field("", max_length=64)
    id_type: str = Field("id_card", max_length=16)
    gender: str = Field("", max_length=8)
    birth_date: date | None = None
    education: str = Field("", max_length=32)
    major: str = Field("", max_length=64)
    mobile: str = Field("", max_length=32)
    email: str = Field("", max_length=128)
    employ_type: str = Field("labor", max_length=16)
    employ_status: str = Field("probation", max_length=16)
    dept_id: int | None = None
    position_id: int | None = None
    hire_date: date | None = None
    leave_date: date | None = None
    contract_no: str = Field("", max_length=64)
    contract_start: date | None = None
    contract_end: date | None = None
    emergency_contact: str = Field("", max_length=64)
    emergency_mobile: str = Field("", max_length=32)
    status: str = Field("enabled", max_length=16)
    remark: str = Field("", max_length=500)

    @field_validator("employ_type")
    @classmethod
    def _employ_type(cls, v: str) -> str:
        if v not in EMPLOY_TYPES:
            raise ValueError(f"雇佣类型必须是 {', '.join(EMPLOY_TYPES)} 之一")
        return v

    @field_validator("employ_status")
    @classmethod
    def _employ_status(cls, v: str) -> str:
        if v not in EMPLOY_STATUSES:
            raise ValueError(f"在职状态必须是 {', '.join(EMPLOY_STATUSES)} 之一")
        return v


class EmployeeControlIn(CamelModel):
    """员工名单管控（黑白名单）入参。"""

    control_type: str = Field("blacklist", max_length=16)
    reason: str = Field("", max_length=500)
    effective_from: date | None = None
    effective_to: date | None = None
    status: str = Field("enabled", max_length=16)
    remark: str = Field("", max_length=500)

    @field_validator("control_type")
    @classmethod
    def _control_type(cls, v: str) -> str:
        if v not in CONTROL_TYPES:
            raise ValueError(f"名单类型必须是 {', '.join(CONTROL_TYPES)} 之一")
        return v


class EmploymentIn(CamelModel):
    """人事事务单据新建/编辑入参（B10-1）。"""

    event_type: str = Field("onboard", max_length=16)
    employee_id: int
    new_dept_id: int | None = None
    new_position_id: int | None = None
    effective_date: date | None = None
    reason: str = Field("", max_length=500)
    remark: str = Field("", max_length=500)
    # 入职专用：同时开通系统账号
    create_account: bool = False
    username: str = Field("", max_length=64)
    password: str = Field("", max_length=128)
    role_ids: list[int] = []

    @field_validator("event_type")
    @classmethod
    def _event_type(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(f"事务类型必须是 {', '.join(EVENT_TYPES)} 之一")
        return v


class EmploymentActionIn(CamelModel):
    """人事事务动作入参（提交 / 撤回 / 生效）：原因由服务端按动作判定。"""

    comment: str = Field("", max_length=500)
    reason: str = Field("", max_length=500)


class DelegateIn(CamelModel):
    """代理人配置入参（B10-1 AB 角 / 临时代理）。"""

    principal_id: int
    agent_id: int
    scope: str = Field("position", max_length=32)
    position_id: int | None = None
    auth_id: int | None = None
    reason: str = Field("", max_length=500)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    auto_takeover: int = 0
    remark: str = Field("", max_length=500)

    @field_validator("scope")
    @classmethod
    def _scope(cls, v: str) -> str:
        if v not in DELEGATE_SCOPES:
            raise ValueError(f"代理范围必须是 {', '.join(DELEGATE_SCOPES)} 之一")
        return v

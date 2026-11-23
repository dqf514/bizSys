"""人事行政模块接口 Schemas。"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator

from app.core.schemas import CamelModel
from app.modules.hr.authorization import AUTH_TYPES, ROLE_CODES


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

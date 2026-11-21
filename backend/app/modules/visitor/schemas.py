"""访客与安全域（B3）入参模型。"""

from datetime import datetime

from pydantic import Field

from app.core.schemas import CamelModel

VISITOR_TYPES = "^(customer|regulator|supplier|courier|temp|outsourced|partner|staff)$"
VISITOR_SOURCES = "^(web|wechat|miniprogram|invite|onsite|partner)$"
ZONE_TYPES = "^(public|welcome|sample|test|prepare|production|tool|datacenter)$"


class ZoneIn(CamelModel):
    """区域与分级维护。"""

    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    zone_type: str = Field("public", pattern=ZONE_TYPES)
    security_level: int = Field(1, ge=1, le=4)
    need_extra_approval: bool = False
    need_escort: bool = False
    need_nda: bool = False
    need_dual_person: bool = False
    camera_control: bool = False
    device_binding: str = Field("", max_length=255)
    capacity: int = Field(0, ge=0)
    status: str = Field("enabled", pattern="^(enabled|disabled)$")
    remark: str = Field("", max_length=2000)


class VisitIn(CamelModel):
    """访客预约 / 登记（多渠道统一入口）。"""

    visitor_name: str = Field(..., min_length=1, max_length=64)
    visitor_company: str = Field("", max_length=128)
    visitor_type: str = Field("customer", pattern=VISITOR_TYPES)
    id_no: str = Field("", max_length=64)
    phone: str = Field("", max_length=32)
    plate_no: str = Field("", max_length=32)
    host_user_id: int | None = None
    host_name: str = Field("", max_length=64)
    host_dept_id: int | None = None
    host_dept_name: str = Field("", max_length=64)
    purpose: str = Field("", max_length=255)
    source: str = Field("web", pattern=VISITOR_SOURCES)
    zone_ids: str = Field("", max_length=1000, description="可进入区域 id 列表，逗号分隔")
    escort_names: str = Field("", max_length=500, description="陪同与见证人，逗号分隔")
    plan_start: datetime | None = None
    plan_end: datetime | None = None
    staff_id: int | None = None
    customer_id: int | None = None
    customer_name: str = Field("", max_length=128)
    remark: str = Field("", max_length=2000)


class VisitApprovalIn(CamelModel):
    """访客审批：被访人 / 部门 / 敏感区域逐级通过或驳回。"""

    level: str = Field("", max_length=32, description="留空表示按当前待审层级自动推进")
    action: str = Field(..., pattern="^(approve|reject)$")
    comment: str = Field("", max_length=1000)


class VisitCheckIn(CamelModel):
    """签入 / 签出。"""

    method: str = Field("qrcode", pattern="^(qrcode|face|ic|plate|manual)$")
    device_id: str = Field("", max_length=64)
    credential_no: str = Field("", max_length=32)
    remark: str = Field("", max_length=500)


class CredentialVerifyIn(CamelModel):
    """凭证核验（门禁 / 闸机 / 梯控回传）。"""

    credential_no: str = Field(..., min_length=1, max_length=32)
    zone_id: int | None = None
    method: str = Field("qrcode", pattern="^(qrcode|face|ic|plate|manual)$")
    device_id: str = Field("", max_length=64)
    direction: str = Field("in", pattern="^(in|out)$")


class NdaIn(CamelModel):
    """NDA 电子签。"""

    title: str = Field("", max_length=128)
    template: str = Field("standard", max_length=32)
    visitor_name: str = Field(..., min_length=1, max_length=64)
    visitor_company: str = Field("", max_length=128)
    signer_title: str = Field("", max_length=64)
    id_no: str = Field("", max_length=64)
    signature_data: str = Field("", max_length=200000, description="手写签名图片 base64")
    visit_id: int | None = None
    staff_id: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    remark: str = Field("", max_length=500)


class BlacklistIn(CamelModel):
    """黑名单维护。"""

    visitor_name: str = Field(..., min_length=1, max_length=64)
    id_no: str = Field("", max_length=64)
    phone: str = Field("", max_length=32)
    company: str = Field("", max_length=128)
    reason: str = Field("", max_length=255)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    source: str = Field("manual", max_length=32)
    status: str = Field("enabled", pattern="^(enabled|disabled)$")
    remark: str = Field("", max_length=2000)


class HandoverIn(CamelModel):
    """样品 / 样车交接登记。"""

    visit_id: int | None = None
    sample_no: str = Field(..., min_length=1, max_length=64)
    sample_name: str = Field("", max_length=128)
    barcode: str = Field("", max_length=64)
    sample_type: str = Field("sample", pattern="^(sample|vehicle|model)$")
    qty: int = Field(1, ge=1)
    handover_user_name: str = Field("", max_length=64)
    receive_user_name: str = Field("", max_length=64)
    remark: str = Field("", max_length=500)


class AlertHandleIn(CamelModel):
    """预警处置。"""

    status: str = Field(..., pattern="^(handled|ignored)$")
    handle_remark: str = Field("", max_length=1000)

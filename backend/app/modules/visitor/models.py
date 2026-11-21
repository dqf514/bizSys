"""访客与安全域（B3）模型。

覆盖 CSV 6–17 的数据落点：
区域分级（vis_zone）、访客登记与审批（vis_visit / vis_approval）、
凭证通行（vis_credential）、合规审计（vis_access_log，只追加不可删改）、
NDA 电子签（vis_nda）、黑名单（vis_blacklist）、样品样车交接（vis_sample_handover）、
滞留/闯入/尾随预警（vis_alert）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel
from app.core.db import Base


class AppendOnlyModel(Base):
    """只追加基类 —— 合规审计日志。

    刻意**不继承** `BaseModel`：没有 `deleted` / `version` / `update_*`，
    从数据模型层面保证"日志不可删改"；接口层同样不提供 update / delete。
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="写入时间")


class VisitorZone(BaseModel):
    """区域与分级（公共接待区 / 样车接收区 / 试验区 / 准备区 / 生产加工区 / 工具仪器间 / 数据机房）。"""

    __tablename__ = "vis_zone"

    code: Mapped[str] = mapped_column(String(32), comment="区域编码")
    name: Mapped[str] = mapped_column(String(64), comment="区域名称")
    zone_type: Mapped[str] = mapped_column(String(32), default="public", comment="区域类型")
    security_level: Mapped[int] = mapped_column(Integer, default=1, comment="安全等级 1-4")
    need_extra_approval: Mapped[int] = mapped_column(Integer, default=0, comment="敏感区域需额外审批")
    need_escort: Mapped[int] = mapped_column(Integer, default=0, comment="需陪同")
    need_nda: Mapped[int] = mapped_column(Integer, default=0, comment="需签保密协议")
    need_dual_person: Mapped[int] = mapped_column(Integer, default=0, comment="高危作业需双人")
    camera_control: Mapped[int] = mapped_column(Integer, default=0, comment="手机相机管控")
    device_binding: Mapped[str] = mapped_column(
        String(255), default="", comment="联动设备 gate/turnstile/lift/video/lims/oa/fire"
    )
    capacity: Mapped[int] = mapped_column(Integer, default=0, comment="同时在场人数上限，0 不限")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="enabled/disabled")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")


class VisitorVisit(BaseModel):
    """访客预约 / 登记单。"""

    __tablename__ = "vis_visit"

    visit_no: Mapped[str] = mapped_column(String(32), default="", comment="访客单号")
    visitor_name: Mapped[str] = mapped_column(String(64), comment="访客姓名")
    visitor_company: Mapped[str] = mapped_column(String(128), default="", comment="访客单位")
    visitor_type: Mapped[str] = mapped_column(String(32), default="customer", comment="访客类型")
    id_no: Mapped[str] = mapped_column(String(64), default="", comment="证件号")
    phone: Mapped[str] = mapped_column(String(32), default="", comment="联系电话")
    plate_no: Mapped[str] = mapped_column(String(32), default="", comment="车牌号")
    host_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="被访人 id")
    host_name: Mapped[str] = mapped_column(String(64), default="", comment="被访人姓名")
    host_dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="被访部门 id")
    host_dept_name: Mapped[str] = mapped_column(String(64), default="", comment="被访部门")
    purpose: Mapped[str] = mapped_column(String(255), default="", comment="来访事由")
    source: Mapped[str] = mapped_column(String(16), default="web", comment="来源 web/wechat/miniprogram/invite/onsite")
    zone_ids: Mapped[str] = mapped_column(Text, default="", comment="可进入区域 id 列表，逗号分隔")
    escort_names: Mapped[str] = mapped_column(Text, default="", comment="陪同与见证人，逗号分隔")
    plan_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="计划进入")
    plan_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="计划离开")
    checkin_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="实际签入")
    checkout_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="实际签出")
    status: Mapped[str] = mapped_column(
        String(16), default="pending", comment="pending/approved/rejected/visiting/left/overdue/cancelled"
    )
    required_levels: Mapped[str] = mapped_column(String(64), default="", comment="需要的审批层级，逗号分隔")
    approved_levels: Mapped[str] = mapped_column(String(64), default="", comment="已通过的审批层级")
    nda_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="关联 NDA")
    credential_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="关联通行凭证")
    credential_no: Mapped[str] = mapped_column(String(32), default="", comment="凭证编号")
    staff_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="客户方人员备案 id")
    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="关联往来单位 id")
    customer_name: Mapped[str] = mapped_column(String(128), default="", comment="关联往来单位")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")


class VisitorApproval(BaseModel):
    """访客审批记录（被访人 / 部门 / 敏感区域 逐级审批）。"""

    __tablename__ = "vis_approval"

    visit_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="访客单 id")
    level: Mapped[str] = mapped_column(String(32), comment="审批层级 host/dept/zone/security")
    approver_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="审批人 id")
    approver_name: Mapped[str] = mapped_column(String(64), default="", comment="审批人姓名")
    action: Mapped[str] = mapped_column(String(16), comment="approve/reject")
    comment: Mapped[str] = mapped_column(Text, default="", comment="审批意见")
    decided_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="审批时间")


class VisitorCredential(BaseModel):
    """通行凭证（二维码 / 人脸 / IC 卡 / 车牌），按"人 + 时间 + 区域"下发最小权限。"""

    __tablename__ = "vis_credential"

    credential_no: Mapped[str] = mapped_column(String(32), default="", comment="凭证编号")
    visit_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="访客单 id")
    visitor_name: Mapped[str] = mapped_column(String(64), default="", comment="访客姓名")
    credential_type: Mapped[str] = mapped_column(String(16), default="qrcode", comment="qrcode/face/ic/plate")
    zone_ids: Mapped[str] = mapped_column(Text, default="", comment="授权区域 id 列表")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="生效时间")
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="失效时间")
    status: Mapped[str] = mapped_column(String(16), default="issued", comment="issued/used/expired/revoked")
    code: Mapped[str] = mapped_column(String(255), default="", comment="凭证载荷（二维码内容 / 卡号）")
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近核验时间")
    used_count: Mapped[int] = mapped_column(Integer, default=0, comment="核验次数")


class VisitorAccessLog(AppendOnlyModel):
    """合规审计日志 —— **只追加**，不可删改，保留期 ≥180 天。

    记录通行核验、签入签出、区域进出、闯入与尾随等事件；接口层不提供 update / delete。
    """

    __tablename__ = "vis_access_log"

    visit_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="访客单 id")
    credential_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="凭证 id")
    credential_no: Mapped[str] = mapped_column(String(32), default="", comment="凭证编号")
    visitor_name: Mapped[str] = mapped_column(String(64), default="", comment="访客姓名")
    zone_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="区域 id")
    zone_name: Mapped[str] = mapped_column(String(64), default="", comment="区域名称")
    direction: Mapped[str] = mapped_column(String(8), default="", comment="in/out")
    event_type: Mapped[str] = mapped_column(
        String(32), default="checkin", comment="checkin/checkout/zone_enter/zone_leave/denied/tailgating/intrusion"
    )
    method: Mapped[str] = mapped_column(String(16), default="qrcode", comment="核验方式")
    result: Mapped[str] = mapped_column(String(8), default="pass", comment="pass/deny")
    device_id: Mapped[str] = mapped_column(String(64), default="", comment="门禁 / 闸机 / 梯控设备号")
    operator_name: Mapped[str] = mapped_column(String(64), default="", comment="操作人")
    happened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="事件时间")
    detail: Mapped[str] = mapped_column(Text, default="", comment="明细")


class VisitorNda(BaseModel):
    """NDA 电子签（CNAS 保密要求：访客进场前签署并留证）。"""

    __tablename__ = "vis_nda"

    nda_no: Mapped[str] = mapped_column(String(32), default="", comment="NDA 编号")
    title: Mapped[str] = mapped_column(String(128), default="", comment="协议标题")
    template: Mapped[str] = mapped_column(String(32), default="standard", comment="模板版本")
    visitor_name: Mapped[str] = mapped_column(String(64), default="", comment="签署人姓名")
    visitor_company: Mapped[str] = mapped_column(String(128), default="", comment="签署人单位")
    signer_title: Mapped[str] = mapped_column(String(64), default="", comment="职务")
    id_no: Mapped[str] = mapped_column(String(64), default="", comment="证件号")
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="签署时间")
    signature_data: Mapped[str] = mapped_column(Text, default="", comment="签名数据（手写签名图片 base64）")
    evidence_hash: Mapped[str] = mapped_column(String(64), default="", comment="存证哈希（防篡改）")
    ip: Mapped[str] = mapped_column(String(64), default="", comment="签署 IP")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="生效时间")
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="失效时间")
    status: Mapped[str] = mapped_column(String(16), default="signed", comment="signed/expired/revoked")
    visit_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="关联访客单")
    staff_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="客户方人员备案 id")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")


class VisitorBlacklist(BaseModel):
    """黑名单（闯入 / 尾随 / 失信人员禁止入内）。"""

    __tablename__ = "vis_blacklist"

    visitor_name: Mapped[str] = mapped_column(String(64), default="", comment="姓名")
    id_no: Mapped[str] = mapped_column(String(64), default="", comment="证件号")
    phone: Mapped[str] = mapped_column(String(32), default="", comment="联系电话")
    company: Mapped[str] = mapped_column(String(128), default="", comment="单位")
    reason: Mapped[str] = mapped_column(String(255), default="", comment="列入原因")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="生效时间")
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="失效时间")
    source: Mapped[str] = mapped_column(String(32), default="manual", comment="来源")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="enabled/disabled")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")


class VisitorSampleHandover(BaseModel):
    """样品 / 样车交接联动（送样人 + 样品条码 + 交接时间 + 接收人，可反查）。"""

    __tablename__ = "vis_sample_handover"

    handover_no: Mapped[str] = mapped_column(String(32), default="", comment="交接单号")
    visit_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="访客单 id")
    sample_no: Mapped[str] = mapped_column(String(64), default="", index=True, comment="样品 / 样车编号")
    sample_name: Mapped[str] = mapped_column(String(128), default="", comment="样品名称")
    barcode: Mapped[str] = mapped_column(String(64), default="", comment="条码")
    sample_type: Mapped[str] = mapped_column(String(16), default="sample", comment="sample/vehicle/model")
    qty: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    handover_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="送样人 id")
    handover_user_name: Mapped[str] = mapped_column(String(64), default="", comment="送样人")
    receive_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="接收人 id")
    receive_user_name: Mapped[str] = mapped_column(String(64), default="", comment="接收人")
    handover_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="交接时间")
    status: Mapped[str] = mapped_column(String(16), default="done", comment="done/returned")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")


class VisitorAlert(BaseModel):
    """预警：滞留超时、闯入、尾随、越权访问、黑名单命中。"""

    __tablename__ = "vis_alert"

    visit_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="访客单 id")
    alert_type: Mapped[str] = mapped_column(
        String(32), default="overstay", comment="overstay/tailgating/intrusion/zone_denied/blacklist"
    )
    level: Mapped[str] = mapped_column(String(16), default="medium", comment="low/medium/high")
    zone_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="区域 id")
    zone_name: Mapped[str] = mapped_column(String(64), default="", comment="区域名称")
    message: Mapped[str] = mapped_column(String(255), default="", comment="预警描述")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="发生时间")
    status: Mapped[str] = mapped_column(String(16), default="open", comment="open/handled/ignored")
    handled_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="处理人 id")
    handled_by_name: Mapped[str] = mapped_column(String(64), default="", comment="处理人")
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="处理时间")
    handle_remark: Mapped[str] = mapped_column(Text, default="", comment="处理说明")

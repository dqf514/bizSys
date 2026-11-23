"""人员授权台账（B9-C3 / HR L2 授权管理 / 合规 3.1「人员能力」）。

检测机构的灵魂控制点：**未授权不得操作对应的检测活动**（HR docx 3.4/3.5）。
本模块提供三件事：

1. **授权状态机**：draft → confirmed → active ⇄ suspended → expired / revoked，
   暂停与撤销原因必填；每次状态变更写**只追加**的变更轨迹（可回溯任一历史时点）。
2. **授权校验**：`check_authorization()` 单条 SELECT 走复合索引 + Python 侧维度匹配；
   `assert_authorized()` 是业务侧的统一拦截入口（超管旁路 + 双开关兜底）。
3. **时点回放**：`state_at()` 按事件轨迹回放某历史时刻的授权状态。

设计取舍：
- **不做跨请求缓存** —— 撤销必须立即生效；只在**单次请求内** memo（`db.info`）。
- **作用域只认显式列**（scope_method / scope_device_id / scope_domain），
  `scope_json` 只是展示快照，避免"快照里恰好有值"变成隐性授权。
- **超管旁路 + `auth.enforce.*` 双开关**：机制上线与业务推行节奏解耦，
  出问题可以运行时关掉而不回滚代码。
"""

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.hr.models import HrAuthorization, HrAuthorizationEvent

# ---------------- 常量 ----------------

AUTH_TYPE_TEST_ITEM = "test_item"
AUTH_TYPE_DEVICE = "device"
AUTH_TYPE_REPORT_ROLE = "report_role"
AUTH_TYPE_SIGNER = "signer"

AUTH_TYPES = (AUTH_TYPE_TEST_ITEM, AUTH_TYPE_DEVICE, AUTH_TYPE_REPORT_ROLE, AUTH_TYPE_SIGNER)

ROLE_PREPARER = "preparer"  # 编制
ROLE_REVIEWER = "reviewer"  # 复核
ROLE_APPROVER = "approver"  # 批准
ROLE_SIGNER = "signer"  # 签字

ROLE_CODES = (ROLE_PREPARER, ROLE_REVIEWER, ROLE_APPROVER, ROLE_SIGNER)

STATUS_DRAFT = "draft"
STATUS_APPROVING = "approving"
STATUS_CONFIRMED = "confirmed"
STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"
STATUS_EXPIRED = "expired"
STATUS_REVOKED = "revoked"
STATUS_REJECTED = "rejected"

# 合法状态跃迁（其余一律拒绝 —— 状态机在数据层兜底，不靠前端）
TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATUS_DRAFT: (STATUS_APPROVING, STATUS_CONFIRMED, STATUS_REJECTED),
    STATUS_APPROVING: (STATUS_CONFIRMED, STATUS_REJECTED, STATUS_DRAFT),
    STATUS_CONFIRMED: (STATUS_ACTIVE, STATUS_REVOKED, STATUS_EXPIRED),
    STATUS_ACTIVE: (STATUS_SUSPENDED, STATUS_REVOKED, STATUS_EXPIRED),
    STATUS_SUSPENDED: (STATUS_ACTIVE, STATUS_REVOKED, STATUS_EXPIRED),
    STATUS_EXPIRED: (),
    STATUS_REVOKED: (),
    STATUS_REJECTED: (STATUS_DRAFT, STATUS_APPROVING),
}

# 需要填写原因的跃迁
REASON_REQUIRED = (STATUS_SUSPENDED, STATUS_REVOKED, STATUS_EXPIRED)

# 授权类型 → 强制开关键（关掉即不拦截）
ENFORCE_KEYS = {
    AUTH_TYPE_REPORT_ROLE: "auth.enforce.report",
    AUTH_TYPE_TEST_ITEM: "auth.enforce.task",
    AUTH_TYPE_DEVICE: "auth.enforce.task",
    AUTH_TYPE_SIGNER: "auth.enforce.report",
}

# 授予"有效"授权的状态
_EFFECTIVE_STATUS = (STATUS_ACTIVE,)


@dataclass
class AuthCheck:
    """授权校验结论。"""

    allowed: bool
    reason: str = ""
    authorization_id: int | None = None
    auth_no: str = ""
    status: str = ""
    bypassed: bool = False  # 是否走了超管旁路 / 开关关闭

    def out(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "authorizationId": self.authorization_id,
            "authNo": self.auth_no,
            "status": self.status,
            "bypassed": self.bypassed,
        }


# ---------------- 基础工具 ----------------


def _now() -> datetime:
    return datetime.now()


def _is_super(user) -> bool:
    try:
        return "super" in (user.role_codes or [])
    except Exception:  # noqa: BLE001
        return False


def _enforce_enabled(db: Session, auth_type: str) -> bool:
    """该授权类型的强制开关是否打开（默认开）。"""
    key = ENFORCE_KEYS.get(auth_type)
    if not key:
        return True
    cached = db.info.get(f"_auth_enforce_{key}")
    if cached is not None:
        return bool(cached)
    value = True
    try:
        from app.modules.settings.service import get_value

        raw = str(get_value(db, key, "1")).strip().lower()
        value = raw not in {"0", "false", "no", "off"}
    except Exception:  # noqa: BLE001 配置读不到按默认（拦截）
        value = True
    db.info[f"_auth_enforce_{key}"] = value
    return value


def snapshot(a: HrAuthorization) -> dict:
    """授权快照（写事件表用）。"""
    return {
        "authNo": a.auth_no,
        "userId": a.user_id,
        "userName": a.user_name,
        "authType": a.auth_type,
        "roleCode": a.role_code,
        "scopeMethod": a.scope_method,
        "scopeDeviceId": a.scope_device_id,
        "scopeDomain": a.scope_domain,
        "validFrom": a.valid_from.isoformat(timespec="seconds") if a.valid_from else "",
        "validTo": a.valid_to.isoformat(timespec="seconds") if a.valid_to else "",
        "status": a.status,
    }


def out(a: HrAuthorization) -> dict:
    """授权行输出（camelCase）。"""
    return {
        "id": a.id,
        "authNo": a.auth_no,
        "userId": a.user_id,
        "userName": a.user_name,
        "deptId": a.dept_id,
        "deptName": a.dept_name,
        "authType": a.auth_type,
        "roleCode": a.role_code,
        "scopeMethod": a.scope_method,
        "scopeParams": a.scope_params,
        "scopeDeviceId": a.scope_device_id,
        "scopeDeviceName": a.scope_device_name,
        "scopeDomain": a.scope_domain,
        "validFrom": a.valid_from.isoformat(timespec="seconds") if a.valid_from else "",
        "validTo": a.valid_to.isoformat(timespec="seconds") if a.valid_to else "",
        "status": a.status,
        "applicantId": a.applicant_id,
        "applicantName": a.applicant_name,
        "approverId": a.approver_id,
        "approverName": a.approver_name,
        "approvedAt": a.approved_at.isoformat(timespec="seconds") if a.approved_at else "",
        "activatedAt": a.activated_at.isoformat(timespec="seconds") if a.activated_at else "",
        "flowInstanceId": a.flow_instance_id,
        "lastReason": a.last_reason or "",
        "remark": a.remark or "",
        "createTime": a.create_time.isoformat(timespec="seconds") if a.create_time else "",
    }


# ---------------- 事件（只追加） ----------------


def write_event(
    db: Session,
    a: HrAuthorization,
    *,
    event_type: str,
    from_status: str,
    to_status: str,
    operator_id: int | None = None,
    operator_name: str = "",
    reason: str = "",
    effective_at: datetime | None = None,
) -> HrAuthorizationEvent:
    """写一条授权变更事件（只追加）。"""
    ev = HrAuthorizationEvent(
        authorization_id=a.id,
        auth_no=a.auth_no,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        operator_id=operator_id,
        operator_name=operator_name or "",
        reason=reason or "",
        effective_at=effective_at or _now(),
        snapshot=json.dumps(snapshot(a), ensure_ascii=False),
    )
    db.add(ev)
    db.flush()
    return ev


def timeline(db: Session, authorization_id: int) -> list[dict]:
    """授权变更轨迹（倒序）。"""
    rows = db.scalars(
        select(HrAuthorizationEvent)
        .where(HrAuthorizationEvent.authorization_id == authorization_id)
        .order_by(HrAuthorizationEvent.id.desc())
    ).all()
    return [
        {
            "id": e.id,
            "eventType": e.event_type,
            "fromStatus": e.from_status,
            "toStatus": e.to_status,
            "operatorId": e.operator_id,
            "operatorName": e.operator_name,
            "reason": e.reason or "",
            "effectiveAt": e.effective_at.isoformat(timespec="seconds") if e.effective_at else "",
            "createTime": e.create_time.isoformat(timespec="seconds") if e.create_time else "",
        }
        for e in rows
    ]


def state_at(db: Session, authorization_id: int, at: datetime) -> dict:
    """回放事件轨迹，返回**该时刻**的授权状态。

    HR docx 要求「可回溯任一历史时点状态」—— 授权当时有效，才认可当时的操作。
    """
    rows = db.scalars(
        select(HrAuthorizationEvent)
        .where(HrAuthorizationEvent.authorization_id == authorization_id)
        .order_by(HrAuthorizationEvent.effective_at, HrAuthorizationEvent.id)
    ).all()
    status = ""
    effective_at = None
    reason = ""
    for e in rows:
        when = e.effective_at or e.create_time
        if when is not None and when <= at:
            status = e.to_status
            effective_at = when
            reason = e.reason or ""
        else:
            break
    return {
        "authorizationId": authorization_id,
        "at": at.isoformat(timespec="seconds"),
        "status": status,
        "effectiveAt": effective_at.isoformat(timespec="seconds") if effective_at else "",
        "reason": reason,
        "effective": status in _EFFECTIVE_STATUS,
    }


# ---------------- 状态机 ----------------


def assert_transition(a: HrAuthorization, to_status: str, reason: str = "") -> None:
    """状态跃迁守卫（非法跃迁 / 缺原因一律拒绝）。"""
    allowed = TRANSITIONS.get(a.status, ())
    if to_status not in allowed:
        raise BizException(
            R.HR_AUTH_INVALID_STATE,
            f"授权状态「{a.status}」不允许变更为「{to_status}」",
        )
    if to_status in REASON_REQUIRED and not (reason or "").strip():
        raise BizException(R.HR_AUTH_INVALID_STATE, f"变更为「{to_status}」必须填写原因")


def transition(
    db: Session,
    a: HrAuthorization,
    to_status: str,
    *,
    event_type: str,
    operator_id: int | None = None,
    operator_name: str = "",
    reason: str = "",
) -> HrAuthorization:
    """执行状态跃迁：守卫 → 改状态 → 写事件 → 写字段级审计（strict）。"""
    from_status = a.status
    assert_transition(a, to_status, reason)
    a.status = to_status
    a.last_reason = reason or ""
    if to_status == STATUS_ACTIVE and not a.activated_at:
        a.activated_at = _now()
    if to_status in (STATUS_CONFIRMED,):
        a.approved_at = _now()
    a.version = (a.version or 0) + 1
    a.update_time = _now()
    db.flush()
    write_event(
        db,
        a,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        operator_id=operator_id,
        operator_name=operator_name,
        reason=reason,
    )
    audit(
        db,
        user_id=operator_id,
        module="hr",
        action=f"authorization_{event_type}",
        biz_type="hr_authorization",
        biz_id=a.id,
        field_name="status",
        old_value=from_status,
        new_value=to_status,
        reason=reason,
        detail={"authNo": a.auth_no, "userName": a.user_name, "authType": a.auth_type},
        strict=True,
    )
    return a


# ---------------- 校验 ----------------


def _scope_match(a: HrAuthorization, method: str | None, device_id: int | None, domain: str | None) -> bool:
    """作用域维度匹配：该维度留空 = 不限。"""
    if a.scope_method and method and a.scope_method != method:
        return False
    if a.scope_method and not method:
        return False
    if a.scope_device_id and device_id and int(a.scope_device_id) != int(device_id):
        return False
    if a.scope_device_id and not device_id:
        return False
    if a.scope_domain and domain and a.scope_domain != domain:
        return False
    if a.scope_domain and not domain:
        return False
    return True


def check_authorization(
    db: Session,
    *,
    user_id: int,
    auth_type: str,
    role_code: str = "",
    role_codes: tuple[str, ...] | list[str] = (),
    method: str | None = None,
    methods: list[str] | tuple[str, ...] | None = None,
    device_id: int | None = None,
    domain: str | None = None,
    at: datetime | None = None,
) -> AuthCheck:
    """查该用户在此时点是否持有有效授权（不做拦截，只回答问题）。

    作用域在 Python 侧匹配（记录维度为空 = 该维度不限）；
    走复合索引 `(user_id, auth_type, status)`。

    - `role_code` / `role_codes`：**任一**命中即可（授权行 role_code 留空 = 角色不限）。
    - `method` / `methods`：方法维度的候选集，**任一**命中即可（一个任务可能含多个依据标准）。
    """
    when = at or _now()
    stmt = select(HrAuthorization).where(
        HrAuthorization.user_id == user_id,
        HrAuthorization.auth_type == auth_type,
        HrAuthorization.deleted == 0,
    )
    rows = db.scalars(stmt).all()

    wanted = {c for c in role_codes if c}
    if role_code:
        wanted.add(role_code)
    candidates = list(methods) if methods else [method]

    role_mismatch = False
    expired = False
    for a in rows:
        if a.status not in _EFFECTIVE_STATUS:
            continue
        if wanted and a.role_code and a.role_code not in wanted:
            role_mismatch = True
            continue
        if a.valid_from and when < a.valid_from:
            continue
        if a.valid_to and when > a.valid_to:
            expired = True
            continue
        for m in candidates:
            if _scope_match(a, m, device_id, domain):
                return AuthCheck(
                    allowed=True,
                    authorization_id=a.id,
                    auth_no=a.auth_no,
                    status=a.status,
                    reason="",
                )

    if role_mismatch:
        need = "、".join(sorted(wanted)) if wanted else "不限"
        return AuthCheck(allowed=False, reason=f"持有 {auth_type} 授权但角色不匹配（需 {need}）")
    if expired:
        return AuthCheck(allowed=False, reason="授权已超过有效期")
    return AuthCheck(allowed=False, reason=f"无 {auth_type} 授权（角色 {role_code or '不限'}）")


def assert_authorized(
    db: Session,
    user,
    *,
    auth_type: str,
    role_code: str = "",
    role_codes: tuple[str, ...] | list[str] = (),
    method: str | None = None,
    methods: list[str] | tuple[str, ...] | None = None,
    device_id: int | None = None,
    domain: str | None = None,
    label: str = "",
) -> AuthCheck:
    """业务侧统一拦截入口。

    - 超管（role_code=super）旁路；
    - `auth.enforce.report` / `auth.enforce.task` 开关关闭时不拦截；
    - 否则查不到有效授权 → 抛 `HR_AUTH_DENIED`。
    """
    if _is_super(user):
        return AuthCheck(allowed=True, reason="超管旁路", bypassed=True)
    if not _enforce_enabled(db, auth_type):
        return AuthCheck(allowed=True, reason="强制开关已关闭", bypassed=True)
    result = check_authorization(
        db,
        user_id=getattr(user, "id", 0) or 0,
        auth_type=auth_type,
        role_code=role_code,
        role_codes=role_codes,
        method=method,
        methods=methods,
        device_id=device_id,
        domain=domain,
    )
    if not result.allowed:
        who = getattr(user, "name", "") or getattr(user, "username", "")
        raise BizException(
            R.HR_AUTH_DENIED,
            f"{who} {label or '该操作'}缺少有效授权：{result.reason}",
        )
    return result


def assert_sod(
    db: Session,
    *,
    preparer_id: int | None,
    reviewer_id: int | None,
    approver_id: int | None,
) -> None:
    """职责分离校验：编制 / 复核 / 批准不得为同一人。"""
    ids = [i for i in (preparer_id, reviewer_id, approver_id) if i]
    if len(ids) != len(set(ids)):
        raise BizException(R.HR_AUTH_SOD_VIOLATION, "编制 / 复核 / 批准不得由同一人担任")

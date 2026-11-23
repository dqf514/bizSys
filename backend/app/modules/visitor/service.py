"""访客与安全域（B3）业务规则：预约登记 / 逐级审批 / 凭证下发 / 签入签出 / 预警 / NDA / 黑名单 / 样品交接。

约定：接收同步 `Session` 作为首参，**不自己 commit**（由 router 统一提交）。
"""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.notify import notify, users_with_perm
from app.core import reqctx, signature
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.visitor.models import (
    VisitorAccessLog,
    VisitorAlert,
    VisitorApproval,
    VisitorBlacklist,
    VisitorCredential,
    VisitorNda,
    VisitorSampleHandover,
    VisitorVisit,
    VisitorZone,
)
from app.services.numbering import next_no

# ---------------- 字典 ----------------

VISIT_STATUS_CN = {
    "pending": "待审批",
    "approving": "审批中",
    "approved": "已通过",
    "rejected": "已驳回",
    "visiting": "在访中",
    "left": "已签离",
    "overdue": "滞留超时",
    "cancelled": "已取消",
}
VISIT_STATUSES = tuple(VISIT_STATUS_CN)

ZONE_TYPE_CN = {
    "public": "公共接待区",
    "welcome": "访客接待区",
    "sample": "样车接收区",
    "test": "试验区",
    "prepare": "准备区",
    "production": "生产加工区",
    "tool": "工具仪器间",
    "datacenter": "数据机房",
}

VISITOR_TYPE_CN = {
    "customer": "客户",
    "regulator": "监管评审",
    "supplier": "供应商",
    "courier": "快递",
    "temp": "临时工",
    "outsourced": "外包维修",
    "partner": "合作方",
    "staff": "本单位员工",
}

VISIT_SOURCE_CN = {
    "web": "网页预约",
    "wechat": "微信预约",
    "miniprogram": "小程序预约",
    "invite": "员工邀请",
    "onsite": "前台现场登记",
    "partner": "客户自助",
    "portal": "合作方门户",
}

APPROVAL_LEVEL_CN = {
    "host": "被访人审批",
    "dept": "部门审批",
    "zone": "敏感区域审批",
}
APPROVAL_LEVELS = ("host", "dept", "zone")

ALERT_TYPE_CN = {
    "overstay": "滞留超时",
    "tailgating": "尾随进入",
    "intrusion": "闯入禁区",
    "zone_denied": "越权访问",
    "blacklist": "黑名单命中",
}

CREDENTIAL_TYPE_CN = {
    "qrcode": "二维码",
    "face": "人脸",
    "ic": "IC 卡",
    "plate": "车牌",
}

MAX_CREDENTIAL_HOURS = 12
TAILGATING_WINDOW_MINUTES = 5


def _now() -> datetime:
    return datetime.now()


def _split_ids(raw: str) -> list[int]:
    out: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _join_ids(ids) -> str:
    return ",".join(str(i) for i in ids)


# ---------------- 区域 ----------------


def load_zones(db: Session, ids) -> list[VisitorZone]:
    """按 id 批量取区域（忽略已删除）。"""
    id_list = [int(i) for i in ids if str(i).strip().isdigit()]
    if not id_list:
        return []
    rows = db.scalars(select(VisitorZone).where(VisitorZone.id.in_(id_list), VisitorZone.deleted == 0)).all()
    return list(rows)


def zone_names(db: Session, ids) -> str:
    return ",".join(z.name for z in load_zones(db, ids))


# ---------------- 审批链 ----------------


def required_levels(db: Session, zone_ids) -> list[str]:
    """需要的审批层级：被访人 → 部门 → 敏感区域额外审批。"""
    levels = ["host"]
    zones = load_zones(db, zone_ids)
    if zones and any(z.need_extra_approval for z in zones):
        levels.append("zone")
    return levels


def approve_visit(
    db: Session,
    visit: VisitorVisit,
    level: str,
    action: str,
    comment: str,
    approver_id: int | None,
    approver_name: str,
) -> VisitorVisit:
    """逐级审批。全部层级通过后置为 approved 并下发通行凭证。"""
    if visit.status != "pending":
        raise BizException(R.VISITOR_INVALID_STATE, f"访客单状态不允许审批：{visit.status}")

    done = set(visit.approved_levels.split(","))
    pending = next((lv for lv in visit.required_levels.split(",") if lv and lv not in done), "")
    if not pending:
        raise BizException(R.VISITOR_INVALID_STATE, "访客单审批已全部完成")
    target = level or pending
    if target != pending:
        raise BizException(R.VISITOR_INVALID_STATE, f"当前待审层级为 {APPROVAL_LEVEL_CN.get(pending, pending)}")

    # 敏感区域要求先签保密协议
    zones = load_zones(db, _split_ids(visit.zone_ids))
    if action == "approve" and any(z.need_nda for z in zones) and not visit.nda_id:
        raise BizException(R.VISITOR_NDA_REQUIRED, "该访客涉及需签保密协议的区域，请先完成 NDA 签署")

    db.add(
        VisitorApproval(
            visit_id=visit.id,
            level=target,
            approver_id=approver_id,
            approver_name=approver_name,
            action=action,
            comment=comment,
        )
    )
    db.flush()

    if action == "reject":
        visit.status = "rejected"
        visit.remark = (visit.remark + "\n" if visit.remark else "") + f"[驳回] {comment}"
        return visit

    approved = [lv for lv in visit.approved_levels.split(",") if lv]
    approved.append(target)
    visit.approved_levels = _join_ids(approved)

    if all(lv in approved for lv in visit.required_levels.split(",") if lv):
        visit.status = "approved"
        issue_credential(db, visit)
        notify_host(db, visit, "访客申请已通过审批")
    return visit


def notify_host(db: Session, visit: VisitorVisit, content: str) -> int:
    if not visit.host_user_id:
        return 0
    return notify(
        db,
        [visit.host_user_id],
        title=f"访客申请 {visit.visit_no}",
        content=content,
        biz_type="visitor_visit",
        biz_id=visit.id,
        link="/visitor/visits",
    )


def notify_security(db: Session, title: str, content: str, visit: VisitorVisit | None = None) -> int:
    """抄送安防 / 访客管理人员（按权限点找人）。"""
    targets = users_with_perm(db, "visitor:visit:checkin")
    return notify(
        db,
        targets,
        title=title,
        content=content,
        biz_type="visitor_visit",
        biz_id=visit.id if visit else None,
        link="/visitor/visits",
    )


# ---------------- 凭证 ----------------


def issue_credential(db: Session, visit: VisitorVisit) -> VisitorCredential:
    """按"人 + 时间 + 区域"下发最小权限凭证。"""
    valid_from = visit.plan_start or _now()
    valid_to = visit.plan_end or (valid_from + timedelta(hours=MAX_CREDENTIAL_HOURS))
    if valid_to - valid_from > timedelta(hours=MAX_CREDENTIAL_HOURS):
        valid_to = valid_from + timedelta(hours=MAX_CREDENTIAL_HOURS)
    cred = VisitorCredential(
        credential_no=next_no(db, "visitor_credential"),
        visit_id=visit.id,
        visitor_name=visit.visitor_name,
        credential_type="qrcode",
        zone_ids=visit.zone_ids,
        valid_from=valid_from,
        valid_to=valid_to,
        status="issued",
        code=secrets.token_hex(16),
    )
    db.add(cred)
    db.flush()
    visit.credential_id = cred.id
    visit.credential_no = cred.credential_no
    return cred


def revoke_credential(db: Session, visit: VisitorVisit) -> None:
    if visit.credential_id:
        cred = db.get(VisitorCredential, visit.credential_id)
        if cred:
            cred.status = "revoked"


# ---------------- 黑名单 ----------------


def match_blacklist(db: Session, name: str, id_no: str, phone: str) -> VisitorBlacklist | None:
    """命中黑名单（证件号优先，其次姓名 + 电话）。"""
    now = _now()
    rows = db.scalars(
        select(VisitorBlacklist).where(
            VisitorBlacklist.deleted == 0, VisitorBlacklist.status == "enabled"
        )
    ).all()
    for row in rows:
        if row.effective_from and row.effective_from > now:
            continue
        if row.effective_to and row.effective_to < now:
            continue
        if id_no and row.id_no and row.id_no == id_no:
            return row
        if phone and row.phone and row.phone == phone and row.visitor_name and row.visitor_name == name:
            return row
    return None


def raise_alert(
    db: Session,
    alert_type: str,
    message: str,
    visit: VisitorVisit | None = None,
    level: str = "medium",
    zone_id: int | None = None,
    zone_name: str = "",
) -> VisitorAlert:
    alert = VisitorAlert(
        visit_id=visit.id if visit else None,
        alert_type=alert_type,
        level=level,
        zone_id=zone_id,
        zone_name=zone_name,
        message=message,
        occurred_at=_now(),
        status="open",
    )
    db.add(alert)
    db.flush()
    notify_security(db, f"访客预警：{ALERT_TYPE_CN.get(alert_type, alert_type)}", message, visit)
    return alert


# ---------------- 签入签出 ----------------


def check_in(
    db: Session,
    visit: VisitorVisit,
    method: str,
    device_id: str,
    credential_no: str,
    operator_name: str,
) -> VisitorVisit:
    """签入：黑名单 / 时间窗 / 区域容量 / 凭证有效性 四道校验，全部落审计日志。"""
    if visit.status not in ("approved", "visiting"):
        raise BizException(R.VISITOR_INVALID_STATE, f"访客单状态不允许签入：{visit.status}")

    black = match_blacklist(db, visit.visitor_name, visit.id_no, visit.phone)
    if black:
        _log_access(
            db,
            visit,
            event_type="denied",
            method=method,
            result="deny",
            device_id=device_id,
            operator_name=operator_name,
            detail=f"黑名单命中：{black.reason}",
        )
        raise_alert(db, "blacklist", f"访客 {visit.visitor_name} 命中黑名单：{black.reason}", visit, level="high")
        raise BizException(R.VISITOR_BLACKLISTED, "该访客在黑名单中，禁止入内")

    now = _now()
    if visit.plan_start and now < visit.plan_start - timedelta(minutes=30):
        raise BizException(R.VISITOR_OUT_OF_WINDOW, "未到计划来访时间")
    if visit.plan_end and now > visit.plan_end + timedelta(hours=2):
        raise BizException(R.VISITOR_OUT_OF_WINDOW, "已超过计划来访时间")

    # 凭证有效期
    if visit.credential_id:
        cred = db.get(VisitorCredential, visit.credential_id)
        if cred:
            if cred.status == "revoked":
                raise BizException(R.VISITOR_CREDENTIAL_INVALID, "通行凭证已作废")
            if cred.valid_from and now < cred.valid_from:
                raise BizException(R.VISITOR_OUT_OF_WINDOW, "通行凭证尚未生效")
            if cred.valid_to and now > cred.valid_to:
                cred.status = "expired"
                raise BizException(R.VISITOR_CREDENTIAL_INVALID, "通行凭证已过期")
            cred.used_at = now
            cred.used_count = (cred.used_count or 0) + 1
            if cred.used_count > 1:
                tail = db.execute(
                    select(VisitorAccessLog)
                    .where(
                        VisitorAccessLog.credential_id == cred.id,
                        VisitorAccessLog.happened_at >= now - timedelta(minutes=TAILGATING_WINDOW_MINUTES),
                    )
                    .order_by(VisitorAccessLog.id.desc())
                    .limit(2)
                ).scalars().all()
                if len(tail) >= 1:
                    raise_alert(
                        db,
                        "tailgating",
                        f"凭证 {cred.credential_no} 在 {TAILGATING_WINDOW_MINUTES} 分钟内重复核验，疑似尾随",
                        visit,
                        level="high",
                    )

    visit.status = "visiting"
    visit.checkin_at = visit.checkin_at or now
    _log_access(
        db,
        visit,
        event_type="checkin",
        method=method,
        result="pass",
        device_id=device_id,
        operator_name=operator_name,
        detail=f"凭证 {credential_no or visit.credential_no}",
    )
    return visit


def check_out(
    db: Session,
    visit: VisitorVisit,
    method: str,
    device_id: str,
    operator_name: str,
) -> VisitorVisit:
    """签出：闭环访客单。"""
    if visit.status not in ("visiting", "overdue"):
        raise BizException(R.VISITOR_INVALID_STATE, f"访客单状态不允许签出：{visit.status}")
    now = _now()
    visit.checkout_at = now
    visit.status = "left"
    revoke_credential(db, visit)
    _log_access(
        db,
        visit,
        event_type="checkout",
        method=method,
        result="pass",
        device_id=device_id,
        operator_name=operator_name,
        detail="访客签离",
    )
    return visit


def _log_access(
    db: Session,
    visit: VisitorVisit | None,
    event_type: str,
    method: str,
    result: str,
    device_id: str = "",
    operator_name: str = "",
    detail: str = "",
    zone_id: int | None = None,
    zone_name: str = "",
    direction: str = "",
) -> None:
    """写只追加审计日志（不可删改）。"""
    db.add(
        VisitorAccessLog(
            visit_id=visit.id if visit else None,
            credential_id=visit.credential_id if visit else None,
            credential_no=visit.credential_no if visit else "",
            visitor_name=visit.visitor_name if visit else "",
            zone_id=zone_id,
            zone_name=zone_name,
            direction=direction,
            event_type=event_type,
            method=method,
            result=result,
            device_id=device_id,
            operator_name=operator_name,
            happened_at=_now(),
            detail=detail,
        )
    )
    db.flush()


def verify_credential(
    db: Session,
    credential_no: str,
    zone_id: int | None,
    method: str,
    device_id: str,
    direction: str,
) -> dict:
    """门禁 / 闸机 / 梯控核验：返回是否放行，并写审计日志。"""
    cred = db.scalar(
        select(VisitorCredential).where(
            VisitorCredential.credential_no == credential_no, VisitorCredential.deleted == 0
        )
    )
    if not cred:
        _log_access(
            db,
            None,
            event_type="denied",
            method=method,
            result="deny",
            device_id=device_id,
            detail=f"凭证不存在：{credential_no}",
        )
        return {"pass": False, "reason": "凭证不存在"}
    visit = db.get(VisitorVisit, cred.visit_id) if cred.visit_id else None
    now = _now()
    reason = ""
    passed = True
    if cred.status == "revoked":
        passed, reason = False, "凭证已作废"
    elif cred.valid_from and now < cred.valid_from:
        passed, reason = False, "凭证未生效"
    elif cred.valid_to and now > cred.valid_to:
        cred.status = "expired"
        passed, reason = False, "凭证已过期"
    elif visit and visit.status not in ("approved", "visiting"):
        passed, reason = False, "访客单未生效"
    elif zone_id and zone_id not in _split_ids(cred.zone_ids):
        passed, reason = False, "该区域未授权"

    zone = db.get(VisitorZone, zone_id) if zone_id else None
    _log_access(
        db,
        visit,
        event_type="zone_enter" if direction == "in" else "zone_leave",
        method=method,
        result="pass" if passed else "deny",
        device_id=device_id,
        detail=reason,
        zone_id=zone_id,
        zone_name=zone.name if zone else "",
        direction=direction,
    )
    if not passed and visit:
        raise_alert(
            db,
            "zone_denied",
            f"访客 {visit.visitor_name} 越权访问区域 {zone.name if zone else zone_id}：{reason}",
            visit,
            level="high",
            zone_id=zone_id,
            zone_name=zone.name if zone else "",
        )
    if passed:
        cred.used_at = now
        cred.used_count = (cred.used_count or 0) + 1
    return {"pass": passed, "reason": reason, "credentialNo": cred.credential_no, "visitId": cred.visit_id}


def scan_overdue(db: Session) -> int:
    """滞留扫描：计划离开时间已过仍未签离 → 置 overdue 并生成预警。"""
    now = _now()
    rows = db.scalars(
        select(VisitorVisit).where(
            VisitorVisit.deleted == 0,
            VisitorVisit.status == "visiting",
            VisitorVisit.plan_end.is_not(None),
            VisitorVisit.plan_end < now,
        )
    ).all()
    for visit in rows:
        visit.status = "overdue"
        raise_alert(
            db,
            "overstay",
            f"访客 {visit.visitor_name}（{visit.visit_no}）超过计划离开时间未签离",
            visit,
            level="high",
        )
    return len(rows)


# ---------------- NDA ----------------


def sign_nda(db: Session, body, creator_name: str, signed_by_id: int | None = None) -> VisitorNda:
    """NDA 电子签：**密码学绑定**签名（B9 合规 2.4 / HR 5.2）。

    签名覆盖：单号 + 签署人身份 + 真实 IP + 签署时间 + 协议关键字段 + 手写图 sha256。
    - 用 `nda_no`（业务单号）而非自增 id 入签：id 在 insert 前未知会造成循环依赖；
    - 真实 IP 取自请求上下文（`app/core/reqctx.py`），不再硬编码空串；
    - 密钥在服务端（HMAC-SHA256），**离线不可复算** —— 这是与存量无密钥 sha256 的本质区别。
    """
    signed_at = _now().replace(microsecond=0)
    nda_no = next_no(db, "visitor_nda")
    signed_ip = reqctx.current().ip or ""
    title = body.title or "保密协议"
    payload = {
        "biz_type": "visitor_nda",
        "nda_no": nda_no,
        "visitor_name": body.visitor_name,
        "visitor_company": body.visitor_company,
        "id_no": body.id_no,
        "title": title,
        "signed_at": signed_at.isoformat(timespec="seconds"),
        "signed_by_id": signed_by_id or 0,
        "signed_by_name": creator_name or "",
        "signed_ip": signed_ip,
        "signature_sha256": signature.sha256_hex(body.signature_data or ""),
    }
    evidence = signature.sign(payload, signature.NDA_FIELDS)
    nda = VisitorNda(
        nda_no=nda_no,
        title=body.title or "访客保密协议",
        template=body.template,
        visitor_name=body.visitor_name,
        visitor_company=body.visitor_company,
        signer_title=body.signer_title,
        id_no=body.id_no,
        signed_at=signed_at,
        signature_data=body.signature_data,
        evidence_hash=evidence,
        ip=signed_ip,
        signed_by_id=signed_by_id,
        signed_by_name=creator_name or "",
        signed_ip=signed_ip,
        sign_alg=signature.ALG,
        sign_version=signature.KEY_VERSION,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        status="signed",
        visit_id=body.visit_id,
        staff_id=body.staff_id,
        remark=body.remark,
    )
    db.add(nda)
    db.flush()
    if body.visit_id:
        visit = db.get(VisitorVisit, body.visit_id)
        if visit:
            visit.nda_id = nda.id
    return nda


def nda_sign_payload(nda: VisitorNda) -> dict:
    """按签署时同样的口径重建签名载荷（验签用）。"""
    return {
        "biz_type": "visitor_nda",
        "nda_no": nda.nda_no,
        "visitor_name": nda.visitor_name,
        "visitor_company": nda.visitor_company,
        "id_no": nda.id_no,
        "title": nda.title,
        "signed_at": nda.signed_at.isoformat(timespec="seconds") if nda.signed_at else "",
        "signed_by_id": nda.signed_by_id or 0,
        "signed_by_name": nda.signed_by_name or "",
        "signed_ip": nda.signed_ip or "",
        "signature_sha256": signature.sha256_hex(nda.signature_data or ""),
    }


def verify_nda_signature(nda: VisitorNda) -> dict:
    """NDA 验签结论。

    verdict：
    - `valid`：HMAC-SHA256 签名与内容一致；
    - `invalid`：签名与内容不一致（内容被改或签名被伪造）；
    - `legacy-unverifiable`：存量行（无密钥 sha256，离线可复算）—— **不能当密码学证据**。
    """
    legacy = (nda.sign_version or "") != signature.KEY_VERSION
    if legacy:
        return {
            "valid": False,
            "verdict": "legacy-unverifiable",
            "alg": nda.sign_alg or "sha256",
            "signedBy": nda.signed_by_name or "",
            "signedAt": nda.signed_at.isoformat(timespec="seconds") if nda.signed_at else "",
            "signedIp": nda.signed_ip or "",
            "reason": "存量签名无服务端密钥绑定，离线可复算，不能作为密码学证据",
        }
    payload = nda_sign_payload(nda)
    ok = signature.verify(payload, signature.NDA_FIELDS, nda.evidence_hash)
    return {
        "valid": ok,
        "verdict": "valid" if ok else "invalid",
        "alg": nda.sign_alg or signature.ALG,
        "signedBy": nda.signed_by_name or "",
        "signedAt": nda.signed_at.isoformat(timespec="seconds") if nda.signed_at else "",
        "signedIp": nda.signed_ip or "",
        "reason": "" if ok else "签名与当前内容不一致（内容被修改或签名被伪造）",
    }


# ---------------- 样品 / 样车交接 ----------------


def create_handover(db: Session, body, visit: VisitorVisit | None) -> VisitorSampleHandover:
    """样品样车交接登记（送样人 + 条码 + 交接时间 + 接收人）。"""
    row = VisitorSampleHandover(
        handover_no=next_no(db, "visitor_handover"),
        visit_id=visit.id if visit else None,
        sample_no=body.sample_no,
        sample_name=body.sample_name,
        barcode=body.barcode,
        sample_type=body.sample_type,
        qty=body.qty,
        handover_user_name=body.handover_user_name or (visit.visitor_name if visit else ""),
        receive_user_name=body.receive_user_name,
        handover_at=_now(),
        status="done",
        remark=body.remark,
    )
    db.add(row)
    db.flush()
    return row


def visitor_stats(db: Session) -> dict:
    """首页概览：在访 / 待审 / 今日签入 / 未处置预警。"""
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    counts = {}
    rows = db.execute(
        select(VisitorVisit.status, func.count()).where(VisitorVisit.deleted == 0).group_by(VisitorVisit.status)
    ).all()
    for status, n in rows:
        counts[status] = n
    checkins = db.scalar(
        select(func.count()).select_from(VisitorVisit).where(
            VisitorVisit.deleted == 0, VisitorVisit.checkin_at >= today
        )
    )
    open_alerts = db.scalar(
        select(func.count()).select_from(VisitorAlert).where(VisitorAlert.deleted == 0, VisitorAlert.status == "open")
    )
    return {
        "visiting": counts.get("visiting", 0),
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "todayCheckins": int(checkins or 0),
        "openAlerts": int(open_alerts or 0),
    }

"""合作方门户业务：独立注册/登录（审核制）+ 招投标白名单能力。

安全边界：本模块只允许访问「已发布及以上」的招标项目公告口径字段、
本人的报名/投标记录；任何内部单据数据不经由此暴露。
"""

import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.config import settings
from app.core.exceptions import BizException
from app.core.redis import get_redis
from app.core.security import create_portal_token, hash_password, verify_password
from app.modules.admin.models import LoginLog
from app.modules.portal.models import PartnerUser
from app.modules.portal.schemas import PortalRegisterIn
from app.modules.procurement.models import TenderBid, TenderProject, TenderRegistration

FAIL_KEY = "portal_login_fail:{username}"
FAIL_LIMIT = 5
FAIL_WINDOW_SEC = 15 * 60

# 门户可见的项目状态（draft/terminated 对外不可见）
PORTAL_VISIBLE = ("published", "evaluating", "awarding", "awarded")


def _fail_guard(username: str) -> None:
    n = int(get_redis().get(FAIL_KEY.format(username=username)) or 0)
    if n >= FAIL_LIMIT:
        raise BizException(R.AUTH_LOCKED, http_status=401)


def _record_fail(username: str) -> None:
    r = get_redis()
    key = FAIL_KEY.format(username=username)
    n = r.incr(key)
    if n == 1:
        r.expire(key, FAIL_WINDOW_SEC)


def partner_out(p: PartnerUser) -> dict:
    return {
        "id": p.id,
        "username": p.username,
        "companyName": p.company_name,
        "contactName": p.contact_name,
        "phone": p.phone,
        "email": p.email,
        "status": p.status,
        "customerId": p.customer_id,
    }


def register(db: Session, body: PortalRegisterIn, ip: str = "") -> dict:
    exists = db.scalar(select(PartnerUser).where(PartnerUser.username == body.username, PartnerUser.deleted == 0))
    if exists:
        raise BizException(R.PORTAL_ACCOUNT_EXISTS)
    p = PartnerUser(
        username=body.username,
        password_hash=hash_password(body.password),
        company_name=body.company_name,
        contact_name=body.contact_name,
        phone=body.phone,
        email=body.email,
        status="pending",
    )
    db.add(p)
    db.flush()
    audit(
        db, user_id=None, module="portal", action="partner_register",
        biz_type="partner_user", biz_id=p.id,
        detail={"username": p.username, "companyName": p.company_name}, ip=ip,
    )
    db.commit()
    return partner_out(p)


def login(db: Session, username: str, password: str, ip: str = "", ua: str = "") -> dict:
    _fail_guard(username)
    p = db.scalar(select(PartnerUser).where(PartnerUser.username == username, PartnerUser.deleted == 0))
    ok = bool(p) and verify_password(password, p.password_hash)
    if ok and p.status == "enabled":
        get_redis().delete(FAIL_KEY.format(username=username))
        p.last_login_at = datetime.now()
        audit(db, user_id=None, module="portal", action="portal_login",
              detail={"username": username, "companyName": p.company_name}, ip=ip)
        db.add(LoginLog(username=f"portal:{username}", success=1, ip=ip or "", ua=(ua or "")[:255]))
        db.commit()
        return {"access_token": create_portal_token(p.id), "token_type": "Bearer", "partner": partner_out(p)}

    if p and p.status in ("pending", "rejected", "disabled"):
        audit(db, user_id=None, module="portal", action="portal_login_denied",
              detail={"username": username, "status": p.status}, ip=ip)
        db.add(LoginLog(username=f"portal:{username}", success=0, reason=p.status, ip=ip or "", ua=(ua or "")[:255]))
        db.commit()
        raise BizException(R.PORTAL_ACCOUNT_PENDING, http_status=401)

    _record_fail(username)
    audit(db, user_id=None, module="portal", action="portal_login_failed", detail={"username": username}, ip=ip)
    db.add(
        LoginLog(username=f"portal:{username}", success=0, reason="用户名或密码错误", ip=ip or "", ua=(ua or "")[:255])
    )
    db.commit()
    raise BizException(R.AUTH_UNAUTHORIZED, "用户名或密码错误", http_status=401)


# ---------------- 附件（校验同内部：扩展名白名单 + 大小上限 + UUID 存储名） ----------------


def save_upload(filename: str, data: bytes) -> tuple[str, str]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.upload_ext_set:
        raise BizException(R.GENERIC_PARAM, f"不支持的文件类型：{ext or '无扩展名'}")
    if not data:
        raise BizException(R.GENERIC_PARAM, "文件为空")
    if len(data) > settings.upload_max_mb * 1024 * 1024:
        raise BizException(R.GENERIC_PARAM, f"文件超过大小上限 {settings.upload_max_mb}MB")
    rel = Path("portal") / f"{uuid.uuid4().hex}.{ext}"
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return str(rel), filename


def file_bytes(rel_path: str) -> tuple[Path, str]:
    """读取 uploads 下文件；防目录穿越。"""
    root = Path(settings.upload_dir).resolve()
    dest = (root / rel_path).resolve()
    if root not in dest.parents or not dest.exists():
        raise BizException(R.GENERIC_NOT_FOUND, "文件已丢失")
    return dest, dest.suffix.lstrip(".").lower()


# ---------------- 招投标（门户白名单） ----------------


def _tender_public_out(t: TenderProject) -> dict:
    """公告口径：不含任何内部评标/他人投标信息。"""
    return {
        "id": t.id,
        "tenderNo": t.tender_no or "",
        "name": t.name,
        "tenderMethod": t.tender_method,
        "budgetAmount": float(t.budget_amount) if t.budget_amount is not None else None,
        "regDeadline": t.reg_deadline.strftime("%Y-%m-%d %H:%M:%S") if t.reg_deadline else "",
        "bidDeadline": t.bid_deadline.strftime("%Y-%m-%d %H:%M:%S") if t.bid_deadline else "",
        "openTime": t.open_time.strftime("%Y-%m-%d %H:%M:%S") if t.open_time else "",
        "announcement": t.announcement or "",
        "status": t.status,
        # 中标公示：已定标项目公开中标单位与金额（公告口径）
        "winnerName": t.winner_name if t.status == "awarded" else "",
        "winnerAmount": (
            float(t.winner_amount) if t.winner_amount is not None and t.status == "awarded" else None
        ),
    }


def _get_visible_tender(db: Session, tender_id: int) -> TenderProject:
    t = db.get(TenderProject, tender_id)
    if not t or t.deleted or t.status not in PORTAL_VISIBLE:
        raise BizException(R.GENERIC_NOT_FOUND)
    return t


def _my_registration(db: Session, tender_id: int, partner_id: int) -> TenderRegistration | None:
    return db.scalar(
        select(TenderRegistration).where(
            TenderRegistration.tender_id == tender_id,
            TenderRegistration.partner_user_id == partner_id,
            TenderRegistration.deleted == 0,
        )
    )


def _my_bid(db: Session, tender_id: int, partner_id: int) -> TenderBid | None:
    return db.scalar(
        select(TenderBid).where(
            TenderBid.tender_id == tender_id,
            TenderBid.partner_user_id == partner_id,
            TenderBid.deleted == 0,
        )
    )


def _reg_out(r: TenderRegistration, tender: TenderProject | None = None) -> dict:
    return {
        "id": r.id,
        "tenderId": r.tender_id,
        "tenderNo": (tender.tender_no or "") if tender else "",
        "tenderName": tender.name if tender else "",
        "companyName": r.company_name,
        "contactName": r.contact_name,
        "contactPhone": r.contact_phone,
        "qualificationName": r.qualification_name,
        "status": r.status,
        "reviewComment": r.review_comment,
        "createTime": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
    }


def _bid_out(b: TenderBid, tender: TenderProject | None = None) -> dict:
    return {
        "id": b.id,
        "tenderId": b.tender_id,
        "tenderNo": (tender.tender_no or "") if tender else "",
        "tenderName": tender.name if tender else "",
        "price": float(b.price),
        "comment": b.comment or "",
        "proposalName": b.proposal_name,
        "submitAt": b.submit_at.strftime("%Y-%m-%d %H:%M:%S") if b.submit_at else "",
        "isWinner": bool(tender and tender.winner_bid_id == b.id and tender.status == "awarded"),
    }


def list_tenders(db: Session, partner: PartnerUser) -> list[dict]:
    rows = db.scalars(
        select(TenderProject)
        .where(TenderProject.deleted == 0, TenderProject.status.in_(PORTAL_VISIBLE))
        .order_by(TenderProject.id.desc())
    ).all()
    out = []
    for t in rows:
        item = _tender_public_out(t)
        reg = _my_registration(db, t.id, partner.id)
        item["myRegistrationStatus"] = reg.status if reg else ""
        bid = _my_bid(db, t.id, partner.id)
        item["myBidId"] = bid.id if bid else None
        item["isWinner"] = bool(t.status == "awarded" and bid and t.winner_bid_id == bid.id)
        out.append(item)
    return out


def tender_detail(db: Session, tender_id: int, partner: PartnerUser) -> dict:
    t = _get_visible_tender(db, tender_id)
    data = _tender_public_out(t)
    reg = _my_registration(db, t.id, partner.id)
    data["myRegistration"] = _reg_out(reg, t) if reg else None
    bid = _my_bid(db, t.id, partner.id)
    data["myBid"] = _bid_out(bid, t) if bid else None
    return data


def register_tender(
    db: Session, tender_id: int, partner: PartnerUser,
    contact_name: str, contact_phone: str, file=None, ip: str = "",
) -> dict:
    t = _get_visible_tender(db, tender_id)
    if t.status != "published":
        raise BizException(R.TENDER_INVALID_STATE, "当前不在报名阶段")
    if t.reg_deadline and datetime.now() > t.reg_deadline:
        raise BizException(R.TENDER_DEADLINE_PASSED, "报名已截止")
    if _my_registration(db, t.id, partner.id):
        raise BizException(R.GENERIC_PARAM, "已报名，请勿重复提交")
    path, name = ("", "")
    if file is not None:
        path, name = save_upload(file.filename or "", file.file.read())
    r = TenderRegistration(
        tender_id=t.id,
        partner_user_id=partner.id,
        company_name=partner.company_name,
        contact_name=contact_name or partner.contact_name,
        contact_phone=contact_phone or partner.phone,
        qualification_path=path,
        qualification_name=name,
        status="pending",
    )
    db.add(r)
    db.flush()
    audit(db, user_id=None, module="portal", action="tender_register",
          biz_type="tender_registration", biz_id=r.id,
          detail={"tenderId": t.id, "tenderNo": t.tender_no, "partner": partner.username}, ip=ip)
    db.commit()
    return _reg_out(r, t)


def my_registrations(db: Session, partner: PartnerUser) -> list[dict]:
    rows = db.scalars(
        select(TenderRegistration)
        .where(TenderRegistration.partner_user_id == partner.id, TenderRegistration.deleted == 0)
        .order_by(TenderRegistration.id.desc())
    ).all()
    tenders = {t.id: t for t in db.scalars(select(TenderProject)).all()}
    return [_reg_out(r, tenders.get(r.tender_id)) for r in rows]


def submit_bid(
    db: Session, tender_id: int, partner: PartnerUser,
    price: float, comment: str, file=None, ip: str = "",
) -> dict:
    t = db.get(TenderProject, tender_id, with_for_update=True)  # 行锁：截止/状态判定与写入原子
    if not t or t.deleted or t.status not in PORTAL_VISIBLE:
        raise BizException(R.GENERIC_NOT_FOUND)
    if t.status != "published":
        raise BizException(R.TENDER_INVALID_STATE, "当前不在投标阶段")
    if t.bid_deadline and datetime.now() > t.bid_deadline:
        raise BizException(R.TENDER_DEADLINE_PASSED, "投标已截止")
    reg = _my_registration(db, t.id, partner.id)
    if not reg or reg.status != "approved":
        raise BizException(R.TENDER_REGISTRATION_NOT_APPROVED)
    if price <= 0:
        raise BizException(R.GENERIC_PARAM, "报价必须大于 0")
    path, name = ("", "")
    if file is not None:
        path, name = save_upload(file.filename or "", file.file.read())
    bid = _my_bid(db, t.id, partner.id)
    if bid:
        bid.price = price
        bid.comment = comment
        if path:
            bid.proposal_path, bid.proposal_name = path, name
        bid.submit_at = datetime.now()
        bid.update_time = datetime.now()
    else:
        bid = TenderBid(
            tender_id=t.id,
            partner_user_id=partner.id,
            registration_id=reg.id,
            company_name=partner.company_name,
            price=price,
            proposal_path=path,
            proposal_name=name,
            comment=comment,
            submit_at=datetime.now(),
        )
        db.add(bid)
    db.flush()
    audit(db, user_id=None, module="portal", action="tender_bid",
          biz_type="tender_bid", biz_id=bid.id,
          detail={"tenderId": t.id, "tenderNo": t.tender_no, "partner": partner.username}, ip=ip)
    db.commit()
    return _bid_out(bid, t)


def my_bids(db: Session, partner: PartnerUser) -> list[dict]:
    rows = db.scalars(
        select(TenderBid)
        .where(TenderBid.partner_user_id == partner.id, TenderBid.deleted == 0)
        .order_by(TenderBid.id.desc())
    ).all()
    tenders = {t.id: t for t in db.scalars(select(TenderProject)).all()}
    return [_bid_out(b, tenders.get(b.tender_id)) for b in rows]

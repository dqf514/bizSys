"""合作方门户路由 /api/v1/portal：独立认证 + 招投标白名单能力。"""

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.client_ip import client_ip
from app.core.db import get_db
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.portal import service as svc
from app.modules.portal.deps import get_current_partner, get_optional_partner
from app.modules.portal.models import PartnerUser
from app.modules.portal.schemas import (
    PortalAccountUpdateIn,
    PortalLoginIn,
    PortalPasswordIn,
    PortalRefreshIn,
    PortalRegisterIn,
    PortalStaffIn,
)
from app.modules.portal.selfservice import (
    cancel_entrust as self_cancel_entrust,
)
from app.modules.portal.selfservice import (
    create_entrust as self_create_entrust,
)
from app.modules.portal.selfservice import (
    my_contracts as self_my_contracts,
)
from app.modules.portal.selfservice import (
    my_entrusts as self_my_entrusts,
)
from app.modules.portal.selfservice import (
    my_staff as self_my_staff,
)
from app.modules.portal.selfservice import (
    register_staff as self_register_staff,
)
from app.modules.task import schemas as task_schemas

router = APIRouter(prefix="/portal", tags=["portal"], route_class=EnvelopeRoute)


@router.post("/auth/register", status_code=201)
def register(body: PortalRegisterIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    return svc.register(db, body, ip)


@router.post("/auth/login")
def login(body: PortalLoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")
    return svc.login(db, body.username, body.password, ip, ua)


@router.post("/auth/refresh")
def refresh(body: PortalRefreshIn, request: Request, db: Session = Depends(get_db)):
    """刷新门户 access token（refresh token 一次性轮换）。"""
    ip = client_ip(request)
    return svc.refresh(db, body.refresh_token, ip)


@router.get("/auth/me")
def me(partner: PartnerUser = Depends(get_current_partner)):
    return svc.partner_out(partner)


@router.post("/auth/logout")
def logout(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    from app.common.audit import record as audit

    svc.revoke_refresh_tokens(partner.id)
    audit(db, user_id=None, module="portal", action="portal_logout", detail={"username": partner.username})
    db.commit()
    return None


@router.get("/branding")
def branding(db: Session = Depends(get_db)):
    """门户站点信息（公开）：站点名 / 联系方式 / 备案号 / 公告。"""
    return svc.branding(db)


@router.get("/account")
def account(partner: PartnerUser = Depends(get_current_partner)):
    """我的账号资料（含权限范围）。"""
    return svc.partner_out(partner)


@router.put("/account")
def update_account(
    body: PortalAccountUpdateIn,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """修改本账号资料（单位 / 联系人 / 电话 / 邮箱）。"""
    from app.common.audit import record as audit

    partner.company_name = body.company_name
    partner.contact_name = body.contact_name
    partner.phone = body.phone
    partner.email = body.email
    partner.update_time = datetime.now()
    audit(db, user_id=None, module="portal", action="portal_account_update",
          detail={"username": partner.username})
    db.commit()
    return svc.partner_out(partner)


@router.post("/account/password")
def change_password(
    body: PortalPasswordIn,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """修改本账号密码（需校验原密码）。"""
    from app.common.audit import record as audit
    from app.core.security import hash_password, verify_password

    if not verify_password(body.old_password or "", partner.password_hash):
        raise BizException(R.AUTH_OLD_PASSWORD_WRONG)
    partner.password_hash = hash_password(body.new_password)
    partner.update_time = datetime.now()
    audit(db, user_id=None, module="portal", action="portal_password_change",
          detail={"username": partner.username})
    db.commit()
    return None


# ---------------- 招投标白名单 ----------------


@router.get("/tenders")
def list_tenders(
    page: int = Query(1, ge=1, le=10**9),
    size: int = Query(20, ge=1, le=200),
    partner: PartnerUser | None = Depends(get_optional_partner),
    db: Session = Depends(get_db),
):
    """公告列表：免登录公开；登录后追加我的报名/投标/中标标记。"""
    items, total = svc.list_tenders(db, partner, page, size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/tenders/{tender_id}")
def tender_detail(
    tender_id: int, partner: PartnerUser | None = Depends(get_optional_partner), db: Session = Depends(get_db)
):
    """公告详情：免登录公开；登录后追加我的报名/投标。"""
    return svc.tender_detail(db, tender_id, partner)


@router.post("/tenders/{tender_id}/register", status_code=201)
def register_tender(
    tender_id: int,
    request: Request,
    contact_name: str = Form(""),
    contact_phone: str = Form(""),
    file: UploadFile | None = None,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    ip = client_ip(request)
    return svc.register_tender(db, tender_id, partner, contact_name, contact_phone, file, ip)


@router.get("/registrations")
def my_registrations(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    return {"items": svc.my_registrations(db, partner)}


@router.post("/tenders/{tender_id}/bid", status_code=201)
def submit_bid(
    tender_id: int,
    request: Request,
    price: float = Form(...),
    comment: str = Form(""),
    file: UploadFile | None = None,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    ip = client_ip(request)
    return svc.submit_bid(db, tender_id, partner, price, comment, file, ip)


@router.get("/bids")
def my_bids(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    return {"items": svc.my_bids(db, partner)}


def _download(rel_path: str, original_name: str) -> Response:
    dest, _ext = svc.file_bytes(rel_path)
    return Response(
        dest.read_bytes(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(original_name or 'file')}"},
    )


@router.get("/registrations/{rid}/attachment")
def my_registration_attachment(
    rid: int, partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)
):
    from app.modules.procurement.models import TenderRegistration

    r = db.get(TenderRegistration, rid)
    if not r or r.deleted or r.partner_user_id != partner.id or not r.qualification_path:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _download(r.qualification_path, r.qualification_name)


@router.get("/bids/{bid}/proposal")
def my_bid_proposal(bid: int, partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    from app.modules.procurement.models import TenderBid

    b = db.get(TenderBid, bid)
    if not b or b.deleted or b.partner_user_id != partner.id or not b.proposal_path:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _download(b.proposal_path, b.proposal_name)


# ---------------- 客户自助（B2）：在线委托 + 外来人员备案 ----------------


@router.get("/contracts")
def my_contracts(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    """本单位的已审批合同：委托下单的合同来源。"""
    return {"items": self_my_contracts(db, partner)}


@router.get("/entrusts")
def my_entrusts(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    return {"items": self_my_entrusts(db, partner)}


@router.post("/entrusts", status_code=201)
def create_entrust(
    body: task_schemas.EntrustIn,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """在线提交任务委托（仿真 / 模型 / 试验 / 委外）。"""
    return self_create_entrust(db, partner, body)


@router.post("/entrusts/{eid}/cancel")
def cancel_entrust(
    eid: int,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """撤回尚未受理的委托。"""
    return self_cancel_entrust(db, partner, eid)


@router.get("/staff")
def my_staff(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    return {"items": self_my_staff(db, partner)}


@router.post("/staff", status_code=201)
def register_staff(
    body: PortalStaffIn,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """外来试验人员 / 跟踪支持人员自助登记备案（客户经理审核后生效）。"""
    return self_register_staff(db, partner, body)

"""门户访客预约路由（前缀 `/portal`，与 `portal/router.py` 同前缀分文件）。

对外能力边界：

- `hosts` / `zones`：**公开**（免登录），只暴露姓名 / 部门 / 区域名称与分级，
  不暴露手机号、邮箱等联系方式；
- `visits/*`：需门户登录，且只允许访问**本账号提交**的访客单；
- `visits/{id}/pass?code=`：**公开**的「通行证」页，凭证码即持有者凭证
  （微信转发链接给访客本人 / 前台扫码用），不返回任何内部审批信息。
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.client_ip import client_ip
from app.core.db import get_db
from app.core.route import EnvelopeRoute
from app.modules.portal import visit_service as vsvc
from app.modules.portal.deps import get_current_partner
from app.modules.portal.models import PartnerUser
from app.modules.portal.schemas import PortalVisitCancelIn, PortalVisitCheckIn, PortalVisitIn
from app.modules.visitor import qr as vqr

router = APIRouter(prefix="/portal", tags=["portal"], route_class=EnvelopeRoute)


def _base_url(request: Request) -> str:
    """门户地址：配置优先，否则取请求来源（反代下由 X-Forwarded-* 决定）。"""
    from app.core.config import settings

    if settings.portal_base_url:
        return settings.portal_base_url
    return str(request.base_url).rstrip("/")


# ---------------- 公开选项 ----------------


@router.get("/hosts")
def hosts(q: str = Query("", max_length=64), db: Session = Depends(get_db)):
    """被访人候选（公开）。"""
    return {"items": vsvc.host_options(db, q)}


@router.get("/zones")
def zones(db: Session = Depends(get_db)):
    """可申请区域（公开，仅启用区域）。"""
    return {"items": vsvc.zone_options(db)}


@router.get("/visits/{visit_id}/pass")
def visit_pass(visit_id: int, code: str = Query("", max_length=128), db: Session = Depends(get_db)):
    """公开通行证：凭证码即持有凭证，微信转发链接直接打开。"""
    return vsvc.pass_info(db, visit_id, code)


# ---------------- 我的访客预约 ----------------


@router.get("/visits")
def my_visits(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    return {"items": vsvc.my_visits(db, partner)}


@router.get("/visits/{visit_id}")
def visit_detail(
    visit_id: int,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    return vsvc.visit_detail(db, partner, visit_id)


@router.post("/visits", status_code=201)
def create_visit(
    body: PortalVisitIn,
    request: Request,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """提交来访申请 → 内部审批 → 审批通过后下发通行凭证。"""
    ip = client_ip(request)
    return vsvc.create_visit(db, partner, body, ip)


@router.post("/visits/{visit_id}/cancel")
def cancel_visit(
    visit_id: int,
    body: PortalVisitCancelIn,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """取消尚未审批完成的预约。"""
    return vsvc.cancel_visit(db, partner, visit_id, body.remark)


@router.get("/visits/{visit_id}/credential")
def visit_credential(
    visit_id: int,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """通行凭证信息（审批通过后可见）。"""
    return vsvc.credential_info(db, partner, visit_id)


@router.get("/visits/{visit_id}/credential/qr")
def visit_credential_qr(
    visit_id: int,
    request: Request,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """通行凭证二维码（SVG）。

    走 `portalHttp` 取回（`<img src>` 不会带 Authorization 头）。
    """
    info = vsvc.credential_info(db, partner, visit_id)
    payload = vqr.credential_payload(_base_url(request), visit_id, info["code"])
    svg = vqr.qr_svg(payload)
    return Response(content=svg, media_type="image/svg+xml")


@router.post("/visits/{visit_id}/checkin")
def visit_checkin(
    visit_id: int,
    body: PortalVisitCheckIn,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """访客自助签到（扫码核验）。拒绝放行同样留痕。"""
    return vsvc.check_in(db, partner, visit_id, body.method, body.device_id)


@router.post("/visits/{visit_id}/checkout")
def visit_checkout(
    visit_id: int,
    body: PortalVisitCheckIn,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """访客自助签离。"""
    return vsvc.check_out(db, partner, visit_id, body.method, body.device_id)

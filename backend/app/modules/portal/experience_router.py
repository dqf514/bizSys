"""门户对外业务能力路由（前缀 `/portal`，与 `portal/router.py` 同前缀分文件）。

端点：

- `GET  /portal/progress`              我的项目进度看板（委托→任务→结算→开票→回款）
- `GET  /portal/reports`               可查阅的正式报告（仅已签章）
- `POST /portal/reports/{id}/download-code`  签发一次性下载码
- `GET  /portal/reports/{id}/download?code=` 下载报告（下载码一次性）
- `GET  /portal/billing`               对账单 / 开票 / 回款
- `GET  /portal/handovers`             样品 / 样车交接单
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.route import EnvelopeRoute
from app.modules.portal import experience_service as xs
from app.modules.portal.deps import get_current_partner
from app.modules.portal.models import PartnerUser

router = APIRouter(prefix="/portal", tags=["portal"], route_class=EnvelopeRoute)


@router.get("/progress")
def progress(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    """我的项目进度看板。"""
    return xs.progress(db, partner)


@router.get("/reports")
def reports(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    """可在线查阅的正式报告。"""
    return {"items": xs.my_reports(db, partner)}


@router.post("/reports/{report_id}/download-code")
def issue_code(
    report_id: int,
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """签发一次性下载码（可转发给他人代下载）。"""
    return xs.issue_download_code(db, partner, report_id)


@router.get("/reports/{report_id}/download")
def download(
    report_id: int,
    code: str = Query("", max_length=64),
    partner: PartnerUser = Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """按一次性下载码下载报告文件（校验后即焚）。"""
    report = xs.consume_download_code(db, partner, report_id, code)
    f, dest = xs.report_file(db, report)
    return Response(
        dest.read_bytes(),
        media_type=f.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f.file_name)}"},
    )


@router.get("/billing")
def billing(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    """对账单 / 开票 / 回款。"""
    return xs.billing(db, partner)


@router.get("/handovers")
def handovers(partner: PartnerUser = Depends(get_current_partner), db: Session = Depends(get_db)):
    """样品 / 样车交接单。"""
    return {"items": xs.handovers(db, partner)}

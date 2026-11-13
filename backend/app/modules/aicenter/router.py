"""AI 中心端点：/admin/ai/* 用量监控与设置（admin:ai:*），/ai/capabilities 登录可用的能力探测。"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.pagination import PAGE_MAX, PageParams
from app.core.db import get_db
from app.core.deps import get_current_user, require_perm
from app.core.route import EnvelopeRoute
from app.modules.aicenter import schemas as S
from app.modules.aicenter import service as svc
from app.modules.auth.models import User
from app.services.excel import export_xlsx, now_filename

router = APIRouter(prefix="/admin/ai", tags=["admin-ai"], route_class=EnvelopeRoute)
cap_router = APIRouter(prefix="/ai", tags=["ai"], route_class=EnvelopeRoute)


@router.get("/usage")
def list_usage(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    _: User = Depends(require_perm("admin:ai:usage")),
    db: Session = Depends(get_db),
):
    return svc.list_usage(db, PageParams(page=page, size=size), request.query_params)


@router.get("/usage/export")
def export_usage(
    request: Request,
    current: User = Depends(require_perm("admin:ai:usage:export")),
    db: Session = Depends(get_db),
):
    rows = svc.usage_export_rows(db, request.query_params)
    payload = export_xlsx(rows, svc.EXPORT_COLUMNS, "ai_usage")
    record(db, user_id=current.id, module="admin", action="ai_usage_export", detail={"count": len(rows)})
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('ai_usage')}"},
    )


@router.get("/stats")
def ai_stats(
    days: int = Query(30, ge=1, le=90),
    _: User = Depends(require_perm("admin:ai:usage")),
    db: Session = Depends(get_db),
):
    return svc.stats(db, days)


@router.get("/settings")
def get_center_settings(
    _: User = Depends(require_perm("admin:ai:settings")),
    db: Session = Depends(get_db),
):
    return svc.center_settings_out(db)


@router.put("/settings")
def put_center_settings(
    body: S.AiCenterSettingsIn,
    current: User = Depends(require_perm("admin:ai:settings")),
    db: Session = Depends(get_db),
):
    data = svc.update_center_settings(db, body, current.id)
    record(db, user_id=current.id, module="admin", action="ai_settings_update", detail=body.model_dump())
    db.commit()
    return data


@cap_router.get("/capabilities")
def ai_capabilities(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """登录即可：前端按此显隐 AI 入口（未配置/功能停用时给明确提示而不是静默失败）。"""
    return svc.capabilities(db)

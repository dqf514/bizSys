"""系统设置路由：/admin/settings（管理）+ /public（免登录品牌信息/Logo）。"""

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.settings import service as svc
from app.modules.settings.schemas import SettingsIn

router = APIRouter(prefix="/admin", tags=["admin-settings"], route_class=EnvelopeRoute)
public_router = APIRouter(prefix="/public", tags=["public"], route_class=EnvelopeRoute)


@router.get("/settings")
def get_settings(
    _: User = Depends(require_perm("admin:setting:list")),
    db: Session = Depends(get_db),
):
    return svc.settings_out(db)


@router.put("/settings")
def put_settings(
    body: SettingsIn,
    current: User = Depends(require_perm("admin:setting:edit")),
    db: Session = Depends(get_db),
):
    out = svc.update_settings(db, body, current.id)
    audit(
        db,
        user_id=current.id,
        module="admin",
        action="settings_update",
        detail={"siteName": out["siteName"], "wecomEnabled": out["wecom"]["enabled"]},
    )
    db.commit()
    return out


@router.post("/settings/logo")
def upload_logo(
    file: UploadFile,
    current: User = Depends(require_perm("admin:setting:edit")),
    db: Session = Depends(get_db),
):
    logo_url = svc.save_logo(db, file.filename or "", file.file.read(), current.id)
    audit(db, user_id=current.id, module="admin", action="settings_logo", detail={"file": file.filename})
    db.commit()
    return {"logoUrl": logo_url}


@public_router.get("/branding")
def branding(db: Session = Depends(get_db)):
    """免登录：登录页/外壳品牌信息。"""
    return svc.branding_out(db)


@public_router.get("/logo")
def logo(request: Request, db: Session = Depends(get_db)):
    """免登录：Logo 文件流。"""
    dest, content_type = svc.logo_file(db)
    return Response(dest.read_bytes(), media_type=content_type, headers={"Cache-Control": "no-cache"})

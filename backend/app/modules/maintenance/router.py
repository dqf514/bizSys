"""数据维护路由：/admin/maintenance（备份设置/备份管理/一键清空）。"""


from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.maintenance import scheduler
from app.modules.maintenance import service as svc
from app.modules.maintenance.backup import delete_backup, list_backups, resolve_backup
from app.modules.maintenance.schemas import MaintenanceSettingsIn, PurgeIn
from app.modules.settings.service import get_value

router = APIRouter(prefix="/admin/maintenance", tags=["admin-maintenance"], route_class=EnvelopeRoute)


@router.get("/settings")
def get_settings(
    _: User = Depends(require_perm("admin:backup:view")),
    db: Session = Depends(get_db),
):
    return svc.settings_out(db)


@router.put("/settings")
def put_settings(
    body: MaintenanceSettingsIn,
    current: User = Depends(require_perm("admin:backup:manage")),
    db: Session = Depends(get_db),
):
    out = svc.update_settings(db, body, current.id)
    audit(db, user_id=current.id, module="admin", action="backup_settings_update", detail=out["backup"])
    db.commit()
    scheduler.reschedule(out["backup"]["time"], out["backup"]["enabled"])
    return out


@router.post("/backup/run")
def run_backup(
    current: User = Depends(require_perm("admin:backup:manage")),
    db: Session = Depends(get_db),
):
    try:
        info = svc.do_backup(db, kind="manual")
    except Exception as exc:  # noqa: BLE001
        raise BizException(R.GENERIC_PARAM, f"备份失败：{exc}") from exc
    audit(db, user_id=current.id, module="admin", action="backup_run", detail=info)
    db.commit()
    return info


@router.get("/backups")
def list_backup_files(
    _: User = Depends(require_perm("admin:backup:view")),
    db: Session = Depends(get_db),
):
    return list_backups(get_value(db, svc.KEY_BACKUP_DIR))


@router.get("/backups/{name}/download")
def download_backup(
    name: str,
    _: User = Depends(require_perm("admin:backup:view")),
    db: Session = Depends(get_db),
):
    try:
        dest = resolve_backup(name, get_value(db, svc.KEY_BACKUP_DIR))
    except FileNotFoundError:
        raise BizException(R.GENERIC_NOT_FOUND, "备份文件不存在") from None
    return FileResponse(dest, media_type="application/gzip", filename=name)


@router.delete("/backups/{name}")
def remove_backup(
    name: str,
    current: User = Depends(require_perm("admin:backup:manage")),
    db: Session = Depends(get_db),
):
    try:
        delete_backup(name, get_value(db, svc.KEY_BACKUP_DIR))
    except FileNotFoundError:
        raise BizException(R.GENERIC_NOT_FOUND, "备份文件不存在") from None
    audit(db, user_id=current.id, module="admin", action="backup_delete", detail={"name": name})
    db.commit()
    return None


@router.post("/purge")
def purge(
    body: PurgeIn,
    current: User = Depends(require_perm("admin:maintenance:purge")),
    db: Session = Depends(get_db),
):
    """一键清空测试数据（高危）：密码+确认词校验，执行前自动备份，事务失败整体回滚。"""
    try:
        result = svc.purge(db, current, body.password, body.confirm, body.force_backup_skip)
    except Exception:
        db.rollback()
        raise
    # 清空后写一条新的审计记录（审计表已清空，这条是清空动作本身的凭证）
    audit(db, user_id=current.id, module="admin", action="maintenance_purge", detail=result["counts"])
    db.commit()
    return result

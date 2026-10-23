"""数据维护路由：/admin/maintenance（备份设置/备份管理/一键清空/记录时间修正）。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.approval.models import ApprovalRecord
from app.modules.auth.models import User
from app.modules.finance.models import Invoice, Payment, Settlement
from app.modules.maintenance import scheduler
from app.modules.maintenance import service as svc
from app.modules.maintenance.backup import delete_backup, list_backups, resolve_backup
from app.modules.maintenance.schemas import MaintenanceSettingsIn, PurgeIn, RetimeIn
from app.modules.report.models import Report
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


# ---------------- 记录时间修正（管理员专用，全程留痕） ----------------

# biz_type: (业务名, 模型, 检索字段, {可修正字段: 字段名})
_RETIME_TARGETS = {
    "approval_record": ("审批记录", ApprovalRecord, "id", {"at": "审批时间"}),
    "report": ("报告", Report, "report_no", {"create_time": "创建时间", "seal_time": "签章时间"}),
    "settlement": ("结算单", Settlement, "settlement_no", {"create_time": "登记时间"}),
    "invoice": ("发票", Invoice, "invoice_no", {"create_time": "登记时间"}),
    "payment": ("到账", Payment, "payment_no", {"create_time": "登记时间"}),
}


def _retime_target(biz_type: str):
    target = _RETIME_TARGETS.get(biz_type)
    if not target:
        raise BizException(R.GENERIC_PARAM, f"不支持的业务类型：{biz_type}")
    return target


def _fmt_dt(v: datetime | None) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%S") if v else ""


@router.get("/retime/lookup")
def retime_lookup(
    biz_type: str = Query(..., alias="bizType"),
    key: str = Query(..., min_length=1, max_length=64),
    _: User = Depends(require_perm("admin:maintenance:retime")),
    db: Session = Depends(get_db),
):
    """按单号/ID 检索单据，返回可修正的时间字段及当前值。"""
    biz_label, model, key_col, fields = _retime_target(biz_type)
    obj = db.scalar(select(model).where(getattr(model, key_col) == key.strip(), model.deleted == 0))
    if not obj:
        raise BizException(R.GENERIC_NOT_FOUND, f"{biz_label}不存在：{key}")
    return {
        "bizType": biz_type,
        "id": obj.id,
        "label": f"{biz_label} {key.strip()}",
        "fields": [
            {"field": f, "fieldLabel": label, "value": _fmt_dt(getattr(obj, f))} for f, label in fields.items()
        ],
    }


@router.post("/retime")
def retime(
    body: RetimeIn,
    current: User = Depends(require_perm("admin:maintenance:retime")),
    db: Session = Depends(get_db),
):
    """修正单据时间字段（服务器本地时区）；审计留痕含原值/新值/修改人/原因。"""
    biz_label, model, _key_col, fields = _retime_target(body.biz_type)
    if body.field not in fields:
        raise BizException(R.GENERIC_PARAM, f"{biz_label}不支持修正字段：{body.field}")
    obj = db.get(model, body.id)
    if not obj or obj.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    old = getattr(obj, body.field)
    new = datetime.strptime(body.value, "%Y-%m-%d %H:%M:%S")
    setattr(obj, body.field, new)
    obj.update_by = current.id
    obj.update_time = datetime.now()
    audit(
        db,
        user_id=current.id,
        module="admin",
        action="maintenance_retime",
        biz_type=body.biz_type,
        biz_id=obj.id,
        detail={
            "field": body.field,
            "fieldLabel": fields[body.field],
            "old": _fmt_dt(old),
            "new": body.value,
            "reason": body.reason,
        },
    )
    db.commit()
    return {"id": obj.id, "field": body.field, "value": body.value}

"""回收站路由 /api/v1/admin/recycle。

- `GET  /admin/recycle`             已删除记录列表（全站，按模块/关键词过滤）
- `GET  /admin/recycle/modules`     可筛选的业务模块清单
- `GET  /admin/recycle/settings`    保留期设置
- `PUT  /admin/recycle/settings`    保留期设置（保留期内禁止彻底删除）
- `POST /admin/recycle/{id}/restore` 恢复
- `POST /admin/recycle/{id}/purge`   彻底删除（保留期内拒绝 → 30006）
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common import recycle
from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.recycle.models import RecycleBin
from app.modules.recycle.schemas import RecycleSettingIn

router = APIRouter(prefix="/admin/recycle", tags=["回收站"], route_class=EnvelopeRoute)


def _out(row: RecycleBin, days: int) -> dict:
    return {
        "id": row.id,
        "module": row.module,
        "resource": row.resource,
        "title": row.title,
        "resourceId": row.resource_id,
        "deletedBy": row.deleted_by,
        "deletedByName": row.deleted_by_name,
        "deletedAt": row.deleted_at.strftime("%Y-%m-%d %H:%M:%S") if row.deleted_at else "",
        "purgeAfter": row.purge_after.strftime("%Y-%m-%d %H:%M:%S") if row.purge_after else "",
        "status": row.status,
        "retentionDays": days,
        "purgedAt": row.purged_at.strftime("%Y-%m-%d %H:%M:%S") if row.purged_at else "",
    }


@router.get("")
def list_recycled(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current=Depends(require_perm("admin:recycle:list")),
    db: Session = Depends(get_db),
):
    """已删除记录列表（全站）。"""
    pp = PageParams(page=page, size=size)
    stmt, total = apply_list_filters(
        select(RecycleBin),
        RecycleBin,
        request.query_params,
        db,
        pp,
        search_cols=["title", "resource"],
        filter_cols={"module": "module", "status": "status"},
        sort_cols={"id", "deleted_at", "purge_after"},
        default_sort=("deleted_at", "desc"),
        extra_where=[RecycleBin.status == "recycled"],
    )
    rows = db.scalars(stmt).all()
    days = recycle.retention_days(db)
    return {
        "items": [_out(r, days) for r in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/modules")
def list_modules(
    current=Depends(require_perm("admin:recycle:list")),
    db: Session = Depends(get_db),
):
    """可筛选的业务模块清单（含各模块待处理条数）。"""
    rows = db.execute(
        select(RecycleBin.module, func.count())
        .where(RecycleBin.status == "recycled", RecycleBin.deleted == 0)
        .group_by(RecycleBin.module)
    ).all()
    return {"items": [{"module": m or "unknown", "count": int(c)} for m, c in rows]}


@router.get("/settings")
def get_settings(
    current=Depends(require_perm("admin:recycle:list")),
    db: Session = Depends(get_db),
):
    """保留期设置（保留期内禁止彻底删除）。"""
    return {"retentionDays": recycle.retention_days(db)}


@router.put("/settings")
def update_settings(
    body: RecycleSettingIn,
    current=Depends(require_perm("admin:recycle:setting")),
    db: Session = Depends(get_db),
):
    """调整保留期（天）。"""
    from app.modules.settings.service import set_value

    set_value(db, recycle.RETENTION_KEY, str(body.retention_days), getattr(current, "id", None), "回收站保留期（天）")
    audit(
        db,
        module="recycle",
        action="recycle_setting_update",
        detail={"retentionDays": body.retention_days},
        user_id=getattr(current, "id", None),
    )
    db.commit()
    return {"retentionDays": body.retention_days}


@router.post("/{rid}/restore")
def restore(
    rid: int,
    current=Depends(require_perm("admin:recycle:restore")),
    db: Session = Depends(get_db),
):
    """恢复一条已删除记录。"""
    row = db.get(RecycleBin, rid)
    if row is None or row.deleted != 0:
        raise BizException(R.RECYCLE_ENTRY_NOT_FOUND, "回收站记录不存在")
    recycle.restore_entry(db, row)
    audit(
        db,
        module="recycle",
        action="recycle_restore",
        detail={"rid": rid, "title": row.title},
        user_id=getattr(current, "id", None),
    )
    db.commit()
    return {"id": rid, "status": row.status}


@router.post("/{rid}/purge")
def purge(
    rid: int,
    current=Depends(require_perm("admin:recycle:purge")),
    db: Session = Depends(get_db),
):
    """彻底删除 —— **保留期内一律拒绝**（30006）。"""
    row = db.get(RecycleBin, rid)
    if row is None or row.deleted != 0:
        raise BizException(R.RECYCLE_ENTRY_NOT_FOUND, "回收站记录不存在")
    recycle.purge_entry(db, row, user=current)
    audit(
        db,
        module="recycle",
        action="recycle_purge",
        detail={"rid": rid, "title": row.title},
        user_id=getattr(current, "id", None),
    )
    db.commit()
    return {"id": rid, "status": row.status}

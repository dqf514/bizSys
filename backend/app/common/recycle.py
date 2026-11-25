"""全站统一回收站（软删除 → 回收站 → 保留期内禁止彻底删除）。

设计要点（与 CLAUDE.md「已知坑」对应）：

- **业务表仍用 `deleted` 标记逻辑删除**。全仓 116 张 `BaseModel` 表都有该列，
  **不给它们新增列**（否则要写 116 张表的迁移，且 `AppendOnlyModel` 表根本没有 `deleted`）。
- **删除人 / 删除时间 / 保留期到期时间**记在新增的登记表 `sys_recycle_bin`（一张表管全站）。
- **保留期**走 `sys_config` 的 `recycle.retention_days`（默认 180 天，可在系统管理调整）：
  保留期内「彻底删除」一律拒绝（错误码 30006），到期后管理员才能手工清除。
- **判定软删一律用 `deleted != 0`** —— 有 3 处历史写法把 `deleted` 赋成自身 id
  （`hr/service.py` 工时、`oa/service.py` 表单、`sales/service.py` 报价模板），
  因为那些表的唯一键里含 `deleted`，写 1 会撞键。别按 `deleted == 1` 判断。
- **恢复是通用的**：按登记表里的表名 + 主键把 `deleted` 置回 0，并回填
  `restore_fields`（用于「改名让位」的场景，如用户/角色/字典项改名成 `#del{id}`）。
- **级联软删的子行**（排程方案 → 排程行、项目 → 项目任务）会一并登记，
  恢复时一起回滚；**物理删除的子行**（任务条目、BOM 子件、流程节点）不可回退 —— 见下方已知边界。

已知边界（诚实标注，不假装闭环）：

1. 「整体替换」语义下的子行是物理删除（`db.delete` / `delete-orphan`），
   恢复父记录时这些子行**不会**回来（任务条目 / 样品、BOM 子件行、流程定义节点）。
2. 磁盘文件（合同附件、合作方附件、头像等）在软删时会被立即 `unlink`，
   恢复后拿不回文件；知识库域的文件**不做即时 unlink**（由 `kb_file` 登记，到期清理）。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.db import Base
from app.core.exceptions import BizException

RETENTION_KEY = "recycle.retention_days"
DEFAULT_RETENTION_DAYS = 180

STATUS_RECYCLED = "recycled"
STATUS_RESTORED = "restored"
STATUS_PURGED = "purged"

# 原表名 → 彻底删除前的额外清理钩子（如删除磁盘文件）
# 按**表名**而不是模块注册：同一模块下不同表的彻底删除动作不一样
# （文档要删磁盘文件，分类/文件夹不用）。
PURGE_HOOKS: dict[str, Callable[[Session, int], None]] = {}


def register_purge_hook(table_name: str, hook: Callable[[Session, int], None]) -> None:
    """注册某张表的彻底删除钩子（如删磁盘文件）。"""
    PURGE_HOOKS[table_name] = hook


def retention_days(db: Session) -> int:
    """保留期天数（sys_config `recycle.retention_days`，默认 180）。"""
    from app.modules.settings.service import get_value

    raw = (get_value(db, RETENTION_KEY, "") or "").strip()
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS
    return days if days > 0 else DEFAULT_RETENTION_DAYS


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_load(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _title_of(obj: Any, fallback: str = "") -> str:
    for attr in ("title", "name", "code", "no", "subject"):
        val = getattr(obj, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback or f"#{getattr(obj, 'id', '')}"


def track(
    db: Session,
    model: Any,
    obj: Any,
    *,
    user: Any = None,
    title: str = "",
    module: str = "",
    resource: str = "",
    restore_fields: dict[str, Any] | None = None,
    cascade: Sequence[tuple[Any, Sequence[int]]] | None = None,
    meta: dict[str, Any] | None = None,
) -> Any:
    """把一条已软删的记录登记进回收站（**不改动 deleted 标记**）。

    用于两种场景：
    1. `soft_delete()` 内部调用；
    2. 调用方自己设了特殊 `deleted` 值（如 `deleted = obj.id` 让唯一键不撞）时，
       先自己改标记，再调本函数登记。
    """
    from app.modules.recycle.models import RecycleBin

    now = datetime.now()
    days = retention_days(db)
    cascade_meta: list[dict[str, Any]] = []
    for child_model, ids in cascade or []:
        ids = [int(i) for i in ids]
        if not ids:
            continue
        cascade_meta.append({"table": child_model.__tablename__, "ids": ids})
    payload = dict(meta or {})
    payload["cascade"] = cascade_meta

    entry = RecycleBin(
        module=module or (model.__module__.rsplit(".", 1)[-1] if model else ""),
        table_name=getattr(model, "__tablename__", ""),
        resource=resource or getattr(model, "__name__", ""),
        resource_id=int(getattr(obj, "id", 0) or 0),
        title=title or _title_of(obj),
        deleted_by=getattr(user, "id", None),
        deleted_by_name=getattr(user, "name", "") or "",
        deleted_at=now,
        purge_after=now + timedelta(days=days),
        status=STATUS_RECYCLED,
        restore_fields=_json_dump(restore_fields or {}),
        meta=_json_dump(payload),
    )
    db.add(entry)
    db.flush()
    return entry


def soft_delete(
    db: Session,
    model: Any,
    obj: Any,
    *,
    user: Any = None,
    title: str = "",
    module: str = "",
    resource: str = "",
    restore_fields: dict[str, Any] | None = None,
    cascade: Sequence[tuple[Any, Sequence[int]]] | None = None,
    meta: dict[str, Any] | None = None,
) -> Any:
    """软删除一条记录并登记进回收站（返回回收站条目）。"""
    if hasattr(obj, "deleted"):
        obj.deleted = 1
    for child_model, ids in cascade or []:
        if not ids:
            continue
        for cid in ids:
            child = db.get(child_model, cid)
            if child is not None and hasattr(child, "deleted"):
                child.deleted = 1
    return track(
        db,
        model,
        obj,
        user=user,
        title=title,
        module=module,
        resource=resource,
        restore_fields=restore_fields,
        cascade=cascade,
        meta=meta,
    )


def restore_entry(db: Session, entry: Any) -> None:
    """恢复一条回收站记录（含级联软删的子行）。"""
    if entry.status != STATUS_RECYCLED:
        raise BizException(R.RECYCLE_NOT_RECYLED, "该记录不在回收站中，无法恢复")
    tbl = Base.metadata.tables.get(entry.table_name)
    if tbl is None:
        raise BizException(R.RECYCLE_RESTORE_FAILED, f"数据表 {entry.table_name} 不存在，无法恢复")
    values: dict[str, Any] = {}
    if "deleted" in tbl.c:
        values["deleted"] = 0
    for key, val in _json_load(entry.restore_fields).items():
        if key in tbl.c:
            values[key] = val
    if values:
        db.execute(tbl.update().where(tbl.c.id == entry.resource_id).values(**values))
    for child in _json_load(entry.meta).get("cascade", []):
        ctbl = Base.metadata.tables.get(child.get("table", ""))
        ids = [int(i) for i in child.get("ids", [])]
        if ctbl is None or not ids or "deleted" not in ctbl.c:
            continue
        db.execute(ctbl.update().where(ctbl.c.id.in_(ids)).values(deleted=0))
    entry.status = STATUS_RESTORED
    entry.update_time = datetime.now()


def purge_entry(db: Session, entry: Any, user: Any = None) -> None:
    """彻底删除一条回收站记录 —— **保留期内一律拒绝**。"""
    if entry.status != STATUS_RECYCLED:
        raise BizException(R.RECYCLE_NOT_RECYLED, "该记录不在回收站中")
    now = datetime.now()
    if entry.purge_after and now < entry.purge_after:
        days = (entry.purge_after - now).days + 1
        raise BizException(
            R.RECYCLE_RETENTION_ACTIVE,
            f"该记录处于保留期内，还需 {days} 天才能彻底删除（到期日 {entry.purge_after:%Y-%m-%d}）",
        )
    hook = PURGE_HOOKS.get(entry.table_name)
    if hook is not None:
        hook(db, entry.resource_id)
    tbl = Base.metadata.tables.get(entry.table_name)
    if tbl is not None:
        db.execute(tbl.delete().where(tbl.c.id == entry.resource_id))
    entry.status = STATUS_PURGED
    entry.purged_at = now
    entry.purged_by = getattr(user, "id", None)
    entry.update_time = now


def recycled_rows(db: Session, module: str = "") -> list[Any]:
    """回收站条目列表（按删除时间倒序）。"""
    from app.modules.recycle.models import RecycleBin

    stmt = select(RecycleBin).where(RecycleBin.status == STATUS_RECYCLED)
    if module:
        stmt = stmt.where(RecycleBin.module == module)
    return list(db.scalars(stmt.order_by(RecycleBin.deleted_at.desc())).all())

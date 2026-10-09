"""审计日志写入（登录/增删改/导出全记）。"""

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger("bizsys.audit")


def record(
    db: Session,
    *,
    user_id: int | None,
    module: str,
    action: str,
    biz_type: str = "",
    biz_id: int | None = None,
    detail: Any = None,
    trace_id: str = "",
    ip: str = "",
) -> None:
    """尽力而为写审计；失败不阻断业务。"""
    try:
        from app.modules.admin.models import SysAuditLog

        row = SysAuditLog(
            user_id=user_id,
            module=module,
            action=action,
            biz_type=biz_type,
            biz_id=biz_id,
            detail=json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
            trace_id=trace_id or None,
            ip=ip or None,
        )
        db.add(row)
    except Exception:
        logger.exception("audit write failed module=%s action=%s", module, action)

"""审计日志写入 —— 字段级证据链（B9 合规基线）。

对应《合规开发原则》2.2「审计追踪不是日志，而是证据链」与 4.4「日志写入只追加，
采用 WORM 介质或哈希链保证不可篡改」。

设计要点：

1. `record()` **保持既有参数集不变**，新增字段全部 keyword-only 且有默认值，
   280+ 个既有调用点零改动；trace_id / ip / UA 缺省从请求上下文（`app/core/reqctx.py`）取。
2. **链头是唯一权威游标**：`sys_audit_chain_head` 单行（chain_key='main'），
   靠 `SELECT ... FOR UPDATE NOWAIT` 串行化。不用 `MAX(id)` —— 并发下必然分叉。
3. 链头更新与审计行插入在**同一事务** → 业务回滚则链上不留空洞。
4. 失败双档：默认尽力而为（写 `sys_audit_failure` 台账留痕）；`strict=True`
   或全局开关 `audit.strict.enabled` 打开时抛 `ADMIN_AUDIT_WRITE_FAILED` 并回滚业务。
5. `create_time` 取数据库权威时间 `NOW(3)`（毫秒），并**显式写入**，
   这样 `row_hash` 里包含的时间戳能被校验方原样复现（列必须是 DATETIME(3)）。
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import reqctx
from app.core import response as R
from app.core.config import settings
from app.core.crypto import derive_key
from app.core.exceptions import BizException

logger = logging.getLogger("bizsys.audit")

CHAIN_KEY = "main"
HASH_ALG = "HMAC-SHA256"
KEY_VERSION = "v1"
CONFIG_STRICT = "audit.strict.enabled"

# 参与哈希的字段（固定顺序，改动即破坏历史链 —— 新增字段只能追加到末尾）
_HASH_FIELDS = (
    "chain_seq",
    "user_id",
    "module",
    "action",
    "biz_type",
    "biz_id",
    "detail",
    "trace_id",
    "ip",
    "field_name",
    "old_value",
    "new_value",
    "reason",
    "user_agent",
    "create_time",
)


# ---------------- 哈希 ----------------
def _chain_key_bytes() -> bytes:
    return derive_key("audit-chain")


def _fmt_ts(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat(timespec="milliseconds")


def _row_payload(row) -> dict[str, Any]:
    """参与哈希的字段快照（写入与校验必须用同一份逻辑）。"""
    return {
        "chain_seq": "" if row.chain_seq is None else row.chain_seq,
        "user_id": "" if row.user_id is None else row.user_id,
        "module": row.module or "",
        "action": row.action or "",
        "biz_type": row.biz_type or "",
        "biz_id": "" if row.biz_id is None else row.biz_id,
        "detail": row.detail or "",
        "trace_id": row.trace_id or "",
        "ip": row.ip or "",
        "field_name": row.field_name or "",
        "old_value": row.old_value or "",
        "new_value": row.new_value or "",
        "reason": row.reason or "",
        "user_agent": row.user_agent or "",
        "create_time": _fmt_ts(row.create_time),
    }


def _canonical(payload: dict[str, Any]) -> str:
    return "\n".join(f"{name}={payload.get(name)}" for name in _HASH_FIELDS) + "\n"


def compute_row_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    msg = f"{prev_hash or ''}\n{_canonical(payload)}".encode()
    return hmac.new(_chain_key_bytes(), msg, hashlib.sha256).hexdigest()


# ---------------- 写入 ----------------
def _server_now(db: Session) -> datetime:
    """数据库权威时间 NOW(3)（毫秒精度）。同一 Session 内缓存，避免每条审计都打库。"""
    cached = db.info.get("_audit_server_now")
    if cached is not None:
        return cached
    value = db.execute(text("SELECT NOW(3)")).scalar()
    if not isinstance(value, datetime):
        value = datetime.now()
    value = value.replace(microsecond=(value.microsecond // 1000) * 1000)
    db.info["_audit_server_now"] = value
    return value


def _strict_enabled(db: Session) -> bool:
    cached = db.info.get("_audit_strict")
    if cached is not None:
        return bool(cached)
    value = False
    try:
        from app.modules.settings.service import get_value

        value = str(get_value(db, CONFIG_STRICT, "0")).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:  # noqa: BLE001 配置读不到时按默认（尽力而为）
        value = False
    db.info["_audit_strict"] = value
    return value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(value)


def _lock_head(db: Session):
    """取链头并加行锁（NOWAIT：拿不到锁立即失败，绝不挂死业务请求）。"""
    from app.modules.admin.models import AuditChainHead

    stmt = (
        select(AuditChainHead)
        .where(AuditChainHead.chain_key == CHAIN_KEY)
        .with_for_update(nowait=True)
    )
    head = db.scalars(stmt).first()
    if head is None:
        # 迁移已初始化单行；这里只兜底极端场景（表刚建好还没插种子行）
        head = AuditChainHead(chain_key=CHAIN_KEY, last_seq=0, last_hash="", last_row_id=0)
        db.add(head)
        db.flush([head])
        head = db.scalars(stmt).first() or head
    return head


def _write_row(
    db: Session,
    *,
    user_id: int | None,
    module: str,
    action: str,
    biz_type: str,
    biz_id: int | None,
    detail: Any,
    trace_id: str,
    ip: str,
    field_name: str,
    old_value: Any,
    new_value: Any,
    reason: str,
    user_agent: str,
) -> None:
    from app.modules.admin.models import AuditLog

    ctx = reqctx.current()
    now = _server_now(db)
    head = _lock_head(db)

    seq = int(head.last_seq or 0) + 1
    prev_hash = head.last_hash or ""

    row = AuditLog(
        user_id=user_id,
        module=module,
        action=action,
        biz_type=biz_type,
        biz_id=biz_id,
        detail=_text(detail),
        trace_id=trace_id or ctx.trace_id or None,
        ip=ip or ctx.ip or None,
        field_name=field_name or "",
        old_value=_text(old_value),
        new_value=_text(new_value),
        reason=_text(reason) if reason else None,
        user_agent=user_agent or ctx.user_agent or "",
        create_time=now,
        chain_seq=seq,
        prev_hash=prev_hash,
        hash_alg=HASH_ALG,
    )
    row.row_hash = compute_row_hash(prev_hash, _row_payload(row))
    db.add(row)
    try:
        db.flush([row])
    except Exception:
        db.expunge(row)
        raise

    head.last_seq = seq
    head.last_hash = row.row_hash
    head.last_row_id = row.id


def _note_failure(
    db: Session,
    *,
    user_id: int | None,
    module: str,
    action: str,
    biz_type: str,
    biz_id: int | None,
    exc: Exception,
) -> None:
    """审计写失败本身也要留痕（证据缺口台账，只追加）。"""
    try:
        from app.modules.admin.models import AuditFailure

        db.add(
            AuditFailure(
                user_id=user_id,
                module=module,
                action=action,
                biz_type=biz_type,
                biz_id=biz_id,
                error=f"{exc.__class__.__name__}: {exc}"[:255],
                detail=_text(str(exc)),
            )
        )
        db.flush()
    except Exception:  # noqa: BLE001 台账写不了也不能阻断业务
        logger.exception("audit failure note failed")


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
    field_name: str = "",
    old_value: Any = None,
    new_value: Any = None,
    reason: str = "",
    user_agent: str = "",
    strict: bool | None = None,
) -> None:
    """写审计（字段级 + 哈希链）。

    默认尽力而为：失败只记 `sys_audit_failure`，不阻断业务。
    `strict=True`（或全局开关 `audit.strict.enabled` 打开）时失败抛
    `ADMIN_AUDIT_WRITE_FAILED`，由调用方的 `db.commit()` 回滚整个事务。
    """
    try:
        _write_row(
            db,
            user_id=user_id,
            module=module,
            action=action,
            biz_type=biz_type,
            biz_id=biz_id,
            detail=detail,
            trace_id=trace_id,
            ip=ip,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            user_agent=user_agent,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("audit write failed module=%s action=%s", module, action)
        _note_failure(
            db,
            user_id=user_id,
            module=module,
            action=action,
            biz_type=biz_type,
            biz_id=biz_id,
            exc=exc,
        )
        if strict or _strict_enabled(db):
            raise BizException(R.ADMIN_AUDIT_WRITE_FAILED) from exc


# ---------------- 校验 ----------------
def verify_chain(db: Session, *, mode: str = "full", from_seq: int | None = None) -> dict:
    """校验审计链完整性。

    四件事：① chain_seq 连续（断号 = 有行被删）② prev_hash 与上一行相连
    ③ 重算 row_hash 比对（内容被改）④ 链头与最后一行一致（链头被改）。
    """
    from app.modules.admin.models import AuditChainHead, AuditLog

    head = db.scalar(select(AuditChainHead).where(AuditChainHead.chain_key == CHAIN_KEY))
    legacy_rows = (
        db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.chain_seq.is_(None))) or 0
    )

    anchor = load_anchor()
    start_seq: int | None = None
    if from_seq is not None:
        start_seq = int(from_seq)
    elif mode == "since_anchor" and anchor:
        start_seq = int(anchor["seq"]) + 1

    stmt = select(AuditLog).where(AuditLog.chain_seq.is_not(None)).order_by(AuditLog.chain_seq)
    if start_seq is not None:
        stmt = stmt.where(AuditLog.chain_seq >= start_seq)
    rows = db.scalars(stmt).all()

    prev_hash = ""
    expected = 1
    if start_seq is not None and start_seq > 1:
        prior = db.scalar(select(AuditLog).where(AuditLog.chain_seq == start_seq - 1))
        prev_hash = (prior.row_hash or "") if prior else ""
        expected = start_seq

    broken: dict[str, Any] | None = None
    checked = 0
    for r in rows:
        checked += 1
        if r.chain_seq != expected:
            broken = {
                "seq": r.chain_seq,
                "rowId": r.id,
                "reason": "seq_gap",
                "expected": expected,
                "actual": r.chain_seq,
            }
            break
        if (r.prev_hash or "") != (prev_hash or ""):
            broken = {
                "seq": r.chain_seq,
                "rowId": r.id,
                "reason": "prev_hash_mismatch",
                "expected": prev_hash,
                "actual": r.prev_hash,
            }
            break
        calc = compute_row_hash(prev_hash, _row_payload(r))
        if calc != (r.row_hash or ""):
            broken = {
                "seq": r.chain_seq,
                "rowId": r.id,
                "reason": "row_hash_mismatch",
                "expected": calc,
                "actual": r.row_hash,
            }
            break
        prev_hash = r.row_hash or ""
        expected = r.chain_seq + 1

    head_matches = True
    if broken is None and rows and head is not None:
        last = rows[-1]
        if int(head.last_seq or 0) != int(last.chain_seq or 0) or (head.last_hash or "") != (
            last.row_hash or ""
        ):
            head_matches = False
            broken = {
                "seq": head.last_seq,
                "rowId": head.last_row_id,
                "reason": "head_mismatch",
                "expected": last.row_hash,
                "actual": head.last_hash,
            }

    anchor_info: dict[str, Any] | None = None
    if anchor:
        anchor_info = {
            "seq": anchor["seq"],
            "hash": anchor["hash"],
            "at": anchor["at"],
            "file": anchor["file"],
            "truncated": False,
            "match": None,
        }
        if head is not None and int(head.last_seq or 0) < int(anchor["seq"]):
            anchor_info["truncated"] = True
        else:
            anchored_row = db.scalar(select(AuditLog).where(AuditLog.chain_seq == anchor["seq"]))
            if anchored_row is None:
                anchor_info["truncated"] = True
            else:
                anchor_info["match"] = (anchored_row.row_hash or "") == anchor["hash"]

    truncated = bool(anchor_info and anchor_info.get("truncated"))
    return {
        "ok": broken is None and head_matches and not truncated,
        "mode": mode,
        "checked": checked,
        "firstSeq": rows[0].chain_seq if rows else None,
        "lastSeq": rows[-1].chain_seq if rows else None,
        "headSeq": int(head.last_seq or 0) if head else 0,
        "headHash": (head.last_hash or "") if head else "",
        "headMatchesLastRow": head_matches,
        "brokenAt": broken,
        "anchor": anchor_info,
        "legacyRows": int(legacy_rows),
        "writeFailures": int(head.write_failures or 0) if head else 0,
        "hashAlg": HASH_ALG,
        "keyVersion": KEY_VERSION,
    }


def evidence_detail(db: Session, row_id: int) -> dict:
    """单条审计证据详情：链上位置 + 重算哈希比对。"""
    from app.modules.admin.models import AuditLog

    row = db.get(AuditLog, row_id)
    if row is None:
        raise BizException(R.GENERIC_NOT_FOUND, "审计记录不存在")

    payload = _row_payload(row)
    recalculated = compute_row_hash(row.prev_hash or "", payload) if row.chain_seq else ""
    return {
        "id": row.id,
        "chainSeq": row.chain_seq,
        "prevHash": row.prev_hash,
        "rowHash": row.row_hash,
        "hashAlg": row.hash_alg,
        "recalculatedHash": recalculated,
        "hashValid": bool(row.chain_seq) and recalculated == (row.row_hash or ""),
        "createTime": _fmt_ts(row.create_time),
        "userId": row.user_id,
        "module": row.module,
        "action": row.action,
        "bizType": row.biz_type,
        "bizId": row.biz_id,
        "fieldName": row.field_name,
        "oldValue": row.old_value,
        "newValue": row.new_value,
        "reason": row.reason,
        "detail": row.detail,
        "traceId": row.trace_id,
        "ip": row.ip,
        "userAgent": row.user_agent,
    }


# ---------------- 锚点（DB 之外的文件） ----------------
def _anchor_dir() -> Path:
    return Path(settings.audit_anchor_dir)


def _sign_anchor(seq: int, chain_hash: str, ts: str) -> str:
    msg = f"{seq}|{chain_hash}|{ts}".encode()
    return hmac.new(derive_key("audit-anchor"), msg, hashlib.sha256).hexdigest()[:32]


def write_anchor(db: Session) -> dict:
    """把当前链头锚定到 DB 之外的文件（只追加）。

    锚点文件不在数据库里 —— 整库被替换/重建时，锚点仍在，
    校验即可发现"链被截断或重写"。
    """
    from app.modules.admin.models import AuditChainHead

    head = db.scalar(select(AuditChainHead).where(AuditChainHead.chain_key == CHAIN_KEY))
    if head is None:
        raise BizException(R.GENERIC_NOT_FOUND, "审计链头不存在")

    seq = int(head.last_seq or 0)
    chain_hash = head.last_hash or ""
    ts = datetime.now().isoformat(timespec="milliseconds")
    directory = _anchor_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"anchor-{datetime.now().strftime('%Y%m%d')}.txt"
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(f"{seq}|{chain_hash}|{ts}|{_sign_anchor(seq, chain_hash, ts)}\n")

    head.anchored_seq = seq
    head.anchored_hash = chain_hash
    head.anchored_at = datetime.now()
    db.flush()
    return {"seq": seq, "hash": chain_hash, "at": ts, "file": str(path)}


def load_anchor() -> dict | None:
    """读取最新锚点（以 DB 之外的文件为准）。"""
    directory = _anchor_dir()
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("anchor-*.txt"))
    latest: dict[str, Any] | None = None
    for file in files:
        try:
            content = file.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            try:
                seq = int(parts[0])
            except ValueError:
                continue
            latest = {"seq": seq, "hash": parts[1], "at": parts[2], "file": str(file)}
    return latest


def list_anchors(limit: int = 50) -> list[dict]:
    """锚点历史（倒序）。"""
    directory = _anchor_dir()
    if not directory.is_dir():
        return []
    out: list[dict] = []
    for file in sorted(directory.glob("anchor-*.txt"), reverse=True):
        try:
            content = file.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            try:
                seq = int(parts[0])
            except ValueError:
                continue
            out.append(
                {
                    "seq": seq,
                    "hash": parts[1],
                    "at": parts[2],
                    "file": str(file),
                    "sigValid": len(parts) > 3 and parts[3] == _sign_anchor(seq, parts[1], parts[2]),
                }
            )
    out.sort(key=lambda x: x["seq"], reverse=True)
    return out[:limit]

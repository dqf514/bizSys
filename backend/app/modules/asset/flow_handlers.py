"""资产域的审批联动（F5）。

到货验收与资产处置原本都是"人工点一下就生效"—— 验收直接写库存流水、
处置直接核销资产。现在二者都接进审批引擎：

- 验收单 → 提交审批 → 通过后由 :func:`on_receipt_approved` 写库存流水；
- 处置单 → 提交审批 → 通过后由 :func:`on_disposal_approved` 落审批人留痕。

人工直通端点（``/receipts/{id}/accept``、``/disposals/{id}/approve``）在流程启用时
被 :func:`app.modules.approval.registry.require_manual` 堵死，流程停用才恢复。
"""

from sqlalchemy.orm import Session

from app.modules.asset.service import accept_receipt


def _operator(db: Session, operator_id: int):
    from app.modules.auth.models import User

    return db.get(User, operator_id) or User(id=operator_id)


def accept_receipt_pass_through(db: Session, row, initiator=None) -> None:
    """直通回调：未绑定验收流程时，提交即验收（写库存流水）。"""
    accept_receipt(db, row, initiator or _operator(db, 0))


def on_receipt_approved(db: Session, row, event) -> None:
    """验收审批通过 → 写库存流水并置为已验收。"""
    accept_receipt(db, row, _operator(db, getattr(event, "operator_id", 0) or 0))


def on_disposal_approved(db: Session, row, event) -> None:
    """处置审批通过 → 记录审批人与审批时间（核销仍由 /complete 执行）。"""
    operator = _operator(db, getattr(event, "operator_id", 0) or 0)
    row.approver_id = getattr(operator, "id", 0) or 0
    row.approver_name = getattr(operator, "name", "") or getattr(operator, "username", "") or ""
    row.approve_at = row.update_time
    db.flush()


__all__ = [
    "accept_receipt_pass_through",
    "on_disposal_approved",
    "on_receipt_approved",
]

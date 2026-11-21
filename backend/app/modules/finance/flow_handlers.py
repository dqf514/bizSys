"""财务域的审批联动（F5）。

回款（到账登记）原本是"财务录进去就算到账"，结算单金额随之被核销 —— 但钱有没有
真的到账、金额对不对，只能靠人工确认。F5 起回款必须经**复核审批**：

- 登记（``POST /finance/payments``）只写单据，状态 ``draft``；
- 提交复核（``POST /finance/payments/{id}/submit``）→ ``approving``；
- 审批通过 → ``confirmed``，由 :func:`on_payment_approved` 重算结算单的已到账金额，
  达到结算金额时把结算单推进到 ``paid``；
- 未复核的登记**不计入**结算单的已到账金额，避免"钱没到账却把应收核销掉"。

未配置复核流程定义时，提交即按人工审核口径直通到 ``confirmed``
（:func:`payment_pass_through`），与任务/结算单的历史口径一致。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.finance.models import Payment, Settlement


def confirmed_paid_total(db: Session, settlement_id: int) -> Decimal:
    """结算单下**已复核确认**的回款合计。"""
    total = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.settlement_id == settlement_id,
            Payment.deleted == 0,
            Payment.status == "confirmed",
        )
    )
    return Decimal(str(total or 0))


def _sync_settlement(db: Session, settlement_id: int) -> None:
    """按已确认回款重算结算单状态。

    已到账金额达到结算金额 → ``paid``；否则回到 ``invoiced``（已开票待收齐）。
    """
    # SessionLocal(autoflush=False)：本函数由审批回写钩子调用时，回款行的新状态
    # 可能还没落库，必须先 flush，否则聚合查询看不到本次复核结果。
    db.flush()
    s = db.get(Settlement, settlement_id)
    if s is None or s.deleted:
        return
    if s.status not in ("invoiced", "paid"):
        return  # 结算单还没走到开票阶段，不参与核销
    paid = confirmed_paid_total(db, settlement_id)
    target = "paid" if paid >= (s.amount or Decimal(0)) else "invoiced"
    if s.status != target:
        s.status = target
        s.update_time = datetime.now()
        db.flush()


def on_payment_approved(db: Session, row, event) -> None:
    """复核通过 → 重算结算单已到账金额与状态。"""
    _sync_settlement(db, row.settlement_id)


def on_payment_rejected(db: Session, row, event) -> None:
    """复核驳回 → 回款不计入已到账，重算结算单状态。"""
    _sync_settlement(db, row.settlement_id)


def payment_pass_through(db: Session, row, initiator=None) -> None:
    """直通回调：未绑定复核流程时，提交即确认入账并同步结算单。"""
    _sync_settlement(db, row.settlement_id)


__all__ = [
    "confirmed_paid_total",
    "on_payment_approved",
    "on_payment_rejected",
    "payment_pass_through",
]

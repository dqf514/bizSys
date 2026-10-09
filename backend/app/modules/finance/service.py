"""财务服务：开票审批事件订阅 + 快照。"""

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.common.events import ApprovalCompleted, ApprovalRejected, ApprovalWithdrawn, subscribe
from app.modules.finance.models import Invoice, Settlement


def snapshot(s: Settlement) -> dict:
    return {
        "settlementNo": s.settlement_no,
        "taskId": s.task_id,
        "taskNo": s.task_no,
        "customerName": s.customer_name,
        "contractNo": s.contract_no,
        "amount": str(s.amount),
        "invoiceableAmount": str(s.invoiceable_amount),
        "status": s.status,
    }


def form_snapshot(s: Settlement) -> dict:
    return json.loads(json.dumps(snapshot(s), ensure_ascii=False, default=str))


def _handle_completed(event: ApprovalCompleted) -> None:
    """开票审批通过 → 结算单 invoiced，并生成发票行（invoice_no 待财务登记）。"""
    if event.biz_type != "invoice":
        return
    db: Session = event.db
    s = db.get(Settlement, event.biz_id)
    if not s or s.deleted or s.status != "invoicing":
        return
    s.status = "invoiced"
    s.approval_instance_id = event.instance_id
    s.update_time = datetime.now()
    db.add(
        Invoice(
            settlement_id=s.id,
            amount=s.invoiceable_amount,
            status="issued",
            approval_instance_id=event.instance_id,
            create_by=event.operator_id,
        )
    )
    db.flush()


def _rollback_pending(db: Session, biz_id: int, instance_id: int) -> None:
    s = db.get(Settlement, biz_id)
    if not s or s.deleted or s.status != "invoicing":
        return
    s.status = "pending"
    s.approval_instance_id = instance_id
    s.update_time = datetime.now()


def _handle_rejected(event: ApprovalRejected) -> None:
    if event.biz_type != "invoice":
        return
    _rollback_pending(event.db, event.biz_id, event.instance_id)


def _handle_withdrawn(event: ApprovalWithdrawn) -> None:
    if event.biz_type != "invoice":
        return
    _rollback_pending(event.db, event.biz_id, event.instance_id)


subscribe(ApprovalCompleted, _handle_completed)
subscribe(ApprovalRejected, _handle_rejected)
subscribe(ApprovalWithdrawn, _handle_withdrawn)

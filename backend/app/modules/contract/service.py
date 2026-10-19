"""合同服务：状态机约束 + 审批事件订阅。"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.events import ApprovalCompleted, ApprovalRejected, ApprovalWithdrawn, subscribe
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.contract.models import Contract

EDITABLE = ("draft", "rejected")


def check_editable(c: Contract) -> None:
    if c.status == "approving":
        raise BizException(R.CONTRACT_EDITING_LOCKED)
    if c.status not in EDITABLE:
        raise BizException(R.CONTRACT_INVALID_STATE, f"状态「{c.status}」不允许编辑")


def snapshot(c: Contract) -> dict:
    return {
        "contractNo": c.contract_no or "",
        "name": c.name,
        "customerId": c.customer_id,
        "customerName": c.customer_name,
        "contractType": c.contract_type,
        "amount": float(c.amount) if c.amount is not None else None,
        "status": c.status,
        "handlerName": c.handler_name,
    }


def _handle_completed(event: ApprovalCompleted) -> None:
    if event.biz_type != "contract":
        return
    db: Session = event.db
    c = db.get(Contract, event.biz_id)
    if not c or c.deleted or c.status != "approving":
        return
    c.status = "approved"
    c.flow_instance_id = event.instance_id
    c.update_time = datetime.now()


def _handle_rejected(event: ApprovalRejected) -> None:
    if event.biz_type != "contract":
        return
    db: Session = event.db
    c = db.get(Contract, event.biz_id)
    if not c or c.deleted or c.status != "approving":
        return
    c.status = "rejected"
    c.flow_instance_id = event.instance_id
    c.update_time = datetime.now()


def _handle_withdrawn(event: ApprovalWithdrawn) -> None:
    """撤回后回写 draft（可编辑/可再提交），避免合同卡在 approving。"""
    if event.biz_type != "contract":
        return
    db: Session = event.db
    c = db.get(Contract, event.biz_id)
    if not c or c.deleted or c.status != "approving":
        return
    c.status = "draft"
    c.flow_instance_id = event.instance_id
    c.update_time = datetime.now()


subscribe(ApprovalCompleted, _handle_completed)
subscribe(ApprovalRejected, _handle_rejected)
subscribe(ApprovalWithdrawn, _handle_withdrawn)


def form_snapshot(c: Contract) -> dict:
    return json.loads(json.dumps(snapshot(c), ensure_ascii=False, default=str))


def load_customer_name(db: Session, customer_id: int) -> str:
    from app.modules.crm.models import Customer

    row = db.scalar(select(Customer.name).where(Customer.id == customer_id, Customer.deleted == 0))
    if not row:
        raise BizException(R.GENERIC_NOT_FOUND, "客户不存在")
    return row

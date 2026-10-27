"""采购服务：状态机约束 + 审批事件订阅 + 关联档案装载。"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.events import ApprovalCompleted, ApprovalRejected, ApprovalWithdrawn, subscribe
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.procurement.models import PurchaseContract, PurchaseRequest, TenderBid, TenderProject

EDITABLE = ("draft", "rejected")


def check_editable(status: str) -> None:
    if status == "approving":
        raise BizException(R.PROCUREMENT_INVALID_STATE, "审批中单据禁止编辑")
    if status not in EDITABLE:
        raise BizException(R.PROCUREMENT_INVALID_STATE, f"状态「{status}」不允许编辑")


def request_snapshot(r: PurchaseRequest) -> dict:
    return {
        "requestNo": r.request_no or "",
        "title": r.title,
        "taskId": r.task_id,
        "taskNo": r.task_no,
        "taskName": r.task_name,
        "purchaseMethod": r.purchase_method,
        "budgetAmount": float(r.budget_amount) if r.budget_amount is not None else None,
        "expectDate": r.expect_date.strftime("%Y-%m-%d") if r.expect_date else "",
        "status": r.status,
        "items": [
            {
                "itemName": i.item_name,
                "spec": i.spec,
                "unit": i.unit,
                "quantity": float(i.quantity),
                "estimatePrice": float(i.estimate_price) if i.estimate_price is not None else None,
            }
            for i in (r.items or [])
            if not i.deleted
        ],
    }


def contract_snapshot(c: PurchaseContract) -> dict:
    return {
        "contractNo": c.contract_no or "",
        "name": c.name,
        "requestId": c.request_id,
        "requestNo": c.request_no,
        "supplierId": c.supplier_id,
        "supplierName": c.supplier_name,
        "amount": float(c.amount) if c.amount is not None else None,
        "status": c.status,
        "handlerName": c.handler_name,
    }


def form_snapshot(obj) -> dict:
    snap = request_snapshot(obj) if isinstance(obj, PurchaseRequest) else contract_snapshot(obj)
    return json.loads(json.dumps(snap, ensure_ascii=False, default=str))


def load_task(db: Session, task_id: int) -> tuple[str, str]:
    from app.modules.task.models import Task

    row = db.execute(select(Task.task_no, Task.task_name).where(Task.id == task_id, Task.deleted == 0)).first()
    if not row:
        raise BizException(R.GENERIC_NOT_FOUND, "关联任务不存在")
    return row[0], row[1]


def load_supplier_name(db: Session, supplier_id: int) -> str:
    """供应商必须是启用的 supplier/both 往来单位。"""
    from app.modules.crm.models import Customer

    row = db.execute(
        select(Customer.name, Customer.partner_type, Customer.status).where(
            Customer.id == supplier_id, Customer.deleted == 0
        )
    ).first()
    if not row or row[1] not in ("supplier", "both") or row[2] != "enabled":
        raise BizException(R.PROCUREMENT_SUPPLIER_INVALID)
    return row[0]


def _handle_completed(event: ApprovalCompleted) -> None:
    if event.biz_type not in ("purchase_request", "purchase_contract", "tender_award"):
        return
    db: Session = event.db
    if event.biz_type == "tender_award":
        _award_completed(db, event.biz_id, event.instance_id)
        return
    model = PurchaseRequest if event.biz_type == "purchase_request" else PurchaseContract
    obj = db.get(model, event.biz_id)
    if not obj or obj.deleted or obj.status != "approving":
        return
    obj.status = "approved"
    obj.flow_instance_id = event.instance_id
    obj.update_time = datetime.now()


def _handle_rejected(event: ApprovalRejected) -> None:
    if event.biz_type not in ("purchase_request", "purchase_contract", "tender_award"):
        return
    db: Session = event.db
    if event.biz_type == "tender_award":
        # 定标被驳回 → 回到评标中，可重新选择投标再提交
        t = db.get(TenderProject, event.biz_id)
        if t and not t.deleted and t.status == "awarding":
            t.status = "evaluating"
            t.award_bid_id = None
            t.flow_instance_id = event.instance_id
            t.update_time = datetime.now()
        return
    model = PurchaseRequest if event.biz_type == "purchase_request" else PurchaseContract
    obj = db.get(model, event.biz_id)
    if not obj or obj.deleted or obj.status != "approving":
        return
    obj.status = "rejected"
    obj.flow_instance_id = event.instance_id
    obj.update_time = datetime.now()


def _handle_withdrawn(event: ApprovalWithdrawn) -> None:
    """撤回后回写 draft（可编辑/可再提交），避免单据卡在 approving。"""
    if event.biz_type not in ("purchase_request", "purchase_contract", "tender_award"):
        return
    db: Session = event.db
    if event.biz_type == "tender_award":
        t = db.get(TenderProject, event.biz_id)
        if t and not t.deleted and t.status == "awarding":
            t.status = "evaluating"
            t.award_bid_id = None
            t.flow_instance_id = event.instance_id
            t.update_time = datetime.now()
        return
    model = PurchaseRequest if event.biz_type == "purchase_request" else PurchaseContract
    obj = db.get(model, event.biz_id)
    if not obj or obj.deleted or obj.status != "approving":
        return
    obj.status = "draft"
    obj.flow_instance_id = event.instance_id
    obj.update_time = datetime.now()


def _award_completed(db: Session, tender_id: int, instance_id: int) -> None:
    """定标审批通过：awarding → awarded，中标投标/单位/金额落库（门户公示口径）。"""
    t = db.get(TenderProject, tender_id)
    if not t or t.deleted or t.status != "awarding" or not t.award_bid_id:
        return
    bid = db.get(TenderBid, t.award_bid_id)
    if not bid or bid.deleted:
        return
    t.status = "awarded"
    t.winner_bid_id = bid.id
    t.winner_name = bid.company_name
    t.winner_amount = bid.price
    t.award_bid_id = None
    t.flow_instance_id = instance_id
    t.update_time = datetime.now()


def tender_snapshot(t: TenderProject, bid: TenderBid | None) -> dict:
    return json.loads(json.dumps({
        "tenderNo": t.tender_no or "",
        "name": t.name,
        "tenderMethod": t.tender_method,
        "budgetAmount": float(t.budget_amount) if t.budget_amount is not None else None,
        "winnerBidId": bid.id if bid else None,
        "winnerName": bid.company_name if bid else "",
        "winnerAmount": float(bid.price) if bid else None,
        "status": t.status,
    }, ensure_ascii=False, default=str))


subscribe(ApprovalCompleted, _handle_completed)
subscribe(ApprovalRejected, _handle_rejected)
subscribe(ApprovalWithdrawn, _handle_withdrawn)

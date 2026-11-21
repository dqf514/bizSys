"""在线任务委托（B2）：委托单状态机、受理发号、生成任务草稿、抄送业务负责人。

行业口径（汽车检测/检验/认证与风洞实验室通用流程）：
    客户在线提交委托申请（基于已审批合同）→ 客户经理受理（技术要求澄清）→ 生成任务草稿
    → 任务流转到试验/加工/仿真执行 → 报告交付 → 委托关闭。
「业务经理代提交」用于电话/邮件委托的补录，来源标记 source=staff 以便区分。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import notify as notify_svc
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.contract.models import Contract
from app.modules.task.models import Task, TaskEntrust, TaskEntrustItem, TaskItem
from app.services.numbering import next_no

# 委托类型 → 业务板块 / 任务类型（受理生成任务时使用）
TYPE_BIZ_BLOCK = {
    "sim": "cfd",
    "model": "model_center",
    "test": "windtunnel_dept",
    "outsource": "consulting_dept",
}
TYPE_TASK_TYPE = {
    "sim": "cfd",
    "model": "model",
    "test": "windtunnel",
    "outsource": "outsource",
}

# 状态机：允许的前置状态 → 目标状态
TRANSITIONS: dict[str, tuple[set[str], str]] = {
    "submit": ({"draft", "rejected"}, "submitted"),
    "accept": ({"submitted"}, "accepted"),
    "reject": ({"submitted"}, "rejected"),
    "dispatch": ({"accepted"}, "dispatched"),
    "close": ({"dispatched"}, "closed"),
    "cancel": ({"draft", "submitted", "accepted"}, "cancelled"),
}

STATUS_CN = {
    "draft": "草稿",
    "submitted": "待受理",
    "accepted": "已受理",
    "rejected": "已驳回",
    "dispatched": "已生成任务",
    "closed": "已关闭",
    "cancelled": "已取消",
}
STATUSES = list(STATUS_CN)

# 访客管理人员权限点（B3 落地后自动生效；当前无此权限时跳过抄送）
VISITOR_ADMIN_PERM = "visitor:visit:list"


def transition(db: Session, entrust: TaskEntrust, action: str) -> TaskEntrust:
    """按状态机流转；受理时发放委托单号。"""
    spec = TRANSITIONS.get(action)
    if not spec:
        raise BizException(R.GENERIC_PARAM, f"未知动作：{action}")
    allowed, target = spec
    if entrust.status not in allowed:
        raise BizException(
            R.TASK_ENTRUST_INVALID_STATE,
            f"状态「{STATUS_CN.get(entrust.status, entrust.status)}」不允许执行「{action}」",
        )
    if action == "accept" and not entrust.entrust_no:
        entrust.entrust_no = next_no(db, "entrust")
        db.flush()
    entrust.status = target
    entrust.version += 1
    entrust.update_time = datetime.now()
    return entrust


def load_contract(db: Session, contract_id: int | None) -> Contract | None:
    """取委托关联合同；必须已审批通过。"""
    if not contract_id:
        return None
    c = db.get(Contract, contract_id)
    if not c or c.deleted or c.status != "approved":
        raise BizException(R.TASK_ENTRUST_CONTRACT_INVALID)
    return c


def create_entrust(
    db: Session,
    body,
    *,
    source: str = "portal",
    applicant_type: str = "portal",
    applicant_id: int | None = None,
    applicant_name: str = "",
    applicant_phone: str = "",
    customer_id: int | None = None,
    customer_name: str = "",
    handler_id: int | None = None,
    handler_name: str = "",
) -> TaskEntrust:
    """创建委托单（status=submitted，客户自助与业务代提交提交后即待受理）。"""
    contract = load_contract(db, body.contract_id)
    if contract:
        customer_id = contract.customer_id
        customer_name = contract.customer_name
    if not customer_id:
        raise BizException(R.CRM_ACCOUNT_NOT_BOUND, "委托单必须关联已审批的合同或绑定往来单位")

    entrust = TaskEntrust(
        title=body.title,
        entrust_type=body.entrust_type or "",
        contract_id=contract.id if contract else None,
        contract_no=contract.contract_no or "" if contract else "",
        customer_id=customer_id,
        customer_name=customer_name,
        biz_block=TYPE_BIZ_BLOCK.get(body.entrust_type or "", ""),
        source=source,
        applicant_type=applicant_type,
        applicant_id=applicant_id,
        applicant_name=applicant_name,
        applicant_phone=applicant_phone,
        requirement=body.requirement,
        sample_desc=body.sample_desc,
        plan_start_date=body.plan_start_date,
        plan_end_date=body.plan_end_date,
        priority=body.priority or "normal",
        amount=body.amount,
        remark=body.remark,
        status="submitted",
        handler_id=handler_id,
        handler_name=handler_name,
        create_by=applicant_id,
    )
    db.add(entrust)
    db.flush()
    sync_items(db, entrust, body.items)
    return entrust


def sync_items(db: Session, entrust: TaskEntrust, items) -> None:
    """整体替换委托明细（按 id 保留）。"""
    keep_ids = {i.id for i in items if getattr(i, "id", None)}
    for old in list(entrust.items):
        if old.id not in keep_ids:
            db.delete(old)
    existing = {i.id: i for i in entrust.items}
    order = 1
    for body in items:
        row = existing.get(body.id) if body.id else None
        if row is None:
            row = TaskEntrustItem(entrust_id=entrust.id)
            db.add(row)
            entrust.items.append(row)
        row.item_code = body.item_code or f"{order:02d}"
        row.name = body.name
        row.std = body.std
        row.qty = body.qty
        row.need_report = body.need_report
        row.report_type = body.report_type
        row.remark = body.remark
        order += 1
    db.flush()


def notify_biz_owner(db: Session, entrust: TaskEntrust, operator_id: int | None = None) -> int:
    """抄送业务负责人（受理后）。返回写入的通知条数。"""
    if not entrust.biz_owner_id:
        return 0
    return notify_svc.notify(
        db,
        [entrust.biz_owner_id],
        title=f"客户委托待执行：{entrust.entrust_no or entrust.title}",
        content=f"{entrust.customer_name} · {entrust.title}",
        biz_type="entrust",
        biz_id=entrust.id,
        link=f"/task/entrusts?id={entrust.id}",
        exclude_user_id=operator_id,
    )


def dispatch_to_task(
    db: Session,
    entrust: TaskEntrust,
    operator,
    body=None,
) -> Task:
    """受理后按委托单生成任务草稿（task_no 在任务提交时发放）。"""
    contract = load_contract(db, entrust.contract_id)
    if not contract:
        raise BizException(R.TASK_ENTRUST_CONTRACT_INVALID)

    owner_id = getattr(body, "owner_id", None) if body else None
    owner_name = getattr(body, "owner_name", "") if body else ""
    dept_id = getattr(body, "dept_id", None) if body else None
    dept_name = getattr(body, "dept_name", "") if body else ""
    plan_finish = getattr(body, "plan_finish_date", None) if body else None

    task = Task(
        task_no=None,
        task_name=entrust.title,
        task_type=TYPE_TASK_TYPE.get(entrust.entrust_type or "", ""),
        contract_id=contract.id,
        contract_no=contract.contract_no or "",
        customer_id=entrust.customer_id,
        customer_name=entrust.customer_name,
        biz_block=entrust.biz_block or TYPE_BIZ_BLOCK.get(entrust.entrust_type or "", ""),
        dept_id=dept_id,
        dept_name=dept_name,
        owner_id=owner_id or (getattr(operator, "id", None)),
        owner_name=owner_name or getattr(operator, "name", "") or getattr(operator, "username", ""),
        content=entrust.requirement or "",
        receiver=entrust.applicant_name,
        receiver_unit=entrust.customer_name,
        plan_finish_date=plan_finish or entrust.plan_end_date,
        status="draft",
        create_by=getattr(operator, "id", None),
    )
    db.add(task)
    db.flush()

    order = 1
    for item in entrust.items:
        if item.deleted:
            continue
        db.add(
            TaskItem(
                task_id=task.id,
                item_code=item.item_code or f"{order:02d}",
                name=item.name,
                std=item.std,
                qty=item.qty,
                need_report=item.need_report,
            )
        )
        order += 1
    db.flush()

    entrust.task_id = task.id
    entrust.task_no = task.task_no or ""
    return task


def close_by_task(db: Session, task_id: int) -> None:
    """任务关闭后自动关闭对应委托单（幂等）。"""
    entrust = db.scalar(
        select(TaskEntrust).where(TaskEntrust.task_id == task_id, TaskEntrust.deleted == 0).limit(1)
    )
    if entrust and entrust.status == "dispatched":
        entrust.status = "closed"
        entrust.version += 1
        entrust.update_time = datetime.now()
        db.flush()

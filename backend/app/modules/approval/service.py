"""审批门面：待办三页签、意见时间线、流程定义管理。"""

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams, page_result
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.approval import engine
from app.modules.approval.models import (
    ApprovalDefinition,
    ApprovalInstance,
    ApprovalNode,
    ApprovalRecord,
    ApprovalTask,
)
from app.modules.approval.schemas import DefinitionIn
from app.modules.auth.models import User

_TASK_STATUS_CN = {
    "pending": "待审批",
    "agreed": "已同意",
    "rejected": "已驳回",
    "transferred": "已转办",
    "cancelled": "已作废",
}


def _task_item(t: ApprovalTask, inst: ApprovalInstance | None) -> dict:
    return {
        "id": t.id,
        "instanceId": t.instance_id,
        "bizType": inst.biz_type if inst else "",
        "bizId": inst.biz_id if inst else 0,
        "title": inst.title if inst else "",
        "status": t.status,
        "statusText": _TASK_STATUS_CN.get(t.status, t.status),
        "nodeName": t.node_name,
        "comment": t.comment,
        "initiatorName": inst.initiator_name if inst else "",
        "assigneeName": t.assignee_name,
        "createTime": t.create_time.strftime("%Y-%m-%d %H:%M:%S") if t.create_time else "",
        "actedAt": t.acted_at.strftime("%Y-%m-%d %H:%M:%S") if t.acted_at else "",
    }


def list_tasks(db: Session, user: User, params: PageParams, tab: str = "todo") -> dict:
    tab = tab or "todo"
    if tab == "todo":
        stmt = select(ApprovalTask).where(
            ApprovalTask.assignee_id == user.id,
            ApprovalTask.status == "pending",
            ApprovalTask.deleted == 0,
        )
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(
            db.scalars(
                stmt.order_by(ApprovalTask.create_time.desc())
                    .offset((params.page - 1) * params.size)
                    .limit(params.size)
            )
        )
        inst_map = _instances_by_id(db, [r.instance_id for r in rows])
        return page_result([_task_item(r, inst_map.get(r.instance_id)) for r in rows], total, params.page, params.size)

    if tab == "done":
        stmt = select(ApprovalRecord).where(
            ApprovalRecord.operator_id == user.id,
            ApprovalRecord.action.in_(("agree", "reject", "transfer", "add_sign")),
            ApprovalRecord.deleted == 0,
        )
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(
            db.scalars(
                stmt.order_by(ApprovalRecord.at.desc())
                    .offset((params.page - 1) * params.size)
                    .limit(params.size)
            )
        )
        inst_map = _instances_by_id(db, [r.instance_id for r in rows])
        items = []
        for r in rows:
            inst = inst_map.get(r.instance_id)
            items.append(
                {
                    "id": r.id,
                    "instanceId": r.instance_id,
                    "bizType": inst.biz_type if inst else "",
                    "bizId": inst.biz_id if inst else 0,
                    "title": inst.title if inst else "",
                    "status": inst.status if inst else "",
                    "statusText": "",
                    "nodeName": r.node_name,
                    "comment": r.comment,
                    "initiatorName": inst.initiator_name if inst else "",
                    "assigneeName": "",
                    "createTime": inst.create_time.strftime("%Y-%m-%d %H:%M:%S") if inst and inst.create_time else "",
                    "actedAt": r.at.strftime("%Y-%m-%d %H:%M:%S") if r.at else "",
                    "action": r.action,
                }
            )
        return page_result(items, total, params.page, params.size)

    if tab == "initiated":
        stmt = select(ApprovalInstance).where(
            ApprovalInstance.initiator_id == user.id,
            ApprovalInstance.deleted == 0,
        )
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(
            db.scalars(
                stmt.order_by(ApprovalInstance.create_time.desc())
                    .offset((params.page - 1) * params.size)
                    .limit(params.size)
            )
        )
        items = []
        for inst in rows:
            pending = pending_names(db, inst.id) if inst.status == "running" else ""
            items.append(_initiated_item(inst, pending))
        return page_result(items, total, params.page, params.size)

    raise BizException(R.GENERIC_PARAM, f"未知页签：{tab}")


def pending_names(db: Session, instance_id: int) -> str:
    rows = db.scalars(
        select(ApprovalTask.assignee_name).where(
            ApprovalTask.instance_id == instance_id,
            ApprovalTask.status == "pending",
            ApprovalTask.deleted == 0,
        )
    )
    return "/".join(dict.fromkeys(rows))


def _initiated_item(inst: ApprovalInstance, pending: str) -> dict:
    return {
        "id": inst.id,
        "instanceId": inst.id,
        "bizType": inst.biz_type,
        "bizId": inst.biz_id,
        "title": inst.title,
        "status": inst.status,
        "statusText": "",
        "nodeName": f"第{inst.current_seq}节点" if inst.status == "running" else "",
        "comment": pending and f"待办：{pending}" or "",
        "initiatorName": inst.initiator_name,
        "assigneeName": pending,
        "createTime": inst.create_time.strftime("%Y-%m-%d %H:%M:%S") if inst.create_time else "",
        "actedAt": inst.finished_at.strftime("%Y-%m-%d %H:%M:%S") if inst.finished_at else "",
    }


def _instances_by_id(db: Session, ids: list[int]) -> dict[int, ApprovalInstance]:
    if not ids:
        return {}
    rows = db.scalars(select(ApprovalInstance).where(ApprovalInstance.id.in_(ids))).all()
    return {r.id: r for r in rows}


def timeline(db: Session, biz_type: str, biz_id: int) -> dict:
    inst = db.scalar(
        select(ApprovalInstance)
        .where(
            ApprovalInstance.biz_type == biz_type,
            ApprovalInstance.biz_id == biz_id,
            ApprovalInstance.deleted == 0,
        )
        .order_by(ApprovalInstance.id.desc())
    )
    if not inst:
        return {"instanceId": 0, "status": "", "currentNode": "", "records": []}
    # 显式查询，避免 identity map 中旧的关系集合
    rows = db.scalars(
        select(ApprovalRecord)
        .where(ApprovalRecord.instance_id == inst.id, ApprovalRecord.deleted == 0)
        .order_by(ApprovalRecord.id)
    ).all()
    records = [
        {
            "action": r.action,
            "operatorName": r.operator_name,
            "nodeName": r.node_name,
            "comment": r.comment,
            "at": r.at.strftime("%Y-%m-%d %H:%M:%S") if r.at else "",
        }
        for r in rows
    ]
    return {
        "instanceId": inst.id,
        "status": inst.status,
        "currentNode": f"第{inst.current_seq}节点" if inst.status == "running" else "",
        "records": records,
    }


def _nodes_payload(definition: ApprovalDefinition) -> list[dict]:
    return [
        {
            "id": n.id,
            "seq": n.seq,
            "nodeName": n.node_name,
            "approverType": n.approver_type,
            "approverValue": n.approver_value,
            "approverName": n.approver_name,
        }
        for n in definition.nodes
        if n.deleted == 0
    ]


def list_definitions(db: Session) -> list[dict]:
    rows = db.scalars(
        select(ApprovalDefinition).where(ApprovalDefinition.deleted == 0).order_by(ApprovalDefinition.id)
    ).all()
    return [
        {
            "id": d.id,
            "code": d.code,
            "name": d.name,
            "bizType": d.biz_type,
            "enabled": d.enabled,
            "remark": d.remark,
            "nodes": _nodes_payload(d),
        }
        for d in rows
    ]


def _validate_nodes(body: DefinitionIn) -> None:
    if not body.nodes:
        raise BizException(R.GENERIC_PARAM, "至少配置一个审批节点")
    seqs = [n.seq for n in body.nodes]
    if len(seqs) != len(set(seqs)):
        raise BizException(R.GENERIC_PARAM, "节点序号不能重复")
    for n in body.nodes:
        if not n.approver_value.strip():
            raise BizException(R.GENERIC_PARAM, f"节点「{n.node_name or n.seq}」未选择审批人")


def create_definition(db: Session, body: DefinitionIn) -> dict:
    _validate_nodes(body)
    if db.scalar(
        select(ApprovalDefinition).where(ApprovalDefinition.code == body.code, ApprovalDefinition.deleted == 0)
    ):
        raise BizException(R.GENERIC_PARAM, f"流程编码已存在：{body.code}")
    d = ApprovalDefinition(
        code=body.code, name=body.name, biz_type=body.biz_type, enabled=body.enabled, remark=body.remark
    )
    db.add(d)
    db.flush()
    for n in sorted(body.nodes, key=lambda x: x.seq):
        db.add(
            ApprovalNode(
                definition_id=d.id,
                seq=n.seq,
                node_name=n.node_name,
                approver_type=n.approver_type,
                approver_value=n.approver_value,
                approver_name=n.approver_name,
            )
        )
    db.flush()
    return next(x for x in list_definitions(db) if x["id"] == d.id)


def update_definition(db: Session, def_id: int, body: DefinitionIn) -> dict:
    _validate_nodes(body)
    d = db.scalar(select(ApprovalDefinition).where(ApprovalDefinition.id == def_id, ApprovalDefinition.deleted == 0))
    if not d:
        raise BizException(R.GENERIC_NOT_FOUND)
    dup = db.scalar(
        select(ApprovalDefinition).where(
            ApprovalDefinition.code == body.code, ApprovalDefinition.id != def_id, ApprovalDefinition.deleted == 0
        )
    )
    if dup:
        raise BizException(R.GENERIC_PARAM, f"流程编码已存在：{body.code}")
    running = db.scalar(
        select(ApprovalInstance.id).where(
            ApprovalInstance.definition_id == d.id,
            ApprovalInstance.status == "running",
            ApprovalInstance.deleted == 0,
        )
    )
    if running:
        raise BizException(R.APPROVAL_INVALID_STATE, "存在进行中的审批实例，暂不能修改流程定义")
    d.code = body.code
    d.name = body.name
    d.biz_type = body.biz_type
    d.enabled = body.enabled
    d.remark = body.remark
    # 整组替换节点
    for n in list(d.nodes):
        db.delete(n)
    db.flush()
    for n in sorted(body.nodes, key=lambda x: x.seq):
        db.add(
            ApprovalNode(
                definition_id=d.id,
                seq=n.seq,
                node_name=n.node_name,
                approver_type=n.approver_type,
                approver_value=n.approver_value,
                approver_name=n.approver_name,
            )
        )
    db.flush()
    db.refresh(d)
    return next(x for x in list_definitions(db) if x["id"] == d.id)


def delete_definition(db: Session, def_id: int) -> None:
    d = db.scalar(select(ApprovalDefinition).where(ApprovalDefinition.id == def_id, ApprovalDefinition.deleted == 0))
    if not d:
        raise BizException(R.GENERIC_NOT_FOUND)
    running = db.scalar(
        select(ApprovalInstance.id).where(
            ApprovalInstance.definition_id == d.id,
            ApprovalInstance.status == "running",
            ApprovalInstance.deleted == 0,
        )
    )
    if running:
        raise BizException(R.APPROVAL_INVALID_STATE, "存在进行中的审批实例，暂不能删除流程定义")
    d.deleted = 1
    d.update_time = datetime.now()


def instance_snapshot(db: Session, instance_id: int) -> dict | None:
    inst = db.get(ApprovalInstance, instance_id)
    if not inst or inst.deleted:
        return None
    snap = None
    if inst.form_snapshot:
        try:
            snap = json.loads(inst.form_snapshot)
        except ValueError:
            snap = None
    return {
        "instanceId": inst.id,
        "bizType": inst.biz_type,
        "bizId": inst.biz_id,
        "title": inst.title,
        "status": inst.status,
        "initiatorName": inst.initiator_name,
        "currentNode": f"第{inst.current_seq}节点" if inst.status == "running" else "",
        "snapshot": snap,
    }


# engine 入口再导出，供业务模块 from app.modules.approval.service import start ...
start = engine.start
approve = engine.approve
reject = engine.reject
withdraw = engine.withdraw
add_sign = engine.add_sign
transfer = engine.transfer

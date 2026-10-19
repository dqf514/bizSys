"""审批门面：待办页签、我发起的（未读角标）、抄送我的、意见时间线、流程定义管理、分支预览。"""

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams, page_result
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.approval import engine
from app.modules.approval.graph import build_process_graph, dumps_graph, parse_json, preview_route
from app.modules.approval.models import (
    ApprovalCc,
    ApprovalDefinition,
    ApprovalInstance,
    ApprovalNode,
    ApprovalRecord,
    ApprovalTask,
    ApprovalViewState,
)
from app.modules.approval.schemas import DefinitionIn, NodeIn
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
        "nodeType": t.node_type,
        "taskKind": t.task_kind,
        "comment": t.comment,
        "initiatorName": inst.initiator_name if inst else "",
        "assigneeName": t.assignee_name,
        "createTime": t.create_time.strftime("%Y-%m-%d %H:%M:%S") if t.create_time else "",
        "actedAt": t.acted_at.strftime("%Y-%m-%d %H:%M:%S") if t.acted_at else "",
    }


def list_tasks(db: Session, user: User, params: PageParams, tab: str = "todo", biz_type: str | None = None) -> dict:
    tab = tab or "todo"
    if tab == "todo":
        stmt = select(ApprovalTask).where(
            ApprovalTask.assignee_id == user.id,
            ApprovalTask.status == "pending",
            ApprovalTask.deleted == 0,
        )
        if biz_type:
            stmt = stmt.join(ApprovalInstance, ApprovalInstance.id == ApprovalTask.instance_id).where(
                ApprovalInstance.biz_type == biz_type
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
        if biz_type:
            stmt = stmt.join(ApprovalInstance, ApprovalInstance.id == ApprovalRecord.instance_id).where(
                ApprovalInstance.biz_type == biz_type
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
        if biz_type:
            stmt = stmt.where(ApprovalInstance.biz_type == biz_type)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(
            db.scalars(
                stmt.order_by(ApprovalInstance.create_time.desc())
                    .offset((params.page - 1) * params.size)
                    .limit(params.size)
            )
        )
        seen_map = _view_states(db, user.id, [i.id for i in rows])
        items = []
        for inst in rows:
            pending = pending_names(db, inst.id) if inst.status == "running" else ""
            items.append(_initiated_item(inst, pending, unread_count(db, inst, user, seen_map.get(inst.id))))
        return page_result(items, total, params.page, params.size)

    raise BizException(R.GENERIC_PARAM, f"未知页签：{tab}")


def _view_states(db: Session, user_id: int, instance_ids: list[int]) -> dict[int, ApprovalViewState]:
    if not instance_ids:
        return {}
    rows = db.scalars(
        select(ApprovalViewState).where(
            ApprovalViewState.user_id == user_id,
            ApprovalViewState.instance_id.in_(instance_ids),
            ApprovalViewState.deleted == 0,
        )
    ).all()
    return {r.instance_id: r for r in rows}


def unread_count(
    db: Session, inst: ApprovalInstance, user: User, seen: ApprovalViewState | None
) -> int:
    """未读进度条数：未看过=全部非本人操作条目；看过=水位之后的非本人条目。"""
    stmt = select(func.count()).select_from(ApprovalRecord).where(
        ApprovalRecord.instance_id == inst.id,
        ApprovalRecord.deleted == 0,
        ApprovalRecord.operator_id != user.id,
    )
    if seen:  # DateTime 秒级精度，从未查看时不取 create_time 作水位，避免同秒漏计
        stmt = stmt.where(ApprovalRecord.at > seen.last_seen_at)
    return db.scalar(stmt) or 0


def mark_instance_seen(db: Session, instance_id: int, user: User) -> None:
    """发起人查看实例详情时推进未读水位（upsert）。"""
    inst = db.get(ApprovalInstance, instance_id)
    if not inst or inst.deleted or inst.initiator_id != user.id:
        return
    seen = db.scalar(
        select(ApprovalViewState).where(
            ApprovalViewState.user_id == user.id,
            ApprovalViewState.instance_id == instance_id,
            ApprovalViewState.deleted == 0,
        )
    )
    now = datetime.now()
    if seen:
        seen.last_seen_at = now
    else:
        db.add(ApprovalViewState(user_id=user.id, instance_id=instance_id, last_seen_at=now))
    db.flush()


def pending_names(db: Session, instance_id: int) -> str:
    rows = db.scalars(
        select(ApprovalTask.assignee_name).where(
            ApprovalTask.instance_id == instance_id,
            ApprovalTask.status == "pending",
            ApprovalTask.deleted == 0,
        )
    )
    return "/".join(dict.fromkeys(rows))


def _initiated_item(inst: ApprovalInstance, pending: str, unread: int = 0) -> dict:
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
        "unreadCount": unread,
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
    return instance_timeline(db, inst.id)


def instance_timeline(db: Session, instance_id: int) -> dict:
    """实例时间线（approval_record 只追加流水，含 payload）。"""
    inst = db.get(ApprovalInstance, instance_id)
    if not inst or inst.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
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
            "seq": r.seq,
            "comment": r.comment,
            "payload": parse_json(r.payload, None),
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


# --- 抄送我的 ---


def list_cc(
    db: Session, user: User, params: PageParams, unread_only: bool = False, biz_type: str | None = None
) -> dict:
    stmt = select(ApprovalCc).where(ApprovalCc.user_id == user.id, ApprovalCc.deleted == 0)
    if unread_only:
        stmt = stmt.where(ApprovalCc.read_at.is_(None))
    if biz_type:
        stmt = stmt.join(ApprovalInstance, ApprovalInstance.id == ApprovalCc.instance_id).where(
            ApprovalInstance.biz_type == biz_type
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.scalars(
            stmt.order_by(ApprovalCc.create_time.desc())
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
                "instanceStatus": inst.status if inst else "",
                "nodeName": r.node_name,
                "initiatorName": inst.initiator_name if inst else "",
                "readAt": r.read_at.strftime("%Y-%m-%d %H:%M:%S") if r.read_at else "",
                "createTime": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
            }
        )
    return page_result(items, total, params.page, params.size)


def mark_cc_read(db: Session, cc_id: int, user: User) -> None:
    cc = db.get(ApprovalCc, cc_id)
    if not cc or cc.deleted or cc.user_id != user.id:
        raise BizException(R.GENERIC_NOT_FOUND)
    if not cc.read_at:
        cc.read_at = datetime.now()
        db.flush()


# --- 流程定义管理 ---


def _nodes_payload(definition: ApprovalDefinition) -> list[dict]:
    return [
        {
            "id": n.id,
            "seq": n.seq,
            "nodeName": n.node_name,
            "nodeType": n.node_type,
            "signMode": n.sign_mode,
            "approverType": n.approver_type,
            "approverValue": n.approver_value,
            "approverName": n.approver_name,
            "branches": parse_json(n.branches, None),
            "defaultSeq": n.default_seq,
        }
        for n in definition.nodes
        if n.deleted == 0
    ]


def _definition_payload(d: ApprovalDefinition) -> dict:
    return {
        "id": d.id,
        "code": d.code,
        "name": d.name,
        "bizType": d.biz_type,
        "enabled": d.enabled,
        "remark": d.remark,
        "variablesSchema": parse_json(d.variables_schema, None),
        "processGraph": parse_json(d.process_graph, None),
        "nodes": _nodes_payload(d),
    }


def list_definitions(db: Session) -> list[dict]:
    rows = db.scalars(
        select(ApprovalDefinition).where(ApprovalDefinition.deleted == 0).order_by(ApprovalDefinition.id)
    ).all()
    return [_definition_payload(d) for d in rows]


def resolve_definition(db: Session, biz_type: str) -> ApprovalDefinition | None:
    """按业务类型解析启用的流程定义（多个取最近更新）；无绑定返回 None（调用方直通）。"""
    return db.scalar(
        select(ApprovalDefinition)
        .where(
            ApprovalDefinition.biz_type == biz_type,
            ApprovalDefinition.enabled == 1,
            ApprovalDefinition.deleted == 0,
        )
        .order_by(ApprovalDefinition.update_time.desc(), ApprovalDefinition.id.desc())
        .limit(1)
    )


def _validate_nodes(body: DefinitionIn) -> None:
    if not body.nodes:
        raise BizException(R.GENERIC_PARAM, "至少配置一个节点")
    seqs = [n.seq for n in body.nodes]
    if len(seqs) != len(set(seqs)):
        raise BizException(R.GENERIC_PARAM, "节点序号不能重复")
    if not any(n.node_type == "approval" for n in body.nodes):
        raise BizException(R.GENERIC_PARAM, "至少配置一个审批节点")
    seq_set = set(seqs)
    for n in body.nodes:
        label = n.node_name or n.seq
        if n.node_type in ("approval", "cc") and not n.approver_value.strip():
            raise BizException(R.GENERIC_PARAM, f"节点「{label}」未选择审批人/抄送人")
        if n.node_type == "condition":
            if not n.branches:
                raise BizException(R.GENERIC_PARAM, f"条件节点「{label}」至少配置一条分支")
            for b in n.branches:
                if b.target_seq not in seq_set:
                    raise BizException(R.GENERIC_PARAM, f"条件节点「{label}」分支目标序号不存在：{b.target_seq}")
            if n.default_seq is not None and n.default_seq not in seq_set:
                raise BizException(R.GENERIC_PARAM, f"条件节点「{label}」默认跳转序号不存在：{n.default_seq}")


def _persist_nodes(db: Session, definition: ApprovalDefinition, body: DefinitionIn) -> None:
    for n in sorted(body.nodes, key=lambda x: x.seq):
        db.add(
            ApprovalNode(
                definition_id=definition.id,
                seq=n.seq,
                node_name=n.node_name,
                node_type=n.node_type,
                sign_mode=n.sign_mode,
                approver_type=n.approver_type,
                approver_value=n.approver_value,
                approver_name=n.approver_name,
                branches=(
                    json.dumps(
                        [{"expr": b.expr, "targetSeq": b.target_seq} for b in n.branches], ensure_ascii=False
                    )
                    if n.branches
                    else None
                ),
                default_seq=n.default_seq,
            )
        )
    db.flush()
    # 设计器提交的图原样存储（保留布局）；未提交则由节点行自动生成等价 LogicFlow 图
    if body.process_graph and isinstance(body.process_graph.get("nodes"), list):
        definition.process_graph = json.dumps(body.process_graph, ensure_ascii=False)
    else:
        definition.process_graph = dumps_graph(build_process_graph([n for n in definition.nodes if n.deleted == 0]))


def create_definition(db: Session, body: DefinitionIn) -> dict:
    _validate_nodes(body)
    if db.scalar(
        select(ApprovalDefinition).where(ApprovalDefinition.code == body.code, ApprovalDefinition.deleted == 0)
    ):
        raise BizException(R.GENERIC_PARAM, f"流程编码已存在：{body.code}")
    d = ApprovalDefinition(
        code=body.code,
        name=body.name,
        biz_type=body.biz_type,
        enabled=body.enabled,
        remark=body.remark,
        variables_schema=(
            json.dumps(body.variables_schema, ensure_ascii=False) if body.variables_schema else None
        ),
    )
    db.add(d)
    db.flush()
    _persist_nodes(db, d, body)
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
    d.variables_schema = json.dumps(body.variables_schema, ensure_ascii=False) if body.variables_schema else None
    # 整组替换节点
    for n in list(d.nodes):
        db.delete(n)
    db.flush()
    _persist_nodes(db, d, body)
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


def preview(db: Session, definition_code: str, variables: dict, draft_nodes: list[NodeIn] | None = None) -> dict:
    """按 variables 预演分支走向（不建实例）；draft_nodes 传入时预览画布草稿节点。"""
    if draft_nodes is not None:
        nodes = [
            ApprovalNode(
                seq=n.seq,
                node_name=n.node_name,
                node_type=n.node_type,
                sign_mode=n.sign_mode,
                approver_type=n.approver_type,
                approver_value=n.approver_value,
                approver_name=n.approver_name,
                branches=(
                    json.dumps(
                        [{"expr": b.expr, "targetSeq": b.target_seq} for b in n.branches], ensure_ascii=False
                    )
                    if n.branches
                    else None
                ),
                default_seq=n.default_seq,
            )
            for n in draft_nodes
        ]
        return {
            "definitionCode": definition_code or "(draft)",
            "variables": variables,
            "route": preview_route(nodes, variables or {}),
        }
    d = db.scalar(
        select(ApprovalDefinition).where(
            ApprovalDefinition.code == definition_code,
            ApprovalDefinition.deleted == 0,
        )
    )
    if not d:
        raise BizException(R.GENERIC_NOT_FOUND, f"流程定义不存在：{definition_code}")
    nodes = [n for n in d.nodes if n.deleted == 0]
    return {
        "definitionCode": d.code,
        "variables": variables,
        "route": preview_route(nodes, variables or {}),
    }


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
    definition = db.get(ApprovalDefinition, inst.definition_id) if inst.definition_id else None
    return {
        "instanceId": inst.id,
        "bizType": inst.biz_type,
        "bizId": inst.biz_id,
        "title": inst.title,
        "status": inst.status,
        "initiatorName": inst.initiator_name,
        "currentNode": f"第{inst.current_seq}节点" if inst.status == "running" else "",
        "currentNodeIds": parse_json(inst.current_node_ids, []),
        "variables": parse_json(inst.variables, None),
        "definitionCode": inst.definition_code,
        "processGraph": parse_json(definition.process_graph, None) if definition else None,
        "snapshot": snap,
    }


# engine 入口再导出，供业务模块 from app.modules.approval.service import start ...
start = engine.start
approve = engine.approve
reject = engine.reject
withdraw = engine.withdraw
add_sign = engine.add_sign
transfer = engine.transfer

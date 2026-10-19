"""流程图构建：由 approval_node 行生成 LogicFlow 兼容的 process_graph JSON。

F1 不做图形化编辑；线性定义自动生成等价图，供 F2 设计器直接打开。
图结构遵循 LogicFlow getGraphData：
{nodes:[{id,type,x,y,text,properties}], edges:[{sourceNodeId,targetNodeId,properties}]}。
节点 id 规则：start / end / n{seq}（n{seq} 与 approval_node.seq 一一对应）。
"""

from __future__ import annotations

import json

from app.modules.approval.condition import eval_condition
from app.modules.approval.models import ApprovalNode

_NODE_TYPE_LABELS = {"approval": "审批", "condition": "条件分支", "cc": "抄送"}


def parse_json(raw: str | None, default):
    if not raw:
        return default
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
    return data


def parse_branches(node: ApprovalNode) -> list[dict]:
    data = parse_json(node.branches, [])
    return [b for b in data if isinstance(b, dict)] if isinstance(data, list) else []


def build_process_graph(nodes: list[ApprovalNode]) -> dict:
    """由顺序节点行生成 LogicFlow 图（condition 的分支/默认边展开为带 expr 的边）。"""
    graph_nodes: list[dict] = [
        {"id": "start", "type": "start", "x": 120, "y": 200, "text": "开始", "properties": {}}
    ]
    edges: list[dict] = []
    ordered = sorted(nodes, key=lambda n: n.seq)
    for i, n in enumerate(ordered):
        nid = f"n{n.seq}"
        graph_nodes.append(
            {
                "id": nid,
                "type": n.node_type,
                "x": 320 + i * 200,
                "y": 200,
                "text": n.node_name or _NODE_TYPE_LABELS.get(n.node_type, f"第{n.seq}节点"),
                "properties": {
                    "seq": n.seq,
                    "signMode": n.sign_mode,
                    "approverType": n.approver_type,
                    "approverValue": n.approver_value,
                    "approverName": n.approver_name,
                },
            }
        )
    end_x = 320 + len(ordered) * 200
    graph_nodes.append({"id": "end", "type": "end", "x": end_x, "y": 200, "text": "结束", "properties": {}})

    # 线性主链：start → n1 → n2 → … → end；条件节点额外展开分支/默认边
    chain = ["start"] + [f"n{n.seq}" for n in ordered] + ["end"]
    for i in range(len(chain) - 1):
        edges.append({"sourceNodeId": chain[i], "targetNodeId": chain[i + 1], "properties": {}})
    for n in ordered:
        if n.node_type != "condition":
            continue
        nid = f"n{n.seq}"
        edges[:] = [e for e in edges if not (e["sourceNodeId"] == nid and not e["properties"].get("expr"))]
        for b in parse_branches(n):
            target = b.get("targetSeq") or b.get("target_seq")
            if target:
                edges.append(
                    {"sourceNodeId": nid, "targetNodeId": f"n{target}", "properties": {"expr": b.get("expr")}}
                )
        if n.default_seq:
            edges.append(
                {"sourceNodeId": nid, "targetNodeId": f"n{n.default_seq}", "properties": {"default": True}}
            )
    return {"nodes": graph_nodes, "edges": edges}


def dumps_graph(graph: dict) -> str:
    return json.dumps(graph, ensure_ascii=False)


def route_from(nodes: list[ApprovalNode], seq: int, variables: dict) -> int | None:
    """求 seq 节点的后继：condition 按 variables 路由，其余顺序取下一节点。返回 None 表示流程末端。"""
    ordered = sorted(nodes, key=lambda n: n.seq)
    by_seq = {n.seq: n for n in ordered}
    node = by_seq.get(seq)
    if node is None:
        return None
    if node.node_type == "condition":
        for b in parse_branches(node):
            target = b.get("targetSeq") or b.get("target_seq")
            if target and eval_condition(b.get("expr"), variables):
                return int(target)
        if node.default_seq:
            return node.default_seq
    following = [n.seq for n in ordered if n.seq > seq]
    return min(following) if following else None


def first_seq(nodes: list[ApprovalNode]) -> int | None:
    seqs = [n.seq for n in nodes]
    return min(seqs) if seqs else None


def preview_route(nodes: list[ApprovalNode], variables: dict) -> list[dict]:
    """按 variables 预演线性走向：返回将经过的节点（审批/抄送）序号与名称。"""
    ordered = {n.seq: n for n in sorted(nodes, key=lambda n: n.seq)}
    path: list[dict] = []
    seq = first_seq(list(ordered.values()))
    guard = 0
    while seq is not None and guard < 100:
        guard += 1
        node = ordered.get(seq)
        if node is None:
            break
        path.append(
            {"seq": node.seq, "nodeName": node.node_name, "nodeType": node.node_type, "signMode": node.sign_mode}
        )
        seq = route_from(list(ordered.values()), seq, variables)
    return path

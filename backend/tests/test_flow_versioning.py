"""流程定义版本化：有进行中实例编辑→自动新版本；老实例按旧版本流转；新发起用最新版；删除→停用。"""

import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.approval import engine
from app.modules.approval import service as approval
from app.modules.approval.models import ApprovalDefinition, ApprovalInstance, ApprovalTask
from app.modules.auth.models import User

UUID = uuid.uuid4().hex[:8]
CODE = f"pwv_{UUID}"


def _admin() -> User:
    db = SessionLocal()
    try:
        return db.scalar(select(User).where(User.username == "admin"))
    finally:
        db.close()


def _node(approver_id: int, seq: int, name: str) -> dict:
    return {
        "seq": seq,
        "nodeName": name,
        "nodeType": "approval",
        "signMode": "or",
        "approverType": "USER",
        "approverValue": str(approver_id),
    }


def _create(client, headers, nodes) -> dict:
    r = client.post(
        "/api/v1/approval/definitions",
        headers=headers,
        json={"code": CODE, "name": CODE, "bizType": "contract", "enabled": 1, "nodes": nodes},
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _update(client, headers, def_id, nodes) -> dict:
    r = client.put(
        f"/api/v1/approval/definitions/{def_id}",
        headers=headers,
        json={"code": CODE, "name": CODE, "bizType": "contract", "enabled": 1, "nodes": nodes},
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _start_instance(biz_id: int) -> ApprovalInstance:
    db = SessionLocal()
    try:
        inst = engine.start(
            db, biz_type="pwv_test", biz_id=biz_id, definition_code=CODE,
            title=f"t{biz_id}", initiator=_admin(),
        )
        db.commit()
        db.refresh(inst)
        return inst
    finally:
        db.close()


def _finish_instance(instance_id: int) -> None:
    """依次同意该实例所有 pending 待办直到完成。"""
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.username == "admin"))
        while True:
            t = db.scalar(
                select(ApprovalTask).where(
                    ApprovalTask.instance_id == instance_id,
                    ApprovalTask.status == "pending",
                    ApprovalTask.deleted == 0,
                )
            )
            if not t:
                break
            approval.approve(db, t.id, admin, "ok")
            db.commit()
    finally:
        db.close()


def _get_def(def_id: int) -> ApprovalDefinition:
    db = SessionLocal()
    try:
        d = db.get(ApprovalDefinition, def_id)
        db.expunge(d)
        return d
    finally:
        db.close()


def test_definition_versioning_flow(client, admin_headers):
    admin = _admin()
    one_node = [_node(admin.id, 1, "一级审批")]
    two_nodes = [_node(admin.id, 1, "一级审批"), _node(admin.id, 2, "二级审批")]

    # 1) 新建 v1
    data = _create(client, admin_headers, one_node)
    v1_id = data["id"]
    assert data["version"] == 1 and data["newVersion"] is False

    # 2) 无进行中实例 → 原地编辑（版本不变，节点整组替换）
    data = _update(client, admin_headers, v1_id, two_nodes)
    assert data["newVersion"] is False and data["version"] == 1
    assert len(data["nodes"]) == 2

    # 3) 发起实例（走当前 v1：2 节点）
    inst1 = _start_instance(900001)
    assert inst1.definition_id == v1_id

    # 4) 有进行中实例 → 编辑自动另存 v2（3 节点），v1 原行不动
    three_nodes = two_nodes + [_node(admin.id, 3, "三级审批")]
    data = _update(client, admin_headers, v1_id, three_nodes)
    assert data["newVersion"] is True and data["version"] == 2 and data["runningCount"] == 1
    v2_id = data["id"]
    assert v2_id != v1_id
    v1 = _get_def(v1_id)
    assert v1.enabled == 1 and len([n for n in v1.nodes if n.deleted == 0]) == 2

    # 5) 新发起解析最新启用版 v2
    inst2 = _start_instance(900002)
    assert inst2.definition_id == v2_id

    # 6) 老实例按 v1（2 节点）流转完成；新实例 v2 需 3 次审批
    _finish_instance(inst1.id)
    _finish_instance(inst2.id)
    db = SessionLocal()
    try:
        i1 = db.get(ApprovalInstance, inst1.id)
        i2 = db.get(ApprovalInstance, inst2.id)
        assert i1.status == "approved" and i2.status == "approved"
        n1 = len([r for r in i1.records if r.action == "agree"])
        n2 = len([r for r in i2.records if r.action == "agree"])
        assert n1 == 2 and n2 == 3
    finally:
        db.close()

    # 7) 删除有进行中实例的定义 → 停用而非报错
    inst3 = _start_instance(900003)
    assert inst3.definition_id == v2_id
    r = client.delete(f"/api/v1/approval/definitions/{v2_id}", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["disabled"] is True
    v2 = _get_def(v2_id)
    assert v2.enabled == 0 and v2.deleted == 0
    # 停用后老实例仍可流转完成
    _finish_instance(inst3.id)
    db = SessionLocal()
    try:
        assert db.get(ApprovalInstance, inst3.id).status == "approved"
    finally:
        db.close()
    # 实例流转完后再删 → 真删（逻辑删）
    r = client.delete(f"/api/v1/approval/definitions/{v2_id}", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["disabled"] is False
    assert _get_def(v2_id).deleted == 1

    # 8) 全部版本删除后同 code 新建 → 重新从 v1 起
    r = client.delete(f"/api/v1/approval/definitions/{v1_id}", headers=admin_headers).json()
    assert r["code"] == 0
    data = _create(client, admin_headers, one_node)
    assert data["version"] == 1
    client.delete(f"/api/v1/approval/definitions/{data['id']}", headers=admin_headers)

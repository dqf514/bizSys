"""F3 流程驱动改造：任务立项流程（绑定/直通）、结算审批（绑定/直通/重提）、待办通知钩子。"""

import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.admin.models import Notify
from app.modules.approval import service as approval
from app.modules.approval.models import ApprovalInstance, ApprovalTask
from app.modules.auth.models import User
from app.modules.task.models import Task

UUID = uuid.uuid4().hex[:8]


def _user_id(username: str) -> int:
    db = SessionLocal()
    try:
        return db.scalar(select(User.id).where(User.username == username))
    finally:
        db.close()


def _create_definition(client, headers, code: str, biz_type: str, approver_id: int) -> int:
    r = client.post(
        "/api/v1/approval/definitions",
        headers=headers,
        json={
            "code": code,
            "name": code,
            "bizType": biz_type,
            "enabled": 1,
            "nodes": [
                {
                    "seq": 1,
                    "nodeName": "审批",
                    "nodeType": "approval",
                    "signMode": "or",
                    "approverType": "USER",
                    "approverValue": str(approver_id),
                }
            ],
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _delete_definition(client, headers, def_id: int) -> None:
    client.delete(f"/api/v1/approval/definitions/{def_id}", headers=headers)


def _act_on_instance(biz_type: str, biz_id: int, action: str, comment: str = "ok") -> None:
    db = SessionLocal()
    try:
        target = None
        for t in db.scalars(select(ApprovalTask).where(ApprovalTask.status == "pending", ApprovalTask.deleted == 0)):
            inst = db.get(ApprovalInstance, t.instance_id)
            if inst and inst.biz_type == biz_type and inst.biz_id == biz_id:
                target = t
                break
        assert target, f"{biz_type}#{biz_id} pending task not found"
        user = db.get(User, target.assignee_id)
        if action == "approve":
            approval.approve(db, target.id, user, comment)
        else:
            approval.reject(db, target.id, user, comment)
        db.commit()
    finally:
        db.close()


def _make_finished_task(admin_id: int) -> int:
    db = SessionLocal()
    try:
        t = Task(task_no=f"RW-F3-{uuid.uuid4().hex[:8]}", task_name="F3结算任务", status="finished", create_by=admin_id)
        db.add(t)
        db.commit()
        return t.id
    finally:
        db.close()


def test_task_initiation_flow(client, admin_headers):
    """绑定 task 定义：提交→approving→通过→in_progress；驳回→rejected→可编辑重提；通知已写。"""
    manager_id = _user_id("manager1")
    def_id = _create_definition(client, admin_headers, f"task_f3_{UUID}", "task", manager_id)
    try:
        r = client.post(
            "/api/v1/task/tasks", headers=admin_headers, json={"task_name": f"立项_{UUID}", "items": [], "samples": []}
        ).json()
        assert r["code"] == 0, r
        tid = r["data"]["id"]

        r = client.post(f"/api/v1/task/tasks/{tid}/submit", headers=admin_headers).json()
        assert r["code"] == 0 and r["data"]["status"] == "approving"

        # 待办通知钩子：manager1 收到站内通知
        db = SessionLocal()
        try:
            notify = db.scalar(
                select(Notify).where(
                    Notify.user_id == manager_id, Notify.biz_type == "task", Notify.biz_id == tid
                )
            )
            assert notify and "待办" in notify.title
        finally:
            db.close()

        # 审批通过 → in_progress（生效可执行）
        _act_on_instance("task", tid, "approve")
        r = client.get(f"/api/v1/task/tasks/{tid}", headers=admin_headers).json()
        assert r["data"]["status"] == "in_progress"
        assert r["data"]["flow"]["instanceId"]
        assert [x["action"] for x in r["data"]["flow"]["timeline"]] == ["start", "agree"]

        # 驳回路径：重提开新实例
        r = client.post(
            "/api/v1/task/tasks", headers=admin_headers, json={"task_name": f"驳回_{UUID}", "items": [], "samples": []}
        ).json()
        tid2 = r["data"]["id"]
        client.post(f"/api/v1/task/tasks/{tid2}/submit", headers=admin_headers)
        _act_on_instance("task", tid2, "reject", "退回修改")
        r = client.get(f"/api/v1/task/tasks/{tid2}", headers=admin_headers).json()
        assert r["data"]["status"] == "rejected"
        # rejected 可编辑
        r = client.put(
            f"/api/v1/task/tasks/{tid2}", headers=admin_headers,
            json={"task_name": f"驳回改_{UUID}", "items": [], "samples": []},
        ).json()
        assert r["code"] == 0, r
        # 重新提交 → approving
        r = client.post(f"/api/v1/task/tasks/{tid2}/submit", headers=admin_headers).json()
        assert r["code"] == 0 and r["data"]["status"] == "approving"
        _act_on_instance("task", tid2, "approve")
        r = client.get(f"/api/v1/task/tasks/{tid2}", headers=admin_headers).json()
        assert r["data"]["status"] == "in_progress"
    finally:
        _delete_definition(client, admin_headers, def_id)


def test_task_submit_direct_without_definition(client, admin_headers):
    """未绑定 task 定义：直通 in_progress（演示环境开箱即用）。"""
    r = client.post(
        "/api/v1/task/tasks", headers=admin_headers, json={"task_name": f"直通_{UUID}", "items": [], "samples": []}
    ).json()
    tid = r["data"]["id"]
    r = client.post(f"/api/v1/task/tasks/{tid}/submit", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "in_progress"
    r = client.get(f"/api/v1/task/tasks/{tid}", headers=admin_headers).json()
    assert r["data"]["flow"] is None


def test_settlement_flow(client, admin_headers):
    """结算单：未绑定义直通；绑定后 创建→approving→通过→pending+任务settled；驳回→rejected→重提。"""
    admin_id = _user_id("admin")
    manager_id = _user_id("manager1")

    # 直通（无 settlement 定义）
    t1 = _make_finished_task(admin_id)
    r = client.post(
        "/api/v1/finance/settlements", headers=admin_headers, json={"taskId": t1, "amount": 8000}
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "pending"
    db = SessionLocal()
    try:
        assert db.get(Task, t1).status == "settled"
    finally:
        db.close()

    def_id = _create_definition(client, admin_headers, f"settle_f3_{UUID}", "settlement", manager_id)
    try:
        # 绑定后：创建即发起审批
        t2 = _make_finished_task(admin_id)
        r = client.post(
            "/api/v1/finance/settlements", headers=admin_headers, json={"taskId": t2, "amount": 9000}
        ).json()
        assert r["code"] == 0, r
        sid = r["data"]["id"]
        assert r["data"]["status"] == "approving"
        _act_on_instance("settlement", sid, "approve")
        r = client.get(f"/api/v1/finance/settlements/{sid}", headers=admin_headers).json()
        assert r["data"]["status"] == "pending"
        db = SessionLocal()
        try:
            assert db.get(Task, t2).status == "settled"
        finally:
            db.close()

        # 驳回 → rejected → 重新提交 → 通过
        t3 = _make_finished_task(admin_id)
        r = client.post(
            "/api/v1/finance/settlements", headers=admin_headers, json={"taskId": t3, "amount": 6000}
        ).json()
        sid2 = r["data"]["id"]
        _act_on_instance("settlement", sid2, "reject", "金额有误")
        r = client.get(f"/api/v1/finance/settlements/{sid2}", headers=admin_headers).json()
        assert r["data"]["status"] == "rejected"
        r = client.post(f"/api/v1/finance/settlements/{sid2}/submit", headers=admin_headers).json()
        assert r["code"] == 0 and r["data"]["status"] == "approving"
        _act_on_instance("settlement", sid2, "approve")
        r = client.get(f"/api/v1/finance/settlements/{sid2}", headers=admin_headers).json()
        assert r["data"]["status"] == "pending"
    finally:
        _delete_definition(client, admin_headers, def_id)

"""工作流引擎合并：会签 / 依次 / 条件分支 / 抄送 / 加签与或签交互 / 未读角标（service 级，事务回滚）。"""

import uuid

from sqlalchemy import select

from app.common.events import ApprovalCompleted, subscribe
from app.common.pagination import PageParams
from app.modules.approval import service
from app.modules.approval.condition import eval_condition
from app.modules.approval.models import ApprovalCc, ApprovalTask
from app.modules.approval.schemas import BranchIn, DefinitionIn, NodeIn
from app.modules.auth.models import User

EVENTS: list = []
subscribe(ApprovalCompleted, lambda e: EVENTS.append(("done", e.biz_type, e.biz_id)))


def _users(db):
    admin = db.scalar(select(User).where(User.username == "admin"))
    m1 = db.scalar(select(User).where(User.username == "manager1"))
    l1 = db.scalar(select(User).where(User.username == "leader1"))
    return admin, m1, l1


def _biz_id() -> int:
    return uuid.uuid4().int % 10**9 + 10**9


def _code() -> str:
    return "t_" + uuid.uuid4().hex[:10]


def _define(db, nodes: list[NodeIn]) -> str:
    code = _code()
    service.create_definition(db, DefinitionIn(code=code, name=code, biz_type="test", nodes=nodes))
    db.flush()
    return code


def _start(db, admin, biz, code, variables=None):
    return service.start(
        db, biz_type="test", biz_id=biz, definition_code=code,
        title="t", initiator=admin, variables=variables,
    )


def _todo(db, user, biz_id):
    page = service.list_tasks(db, user, PageParams(), "todo")
    return [i for i in page["items"] if i["bizId"] == biz_id]


def test_and_sign_requires_all(db):
    """会签：全员通过才推进，第一人同意后实例仍 running。"""
    admin, m1, l1 = _users(db)
    code = _define(db, [
        NodeIn(seq=1, node_name="会签", sign_mode="and", approver_value=f"{m1.id},{l1.id}"),
    ])
    biz = _biz_id()
    inst = _start(db, admin, biz, code)
    db.flush()
    assert len(_todo(db, m1, biz)) == 1 and len(_todo(db, l1, biz)) == 1

    inst = service.approve(db, _todo(db, m1, biz)[0]["id"], m1, "ok")
    assert inst.status == "running"
    assert len(_todo(db, l1, biz)) == 1  # 另一人待办不受影响

    inst = service.approve(db, _todo(db, l1, biz)[0]["id"], l1, "ok")
    assert inst.status == "approved"
    assert ("done", "test", biz) in EVENTS
    db.rollback()


def test_sequential_sign(db):
    """依次签：同一时刻只有队列首人持有待办，同意后逐个流转。"""
    admin, m1, l1 = _users(db)
    code = _define(db, [
        NodeIn(seq=1, node_name="依次", sign_mode="sequential", approver_value=f"{m1.id},{l1.id}"),
    ])
    biz = _biz_id()
    inst = _start(db, admin, biz, code)
    db.flush()
    assert len(_todo(db, m1, biz)) == 1
    assert len(_todo(db, l1, biz)) == 0

    inst = service.approve(db, _todo(db, m1, biz)[0]["id"], m1, "ok")
    assert inst.status == "running"
    assert len(_todo(db, m1, biz)) == 0
    assert len(_todo(db, l1, biz)) == 1

    inst = service.approve(db, _todo(db, l1, biz)[0]["id"], l1, "ok")
    assert inst.status == "approved"
    db.rollback()


def _branch_definition(db, admin, m1, l1) -> str:
    return _define(db, [
        NodeIn(seq=1, node_name="部门审批", approver_value=str(m1.id)),
        NodeIn(
            seq=2, node_name="金额判断", node_type="condition",
            branches=[BranchIn(expr={"field": "amount", "op": "gte", "value": 100000}, target_seq=3)],
            default_seq=4,
        ),
        NodeIn(seq=3, node_name="大额审批", approver_value=str(l1.id)),
        NodeIn(seq=4, node_name="抄送管理员", node_type="cc", approver_value=str(admin.id)),
    ])


def test_condition_branch_routes_by_variables(db):
    """条件分支：amount>=10w 走大额审批，否则默认跳到抄送后直接完成。"""
    admin, m1, l1 = _users(db)
    code = _branch_definition(db, admin, m1, l1)

    # 大额：1 → 条件 → 3 → cc → end
    biz = _biz_id()
    inst = _start(db, admin, biz, code, variables={"amount": 200000})
    db.flush()
    assert inst.status == "running"
    service.approve(db, _todo(db, m1, biz)[0]["id"], m1, "ok")
    assert len(_todo(db, l1, biz)) == 1
    inst = service.approve(db, _todo(db, l1, biz)[0]["id"], l1, "ok")
    assert inst.status == "approved"

    # 小额：1 → 条件（未命中走默认） → cc → end，无需大额审批
    biz2 = _biz_id()
    inst2 = _start(db, admin, biz2, code, variables={"amount": 50000})
    db.flush()
    inst2 = service.approve(db, _todo(db, m1, biz2)[0]["id"], m1, "ok")
    assert inst2.status == "approved"
    assert len(_todo(db, l1, biz2)) == 0
    db.rollback()


def test_condition_preview(db):
    """分支预览：按 variables 返回将经过的节点序列。"""
    admin, m1, l1 = _users(db)
    code = _branch_definition(db, admin, m1, l1)
    big = service.preview(db, code, {"amount": 200000})
    assert [n["seq"] for n in big["route"]] == [1, 2, 3, 4]
    small = service.preview(db, code, {"amount": 50000})
    assert [n["seq"] for n in small["route"]] == [1, 2, 4]
    db.rollback()


def test_cc_node_and_read(db):
    """抄送节点：产生 approval_cc 与 cc 时间线，不阻塞流转；支持已读标记。"""
    admin, m1, l1 = _users(db)
    code = _branch_definition(db, admin, m1, l1)
    biz = _biz_id()
    inst = _start(db, admin, biz, code, variables={"amount": 50000})
    db.flush()
    inst = service.approve(db, _todo(db, m1, biz)[0]["id"], m1, "ok")
    assert inst.status == "approved"  # cc 不阻塞

    cc = db.scalar(select(ApprovalCc).where(ApprovalCc.instance_id == inst.id, ApprovalCc.user_id == admin.id))
    assert cc and cc.read_at is None
    page = service.list_cc(db, admin, PageParams(), unread_only=True)
    assert any(i["instanceId"] == inst.id for i in page["items"])
    service.mark_cc_read(db, cc.id, admin)
    db.flush()
    page = service.list_cc(db, admin, PageParams(), unread_only=True)
    assert all(i["instanceId"] != inst.id for i in page["items"])

    tl = service.timeline(db, "test", biz)
    assert "cc" in [r["action"] for r in tl["records"]]
    db.rollback()


def test_add_sign_or_sign_interaction(db):
    """加签与或签交互：一人通过后同节点其他或签待办作废，加签待办保留且须完成后节点才推进。"""
    admin, m1, l1 = _users(db)
    code = _define(db, [
        NodeIn(seq=1, node_name="或签", sign_mode="or", approver_value=f"{m1.id},{l1.id}"),
        NodeIn(seq=2, node_name="终审", approver_value=str(admin.id)),
    ])
    biz = _biz_id()
    _start(db, admin, biz, code)
    db.flush()

    t_m1 = _todo(db, m1, biz)[0]
    service.add_sign(db, t_m1["id"], m1, admin, "帮忙把关")
    assert len(_todo(db, admin, biz)) == 1

    inst = service.approve(db, t_m1["id"], m1, "ok")
    assert inst.status == "running"  # 加签待办未清，节点不推进
    assert len(_todo(db, l1, biz)) == 0  # 其他或签待办已作废
    l1_task = db.scalar(
        select(ApprovalTask).where(
            ApprovalTask.instance_id == inst.id, ApprovalTask.assignee_id == l1.id, ApprovalTask.seq == 1
        )
    )
    assert l1_task.status == "cancelled"
    assert len(_todo(db, admin, biz)) == 1  # 加签待办保留

    inst = service.approve(db, _todo(db, admin, biz)[0]["id"], admin, "加签同意")
    assert inst.status == "running" and inst.current_seq == 2  # 节点推进到终审
    inst = service.approve(db, _todo(db, admin, biz)[0]["id"], admin, "ok")
    assert inst.status == "approved"
    db.rollback()


def test_initiated_unread_badge(db):
    """我发起的：他人处理后未读角标 +1，查看详情后清零。"""
    admin, m1, l1 = _users(db)
    biz = _biz_id()
    _start(db, admin, biz, "contract_approve")
    db.flush()
    service.approve(db, _todo(db, m1, biz)[0]["id"], m1, "ok")

    page = service.list_tasks(db, admin, PageParams(), "initiated")
    item = next(i for i in page["items"] if i["bizId"] == biz)
    assert item["unreadCount"] >= 1

    service.mark_instance_seen(db, item["instanceId"], admin)
    db.flush()
    page = service.list_tasks(db, admin, PageParams(), "initiated")
    item = next(i for i in page["items"] if i["bizId"] == biz)
    assert item["unreadCount"] == 0
    db.rollback()


def test_eval_condition_ops():
    """表达式求值：常用操作 + 字符串表达式不执行（防 eval 注入）。"""
    v = {"amount": 100, "tags": ["a", "b"], "name": "合同审批", "form": {"kind": "purchase"}}
    assert eval_condition({"field": "amount", "op": "eq", "value": 100}, v)
    assert eval_condition({"field": "amount", "op": "ne", "value": 200}, v)
    assert eval_condition({"field": "amount", "op": "gte", "value": 100}, v)
    assert eval_condition({"field": "amount", "op": "lt", "value": 101}, v)
    assert eval_condition({"field": "amount", "op": "in", "value": [50, 100]}, v)
    assert eval_condition({"field": "tags", "op": "contains", "value": "a"}, v)
    assert eval_condition({"field": "name", "op": "contains", "value": "合同"}, v)
    assert eval_condition({"field": "form.kind", "op": "eq", "value": "purchase"}, v)
    assert not eval_condition({"field": "amount", "op": "gt", "value": 100}, v)
    assert not eval_condition("__import__('os').system('x')", v)  # 字符串表达式不执行
    assert eval_condition("default", v)
    assert not eval_condition({"field": "missing", "op": "eq", "value": 1}, v)

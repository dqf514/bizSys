"""审批引擎：同意链 / 错误码 / 驳回 / 撤回 / 加签 / 转办（service 级，事务回滚）。"""

import uuid

from sqlalchemy import select

from app.common.events import ApprovalCompleted, ApprovalRejected, subscribe
from app.common.pagination import PageParams
from app.core.exceptions import BizException
from app.modules.approval import service
from app.modules.auth.models import User

EVENTS: list = []
subscribe(ApprovalCompleted, lambda e: EVENTS.append(("done", e.biz_type, e.biz_id)))
subscribe(ApprovalRejected, lambda e: EVENTS.append(("rej", e.biz_type, e.biz_id)))


def _users(db):
    admin = db.scalar(select(User).where(User.username == "admin"))
    m1 = db.scalar(select(User).where(User.username == "manager1"))
    l1 = db.scalar(select(User).where(User.username == "leader1"))
    return admin, m1, l1


def _biz_id() -> int:
    return uuid.uuid4().int % 10**9 + 10**9  # 不与真实业务 id 冲突


def _todo(db, user, biz_id):
    page = service.list_tasks(db, user, PageParams(), "todo")
    return [i for i in page["items"] if i["bizId"] == biz_id]


def test_full_approve_chain(db):
    admin, m1, l1 = _users(db)
    biz = _biz_id()
    inst = service.start(
        db, biz_type="contract", biz_id=biz, definition_code="contract_approve",
        title="测试", initiator=admin, form_snapshot={"k": "v"},
    )
    db.flush()
    assert inst.status == "running"

    t = _todo(db, m1, biz)
    assert len(t) == 1
    inst = service.approve(db, t[0]["id"], m1, "ok")
    assert inst.status == "running" and inst.current_seq == 2

    t2 = _todo(db, l1, biz)
    assert len(t2) == 1
    inst = service.approve(db, t2[0]["id"], l1, "pass")
    assert inst.status == "approved"
    assert ("done", "contract", biz) in EVENTS
    db.rollback()


def test_error_codes(db):
    admin, m1, l1 = _users(db)
    biz = _biz_id()
    service.start(db, biz_type="contract", biz_id=biz, definition_code="contract_approve", title="x", initiator=admin)
    db.flush()

    # 70004 重复发起
    try:
        service.start(db, biz_type="contract", biz_id=biz, definition_code="contract_approve", title="x", initiator=admin)
        raise AssertionError("expected 70004")
    except BizException as e:
        assert e.code == 70004

    t = _todo(db, m1, biz)
    # 70002 非当前审批人
    try:
        service.approve(db, t[0]["id"], l1, "")
        raise AssertionError("expected 70002")
    except BizException as e:
        assert e.code == 70002
    # 70003 驳回意见必填
    try:
        service.reject(db, t[0]["id"], m1, "   ")
        raise AssertionError("expected 70003")
    except BizException as e:
        assert e.code == 70003
    db.rollback()


def test_reject_and_timeline(db):
    admin, m1, l1 = _users(db)
    biz = _biz_id()
    service.start(db, biz_type="contract", biz_id=biz, definition_code="contract_approve", title="r", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    inst = service.reject(db, t[0]["id"], m1, "打回")
    assert inst.status == "rejected"
    assert ("rej", "contract", biz) in EVENTS
    tl = service.timeline(db, "contract", biz)
    assert [x["action"] for x in tl["records"]] == ["start", "reject"]
    db.rollback()


def test_withdraw_transfer_addsign(db):
    admin, m1, l1 = _users(db)

    # 撤回
    biz = _biz_id()
    inst = service.start(db, biz_type="contract", biz_id=biz, definition_code="contract_approve", title="w", initiator=admin)
    db.flush()
    inst = service.withdraw(db, inst.id, admin)
    assert inst.status == "withdrawn"

    # 转办后仍可撤回（转办≠已审）
    biz2 = _biz_id()
    inst2 = service.start(db, biz_type="contract", biz_id=biz2, definition_code="contract_approve", title="t", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz2)
    service.transfer(db, t[0]["id"], m1, admin, "转你")
    assert len(_todo(db, admin, biz2)) == 1
    inst2 = service.withdraw(db, inst2.id, admin)
    assert inst2.status == "withdrawn"

    # 加签
    biz3 = _biz_id()
    service.start(db, biz_type="contract", biz_id=biz3, definition_code="contract_approve", title="a", initiator=admin)
    db.flush()
    t3 = _todo(db, m1, biz3)
    service.add_sign(db, t3[0]["id"], m1, admin, "帮忙")
    assert len(_todo(db, admin, biz3)) == 1
    tl = service.timeline(db, "contract", biz3)
    assert [x["action"] for x in tl["records"]] == ["start", "add_sign"]
    db.rollback()

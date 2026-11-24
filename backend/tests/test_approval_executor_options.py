"""E1 引擎升级：办理节点（executor）+ 流程通用选项（options）+ 节点字段权限（field_permissions）。

覆盖：
- 办理节点建待办 → 办理人处理后流程继续推进；
- 通用选项：意见必填 / 办理意见必填 / 允许加签 / 通过后可撤销；
- 定义保存后 options 与 fieldPermissions 能从接口出参读回。
"""

import uuid

from sqlalchemy import select

from app.core.exceptions import BizException
from app.modules.approval import service
from app.modules.approval.schemas import DefinitionIn, NodeIn
from app.modules.auth.models import User

BIZ = "e1test"


def _users(db):
    admin = db.scalar(select(User).where(User.username == "admin"))
    m1 = db.scalar(select(User).where(User.username == "manager1"))
    l1 = db.scalar(select(User).where(User.username == "leader1"))
    return admin, m1, l1


def _biz_id() -> int:
    return uuid.uuid4().int % 10**9 + 10**9


def _code() -> str:
    return "e1_" + uuid.uuid4().hex[:8]


def _node(seq, name, node_type, user, **kw):
    return NodeIn(
        seq=seq,
        node_name=name,
        node_type=node_type,
        approver_type="USER",
        approver_value=str(user.id),
        approver_name=user.name or user.username,
        **kw,
    )


def _make_definition(db, admin, m1, l1, *, options=None, field_permissions=None):
    code = _code()
    body = DefinitionIn(
        code=code,
        name="E1 测试流程",
        biz_type=BIZ,
        options=options,
        nodes=[
            _node(1, "部门审批", "approval", m1),
            _node(2, "出纳办理", "executor", l1, field_permissions=field_permissions),
            _node(3, "总经理审批", "approval", admin),
        ],
    )
    out = service.create_definition(db, body)
    return code, out


def _todo(db, user, biz_id):
    page = service.list_tasks(db, user, service.PageParams(), "todo")
    return [i for i in page["items"] if i["bizId"] == biz_id]


def test_executor_node_flow(db):
    """办理节点：办理人待办 nodeType=executor，处理后推进到下一个审批节点。"""
    admin, m1, l1 = _users(db)
    code, out = _make_definition(db, admin, m1, l1)
    assert out["nodes"][1]["nodeType"] == "executor"
    biz = _biz_id()
    service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="办理测试", initiator=admin)
    db.flush()

    t = _todo(db, m1, biz)
    assert len(t) == 1
    inst = service.approve(db, t[0]["id"], m1, "同意")
    db.flush()
    assert inst.status == "running" and inst.current_seq == 2

    t2 = _todo(db, l1, biz)
    assert len(t2) == 1
    assert t2[0]["nodeType"] == "executor"
    inst = service.approve(db, t2[0]["id"], l1, "已办理")
    db.flush()
    assert inst.status == "running" and inst.current_seq == 3

    t3 = _todo(db, admin, biz)
    assert len(t3) == 1
    inst = service.approve(db, t3[0]["id"], admin, "通过")
    assert inst.status == "approved"
    db.rollback()


def test_options_comment_required(db):
    """通用选项 commentRequired：同意也必须填意见（默认行为不变 —— 由 options 打开）。"""
    admin, m1, l1 = _users(db)
    code, _ = _make_definition(db, admin, m1, l1, options={"commentRequired": True})
    biz = _biz_id()
    service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="意见必填", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    try:
        service.approve(db, t[0]["id"], m1, "  ")
        raise AssertionError("expected 70003")
    except BizException as e:
        assert e.code == 70003
    db.rollback()


def test_options_executor_comment_required(db):
    """通用选项 executorCommentRequired：办理节点意见必填。"""
    admin, m1, l1 = _users(db)
    code, _ = _make_definition(db, admin, m1, l1, options={"executorCommentRequired": True})
    biz = _biz_id()
    service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="办理意见必填", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    service.approve(db, t[0]["id"], m1, "同意")
    db.flush()
    t2 = _todo(db, l1, biz)
    try:
        service.approve(db, t2[0]["id"], l1, "")
        raise AssertionError("expected 70003")
    except BizException as e:
        assert e.code == 70003
    db.rollback()


def test_options_allow_add_sign(db):
    """通用选项 allowAddSign=false：禁止加签。"""
    admin, m1, l1 = _users(db)
    code, _ = _make_definition(db, admin, m1, l1, options={"allowAddSign": False})
    biz = _biz_id()
    service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="禁止加签", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    try:
        service.add_sign(db, t[0]["id"], m1, admin, "帮忙")
        raise AssertionError("expected BizException")
    except BizException as e:
        assert "加签" in str(e.message or "")
    db.rollback()


def test_options_comment_sign_required(db):
    """通用选项 commentSignRequired：审批意见必须带签名，签名随时间线留痕。"""
    admin, m1, l1 = _users(db)
    code, _ = _make_definition(db, admin, m1, l1, options={"commentSignRequired": True})
    biz = _biz_id()
    service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="意见需签名", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    # 无签名 → 拒绝
    try:
        service.approve(db, t[0]["id"], m1, "同意")
        raise AssertionError("expected 70003")
    except BizException as e:
        assert e.code == 70003
        assert "签名" in str(e.message or "")
    # 带签名 → 通过，签名写入时间线 payload
    inst = service.approve(db, t[0]["id"], m1, "同意", "data:image/png;base64,AAAA")
    db.flush()
    tl = service.instance_timeline(db, inst.id)
    agree = next(r for r in tl["records"] if r["action"] == "agree")
    assert agree["payload"]["signature"] == "data:image/png;base64,AAAA"
    db.rollback()


def test_options_reject_sign_required(db):
    """commentSignRequired：驳回同样需要签名。"""
    admin, m1, l1 = _users(db)
    code, _ = _make_definition(db, admin, m1, l1, options={"commentSignRequired": True})
    biz = _biz_id()
    service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="驳回需签名", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    try:
        service.reject(db, t[0]["id"], m1, "不同意")
        raise AssertionError("expected 70003")
    except BizException as e:
        assert e.code == 70003
    db.rollback()


def test_executor_node_signature_not_required(db):
    """办理节点不强制签名（走「办理意见必填」口径）。"""
    admin, m1, l1 = _users(db)
    code, _ = _make_definition(db, admin, m1, l1, options={"commentSignRequired": True})
    biz = _biz_id()
    service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="办理免签", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    # 审批节点需要签名
    service.approve(db, t[0]["id"], m1, "同意", "data:image/png;base64,AAAA")
    db.flush()
    t2 = _todo(db, l1, biz)
    assert t2[0]["nodeType"] == "executor"
    inst = service.approve(db, t2[0]["id"], l1, "已办理")
    db.flush()
    assert inst.status == "running" and inst.current_seq == 3
    db.rollback()


def test_task_list_exposes_option_flags(db):
    """待办出参带流程通用选项标记（前端据此决定意见必填 / 签名 / 加签）。"""
    admin, m1, l1 = _users(db)
    code, _ = _make_definition(
        db,
        admin,
        m1,
        l1,
        options={"commentRequired": True, "commentSignRequired": True, "allowAddSign": False},
    )
    biz = _biz_id()
    service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="选项标记", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    assert t[0]["commentRequired"] is True
    assert t[0]["commentSignRequired"] is True
    assert t[0]["allowAddSign"] is False
    db.rollback()


def test_task_list_allow_add_sign_default_true(db):
    """未配置 allowAddSign → 保持既有行为（允许加签）。"""
    admin, m1, l1 = _users(db)
    code, _ = _make_definition(db, admin, m1, l1)
    biz = _biz_id()
    service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="默认加签", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    assert t[0]["allowAddSign"] is True
    db.rollback()


def test_options_withdraw_after_approved(db):
    """通用选项 allowWithdrawAfterApproved：已通过后发起人仍可撤销。"""
    admin, m1, l1 = _users(db)
    code, _ = _make_definition(
        db, admin, m1, l1, options={"allowWithdrawAfterApproved": True}
    )
    biz = _biz_id()
    inst = service.start(db, biz_type=BIZ, biz_id=biz, definition_code=code, title="可撤销", initiator=admin)
    db.flush()
    t = _todo(db, m1, biz)
    service.approve(db, t[0]["id"], m1, "同意")
    db.flush()
    t2 = _todo(db, l1, biz)
    service.approve(db, t2[0]["id"], l1, "办理")
    db.flush()
    t3 = _todo(db, admin, biz)
    inst = service.approve(db, t3[0]["id"], admin, "通过")
    assert inst.status == "approved"
    inst = service.withdraw(db, inst.id, admin, "反悔")
    assert inst.status == "withdrawn"
    db.rollback()


def test_definition_options_and_field_permissions_persisted(db):
    """定义保存后 options / fieldPermissions 能从出参读回（流程包导出的前提）。"""
    admin, m1, l1 = _users(db)
    code, out = _make_definition(
        db,
        admin,
        m1,
        l1,
        options={"commentRequired": True, "allowAddSign": False},
        field_permissions={"amount": "viewonly", "reason": "editable"},
    )
    assert out["options"]["commentRequired"] is True
    node2 = out["nodes"][1]
    assert node2["fieldPermissions"]["amount"] == "viewonly"
    assert node2["fieldPermissions"]["reason"] == "editable"

    # 重新读一次（出参走 DB）
    rows = {d["code"]: d for d in service.list_definitions(db)}
    again = rows[code]
    assert again["options"]["allowAddSign"] is False
    assert again["nodes"][1]["fieldPermissions"]["amount"] == "viewonly"
    db.rollback()


def test_invalid_field_permission_rejected(db):
    """非法字段权限取值直接拒绝。"""
    admin, m1, l1 = _users(db)
    body = DefinitionIn(
        code=_code(),
        name="非法权限",
        biz_type=BIZ,
        nodes=[
            _node(1, "部门审批", "approval", m1),
            _node(2, "出纳办理", "executor", l1, field_permissions={"amount": "readonly"}),
        ],
    )
    try:
        service.create_definition(db, body)
        raise AssertionError("expected BizException")
    except BizException as e:
        assert "字段权限" in str(e.message or "")
    db.rollback()

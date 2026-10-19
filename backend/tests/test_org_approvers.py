"""组织任职与组织审批人（F4b 并入需求，对齐 TPCworkflow）：

- sys_user_dept 任职模型：主部门/负责人；user.dept_id 冗余同步；
- approver_type 扩展：DEPT_LEADER / PARENT_DEPT_LEADER / SUPERVISOR_CHAIN；
- 解析失败兜底（跳过该级 / 兜底角色，写时间线，不卡死）；部门成员 API；种子幂等。
"""

import json
import uuid

from sqlalchemy import func, select

from app.core.security import hash_password
from app.modules.admin import org
from app.modules.admin.models import Dept, Role, UserDept, UserRole
from app.modules.approval import service
from app.modules.approval.models import ApprovalDefinition, ApprovalNode, ApprovalTask
from app.modules.auth.models import User


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:6]}"


def _biz_id() -> int:
    return uuid.uuid4().int % 10**9 + 10**9


def _mk_user(db, username: str) -> User:
    u = User(username=username, password_hash=hash_password("Test@123456"), name=username, status="enabled")
    db.add(u)
    db.flush()
    return u


def _mk_dept(db, code: str, parent: Dept | None = None) -> Dept:
    d = Dept(name=f"部门{code}", code=code, parent_id=parent.id if parent else None)
    db.add(d)
    db.flush()
    return d


def _mk_member(db, user: User, dept: Dept, is_primary=0, is_leader=0) -> UserDept:
    m = UserDept(user_id=user.id, dept_id=dept.id, is_primary=is_primary, is_leader=is_leader)
    db.add(m)
    db.flush()
    return m


def _mk_definition(db, code: str, nodes: list[dict]) -> ApprovalDefinition:
    d = ApprovalDefinition(code=code, name=code, biz_type="oa_test")
    db.add(d)
    db.flush()
    for n in nodes:
        db.add(
            ApprovalNode(
                definition_id=d.id,
                seq=n["seq"],
                node_name=n.get("name", f"节点{n['seq']}"),
                node_type=n.get("node_type", "approval"),
                sign_mode=n.get("sign_mode", "or"),
                approver_type=n.get("approver_type", "USER"),
                approver_value=n.get("approver_value", ""),
                chain_levels=n.get("chain_levels"),
            )
        )
    db.flush()
    return d


def _start(db, code: str, initiator: User):
    return service.start(
        db, biz_type="oa_test", biz_id=_biz_id(), definition_code=code, title="t", initiator=initiator
    )


def _pending_tasks(db, instance_id: int) -> list[ApprovalTask]:
    return list(
        db.scalars(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == instance_id,
                ApprovalTask.status == "pending",
                ApprovalTask.deleted == 0,
            )
        ).all()
    )


def _records(db, inst) -> list[str]:
    return [r.action for r in inst.records]


# ---------------- 解析语义 ----------------


def test_dept_leader_resolution(db):
    a = _mk_dept(db, _uniq("A"))
    initiator = _mk_user(db, _uniq("u_init"))
    leader = _mk_user(db, _uniq("u_lead"))
    _mk_member(db, initiator, a, is_primary=1)
    _mk_member(db, leader, a, is_leader=1)
    d = _mk_definition(db, _uniq("flow_"), [{"seq": 1, "approver_type": "DEPT_LEADER"}])
    inst = _start(db, d.code, initiator)
    db.flush()
    tasks = _pending_tasks(db, inst.id)
    assert [t.assignee_id for t in tasks] == [leader.id]
    db.rollback()


def test_dept_leader_excludes_initiator(db):
    a = _mk_dept(db, _uniq("A"))
    initiator = _mk_user(db, _uniq("u_init"))
    other = _mk_user(db, _uniq("u_lead"))
    _mk_member(db, initiator, a, is_primary=1, is_leader=1)  # 发起人也是负责人 → 排除自审
    _mk_member(db, other, a, is_leader=1)
    d = _mk_definition(db, _uniq("flow_"), [{"seq": 1, "approver_type": "DEPT_LEADER"}])
    inst = _start(db, d.code, initiator)
    db.flush()
    tasks = _pending_tasks(db, inst.id)
    assert [t.assignee_id for t in tasks] == [other.id]
    db.rollback()


def test_dept_leader_no_leader_auto_pass(db):
    """主部门无负责人且无兜底角色 → 节点 auto_pass 跳过，流程不卡死，时间线有记录。"""
    a = _mk_dept(db, _uniq("A"))
    initiator = _mk_user(db, _uniq("u_init"))
    fallback_user = _mk_user(db, _uniq("u_end"))
    _mk_member(db, initiator, a, is_primary=1)
    d = _mk_definition(
        db,
        _uniq("flow_"),
        [
            {"seq": 1, "approver_type": "DEPT_LEADER"},
            {"seq": 2, "approver_type": "USER", "approver_value": str(fallback_user.id)},
        ],
    )
    inst = _start(db, d.code, initiator)
    db.flush()
    assert inst.status == "running" and inst.current_seq == 2
    tasks = _pending_tasks(db, inst.id)
    assert [t.assignee_id for t in tasks] == [fallback_user.id]
    assert "auto_pass" in _records(db, inst)
    db.rollback()


def test_dept_leader_fallback_role(db):
    """无负责人但配置了兜底角色（approver_value=角色code）→ 落到兜底角色，时间线记 fallback。"""
    a = _mk_dept(db, _uniq("A"))
    initiator = _mk_user(db, _uniq("u_init"))
    fb = _mk_user(db, _uniq("u_fb"))
    _mk_member(db, initiator, a, is_primary=1)
    role = Role(code=_uniq("role_"), name="兜底角色")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=fb.id, role_id=role.id))
    db.flush()
    d = _mk_definition(
        db, _uniq("flow_"), [{"seq": 1, "approver_type": "DEPT_LEADER", "approver_value": role.code}]
    )
    inst = _start(db, d.code, initiator)
    db.flush()
    tasks = _pending_tasks(db, inst.id)
    assert [t.assignee_id for t in tasks] == [fb.id]
    assert "fallback" in _records(db, inst)
    db.rollback()


def test_parent_dept_leader(db):
    root = _mk_dept(db, _uniq("R"))
    child = _mk_dept(db, _uniq("C"), parent=root)
    initiator = _mk_user(db, _uniq("u_init"))
    boss = _mk_user(db, _uniq("u_boss"))
    _mk_member(db, initiator, child, is_primary=1)
    _mk_member(db, boss, root, is_leader=1)
    d = _mk_definition(db, _uniq("flow_"), [{"seq": 1, "approver_type": "PARENT_DEPT_LEADER"}])
    inst = _start(db, d.code, initiator)
    db.flush()
    tasks = _pending_tasks(db, inst.id)
    assert [t.assignee_id for t in tasks] == [boss.id]
    db.rollback()


def test_parent_dept_leader_no_parent_auto_pass(db):
    root = _mk_dept(db, _uniq("R"))
    initiator = _mk_user(db, _uniq("u_init"))
    _mk_member(db, initiator, root, is_primary=1)
    d = _mk_definition(
        db,
        _uniq("flow_"),
        [{"seq": 1, "approver_type": "PARENT_DEPT_LEADER"}],
    )
    inst = _start(db, d.code, initiator)
    db.flush()
    # 唯一节点被跳过 → 实例直接通过
    assert inst.status == "approved"
    assert "auto_pass" in _records(db, inst)
    db.rollback()


def test_supervisor_chain_levels(db):
    """三级部门链：levels=0 到根 [la,lb,lc]；levels=2 截断 [la,lb]；逐级 sequential 推进。"""
    root = _mk_dept(db, _uniq("R"))
    mid = _mk_dept(db, _uniq("M"), parent=root)
    leaf = _mk_dept(db, _uniq("L"), parent=mid)
    initiator = _mk_user(db, _uniq("u_init"))
    la, lb, lc = (_mk_user(db, _uniq(f"u_{x}")) for x in "abc")
    _mk_member(db, initiator, leaf, is_primary=1)
    _mk_member(db, la, leaf, is_leader=1)
    _mk_member(db, lb, mid, is_leader=1)
    _mk_member(db, lc, root, is_leader=1)

    # 截断到 2 级
    d2 = _mk_definition(
        db,
        _uniq("flow_"),
        [{"seq": 1, "approver_type": "SUPERVISOR_CHAIN", "chain_levels": 2}],
    )
    inst = _start(db, d2.code, initiator)
    db.flush()
    tasks = _pending_tasks(db, inst.id)
    assert len(tasks) == 1 and tasks[0].assignee_id == la.id  # 依次签：仅队首持有待办
    queue = json.loads(tasks[0].action_meta)["sequential_queue"]
    assert queue == [la.id, lb.id]

    # 到根：三级全收
    d3 = _mk_definition(
        db, _uniq("flow_"), [{"seq": 1, "approver_type": "SUPERVISOR_CHAIN"}]
    )
    inst2 = _start(db, d3.code, initiator)
    db.flush()
    t = _pending_tasks(db, inst2.id)[0]
    assert json.loads(t.action_meta)["sequential_queue"] == [la.id, lb.id, lc.id]
    # 逐级推进：la 同意 → lb 持有待办
    service.approve(db, t.id, la, "ok")
    db.flush()
    t2 = _pending_tasks(db, inst2.id)
    assert len(t2) == 1 and t2[0].assignee_id == lb.id
    db.rollback()


def test_supervisor_chain_skip_middle_level(db):
    """中间级无负责人 → 跳过该级并记录，链条继续向上。"""
    root = _mk_dept(db, _uniq("R"))
    mid = _mk_dept(db, _uniq("M"), parent=root)
    leaf = _mk_dept(db, _uniq("L"), parent=mid)
    initiator = _mk_user(db, _uniq("u_init"))
    la, lc = _mk_user(db, _uniq("u_a")), _mk_user(db, _uniq("u_c"))
    _mk_member(db, initiator, leaf, is_primary=1)
    _mk_member(db, la, leaf, is_leader=1)
    _mk_member(db, lc, root, is_leader=1)
    d = _mk_definition(db, _uniq("flow_"), [{"seq": 1, "approver_type": "SUPERVISOR_CHAIN"}])
    inst = _start(db, d.code, initiator)
    db.flush()
    t = _pending_tasks(db, inst.id)[0]
    assert json.loads(t.action_meta)["sequential_queue"] == [la.id, lc.id]
    fb_records = [r for r in inst.records if r.action == "fallback"]
    assert fb_records and "已跳过" in fb_records[0].comment
    db.rollback()


def test_org_type_with_and_sign(db):
    """组织类型 + 会签：部门两名负责人同时持有待办，全员通过才推进。"""
    a = _mk_dept(db, _uniq("A"))
    initiator = _mk_user(db, _uniq("u_init"))
    l1, l2 = _mk_user(db, _uniq("u_l1")), _mk_user(db, _uniq("u_l2"))
    end = _mk_user(db, _uniq("u_end"))
    _mk_member(db, initiator, a, is_primary=1)
    _mk_member(db, l1, a, is_leader=1)
    _mk_member(db, l2, a, is_leader=1)
    d = _mk_definition(
        db,
        _uniq("flow_"),
        [
            {"seq": 1, "approver_type": "DEPT_LEADER", "sign_mode": "and"},
            {"seq": 2, "approver_type": "USER", "approver_value": str(end.id)},
        ],
    )
    inst = _start(db, d.code, initiator)
    db.flush()
    tasks = _pending_tasks(db, inst.id)
    assert sorted(t.assignee_id for t in tasks) == sorted([l1.id, l2.id])
    service.approve(db, tasks[0].id, l1 if tasks[0].assignee_id == l1.id else l2, "ok")
    db.flush()
    assert inst.current_seq == 1  # 会签未齐，不推进
    rest = _pending_tasks(db, inst.id)[0]
    service.approve(db, rest.id, l2 if rest.assignee_id == l2.id else l1, "ok")
    db.flush()
    assert inst.current_seq == 2
    db.rollback()


def test_primary_dept_fallback_to_user_dept_id(db):
    """无任职记录时回退 user.dept_id（旧字段兼容）。"""
    a = _mk_dept(db, _uniq("A"))
    initiator = _mk_user(db, _uniq("u_init"))
    leader = _mk_user(db, _uniq("u_lead"))
    initiator.dept_id = a.id  # 仅旧字段，无任职行
    db.flush()
    _mk_member(db, leader, a, is_leader=1)
    assert org.primary_dept_id(db, initiator.id) == a.id
    d = _mk_definition(db, _uniq("flow_"), [{"seq": 1, "approver_type": "DEPT_LEADER"}])
    inst = _start(db, d.code, initiator)
    db.flush()
    assert _pending_tasks(db, inst.id)[0].assignee_id == leader.id
    db.rollback()


def test_definition_api_accepts_org_types(client, admin_headers):
    """定义 API：组织类型节点允许空 approver_value；SUPERVISOR_CHAIN 带级数。"""
    r = client.post(
        "/api/v1/approval/definitions",
        headers=admin_headers,
        json={
            "code": _uniq("org_api_"),
            "name": "组织审批",
            "bizType": "oa_test",
            "nodes": [
                {"seq": 1, "nodeName": "部门负责人", "approverType": "DEPT_LEADER"},
                {"seq": 2, "nodeName": "逐级审批", "approverType": "SUPERVISOR_CHAIN", "chainLevels": 3},
            ],
        },
    ).json()
    assert r["code"] == 0, r
    nodes = r["data"]["nodes"]
    assert nodes[1]["chainLevels"] == 3
    # 非法类型仍拒绝
    bad = client.post(
        "/api/v1/approval/definitions",
        headers=admin_headers,
        json={
            "code": _uniq("org_bad_"),
            "name": "x",
            "bizType": "oa_test",
            "nodes": [{"seq": 1, "approverType": "NOPE"}],
        },
    )
    assert bad.status_code == 422


# ---------------- 部门成员 API ----------------


def test_dept_members_api(client, admin_headers, db):
    # 建部门 + 两个用户
    dept_code = _uniq("T")
    dept = client.post(
        "/api/v1/admin/depts", headers=admin_headers, json={"name": _uniq("测试部"), "code": dept_code}
    ).json()
    assert dept["code"] == 0
    dept_id = db.scalar(select(Dept.id).where(Dept.code == dept_code, Dept.deleted == 0))
    assert dept_id
    u1 = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": _uniq("m_user1"), "password": "Test@123456", "name": "成员甲"},
    ).json()
    u2 = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": _uniq("m_user2"), "password": "Test@123456", "name": "成员乙"},
    ).json()
    assert u1["code"] == 0 and u2["code"] == 0
    uid1, uid2 = u1["data"]["id"], u2["data"]["id"]

    # 设置成员：u1 负责人+主部门，u2 普通成员
    r = client.put(
        f"/api/v1/admin/depts/{dept_id}/members",
        headers=admin_headers,
        json={"members": [{"userId": uid1, "isPrimary": 1, "isLeader": 1}, {"userId": uid2}]},
    ).json()
    assert r["code"] == 0, r
    members = client.get(f"/api/v1/admin/depts/{dept_id}/members", headers=admin_headers).json()["data"]
    by_uid = {m["userId"]: m for m in members}
    assert by_uid[uid1]["isLeader"] == 1 and by_uid[uid1]["isPrimary"] == 1
    assert by_uid[uid2]["isLeader"] == 0
    # 主部门同步到 user.dept_id（结束当前事务快照，读到 API 会话已提交的数据）
    db.commit()
    u1_row = db.get(User, uid1)
    assert u1_row and u1_row.dept_id == dept_id
    # 重复 PUT 幂等：整组替换不堆叠
    r2 = client.put(
        f"/api/v1/admin/depts/{dept_id}/members",
        headers=admin_headers,
        json={"members": [{"userId": uid1, "isPrimary": 1, "isLeader": 1}]},
    ).json()
    assert r2["code"] == 0
    members2 = client.get(f"/api/v1/admin/depts/{dept_id}/members", headers=admin_headers).json()["data"]
    assert len(members2) == 1
    db.rollback()


def test_seed_membership_idempotent(db):
    """种子幂等：重跑不重复插入任职、主部门唯一。"""
    m1 = db.scalar(select(User).where(User.username == "manager1"))
    assert m1 is not None
    cnt = db.scalar(
        select(func.count()).select_from(
            select(UserDept).where(UserDept.user_id == m1.id, UserDept.deleted == 0).subquery()
        )
    )
    assert cnt and cnt >= 1
    from app.seeds import init_data as seed

    seed.main()
    db.expire_all()
    cnt2 = db.scalar(
        select(func.count()).select_from(
            select(UserDept).where(UserDept.user_id == m1.id, UserDept.deleted == 0).subquery()
        )
    )
    assert cnt2 == cnt
    primary_cnt = db.scalar(
        select(func.count()).select_from(
            select(UserDept)
            .where(UserDept.user_id == m1.id, UserDept.is_primary == 1, UserDept.deleted == 0)
            .subquery()
        )
    )
    assert primary_cnt == 1
    db.rollback()

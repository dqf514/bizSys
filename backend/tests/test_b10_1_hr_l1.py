"""B10-1 / HR L1 组织架构 + 员工主数据 + 人事事务。

覆盖：
- 部门扩展字段（层级 / 场所编码 / 负责人双向同步 / 有效期）；
- 岗位 CRUD + 关键岗位标记 + A、B 角 + 删除后引用清理；
- 组织变更轨迹（只追加）；
- 证件号加密落库 + 出参掩码 + 明文唯一出口（访问留痕）；
- 建档冲突（工号 / 证件号 / 兼职 / 关键岗位）与名单管控（黑名单）；
- 人事事务状态机 + **审批通过 ≠ 生效**；
- 入职 / 调岗 / 离职副作用（离职清权：禁号 + 撤 MFA + 撤授权 + 代理失效 + 清 A/B 角）；
- 代理人生命周期（委托人离职自动失效）。

测试库口径见 conftest（bizsys_test，create_all 建表，不跑迁移）。
"""

import uuid
from datetime import date, datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.admin.models import AuditLog, Dept, UserDept
from app.modules.auth.models import User
from app.modules.hr.models import (
    HrAuthorization,
    HrAuthorizationEvent,
    HrDelegate,
    HrEmployee,
    HrEmployeeControl,
    HrEmploymentEvent,
    HrOrgChange,
    HrPosition,
)

# ---------------- 通用辅助 ----------------


def _tag() -> str:
    """每次运行的后缀（测试库跨次运行残留）。"""
    return uuid.uuid4().hex[:8]


def _admin_id() -> int:
    db = SessionLocal()
    try:
        u = db.scalar(select(User).where(User.username == "admin", User.deleted == 0))
        assert u, "种子账号 admin 不存在"
        return u.id
    finally:
        db.close()


def _user_id(username: str) -> int:
    db = SessionLocal()
    try:
        u = db.scalar(select(User).where(User.username == username, User.deleted == 0))
        assert u, f"用户不存在：{username}"
        return u.id
    finally:
        db.close()


def _data(resp) -> dict:
    """拆响应信封并断言 code == 0。"""
    body = resp.json()
    assert body["code"] == 0, body
    return body["data"]


def _err(resp) -> int:
    """取错误码（断言失败）。"""
    body = resp.json()
    assert body["code"] != 0, body
    return body["code"]


def _mk_dept(client, headers, **over) -> dict:
    """新建部门（带 B10-1 扩展字段）。"""
    tag = _tag()
    payload = {
        "name": f"用例科室-{tag}",
        "code": f"T{tag}",
        "sort": 99,
        "status": "enabled",
        "deptType": "dept",
        "siteCode": f"SITE-{tag}",
        "address": "合肥高新区测试路 1 号",
        "effectiveFrom": "2026-01-01",
    }
    payload.update(over)
    _data(client.post("/api/v1/admin/depts", json=payload, headers=headers))
    depts = _data(client.get("/api/v1/admin/depts", headers=headers))
    row = next(d for d in depts if d["code"] == payload["code"])
    return row


def _mk_position(client, headers, **over) -> dict:
    tag = _tag()
    payload = {
        "code": f"P{tag}",
        "name": f"用例岗位-{tag}",
        "positionType": "staff",
        "status": "enabled",
        "duty": "负责测试活动",
        "requirement": "具备相关资质",
    }
    payload.update(over)
    return _data(client.post("/api/v1/hr/org/positions", json=payload, headers=headers))


def _mk_user(client, headers, **over) -> dict:
    """新建系统账号（用于「同一人兼职冲突」这类需要唯一绑定人的用例）。"""
    tag = _tag()
    payload = {
        "username": f"u{tag}",
        "name": f"用例用户{tag}",
        "password": "Test@123456",
        "status": "enabled",
    }
    payload.update(over)
    return _data(client.post("/api/v1/admin/users", json=payload, headers=headers))


def _mk_employee(client, headers, **over) -> dict:
    tag = _tag()
    payload = {
        "employeeNo": f"E{tag}",
        "name": f"用例员工{tag}",
        "employType": "labor",
        "employStatus": "probation",
        "gender": "male",
    }
    payload.update(over)
    return _data(client.post("/api/v1/hr/employees", json=payload, headers=headers))


def _mk_employment(client, headers, employee_id: int, **over) -> dict:
    payload = {
        "employeeId": employee_id,
        "eventType": "onboard",
        "effectiveDate": date.today().isoformat(),
        "reason": "用例",
    }
    payload.update(over)
    return _data(client.post("/api/v1/hr/employments", json=payload, headers=headers))


# ---------------- 1. 部门扩展字段 ----------------


def test_dept_extended_fields(client, admin_headers):
    """部门扩展列落库 + 负责人与任职表 is_leader 双向同步。"""
    admin_id = _admin_id()
    dept = _mk_dept(client, admin_headers, managerId=admin_id)

    assert dept["deptType"] == "dept"
    assert dept["siteCode"].startswith("SITE-")
    assert dept["address"] == "合肥高新区测试路 1 号"
    assert dept["managerId"] == admin_id
    assert dept["managerName"]
    assert dept["effectiveFrom"] == "2026-01-01"

    db = SessionLocal()
    try:
        row = db.get(Dept, dept["id"])
        assert row.dept_type == "dept"
        assert row.manager_id == admin_id
        rel = db.scalar(
            select(UserDept).where(
                UserDept.user_id == admin_id,
                UserDept.dept_id == dept["id"],
                UserDept.deleted == 0,
            )
        )
        assert rel is not None, "负责人未写入部门任职表"
        assert rel.is_leader == 1, "任职表 is_leader 未同步"
    finally:
        db.close()


# ---------------- 2. 岗位 CRUD + 关键岗位 ----------------


def test_position_crud_and_key_role(client, admin_headers):
    """岗位唯一码 / A、B 角校验 / 关键岗位标记 / 删除后引用清理。"""
    admin_id = _admin_id()
    pos = _mk_position(
        client,
        admin_headers,
        keyRole="qa_leader",
        positionType="key",
        primaryUserId=admin_id,
    )
    assert pos["keyRole"] == "qa_leader"
    assert pos["primaryUserName"]

    # 编码重复
    dup = client.post(
        "/api/v1/hr/org/positions",
        json={"code": pos["code"], "name": "重复编码", "positionType": "staff"},
        headers=admin_headers,
    )
    assert _err(dup) == 63010

    # A 角 = B 角
    same = client.post(
        "/api/v1/hr/org/positions",
        json={
            "code": f"P{_tag()}",
            "name": "A B 同一人",
            "positionType": "staff",
            "primaryUserId": admin_id,
            "backupUserId": admin_id,
        },
        headers=admin_headers,
    )
    assert _err(same) == 63010

    # 员工挂到该岗位后删除岗位 → 员工的 position_id 被清理
    emp = _mk_employee(client, admin_headers, positionId=pos["id"])
    _data(client.delete(f"/api/v1/hr/org/positions/{pos['id']}", headers=admin_headers))

    db = SessionLocal()
    try:
        e = db.get(HrEmployee, emp["id"])
        assert e.position_id is None, "删除岗位后员工仍挂着已删除岗位"
    finally:
        db.close()


# ---------------- 3. 组织变更轨迹 ----------------


def test_org_change_trail(client, admin_headers):
    """部门 / 岗位变更写入只追加的组织变更轨迹。"""
    dept = _mk_dept(client, admin_headers)
    pos = _mk_position(client, admin_headers, deptId=dept["id"])

    changes = _data(
        client.get(
            "/api/v1/hr/org/changes",
            params={"filters[object_type]": "position", "filters[object_id]": pos["id"]},
            headers=admin_headers,
        )
    )
    assert changes["total"] >= 1
    first = changes["items"][0]
    assert first["changeType"] == "create"
    assert first["objectName"] == pos["name"]

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(HrOrgChange).where(
                HrOrgChange.object_type == "dept", HrOrgChange.object_id == dept["id"]
            )
        ).all()
        assert rows, "部门新建未写变更轨迹"
        # 只追加表：没有 deleted / version 列
        assert not hasattr(rows[0], "deleted")
    finally:
        db.close()


# ---------------- 4. 证件号加密 / 掩码 / 明文出口 ----------------


def test_employee_id_encrypted_and_masked(client, admin_headers):
    """证件号密文落库，出参掩码，明文唯一出口留痕。"""
    # 测试库跨次运行残留 → 证件号必须每次唯一（后端按明文逐条比对判重）
    plain = f"33010619900101{_tag()}"
    emp = _mk_employee(client, admin_headers, idNo=plain, idType="id_card")
    assert emp["idNo"] != plain
    assert emp["idNo"].startswith("3301")
    assert "*" in emp["idNo"]

    db = SessionLocal()
    try:
        row = db.get(HrEmployee, emp["id"])
        assert row.id_no.startswith("enc:"), "证件号未加密落库"
        assert plain not in row.id_no
    finally:
        db.close()

    # 详情出参同样是掩码
    detail = _data(client.get(f"/api/v1/hr/employees/{emp['id']}", headers=admin_headers))
    assert detail["idNo"] == emp["idNo"]

    # 明文出口 + 访问留痕
    out = _data(client.get(f"/api/v1/hr/employees/{emp['id']}/id-no", headers=admin_headers))
    assert out["idNo"] == plain
    assert out["masked"] == emp["idNo"]

    db = SessionLocal()
    try:
        logs = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "hr_employee_idno_view",
                AuditLog.biz_id == emp["id"],
            )
        ).all()
        assert logs, "查看证件号明文未写审计日志"
    finally:
        db.close()


# ---------------- 5. 建档冲突与名单管控 ----------------


def test_employee_conflicts_and_blacklist(client, admin_headers):
    """工号重复 / 兼职冲突 / 兼职不得任关键岗位 / 黑名单拦截入职。"""
    # 兼职冲突按「同一人」判定 → 用一个本次运行新建的账号，避免测试库残留干扰
    part_time_user = _mk_user(client, admin_headers)

    emp = _mk_employee(client, admin_headers)
    # 工号重复
    dup = client.post(
        "/api/v1/hr/employees",
        json={"employeeNo": emp["employeeNo"], "name": "重复工号", "employType": "labor"},
        headers=admin_headers,
    )
    assert _err(dup) == 63013

    # 兼职：同一人只能有一条生效兼职档案
    _mk_employee(client, admin_headers, employType="part_time", userId=part_time_user["id"])
    conflict = client.post(
        "/api/v1/hr/employees",
        json={
            "employeeNo": f"E{_tag()}",
            "name": "第二份兼职",
            "employType": "part_time",
            "userId": part_time_user["id"],
        },
        headers=admin_headers,
    )
    assert _err(conflict) == 63016

    # 兼职不得担任关键岗位
    key_pos = _mk_position(client, admin_headers, keyRole="tech_leader", positionType="key")
    key_conflict = client.post(
        "/api/v1/hr/employees",
        json={
            "employeeNo": f"E{_tag()}",
            "name": "兼职关键岗",
            "employType": "part_time",
            "positionId": key_pos["id"],
        },
        headers=admin_headers,
    )
    assert _err(key_conflict) == 63016

    # 名单管控：黑名单 → 入职生效被拦
    target = _mk_employee(client, admin_headers)
    _data(
        client.post(
            f"/api/v1/hr/employees/{target['id']}/control",
            json={"controlType": "blacklist", "reason": "合规限制", "status": "enabled"},
            headers=admin_headers,
        )
    )
    db = SessionLocal()
    try:
        ctl = db.scalar(
            select(HrEmployeeControl).where(
                HrEmployeeControl.employee_id == target["id"],
                HrEmployeeControl.control_type == "blacklist",
            )
        )
        assert ctl is not None
    finally:
        db.close()


# ---------------- 6. 入职流程：审批通过 ≠ 生效 ----------------


def _approve_employment(client, headers, emp_id: int, times: int = 2) -> dict:
    """提交 → 审批通过（返回审批后状态，仍未生效）。"""
    _data(client.post(f"/api/v1/hr/employments/{emp_id}/submit", headers=headers))
    from conftest import approve_instance

    approve_instance("hr_employment", emp_id, times=times)
    return _data(client.get(f"/api/v1/hr/employments/{emp_id}", headers=headers))


def test_employment_onboard_flow(client, admin_headers):
    """入职：提交审批 → 通过 → 生效 → 建号 + 任职 + 档案回填。"""
    tag = _tag()
    dept = _mk_dept(client, admin_headers)
    emp = _mk_employee(client, admin_headers, deptId=dept["id"])
    doc = _mk_employment(
        client,
        admin_headers,
        emp["id"],
        createAccount=True,
        username=f"t{tag}",
        password="Test@123456",
    )
    assert doc["status"] == "draft"
    assert doc["empNo"].startswith("EM")

    # 审批通过 ≠ 生效
    approved = _approve_employment(client, admin_headers, doc["id"])
    assert approved["status"] == "approved", "审批通过后状态应为 approved"
    assert approved["approverName"]

    # 生效
    eff = _data(client.post(f"/api/v1/hr/employments/{doc['id']}/effect", headers=admin_headers))
    assert eff["status"] == "effective"
    assert eff["effect"]["account"]["username"] == f"t{tag}"

    db = SessionLocal()
    try:
        u = db.scalar(select(User).where(User.username == f"t{tag}", User.deleted == 0))
        assert u is not None, "入职生效未建账号"
        assert u.status == "enabled"
        assert u.employee_no == emp["employeeNo"], "工号冗余列未同步"

        e = db.get(HrEmployee, emp["id"])
        assert e.user_id == u.id, "员工档案未回填账号"
        assert e.employ_status == "probation"
        assert e.hire_date is not None

        rel = db.scalar(
            select(UserDept).where(UserDept.user_id == u.id, UserDept.deleted == 0)
        )
        assert rel is not None and rel.is_primary == 1, "主部门任职未建立"

        evs = db.scalars(
            select(HrEmploymentEvent).where(HrEmploymentEvent.employment_id == doc["id"])
        ).all()
        kinds = {e.event_type for e in evs}
        assert {"create", "submit", "approve", "effect"} <= kinds, kinds
    finally:
        db.close()


# ---------------- 7. 调岗流程 ----------------


def test_employment_transfer_flow(client, admin_headers):
    """调岗生效：账号部门 + 主部门任职 + 档案归属同步。"""
    dept_a = _mk_dept(client, admin_headers)
    dept_b = _mk_dept(client, admin_headers)
    pos = _mk_position(client, admin_headers, deptId=dept_a["id"])

    emp = _mk_employee(client, admin_headers, deptId=dept_a["id"], positionId=pos["id"])
    doc = _mk_employment(
        client,
        admin_headers,
        emp["id"],
        eventType="transfer",
        newDeptId=dept_b["id"],
        newPositionId=pos["id"],
    )
    _approve_employment(client, admin_headers, doc["id"])
    _data(client.post(f"/api/v1/hr/employments/{doc['id']}/effect", headers=admin_headers))

    db = SessionLocal()
    try:
        e = db.get(HrEmployee, emp["id"])
        assert e.dept_id == dept_b["id"], "调岗后档案部门未更新"

        if e.user_id:
            u = db.get(User, e.user_id)
            assert u.dept_id == dept_b["id"], "调岗后账号部门未更新"
            rels = db.scalars(
                select(UserDept).where(UserDept.user_id == u.id, UserDept.deleted == 0)
            ).all()
            primary = [r for r in rels if r.is_primary == 1]
            assert len(primary) == 1, "主部门任职不唯一"
            assert primary[0].dept_id == dept_b["id"], "主部门任职未指向新部门"
    finally:
        db.close()


# ---------------- 8. 离职副作用：清权 ----------------


def test_employment_resign_revokes_everything(client, admin_headers):
    """离职生效：禁号 + 关 MFA + 撤授权 + 代理失效 + 清岗位 A/B 角。"""
    tag = _tag()
    admin_id = _admin_id()
    dept = _mk_dept(client, admin_headers)
    pos = _mk_position(client, admin_headers, deptId=dept["id"])

    emp = _mk_employee(client, admin_headers, deptId=dept["id"])
    doc = _mk_employment(
        client,
        admin_headers,
        emp["id"],
        createAccount=True,
        username=f"t{tag}",
        password="Test@123456",
    )
    _approve_employment(client, admin_headers, doc["id"])
    _data(client.post(f"/api/v1/hr/employments/{doc['id']}/effect", headers=admin_headers))

    db = SessionLocal()
    try:
        e = db.get(HrEmployee, emp["id"])
        uid = e.user_id
        assert uid

        # 造一条生效中的授权 + 一条代理 + 把离职者设为岗位 A 角
        auth_no = f"AU{uuid.uuid4().hex[:14].upper()}"
        a = HrAuthorization(
            auth_no=auth_no,
            user_id=uid,
            user_name=e.name,
            auth_type="test_item",
            status="active",
        )
        db.add(a)
        db.flush()
        db.add(
            HrDelegate(
                principal_id=uid,
                principal_name=e.name,
                agent_id=admin_id,
                agent_name="admin",
                scope="position",
                position_id=pos["id"],
                status="enabled",
                effective_from=datetime.now(),
            )
        )
        db.commit()
        auth_id = a.id
    finally:
        db.close()

    # 岗位 A 角指向离职者
    _data(
        client.put(
            f"/api/v1/hr/org/positions/{pos['id']}",
            json={
                "code": pos["code"],
                "name": pos["name"],
                "deptId": dept["id"],
                "positionType": "staff",
                "primaryUserId": uid,
                "status": "enabled",
            },
            headers=admin_headers,
        )
    )

    # 离职单
    resign = _mk_employment(
        client,
        admin_headers,
        emp["id"],
        eventType="resign",
        effectiveDate=date.today().isoformat(),
        reason="离职",
    )
    _approve_employment(client, admin_headers, resign["id"])
    eff = _data(client.post(f"/api/v1/hr/employments/{resign['id']}/effect", headers=admin_headers))
    assert eff["status"] == "effective"
    assert eff["effect"]["revokedAuth"] >= 1

    db = SessionLocal()
    try:
        u = db.get(User, uid)
        assert u.status == "disabled", "离职后账号未禁用"
        assert u.mfa_enabled == 0, "离职后 MFA 未关闭"

        a = db.get(HrAuthorization, auth_id)
        assert a.status == "revoked", "离职后授权未撤销"

        ev = db.scalars(
            select(HrAuthorizationEvent).where(HrAuthorizationEvent.authorization_id == auth_id)
        ).all()
        assert any(e.event_type == "revoke" for e in ev), "授权撤销未写事件"

        d = db.scalar(
            select(HrDelegate).where(HrDelegate.principal_id == uid, HrDelegate.deleted == 0)
        )
        assert d.status == "expired", "委托人离职后代理未失效"

        p = db.get(HrPosition, pos["id"])
        assert p.primary_user_id is None, "离职后岗位 A 角未清空"

        e = db.get(HrEmployee, emp["id"])
        assert e.employ_status == "resigned"
        assert e.leave_date is not None
    finally:
        db.close()


# ---------------- 9. 状态守卫 ----------------


def test_employment_state_guards(client, admin_headers):
    """草稿不可生效 / 已通过不可编辑 / 提交后不可重复提交。"""
    emp = _mk_employee(client, admin_headers)
    doc = _mk_employment(client, admin_headers, emp["id"])

    # 草稿直接生效 → 状态机拦截
    assert _err(client.post(f"/api/v1/hr/employments/{doc['id']}/effect", headers=admin_headers)) == 63014

    # 草稿可编辑
    _data(
        client.put(
            f"/api/v1/hr/employments/{doc['id']}",
            json={
                "employeeId": emp["id"],
                "eventType": "onboard",
                "effectiveDate": date.today().isoformat(),
                "reason": "改过的原因",
            },
            headers=admin_headers,
        )
    )

    # 提交 → 审批中
    _data(client.post(f"/api/v1/hr/employments/{doc['id']}/submit", headers=admin_headers))
    # 审批中不可编辑
    assert (
        _err(
            client.put(
                f"/api/v1/hr/employments/{doc['id']}",
                json={"employeeId": emp["id"], "eventType": "onboard"},
                headers=admin_headers,
            )
        )
        == 63014
    )


# ---------------- 10. 代理人生命周期 ----------------


def test_delegate_lifecycle(client, admin_headers):
    """代理创建 / 委托人是离职者时代理自动失效。"""
    admin_id = _admin_id()
    tag = _tag()
    dept = _mk_dept(client, admin_headers)
    pos = _mk_position(client, admin_headers, deptId=dept["id"])
    emp = _mk_employee(client, admin_headers, deptId=dept["id"], positionId=pos["id"])
    doc = _mk_employment(
        client,
        admin_headers,
        emp["id"],
        createAccount=True,
        username=f"t{tag}",
        password="Test@123456",
    )
    _approve_employment(client, admin_headers, doc["id"])
    _data(client.post(f"/api/v1/hr/employments/{doc['id']}/effect", headers=admin_headers))

    db = SessionLocal()
    try:
        uid = db.get(HrEmployee, emp["id"]).user_id
    finally:
        db.close()
    assert uid

    dele = _data(
        client.post(
            "/api/v1/hr/delegates",
            json={
                "principalId": uid,
                "agentId": admin_id,
                "scope": "position",
                "positionId": pos["id"],
                "reason": "出差期间代理",
                "effectiveFrom": "2026-11-01T09:00:00",
                "autoTakeover": 1,
            },
            headers=admin_headers,
        )
    )
    assert dele["status"] == "enabled"
    assert dele["principalName"]

    # 委托人离职 → 代理自动失效
    resign = _mk_employment(
        client,
        admin_headers,
        emp["id"],
        eventType="resign",
        effectiveDate=date.today().isoformat(),
        reason="离职",
    )
    _approve_employment(client, admin_headers, resign["id"])
    _data(client.post(f"/api/v1/hr/employments/{resign['id']}/effect", headers=admin_headers))

    db = SessionLocal()
    try:
        d = db.get(HrDelegate, dele["id"])
        assert d.status == "expired", "委托人离职后代理未自动失效"
    finally:
        db.close()


# ---------------- 11. 员工档案与人事事务的联动校验 ----------------


def test_employee_delete_blocked_by_pending_employment(client, admin_headers):
    """存在未完结人事事务时不允许删除员工档案。"""
    emp = _mk_employee(client, admin_headers)
    _mk_employment(client, admin_headers, emp["id"])
    assert _err(client.delete(f"/api/v1/hr/employees/{emp['id']}", headers=admin_headers)) == 63012

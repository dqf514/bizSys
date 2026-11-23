"""B9-C3 人员授权台账与拦截点。

覆盖：
- 授权状态机（全路径 + 非法跃迁 + 暂停/撤销原因必填）；
- 变更轨迹只追加 + 时点回放（state_at）；
- 授权校验（命中 / 未命中 / 过期 / 范围不符 / 角色不符 / 超管旁路 / 开关旁路）；
- 拦截点：无授权不能编制报告、不能签章、不能录入进度、不能承接任务；
- 职责分离（编制 / 复核 / 批准不得同一人）；
- 授权审批联动（通过 → confirmed + 写变更轨迹）。
"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.exceptions import BizException
from app.core.security import hash_password
from app.modules.admin.models import Role
from app.modules.auth.models import User
from app.modules.hr import authorization as auth
from app.modules.hr.models import HrAuthorization, HrAuthorizationEvent

# ---------------- 辅助 ----------------


def _user_id(username: str) -> int:
    db = SessionLocal()
    try:
        u = db.scalar(select(User).where(User.username == username, User.deleted == 0))
        assert u, f"用户不存在：{username}"
        return u.id
    finally:
        db.close()


def _fresh_user() -> int:
    """建一个**没有任何授权**的干净账号（避免与演示种子授权互相干扰）。"""
    db = SessionLocal()
    try:
        u = User(
            username=f"t{uuid.uuid4().hex[:12]}",
            password_hash=hash_password("Test@123456"),
            name="授权用例用户",
            status="enabled",
        )
        db.add(u)
        db.flush()
        db.commit()
        return u.id
    finally:
        db.close()


def _make_auth(
    user_id: int,
    auth_type: str = "test_item",
    role_code: str = "",
    scope_method: str = "",
    scope_device_id: int | None = None,
    scope_domain: str = "",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    status: str = "active",
    effective_at: datetime | None = None,
) -> int:
    """直接落一条授权（绕开审批以便单测状态机与校验）。"""
    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        a = HrAuthorization(
            auth_no=f"T{uuid.uuid4().hex[:14].upper()}",
            user_id=user_id,
            user_name=(u.name or u.username) if u else "",
            auth_type=auth_type,
            role_code=role_code,
            scope_method=scope_method,
            scope_device_id=scope_device_id,
            scope_domain=scope_domain,
            valid_from=valid_from,
            valid_to=valid_to,
            status=status,
            create_by=user_id,
        )
        db.add(a)
        db.flush()
        auth.write_event(
            db,
            a,
            event_type="create",
            from_status="",
            to_status=status,
            operator_id=user_id,
            operator_name=a.user_name,
            reason="测试数据",
            effective_at=effective_at,
        )
        db.commit()
        return a.id
    finally:
        db.close()


def _events(aid: int) -> list[dict]:
    db = SessionLocal()
    try:
        return auth.timeline(db, aid)
    finally:
        db.close()


def _new_user(client, admin_headers, role_code: str = "biz_user") -> tuple[str, dict]:
    """建一个只有菜单权限、**没有任何业务授权**的账号（用于验证拦截）。"""
    db = SessionLocal()
    try:
        role = db.scalar(select(Role).where(Role.code == role_code, Role.deleted == 0))
        role_id = role.id
    finally:
        db.close()
    username = f"u{uuid.uuid4().hex[:10]}"
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "password": "Test@123456",
            "name": f"未授权用户_{username}",
            "status": "enabled",
            "role_ids": [role_id],
        },
    ).json()
    assert r["code"] == 0, r
    from conftest import _login

    return username, _login(client, username, "Test@123456")


def _user_id_of(headers: dict) -> int:
    """从 Bearer token 解出用户 id。"""
    from app.core.security import decode_token

    payload = decode_token(headers["Authorization"].split(" ", 1)[1], "access")
    return int(payload["sub"])


# ---------------- 状态机 ----------------


def test_authorization_state_machine_full_path():
    uid = _fresh_user()
    aid = _make_auth(uid, "test_item", status="draft")
    db = SessionLocal()
    try:
        a = db.get(HrAuthorization, aid)
        assert a.status == "draft"
        auth.transition(db, a, "confirmed", event_type="approve", operator_id=uid, reason="审批通过")
        auth.transition(db, a, "active", event_type="activate", operator_id=uid, reason="授权生效")
        assert a.status == "active" and a.activated_at
        auth.transition(db, a, "suspended", event_type="suspend", operator_id=uid, reason="人员离岗暂离")
        assert a.status == "suspended"
        auth.transition(db, a, "active", event_type="resume", operator_id=uid, reason="返岗恢复")
        assert a.status == "active"
        auth.transition(db, a, "revoked", event_type="revoke", operator_id=uid, reason="资格取消")
        assert a.status == "revoked"
        db.commit()
    finally:
        db.close()

    evs = _events(aid)
    types = [e["eventType"] for e in evs]
    assert {"approve", "activate", "suspend", "revoke"} <= set(types)
    # 倒序返回，最新在前
    assert evs[0]["eventType"] == "revoke"
    assert evs[0]["fromStatus"] == "active" and evs[0]["toStatus"] == "revoked"


def test_illegal_transition_rejected():
    uid = _fresh_user()
    aid = _make_auth(uid, "test_item", status="draft")
    db = SessionLocal()
    try:
        a = db.get(HrAuthorization, aid)
        # draft 不能直接跳到 active
        with pytest.raises(BizException) as e:
            auth.transition(db, a, "active", event_type="activate", operator_id=uid, reason="x")
        assert e.value.code == 63005
        # 已撤销是终态
        a.status = "revoked"
        db.flush()
        with pytest.raises(BizException) as e:
            auth.transition(db, a, "active", event_type="resume", operator_id=uid, reason="x")
        assert e.value.code == 63005
        db.rollback()
    finally:
        db.close()


def test_suspend_and_revoke_require_reason():
    uid = _fresh_user()
    aid = _make_auth(uid, "test_item", status="active")
    db = SessionLocal()
    try:
        a = db.get(HrAuthorization, aid)
        with pytest.raises(BizException) as e:
            auth.transition(db, a, "suspended", event_type="suspend", operator_id=uid, reason="   ")
        assert e.value.code == 63005
        with pytest.raises(BizException) as e:
            auth.transition(db, a, "revoked", event_type="revoke", operator_id=uid, reason="")
        assert e.value.code == 63005
        db.rollback()
    finally:
        db.close()


def test_event_table_is_append_only():
    """变更轨迹表没有 deleted / version 列（只追加）。"""
    cols = set(HrAuthorizationEvent.__table__.columns.keys())
    assert "deleted" not in cols and "version" not in cols
    assert "update_time" not in cols and "update_by" not in cols
    assert {"id", "create_time", "authorization_id", "event_type", "to_status"} <= cols


def test_state_at_replays_history():
    uid = _fresh_user()
    aid = _make_auth(uid, "test_item", status="draft")
    db = SessionLocal()
    try:
        a = db.get(HrAuthorization, aid)
        base = datetime(2026, 1, 1, 10, 0, 0)
        for etype, frm, to, at in (
            ("approve", "draft", "confirmed", base),
            ("activate", "confirmed", "active", base + timedelta(seconds=10)),
            ("suspend", "active", "suspended", base + timedelta(seconds=20)),
        ):
            auth.write_event(
                db,
                a,
                event_type=etype,
                from_status=frm,
                to_status=to,
                operator_id=uid,
                reason=etype,
                effective_at=at,
            )
        db.commit()

        assert auth.state_at(db, aid, base)["status"] == "confirmed"
        assert auth.state_at(db, aid, base)["effective"] is False
        assert auth.state_at(db, aid, base + timedelta(seconds=10))["status"] == "active"
        assert auth.state_at(db, aid, base + timedelta(seconds=10))["effective"] is True
        assert auth.state_at(db, aid, base + timedelta(seconds=20))["status"] == "suspended"
        assert auth.state_at(db, aid, base + timedelta(seconds=20))["effective"] is False
        # 事件发生之前 → 无状态
        assert auth.state_at(db, aid, base - timedelta(seconds=1))["status"] == ""
    finally:
        db.close()


# ---------------- 校验 ----------------


def test_check_authorization_hit_miss_expired_scope():
    uid = _fresh_user()
    now = datetime.now().replace(microsecond=0)
    _make_auth(uid, "test_item", "", scope_method="GB/T 1000")
    _make_auth(uid, "device", "", scope_device_id=42)
    _make_auth(
        uid,
        "report_role",
        "preparer",
        valid_from=now - timedelta(days=10),
        valid_to=now - timedelta(days=1),  # 已过期
    )

    db = SessionLocal()
    try:
        # 方法维度命中
        assert auth.check_authorization(db, user_id=uid, auth_type="test_item", method="GB/T 1000").allowed
        # 方法维度不符
        miss = auth.check_authorization(db, user_id=uid, auth_type="test_item", method="GB/T 2000")
        assert not miss.allowed
        # 设备维度命中 / 不符
        assert auth.check_authorization(db, user_id=uid, auth_type="device", device_id=42).allowed
        assert not auth.check_authorization(db, user_id=uid, auth_type="device", device_id=43).allowed
        # 角色不符
        bad_role = auth.check_authorization(
            db, user_id=uid, auth_type="report_role", role_code="approver", method=None
        )
        assert not bad_role.allowed
        # 有效期已过
        expired = auth.check_authorization(
            db, user_id=uid, auth_type="report_role", role_code="preparer", method=None
        )
        assert not expired.allowed and "有效期" in expired.reason
        # 完全没授权的类型
        assert not auth.check_authorization(db, user_id=uid, auth_type="signer", method=None).allowed
    finally:
        db.close()


def test_check_authorization_multiple_methods_and_roles():
    """任务含多个依据标准时，任一命中即放行；角色多选同理。"""
    uid = _fresh_user()
    _make_auth(uid, "test_item", "", scope_method="GB/T 1000")
    _make_auth(uid, "report_role", "signer")
    db = SessionLocal()
    try:
        assert auth.check_authorization(
            db, user_id=uid, auth_type="test_item", methods=["GB/T 2000", "GB/T 1000"]
        ).allowed
        assert not auth.check_authorization(
            db, user_id=uid, auth_type="test_item", methods=["GB/T 2000", "GB/T 3000"]
        ).allowed
        # 多角色任一满足
        assert auth.check_authorization(
            db, user_id=uid, auth_type="report_role", role_codes=("approver", "signer"), method=None
        ).allowed
        assert not auth.check_authorization(
            db, user_id=uid, auth_type="report_role", role_codes=("approver", "reviewer"), method=None
        ).allowed
    finally:
        db.close()


def test_super_bypasses_authorization_check():
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.username == "admin", User.deleted == 0))
        res = auth.assert_authorized(
            db, admin, auth_type="report_role", role_code="approver", method="GB/T 1"
        )
        assert res.allowed and res.bypassed
    finally:
        db.close()


def test_enforce_switch_disables_interception():
    """强制开关关闭 → 不拦截（机制可运行时下线，不必回滚代码）。"""
    from app.modules.settings.service import set_value

    db = SessionLocal()
    try:
        set_value(db, "auth.enforce.report", "0")
        db.commit()
        u = db.scalar(select(User).where(User.username == "leader1", User.deleted == 0))
        res = auth.assert_authorized(db, u, auth_type="report_role", role_code="approver", method=None)
        assert res.allowed and res.bypassed
    finally:
        db.close()
    db = SessionLocal()
    try:
        set_value(db, "auth.enforce.report", "1")
        db.commit()
    finally:
        db.close()


def test_sod_violation():
    db = SessionLocal()
    try:
        with pytest.raises(BizException) as e:
            auth.assert_sod(db, preparer_id=7, reviewer_id=7, approver_id=9)
        assert e.value.code == 63008
        auth.assert_sod(db, preparer_id=1, reviewer_id=2, approver_id=3)
    finally:
        db.close()


# ---------------- 拦截点（HTTP） ----------------


def test_report_flow_requires_preparer_and_signer_authorization(client, admin_headers):
    """无授权不能编制报告；无授权不能签章；补授权后可放行。"""
    from conftest import approve_instance
    from test_report_flow import _act_on_report, _make_task, _upload

    headers = admin_headers
    suf = uuid.uuid4().hex[:8]
    tid, item = _make_task(client, headers, suf)
    item_id = item["id"]

    _, uheaders = _new_user(client, admin_headers)

    # ① 无编制授权 → 拒绝（63007）
    r = _upload(client, uheaders, item_id)
    assert r["code"] == 63007, r

    # ② 给编制授权 → 放行
    _make_auth(_user_id_of(uheaders), "report_role", "preparer")
    r = _upload(client, uheaders, item_id)
    assert r["code"] == 0, r
    rid = r["data"]["id"]

    # ③ 签批通过 → 用章审批通过
    assert client.post(f"/api/v1/report/reports/{rid}/submit", headers=headers, json={}).json()["code"] == 0
    _act_on_report("approve", rid)
    assert client.post(f"/api/v1/report/reports/{rid}/seal-apply", headers=headers, json={}).json()["code"] == 0
    approve_instance("report_seal", rid, times=2)

    # ④ 无用章授权 → 拒绝（63007）
    r = client.post(f"/api/v1/report/reports/{rid}/seal", headers=uheaders, json={}).json()
    assert r["code"] == 63007, r

    # ⑤ 补签字授权 → 放行
    _make_auth(_user_id_of(uheaders), "report_role", "signer")
    r = client.post(f"/api/v1/report/reports/{rid}/seal", headers=uheaders, json={}).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "sealed"
    # 签章后锁定
    assert client.post(f"/api/v1/report/reports/{rid}/seal", headers=uheaders, json={}).json()["code"] == 61002


def test_progress_recording_requires_test_item_authorization(client, admin_headers):
    """无 test_item 授权不能录入检测进度。"""
    from test_report_flow import _make_task

    suf = uuid.uuid4().hex[:8]
    tid, _item = _make_task(client, admin_headers, suf, need_report=0)
    _, uheaders = _new_user(client, admin_headers)

    body = {"percent": 50, "note": "进度"}
    r = client.post(f"/api/v1/task/tasks/{tid}/progress", headers=uheaders, json=body).json()
    assert r["code"] == 63007, r

    _make_auth(_user_id_of(uheaders), "test_item")
    r = client.post(f"/api/v1/task/tasks/{tid}/progress", headers=uheaders, json=body).json()
    assert r["code"] == 0, r


def test_assignment_requires_test_item_authorization(client, admin_headers):
    """派工给无 test_item 授权的人 → 拒绝。"""
    from test_report_flow import _make_task

    suf = uuid.uuid4().hex[:8]
    tid, _item = _make_task(client, admin_headers, suf, need_report=0)
    _, uheaders = _new_user(client, admin_headers)
    uid = _user_id_of(uheaders)

    body = {"dimension": "person", "resource_id": uid, "resource_name": "未授权检测员"}
    r = client.post(f"/api/v1/task/tasks/{tid}/assignments", headers=admin_headers, json=body).json()
    assert r["code"] == 63007, r

    _make_auth(uid, "test_item")
    r = client.post(f"/api/v1/task/tasks/{tid}/assignments", headers=admin_headers, json=body).json()
    assert r["code"] == 0, r


# ---------------- 审批联动 + 台账接口 ----------------


def test_authorization_approval_flow_and_api(client, admin_headers):
    """授权须经审批确认后方可生效（不允许人工直通）；通过后 confirmed + 写变更轨迹。"""
    from conftest import approve_instance

    uid = _user_id("leader1")
    body = {
        "user_id": uid,
        "auth_type": "test_item",
        "role_code": "",
        "scope_method": "GB/T 3000",
        "valid_from": "2026-01-01T00:00:00",
        "remark": f"C3 用例_{uuid.uuid4().hex[:8]}",
    }
    r = client.post("/api/v1/hr/authorizations", headers=admin_headers, json=body).json()
    assert r["code"] == 0, r
    aid = r["data"]["id"]
    assert r["data"]["status"] == "draft" and r["data"]["authNo"].startswith("AU")

    r = client.post(f"/api/v1/hr/authorizations/{aid}/submit", headers=admin_headers, json={}).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "approving"

    # 两级审批（技术负责人 → 质量负责人）
    approve_instance("hr_authorization", aid, times=2)
    detail = client.get(f"/api/v1/hr/authorizations/{aid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "confirmed", detail
    assert detail["approverName"], detail

    # 生效 → active
    r = client.post(f"/api/v1/hr/authorizations/{aid}/activate", headers=admin_headers, json={}).json()
    assert r["code"] == 0 and r["data"]["status"] == "active"

    # 变更轨迹可查
    tl = client.get(f"/api/v1/hr/authorizations/{aid}/timeline", headers=admin_headers).json()["data"]
    types = [e["eventType"] for e in tl["items"]]
    assert {"create", "submit", "approve", "activate"} <= set(types)

    # 时点回放接口
    st = client.get(
        f"/api/v1/hr/authorizations/{aid}/state-at",
        headers=admin_headers,
        params={"at": "2030-01-01T00:00:00"},
    ).json()["data"]
    assert st["status"] == "active" and st["effective"] is True

    # 计数（all 存在且含本条）
    counts = client.get("/api/v1/hr/authorizations/counts", headers=admin_headers).json()["data"]
    assert "all" in counts and counts["all"] >= 1

    # 列表 + 导出
    lst = client.get(
        "/api/v1/hr/authorizations", headers=admin_headers, params={"q": body["remark"]}
    ).json()["data"]
    assert lst["total"] == 1 and lst["items"][0]["id"] == aid
    resp = client.get("/api/v1/hr/authorizations/export", headers=admin_headers)
    assert resp.status_code == 200


def test_authorization_api_state_guards(client, admin_headers):
    """非法状态跃迁 / 缺原因 → 接口层也拦得住。"""
    uid = _user_id("leader1")
    r = client.post(
        "/api/v1/hr/authorizations",
        headers=admin_headers,
        json={"user_id": uid, "auth_type": "test_item", "remark": f"守卫_{uuid.uuid4().hex[:8]}"},
    ).json()
    assert r["code"] == 0
    aid = r["data"]["id"]
    # 草稿不能直接激活
    act = client.post(f"/api/v1/hr/authorizations/{aid}/activate", headers=admin_headers, json={}).json()
    assert act["code"] == 63005
    # 撤销缺原因
    rev = client.post(f"/api/v1/hr/authorizations/{aid}/revoke", headers=admin_headers, json={}).json()
    assert rev["code"] == 63005
    # 不存在的授权
    assert client.get("/api/v1/hr/authorizations/99999999", headers=admin_headers).json()["code"] == 63006

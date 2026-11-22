"""F6 门户访客预约闭环（HTTP 黑盒）。

链路：门户注册 → 内部审核（绑定往来单位 + 开通 visit 权限范围）→ 门户登录
→ 提交来访申请（指定被访人）→ 通用审批引擎按**表单变量**把待办派给被访人
→ 被访人审批通过 → 自动下发通行凭证 → 门户拿二维码 → 扫码签到 → 签离。

同时覆盖：驳回路径、跨账号隔离、无 visit 权限范围被拒、域内人工直通被拦截（70005）。
"""

import uuid
from datetime import datetime, timedelta

UUID = uuid.uuid4().hex[:8]


def _mk_customer(client, headers, tag="F6访客") -> int:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": f"{tag}客户_{suf}", "tax_no": f"913401F6{suf}", "status": "enabled"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _mk_zone(client, headers, security_level=1, need_nda=0) -> int:
    """建访客区域（门户可申请的区域）。"""
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/visitor/zones",
        headers=headers,
        json={
            "code": f"F6Z{suf}",
            "name": f"F6区域_{suf}",
            "zone_type": "public",
            "security_level": security_level,
            "need_nda": need_nda,
            "status": "enabled",
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _host_id(username="manager1") -> int:
    from app.core.db import SessionLocal
    from app.modules.auth.models import User

    db = SessionLocal()
    try:
        u = db.scalar(select_one(User, username))
        assert u, f"找不到用户 {username}"
        return u.id
    finally:
        db.close()


def select_one(model, username):
    from sqlalchemy import select

    return select(model).where(model.username == username, model.deleted == 0)


def _portal_account(client, admin_headers, *, scopes="entrust,staff,visit") -> tuple[str, dict]:
    """注册 + 内部审核（绑定往来单位），返回 (username, headers)。"""
    suf = uuid.uuid4().hex[:8]
    username = f"f6visit_{suf}"
    r = client.post(
        "/api/v1/portal/auth/register",
        json={
            "username": username,
            "password": "Portal@123456",
            "company_name": f"F6访客公司_{suf}",
            "contact_name": "访客联系人",
            "phone": "13900000001",
            "company_type": "customer",
        },
    ).json()
    assert r["code"] == 0, r
    cid = _mk_customer(client, admin_headers)
    accs = client.get("/api/v1/crm/accounts", headers=admin_headers, params={"q": username}).json()
    acc = [i for i in accs["data"]["items"] if i["username"] == username]
    assert acc, accs
    rev = client.post(
        f"/api/v1/crm/accounts/{acc[0]['id']}/review",
        headers=admin_headers,
        json={
            "action": "approve",
            "comment": "F6 访客预约",
            "customer_id": cid,
            "perm_scope": scopes,
            "staff_limit": 3,
        },
    ).json()
    assert rev["code"] == 0, rev
    login = client.post(
        "/api/v1/portal/auth/login", json={"username": username, "password": "Portal@123456"}
    ).json()
    assert login["code"] == 0, login
    return username, {"Authorization": f"Bearer {login['data']['access_token']}"}


def _submit_visit(client, headers, host_user_id: int, zone_ids: list[int], **kw):
    now = datetime.now()
    payload = {
        "visitor_name": kw.get("visitor_name", f"访客_{UUID}"),
        "visitor_company": kw.get("visitor_company", "F6访客公司"),
        "id_no": kw.get("id_no", ""),
        "phone": kw.get("phone", "13900000002"),
        "host_user_id": host_user_id,
        "zone_ids": zone_ids,
        "purpose": kw.get("purpose", "项目对接"),
        "plan_start": (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "plan_end": (now + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"),
        "nda_signed": kw.get("nda_signed", False),
    }
    return client.post("/api/v1/portal/visits", headers=headers, json=payload).json()


def _visit_row(visit_id: int):
    from app.core.db import SessionLocal
    from app.modules.visitor.models import VisitorVisit

    db = SessionLocal()
    try:
        return db.get(VisitorVisit, visit_id)
    finally:
        db.close()


def _approve_visit_task(visit_id: int, action="approve", comment="同意"):
    """推进访客单的审批待办（被访人节点）。"""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.approval import service as approval
    from app.modules.approval.models import ApprovalInstance, ApprovalTask
    from app.modules.auth.models import User

    db = SessionLocal()
    try:
        target = None
        for t in db.scalars(
            select(ApprovalTask).where(ApprovalTask.status == "pending", ApprovalTask.deleted == 0)
        ).all():
            inst = db.get(ApprovalInstance, t.instance_id)
            if inst and inst.biz_type == "visitor_visit" and inst.biz_id == visit_id:
                target = t
                break
        assert target, f"访客单 {visit_id} 没有待办"
        user = db.get(User, target.assignee_id)
        if action == "approve":
            approval.approve(db, target.id, user, comment)
        else:
            approval.reject(db, target.id, user, comment)
        db.commit()
        return target.assignee_id
    finally:
        db.close()


# ---------------- 公开选项 ----------------


def test_portal_hosts_and_zones_are_public(client, admin_headers):
    """被访人候选与可申请区域免登录可读，且不暴露手机号/邮箱。"""
    zone_id = _mk_zone(client, admin_headers)
    r = client.get("/api/v1/portal/hosts").json()
    assert r["code"] == 0, r
    assert r["data"]["items"], r
    for item in r["data"]["items"]:
        assert "mobile" not in item and "email" not in item

    z = client.get("/api/v1/portal/zones").json()
    assert z["code"] == 0, z
    ids = [i["id"] for i in z["data"]["items"]]
    assert zone_id in ids, z


# ---------------- 提交预约 → 审批 ----------------


def test_portal_visit_submit_creates_flow_and_todo(client, admin_headers):
    """提交预约 → 访客单进入审批中 → 待办派给**被访人本人**（FORM_USER 变量解析）。"""
    zone_id = _mk_zone(client, admin_headers)
    host_id = _host_id("manager1")
    _username, headers = _portal_account(client, admin_headers)

    r = _submit_visit(client, headers, host_id, [zone_id])
    assert r["code"] == 0, r
    data = r["data"]
    assert data["status"] == "approving", data
    assert data["flowInstanceId"], data

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.approval.models import ApprovalTask

    db = SessionLocal()
    try:
        tasks = db.scalars(
            select(ApprovalTask).where(ApprovalTask.status == "pending", ApprovalTask.deleted == 0)
        ).all()
        mine = [t for t in tasks if t.instance_id == data["flowInstanceId"]]
        assert mine, "没有产生待办"
        assert mine[0].assignee_id == host_id, mine[0].assignee_name
        assert mine[0].node_name == "被访人审批", mine[0].node_name
    finally:
        db.close()


def test_portal_visit_approve_issues_credential_and_checkin(client, admin_headers):
    """审批通过 → 自动下发凭证 → 门户取二维码 → 签到 → 签离。"""
    zone_id = _mk_zone(client, admin_headers)
    host_id = _host_id("manager1")
    _username, headers = _portal_account(client, admin_headers)
    r = _submit_visit(client, headers, host_id, [zone_id])
    assert r["code"] == 0, r
    visit_id = r["data"]["id"]

    _approve_visit_task(visit_id, "approve", "同意来访")

    detail = client.get(f"/api/v1/portal/visits/{visit_id}", headers=headers).json()
    assert detail["code"] == 0, detail
    assert detail["data"]["status"] == "approved", detail["data"]
    assert detail["data"]["credentialNo"], detail["data"]

    cred = client.get(f"/api/v1/portal/visits/{visit_id}/credential", headers=headers).json()
    assert cred["code"] == 0, cred
    assert cred["data"]["code"], cred

    qr = client.get(f"/api/v1/portal/visits/{visit_id}/credential/qr", headers=headers)
    assert qr.status_code == 200
    assert "svg" in qr.headers["content-type"], qr.headers
    assert b"<svg" in qr.content

    ci = client.post(
        f"/api/v1/portal/visits/{visit_id}/checkin",
        headers=headers,
        json={"method": "qrcode", "device_id": "gate-01"},
    ).json()
    assert ci["code"] == 0, ci
    assert ci["data"]["status"] == "visiting", ci["data"]

    co = client.post(
        f"/api/v1/portal/visits/{visit_id}/checkout",
        headers=headers,
        json={"method": "qrcode", "device_id": "gate-01"},
    ).json()
    assert co["code"] == 0, co
    assert co["data"]["status"] == "left", co["data"]


def test_portal_visit_reject_path(client, admin_headers):
    """被访人驳回 → 访客单 rejected，门户可见结论。"""
    zone_id = _mk_zone(client, admin_headers)
    host_id = _host_id("manager1")
    _username, headers = _portal_account(client, admin_headers)
    r = _submit_visit(client, headers, host_id, [zone_id])
    assert r["code"] == 0, r
    visit_id = r["data"]["id"]

    _approve_visit_task(visit_id, "reject", "非工作日不接待")

    detail = client.get(f"/api/v1/portal/visits/{visit_id}", headers=headers).json()
    assert detail["data"]["status"] == "rejected", detail["data"]


def test_portal_visit_cancel(client, admin_headers):
    """审批中可取消预约。"""
    zone_id = _mk_zone(client, admin_headers)
    host_id = _host_id("manager1")
    _username, headers = _portal_account(client, admin_headers)
    r = _submit_visit(client, headers, host_id, [zone_id])
    visit_id = r["data"]["id"]
    c = client.post(
        f"/api/v1/portal/visits/{visit_id}/cancel", headers=headers, json={"remark": "行程变更"}
    ).json()
    assert c["code"] == 0, c
    assert c["data"]["status"] == "cancelled", c["data"]


# ---------------- 隔离与守卫 ----------------


def test_portal_visit_other_account_is_forbidden(client, admin_headers):
    """别的门户账号看不到也不许访问本账号的访客单。"""
    zone_id = _mk_zone(client, admin_headers)
    host_id = _host_id("manager1")
    _u1, h1 = _portal_account(client, admin_headers)
    _u2, h2 = _portal_account(client, admin_headers)
    r = _submit_visit(client, h1, host_id, [zone_id])
    visit_id = r["data"]["id"]

    got = client.get(f"/api/v1/portal/visits/{visit_id}", headers=h2).json()
    assert got["code"] == 98011, got

    lst = client.get("/api/v1/portal/visits", headers=h2).json()
    assert lst["code"] == 0, lst
    assert all(i["id"] != visit_id for i in lst["data"]["items"]), lst


def test_portal_visit_requires_visit_scope(client, admin_headers):
    """账号未开通 visit 权限范围时，提交预约被拒（96008）。"""
    zone_id = _mk_zone(client, admin_headers)
    host_id = _host_id("manager1")
    _username, headers = _portal_account(client, admin_headers, scopes="entrust,staff")
    r = _submit_visit(client, headers, host_id, [zone_id])
    assert r["code"] == 96008, r


def test_internal_approve_blocked_when_flow_enabled(client, admin_headers):
    """访客单已进流程后，域内人工直通端点被拦截（70005）。"""
    zone_id = _mk_zone(client, admin_headers)
    host_id = _host_id("manager1")
    _username, headers = _portal_account(client, admin_headers)
    r = _submit_visit(client, headers, host_id, [zone_id])
    visit_id = r["data"]["id"]

    blocked = client.post(
        f"/api/v1/visitor/visits/{visit_id}/approve",
        headers=admin_headers,
        json={"level": "host", "action": "approve", "comment": "直接通过"},
    ).json()
    assert blocked["code"] == 70005, blocked


def test_portal_visit_nda_required_zone(client, admin_headers):
    """敏感区域要求先确认保密协议，否则拒绝提交。"""
    zone_id = _mk_zone(client, admin_headers, need_nda=1)
    host_id = _host_id("manager1")
    _username, headers = _portal_account(client, admin_headers)
    r = _submit_visit(client, headers, host_id, [zone_id], nda_signed=False)
    assert r["code"] == 98007, r

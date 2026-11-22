"""F6 门户守卫：两套认证的隔离、权限范围、refresh token 生命周期。

覆盖：
- 门户 token 可达门户自助接口（`/portal/entrusts` `/portal/staff` `/portal/contracts` …），
  且**不能**访问任何内部接口（内部 token 反之亦然）；
- `perm_scope` 逐接口校验（招投标要 `tender`、委托要 `entrust`、人员备案要 `staff`、访客要 `visit`）；
- refresh token 轮换 / 吊销（登出后不可再用）；
- `GET /portal/branding` 公开可读。
"""

import uuid


def _register_and_review(client, admin_headers, *, scopes: str, company_type="customer"):
    """注册门户账号 + 内部审核（绑定往来单位），返回 (access, refresh, headers)。"""
    suf = uuid.uuid4().hex[:8]
    username = f"f6guard_{suf}"
    r = client.post(
        "/api/v1/portal/auth/register",
        json={
            "username": username,
            "password": "Portal@123456",
            "company_name": f"F6守卫公司_{suf}",
            "contact_name": "守卫联系人",
            "phone": "13900000003",
            "company_type": company_type,
        },
    ).json()
    assert r["code"] == 0, r
    cust = client.post(
        "/api/v1/crm/customers",
        headers=admin_headers,
        json={"name": f"F6守卫客户_{suf}", "tax_no": f"913401F6{suf}", "status": "enabled"},
    ).json()
    assert cust["code"] == 0, cust
    accs = client.get("/api/v1/crm/accounts", headers=admin_headers, params={"q": username}).json()
    acc = [i for i in accs["data"]["items"] if i["username"] == username]
    assert acc, accs
    rev = client.post(
        f"/api/v1/crm/accounts/{acc[0]['id']}/review",
        headers=admin_headers,
        json={
            "action": "approve",
            "comment": "F6 守卫",
            "customer_id": cust["data"]["id"],
            "perm_scope": scopes,
            "staff_limit": 3,
        },
    ).json()
    assert rev["code"] == 0, rev
    login = client.post(
        "/api/v1/portal/auth/login", json={"username": username, "password": "Portal@123456"}
    ).json()
    assert login["code"] == 0, login
    d = login["data"]
    return d["access_token"], d["refresh_token"], {"Authorization": f"Bearer {d['access_token']}"}


# ---------------- 认证隔离 ----------------


def test_portal_token_reaches_portal_selfservice(client, admin_headers):
    """门户 token 可达门户自助端点（orders / staff 等）。"""
    _acc, _ref, headers = _register_and_review(
        client, admin_headers, scopes="entrust,staff,visit,tender"
    )
    for path in (
        "/api/v1/portal/entrusts",
        "/api/v1/portal/staff",
        "/api/v1/portal/contracts",
        "/api/v1/portal/registrations",
        "/api/v1/portal/bids",
        "/api/v1/portal/visits",
    ):
        r = client.get(path, headers=headers).json()
        assert r["code"] == 0, (path, r)


def test_portal_token_rejected_on_internal_api(client, admin_headers):
    """门户 token 不能访问内部接口。"""
    _acc, _ref, headers = _register_and_review(client, admin_headers, scopes="entrust,staff")
    for path in ("/api/v1/auth/me", "/api/v1/crm/customers", "/api/v1/visitor/visits"):
        r = client.get(path, headers=headers)
        body = r.json()
        assert body["code"] != 0, (path, body)
        assert r.status_code in (401, 403), (path, r.status_code)


def test_internal_token_rejected_on_portal_api(client, admin_headers):
    """内部 token 不能访问门户接口（两套认证互不通用）。"""
    for path in ("/api/v1/portal/auth/me", "/api/v1/portal/visits", "/api/v1/portal/progress"):
        r = client.get(path, headers=admin_headers)
        body = r.json()
        assert body["code"] != 0, (path, body)
        assert r.status_code in (401, 403), (path, r.status_code)


def test_portal_branding_is_public(client):
    """站点品牌信息公开可读（门户首屏渲染用）。"""
    r = client.get("/api/v1/portal/branding")
    body = r.json()
    assert body["code"] == 0, body
    assert "siteName" in body["data"], body


# ---------------- 权限范围 ----------------


def test_tender_scope_is_required(client, admin_headers):
    """未开通 tender 范围时，招投标的"我的"数据与报名/投标动作被拒（96008）。

    公告**浏览**是公开的（免登录），不受范围限制。
    """
    _acc, _ref, headers = _register_and_review(client, admin_headers, scopes="entrust,staff")
    # 公开公告浏览不受影响
    assert client.get("/api/v1/portal/tenders").json()["code"] == 0
    assert client.get("/api/v1/portal/tenders", headers=headers).json()["code"] == 0
    # 我的报名 / 我的投标 / 报名动作 需要 tender 范围
    assert client.get("/api/v1/portal/registrations", headers=headers).json()["code"] == 96008
    assert client.get("/api/v1/portal/bids", headers=headers).json()["code"] == 96008
    reg = client.post("/api/v1/portal/tenders/1/register", headers=headers)
    assert reg.json()["code"] == 96008, reg.json()


def test_staff_scope_is_required(client, admin_headers):
    """未开通 staff 范围时，人员备案接口被拒（96008）。"""
    _acc, _ref, headers = _register_and_review(client, admin_headers, scopes="entrust,tender")
    r = client.get("/api/v1/portal/staff", headers=headers).json()
    assert r["code"] == 96008, r


def test_entrust_scope_is_required(client, admin_headers):
    """未开通 entrust 范围时，在线委托接口被拒（96008）。"""
    _acc, _ref, headers = _register_and_review(client, admin_headers, scopes="staff,tender")
    r = client.get("/api/v1/portal/entrusts", headers=headers).json()
    assert r["code"] == 96008, r


# ---------------- refresh token 生命周期 ----------------


def test_portal_refresh_rotates_and_logout_revokes(client, admin_headers):
    """refresh token 可轮换；旧码不可复用；登出后全部失效。"""
    access, refresh, headers = _register_and_review(client, admin_headers, scopes="entrust,staff")

    refreshed = client.post("/api/v1/portal/auth/refresh", json={"refresh_token": refresh}).json()
    assert refreshed["code"] == 0, refreshed
    new_access = refreshed["data"]["access_token"]
    new_refresh = refreshed["data"]["refresh_token"]
    assert new_access and new_refresh
    assert new_refresh != refresh

    # 新 access 可用
    me = client.get("/api/v1/portal/auth/me", headers={"Authorization": f"Bearer {new_access}"}).json()
    assert me["code"] == 0, me

    # 旧 refresh 已作废（轮换）
    reuse = client.post("/api/v1/portal/auth/refresh", json={"refresh_token": refresh}).json()
    assert reuse["code"] == 20001, reuse

    # 登出 → refresh 吊销
    out = client.post("/api/v1/portal/auth/logout", headers={"Authorization": f"Bearer {new_access}"})
    assert out.status_code == 200, out
    after = client.post("/api/v1/portal/auth/refresh", json={"refresh_token": new_refresh}).json()
    assert after["code"] == 20001, after


def test_portal_refresh_rejects_garbage(client):
    """非法 refresh token 直接 401。"""
    r = client.post("/api/v1/portal/auth/refresh", json={"refresh_token": "not-a-token"})
    body = r.json()
    assert body["code"] == 20001, body


# ---------------- 账号自助 ----------------


def test_portal_account_update_and_password(client, admin_headers):
    """合作方可自助维护联系方式与改密；不能改往来单位绑定。"""
    _acc, _ref, headers = _register_and_review(client, admin_headers, scopes="entrust,staff")

    upd = client.put(
        "/api/v1/portal/account",
        headers=headers,
        json={"company_name": "F6更名公司", "contact_name": "新联系人", "phone": "13900000009"},
    ).json()
    assert upd["code"] == 0, upd
    assert upd["data"]["companyName"] == "F6更名公司", upd
    assert upd["data"]["contactName"] == "新联系人", upd

    # 改密
    wrong = client.post(
        "/api/v1/portal/account/password",
        headers=headers,
        json={"old_password": "wrong-pass", "new_password": "Portal@1234567"},
    ).json()
    assert wrong["code"] != 0, wrong

    ok = client.post(
        "/api/v1/portal/account/password",
        headers=headers,
        json={"old_password": "Portal@123456", "new_password": "Portal@1234567"},
    ).json()
    assert ok["code"] == 0, ok

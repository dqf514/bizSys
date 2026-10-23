"""批次5：测试反馈整改——分页上限 / 合同金额与日期校验 / 角色枚举 / menus/tree 权限 / 选人端点。"""

import uuid

UUID = uuid.uuid4().hex[:8]


def _login(client, username: str, password: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    data = r.json()
    assert data["code"] == 0, data
    return {"Authorization": f"Bearer {data['data']['access_token']}"}


def _create_user(client, admin_headers, role_ids: list[int]) -> dict:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": f"b5_{suf}", "password": "Test@123456", "name": "批次5", "status": "enabled",
              "role_ids": role_ids},
    ).json()
    assert r["code"] == 0, r
    return _login(client, f"b5_{suf}", "Test@123456")


# ---------------- 分页上限 ----------------


def test_page_overflow_rejected(client, admin_headers):
    """page 超出上限（原 OFFSET bigint 溢出 500）→ 422 + 10001，不再 500。"""
    for path in ("/api/v1/admin/users", "/api/v1/task/tasks", "/api/v1/contract/contracts"):
        r = client.get(path, headers=admin_headers, params={"page": 10**19, "size": 20})
        assert r.status_code == 422, (path, r.status_code, r.text[:200])
        assert r.json()["code"] == 10001, (path, r.json())
    # 边界值 10**9 仍合法
    r = client.get("/api/v1/admin/users", headers=admin_headers, params={"page": 10**9, "size": 1})
    assert r.json()["code"] == 0, r.json()


# ---------------- 合同金额 / 日期校验 ----------------


def _customer_id(client, admin_headers) -> int:
    r = client.post(
        "/api/v1/crm/customers",
        headers=admin_headers,
        json={"name": f"批次5客户_{UUID}"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def test_contract_amount_validation(client, admin_headers):
    """合同金额必须为正且不超过 Numeric(14,2) 上限。"""
    cid = _customer_id(client, admin_headers)
    base = {"name": f"金额校验_{UUID}", "customerId": cid}
    for bad in (-5, 0, 1e13):
        r = client.post("/api/v1/contract/contracts", headers=admin_headers, json={**base, "amount": bad})
        assert r.status_code == 422, (bad, r.status_code, r.text[:200])
        assert r.json()["code"] == 10001, r.json()
    r = client.post("/api/v1/contract/contracts", headers=admin_headers, json={**base, "amount": 100.5})
    assert r.json()["code"] == 0, r.json()


def test_contract_date_range(client, admin_headers):
    """结束日期早于开始日期 → 422 + 中文提示。"""
    cid = _customer_id(client, admin_headers)
    r = client.post(
        "/api/v1/contract/contracts",
        headers=admin_headers,
        json={"name": f"日期校验_{UUID}", "customerId": cid, "startDate": "2026-03-01", "endDate": "2026-01-01"},
    )
    assert r.status_code == 422, (r.status_code, r.text[:200])
    body = r.json()
    assert body["code"] == 10001 and "结束日期" in body["message"], body


# ---------------- 角色枚举校验 ----------------


def test_role_enum_validation(client, admin_headers):
    """RoleIn 的 dataScope/status 只允许已知枚举值。"""
    base = {"code": f"b5role_{UUID}", "name": f"批次5角色_{UUID}"}
    for patch in ({"dataScope": "bogus"}, {"status": "bogus"}):
        r = client.post("/api/v1/admin/roles", headers=admin_headers, json={**base, **patch})
        assert r.status_code == 422, (patch, r.status_code, r.text[:200])
        assert r.json()["code"] == 10001, r.json()


# ---------------- menus/tree 权限 ----------------


def _flatten(tree):
    for node in tree:
        yield node
        yield from _flatten(node.get("children") or [])


def test_menus_tree_permission(client, admin_headers):
    """menus/tree 任一相关权限可读：无权限 403；仅 admin:role:edit（角色授权弹窗共用）也可 200。"""
    no_perm = _create_user(client, admin_headers, [])
    r = client.get("/api/v1/admin/menus/tree", headers=no_perm)
    assert r.status_code == 403, (r.status_code, r.text[:200])

    tree = client.get(
        "/api/v1/admin/menus/tree", headers=admin_headers, params={"include_buttons": True}
    ).json()["data"]
    role_menu = next(m for m in _flatten(tree) if m.get("permission") == "admin:role:edit")
    r = client.post(
        "/api/v1/admin/roles",
        headers=admin_headers,
        json={"code": f"b5tree_{UUID}", "name": f"仅角色编辑_{UUID}"},
    ).json()
    assert r["code"] == 0, r
    role_id = r["data"]["id"]
    r = client.put(f"/api/v1/admin/roles/{role_id}/menus", headers=admin_headers, json={"menuIds": [role_menu["id"]]})
    assert r.json()["code"] == 0, r.json()
    role_only = _create_user(client, admin_headers, [role_id])
    r = client.get("/api/v1/admin/menus/tree", headers=role_only)
    assert r.json()["code"] == 0, r.json()


# ---------------- 选人端点 ----------------


def test_user_options_login_only(client, admin_headers):
    """users/options 登录即可读（转办/加签/通知选人），返回轻量 id/label/sub。"""
    headers = _create_user(client, admin_headers, [])
    r = client.get("/api/v1/admin/users/options", headers=headers, params={"limit": 5})
    assert r.status_code == 200 and r.json()["code"] == 0, r.text[:200]
    items = r.json()["data"]
    assert items and set(items[0].keys()) == {"id", "label", "sub"}, items
    # limit 上限 100
    r = client.get("/api/v1/admin/users/options", headers=headers, params={"limit": 101})
    assert r.status_code == 422, r.status_code

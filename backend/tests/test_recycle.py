"""全站统一回收站（B11）：删除登记 → 恢复 → 保留期内禁止彻底删除。

覆盖：
- 删除任意业务记录后进入 `sys_recycle_bin`（按模块 / 关键词可查）
- 恢复：数据回到未删除状态，唯一键被改名的记录恢复原名
- 保留期设置（sys_config `recycle.retention_days`）
- 保留期内「彻底删除」一律拒绝（30006）；到期后允许
"""

import uuid
from datetime import datetime, timedelta

import pytest

SUF = uuid.uuid4().hex[:8]


def _make_customer(client, headers, name: str) -> int:
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": name, "level": "A"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _bin_entry(client, headers, module: str, keyword: str) -> dict:
    lst = client.get(
        "/api/v1/admin/recycle",
        headers=headers,
        params={"module": module, "q": keyword, "size": 50},
    ).json()["data"]["items"]
    assert lst, f"回收站未找到条目：{module}/{keyword}"
    return lst[0]


# ---------------- 保留期设置 ----------------


def test_recycle_retention_setting(client, admin_headers):
    r = client.get("/api/v1/admin/recycle/settings", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["retentionDays"] == 180  # 默认 180 天

    r = client.put("/api/v1/admin/recycle/settings", headers=admin_headers, json={"retentionDays": 90}).json()
    assert r["code"] == 0, r
    assert r["data"]["retentionDays"] == 90

    # 还原
    client.put("/api/v1/admin/recycle/settings", headers=admin_headers, json={"retentionDays": 180})


def test_recycle_modules_list(client, admin_headers):
    name = f"回收站模块客户_{SUF}"
    cid = _make_customer(client, admin_headers, name)
    client.delete(f"/api/v1/crm/customers/{cid}", headers=admin_headers)

    r = client.get("/api/v1/admin/recycle/modules", headers=admin_headers).json()
    assert r["code"] == 0, r
    modules = {m["module"]: m["count"] for m in r["data"]["items"]}
    assert "crm" in modules and modules["crm"] >= 1


# ---------------- 删除 → 登记 → 恢复 ----------------


def test_delete_then_restore_customer(client, admin_headers):
    name = f"待恢复客户_{SUF}"
    cid = _make_customer(client, admin_headers, name)

    r = client.delete(f"/api/v1/crm/customers/{cid}", headers=admin_headers).json()
    assert r["code"] == 0, r

    entry = _bin_entry(client, admin_headers, "crm", name)
    assert entry["resourceId"] == cid
    assert entry["status"] == "recycled"
    assert entry["deletedByName"]
    assert entry["purgeAfter"] > entry["deletedAt"]

    # 恢复
    r = client.post(f"/api/v1/admin/recycle/{entry['id']}/restore", headers=admin_headers).json()
    assert r["code"] == 0, r

    lst = client.get(
        "/api/v1/crm/customers", headers=admin_headers, params={"q": name}
    ).json()["data"]["items"]
    assert any(c["id"] == cid for c in lst)


def test_restore_reverts_renamed_unique_key(client, admin_headers):
    """删用户时用户名被改成 `#del{id}` 让位，恢复后应还原原用户名。"""
    username = f"tmpuser_{SUF}"
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "name": f"临时用户_{SUF}",
            "password": "Test@123456",
            "roleIds": [],
            "status": "enabled",
        },
    ).json()
    assert r["code"] == 0, r
    uid = r["data"]["id"]

    r = client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers).json()
    assert r["code"] == 0, r

    entry = _bin_entry(client, admin_headers, "admin", f"临时用户_{SUF}")
    r = client.post(f"/api/v1/admin/recycle/{entry['id']}/restore", headers=admin_headers).json()
    assert r["code"] == 0, r

    lst = client.get("/api/v1/admin/users", headers=admin_headers, params={"q": username}).json()["data"][
        "items"
    ]
    user = next(u for u in lst if u["id"] == uid)
    assert user["username"] == username


# ---------------- 彻底删除的保留期闸门 ----------------


def test_purge_blocked_inside_retention_window(client, admin_headers):
    name = f"保留期内客户_{SUF}"
    cid = _make_customer(client, admin_headers, name)
    client.delete(f"/api/v1/crm/customers/{cid}", headers=admin_headers)
    entry = _bin_entry(client, admin_headers, "crm", name)

    r = client.post(f"/api/v1/admin/recycle/{entry['id']}/purge", headers=admin_headers).json()
    assert r["code"] != 0
    assert r["code"] == 30006  # RECYCLE_RETENTION_ACTIVE


def test_purge_allowed_after_retention_window(client, admin_headers, db):
    from app.modules.recycle.models import RecycleBin

    name = f"到期客户_{SUF}"
    cid = _make_customer(client, admin_headers, name)
    client.delete(f"/api/v1/crm/customers/{cid}", headers=admin_headers)
    entry = _bin_entry(client, admin_headers, "crm", name)

    # 把到期时间往前挪（模拟保留期已过）
    row = db.get(RecycleBin, entry["id"])
    row.purge_after = datetime.now() - timedelta(days=1)
    db.commit()

    r = client.post(f"/api/v1/admin/recycle/{entry['id']}/purge", headers=admin_headers).json()
    assert r["code"] == 0, r

    # 记录已真正删除
    lst = client.get("/api/v1/crm/customers", headers=admin_headers, params={"q": name}).json()["data"]["items"]
    assert all(c["id"] != cid for c in lst)


def test_purge_unknown_entry(client, admin_headers):
    r = client.post("/api/v1/admin/recycle/99999999/purge", headers=admin_headers).json()
    assert r["code"] != 0
    assert r["code"] == 30007  # RECYCLE_ENTRY_NOT_FOUND


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

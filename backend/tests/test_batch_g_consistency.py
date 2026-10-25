"""批次G 全站一致性：状态页签 counts 端点 + 检索 q 补齐（approval/oa）。"""

import uuid

BASE_OA = "/api/v1/oa"


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _check_counts(client, headers, list_url, counts_url, keys):
    """counts 与列表 total 一致：all = 各状态之和 = 列表 size=1 的 total。"""
    c = client.get(counts_url, headers=headers).json()
    assert c["code"] == 0, (counts_url, c)
    data = c["data"]
    for k in keys:
        assert k in data, (counts_url, k, data)
    assert data["all"] == sum(v for k, v in data.items() if k != "all")
    lst = client.get(list_url, params={"page": 1, "size": 1}, headers=headers).json()
    assert lst["code"] == 0, (list_url, lst)
    assert data["all"] == lst["data"]["total"], (counts_url, data, lst["data"]["total"])


def test_counts_endpoints(client, admin_headers):
    _check_counts(
        client, admin_headers, "/api/v1/crm/customers", "/api/v1/crm/customers/counts", ["enabled", "disabled"]
    )
    _check_counts(
        client, admin_headers, "/api/v1/contract/contracts", "/api/v1/contract/contracts/counts",
        ["draft", "approving", "approved", "rejected", "voided"],
    )
    _check_counts(
        client, admin_headers, "/api/v1/finance/settlements", "/api/v1/finance/settlements/counts",
        ["approving", "pending", "invoicing", "invoiced", "paid", "rejected"],
    )
    _check_counts(
        client, admin_headers, "/api/v1/finance/invoices", "/api/v1/finance/invoices/counts", ["approving", "issued"]
    )
    _check_counts(
        client, admin_headers, "/api/v1/report/reports", "/api/v1/report/reports/counts",
        ["uploaded", "approving", "approved", "rejected", "sealed"],
    )
    _check_counts(client, admin_headers, "/api/v1/admin/users", "/api/v1/admin/users/counts", ["enabled", "disabled"])
    _check_counts(
        client, admin_headers, f"{BASE_OA}/instances/my", f"{BASE_OA}/instances/my/counts",
        ["running", "approved", "rejected", "withdrawn", "terminated"],
    )
    _check_counts(
        client, admin_headers, f"{BASE_OA}/admin/instances", f"{BASE_OA}/admin/instances/counts",
        ["running", "approved", "rejected", "withdrawn", "terminated"],
    )


def test_approval_counts_and_q(client, admin_headers, manager_headers):
    # 页签计数键齐全且与列表一致
    c = client.get("/api/v1/approval/tasks/counts", headers=admin_headers).json()
    assert c["code"] == 0
    data = c["data"]
    assert set(data) == {"todo", "done", "initiated", "cc"}
    for tab in ("todo", "done", "initiated"):
        lst = client.get(
            "/api/v1/approval/tasks", params={"tab": tab, "page": 1, "size": 1}, headers=admin_headers
        ).json()
        assert data[tab] == lst["data"]["total"], (tab, data, lst["data"]["total"])
    cc = client.get("/api/v1/approval/cc", params={"page": 1, "size": 1}, headers=admin_headers).json()
    assert data["cc"] == cc["data"]["total"]

    # 发起一条绑定流程的 OA 单 → 审批实例标题含表单名，可按 q 检索
    flow_id = next(
        d["id"] for d in client.get(f"{BASE_OA}/admin/flow-defs", headers=admin_headers).json()["data"]
        if d["code"] == "oa_leave_approve"
    )
    key = _uniq("ut_gq_")
    r = client.post(
        f"{BASE_OA}/admin/forms",
        headers=admin_headers,
        json={
            "key": key,
            "name": f"检索{key}",
            "category": "other",
            "fields": [{"key": "a", "label": "A", "type": "text"}],
            "flowDefinitionId": flow_id,
        },
    ).json()
    assert r["code"] == 0, r
    fid = r["data"]["id"]
    assert client.post(f"{BASE_OA}/admin/forms/{fid}/publish", headers=admin_headers).json()["code"] == 0
    ap = client.post(f"{BASE_OA}/instances", headers=admin_headers, json={"formId": fid, "data": {"a": "x"}}).json()
    assert ap["code"] == 0, ap

    # initiated（发起人=admin）q 命中/不命中
    hit = client.get(
        "/api/v1/approval/tasks", params={"tab": "initiated", "q": key, "page": 1, "size": 50}, headers=admin_headers
    ).json()
    assert hit["data"]["total"] >= 1
    miss = client.get(
        "/api/v1/approval/tasks", params={"tab": "initiated", "q": "zzz_no_match", "page": 1, "size": 50},
        headers=admin_headers,
    ).json()
    assert miss["data"]["total"] == 0

    # todo（审批人=manager1）q 命中 / related q 命中
    todo_hit = client.get(
        "/api/v1/approval/tasks", params={"tab": "todo", "q": key, "page": 1, "size": 50}, headers=manager_headers
    ).json()
    assert todo_hit["data"]["total"] >= 1
    rel_hit = client.get(
        f"{BASE_OA}/related", params={"tab": "todo", "q": key, "page": 1, "size": 50}, headers=manager_headers
    ).json()
    assert rel_hit["data"]["total"] >= 1
    rel_miss = client.get(
        f"{BASE_OA}/related",
        params={"tab": "todo", "q": "zzz_no_match", "page": 1, "size": 50},
        headers=manager_headers,
    ).json()
    assert rel_miss["data"]["total"] == 0

    # 我的申请 q（display_no / form_name）
    my = client.get(f"{BASE_OA}/instances/my", params={"q": key}, headers=admin_headers).json()
    assert my["data"]["total"] == 1
    my_miss = client.get(f"{BASE_OA}/instances/my", params={"q": "zzz_no_match"}, headers=admin_headers).json()
    assert my_miss["data"]["total"] == 0

    # 与我相关 counts 键齐全（manager1 至少 1 条待办）
    rc = client.get(f"{BASE_OA}/related/counts", headers=manager_headers).json()
    assert rc["code"] == 0 and set(rc["data"]) == {"todo", "done", "cc"}
    assert rc["data"]["todo"] >= 1

"""采购管理一期主链路（HTTP）：往来单位扩展 → 申请审批 → 生成合同 → 会签 → 出入库。

测试库数据跨用例持久：所有业务数据带唯一后缀，用户名 pp_ 前缀。
"""

import io
import uuid

from openpyxl import load_workbook

UUID = uuid.uuid4().hex[:8]


def _login(client, username: str, password: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    data = r.json()
    assert data["code"] == 0, data
    return {"Authorization": f"Bearer {data['data']['access_token']}"}


def _create_partner(client, headers, partner_type: str, name: str):
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={
            "name": f"{name}_{suf}",
            "partner_type": partner_type,
            "tax_no": f"913401PP{suf}",
            "customer_type": "enterprise",
            "status": "enabled",
            "supply_category": "equipment" if partner_type in ("supplier", "both") else "",
            "supplier_rating": "A" if partner_type in ("supplier", "both") else "",
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _todo_for(client, headers, biz_id: int, biz_type: str):
    """按 bizType+bizId 过滤待办：测试库跨用例持久，其他模块可能存在同 bizId 的待办。"""
    page = client.get("/api/v1/approval/tasks", headers=headers, params={"tab": "todo", "size": 200}).json()
    return [i for i in page["data"]["items"] if i["bizId"] == biz_id and i["bizType"] == biz_type]


def _mk_request(client, headers, title: str, task_id: int | None = None):
    r = client.post(
        "/api/v1/procurement/requests",
        headers=headers,
        json={
            "title": title,
            "task_id": task_id,
            "purchase_method": "inquiry",
            "budget_amount": 12000,
            "expect_date": "2026-12-31",
            "reason": "测试采购事由",
            "items": [
                {"item_name": "压力传感器", "spec": "0-1MPa", "unit": "个", "quantity": 2, "estimate_price": 5000},
                {"item_name": "数据线", "spec": "2m", "unit": "根", "quantity": 4, "estimate_price": 500},
            ],
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def test_partner_type_extension(client, admin_headers):
    """往来单位：partner_type 建/查/筛选/options 过滤。"""
    supplier = _create_partner(client, admin_headers, "supplier", f"pp_供应商{UUID}")
    customer = _create_partner(client, admin_headers, "customer", f"pp_客户{UUID}")
    assert supplier["partnerType"] == "supplier"
    assert supplier["supplyCategory"] == "equipment"

    # 列表 filters[partner_type]
    r = client.get(
        "/api/v1/crm/customers", headers=admin_headers, params={"filters[partner_type]": "supplier", "size": 200}
    ).json()
    ids = [i["id"] for i in r["data"]["items"]]
    assert supplier["id"] in ids and customer["id"] not in ids

    # options 过滤：supplier 只见 supplier/both
    opts = client.get(
        "/api/v1/crm/customers/options", headers=admin_headers, params={"partner_type": "supplier", "limit": 100}
    ).json()["data"]
    opt_ids = [o["id"] for o in opts]
    assert supplier["id"] in opt_ids and customer["id"] not in opt_ids
    opts_c = client.get(
        "/api/v1/crm/customers/options", headers=admin_headers, params={"partner_type": "customer", "limit": 100}
    ).json()["data"]
    assert customer["id"] in [o["id"] for o in opts_c]

    # 编辑改 both
    r = client.put(
        f"/api/v1/crm/customers/{supplier['id']}",
        headers=admin_headers,
        json={"name": supplier["name"], "partner_type": "both", "tax_no": supplier["taxNo"], "status": "enabled"},
    ).json()
    assert r["code"] == 0 and r["data"]["partnerType"] == "both"


def test_purchase_request_flow(client, admin_headers, manager_headers, leader_headers):
    """申请：CRUD → 提交（发 PR 号）→ 两级审批 → approved；驳回/撤回路径；counts/q/导出。"""
    req = _mk_request(client, admin_headers, f"pp_采购申请{UUID}")
    rid = req["id"]
    assert req["requestNo"] == "" and req["status"] == "draft"
    assert len(req["items"]) == 2

    # 编辑（乐观锁）
    r = client.put(
        f"/api/v1/procurement/requests/{rid}",
        headers=admin_headers,
        json={
            "title": req["title"],
            "purchase_method": "negotiation",
            "budget_amount": 13000,
            "items": [{"item_name": "压力传感器", "spec": "0-1MPa", "unit": "个", "quantity": 3}],
            "version": req["version"] + 99,
        },
    ).json()
    assert r["code"] == 10003  # 乐观锁
    r = client.put(
        f"/api/v1/procurement/requests/{rid}",
        headers=admin_headers,
        json={
            "title": req["title"],
            "purchase_method": "negotiation",
            "budget_amount": 13000,
            "items": [{"item_name": "压力传感器", "spec": "0-1MPa", "unit": "个", "quantity": 3}],
            "version": req["version"],
        },
    ).json()
    assert r["code"] == 0 and r["data"]["purchaseMethod"] == "negotiation"

    # q 搜索 + counts
    r = client.get("/api/v1/procurement/requests", headers=admin_headers, params={"q": f"pp_采购申请{UUID}"}).json()
    assert r["data"]["total"] == 1
    counts = client.get("/api/v1/procurement/requests/counts", headers=admin_headers).json()["data"]
    assert counts["all"] >= 1 and "draft" in counts

    # 未批准申请不能生成合同
    r = client.post(
        f"/api/v1/procurement/requests/{rid}/generate-contract", headers=admin_headers, json={"supplier_id": 1}
    ).json()
    assert r["code"] == 95003

    # 空明细不能提交
    empty = client.post(
        "/api/v1/procurement/requests", headers=admin_headers, json={"title": f"pp_空明细{UUID}", "items": []}
    ).json()["data"]
    r = client.post(f"/api/v1/procurement/requests/{empty['id']}/submit", headers=admin_headers, json={}).json()
    assert r["code"] == 10001

    # 提交审批：发 PR 编号
    r = client.post(
        f"/api/v1/procurement/requests/{rid}/submit", headers=admin_headers, json={"comment": "请审批"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "approving"
    assert r["data"]["requestNo"].startswith("PR")

    # 审批中禁编辑
    r = client.put(
        f"/api/v1/procurement/requests/{rid}",
        headers=admin_headers,
        json={"title": "x", "items": [{"item_name": "a", "quantity": 1}]},
    ).json()
    assert r["code"] == 95001

    # manager1 → leader1 顺序审批
    todo = _todo_for(client, manager_headers, rid, "purchase_request")
    assert todo
    r = client.post(
        f"/api/v1/approval/tasks/{todo[0]['id']}/approve", headers=manager_headers, json={"comment": "ok"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "running"
    todo = _todo_for(client, leader_headers, rid, "purchase_request")
    assert todo
    r = client.post(
        f"/api/v1/approval/tasks/{todo[0]['id']}/approve", headers=leader_headers, json={"comment": "ok"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "approved"

    detail = client.get(f"/api/v1/procurement/requests/{rid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "approved"
    assert [x["action"] for x in detail["timeline"]] == ["start", "agree", "agree"]
    return detail


def test_purchase_request_reject_withdraw(client, admin_headers, manager_headers):
    """驳回 → 可编辑可重提；撤回 → 回写 draft。"""
    req = _mk_request(client, admin_headers, f"pp_驳回申请{UUID}")
    rid = req["id"]
    client.post(f"/api/v1/procurement/requests/{rid}/submit", headers=admin_headers, json={})
    todo = _todo_for(client, manager_headers, rid, "purchase_request")
    r = client.post(
        f"/api/v1/approval/tasks/{todo[0]['id']}/reject", headers=manager_headers, json={"comment": "预算偏高"}
    ).json()
    assert r["code"] == 0
    detail = client.get(f"/api/v1/procurement/requests/{rid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "rejected"

    # 驳回后可重提（沿用原编号）
    r = client.post(f"/api/v1/procurement/requests/{rid}/submit", headers=admin_headers, json={}).json()
    assert r["code"] == 0 and r["data"]["requestNo"] == detail["requestNo"]

    # 发起人撤回 → draft
    inst_id = r["data"]["flowInstanceId"]
    r = client.post(f"/api/v1/approval/instances/{inst_id}/withdraw", headers=admin_headers, json={}).json()
    assert r["code"] == 0
    detail = client.get(f"/api/v1/procurement/requests/{rid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "draft"


def test_purchase_contract_countersign(client, admin_headers, manager_headers, leader_headers):
    """会签：manager1+leader1 同时持待办、全员过节点 → 终审 → approved；幂等生成；出入库链路。"""
    req = _mk_request(client, admin_headers, f"pp_会签申请{UUID}")
    rid = req["id"]
    client.post(f"/api/v1/procurement/requests/{rid}/submit", headers=admin_headers, json={})
    for h in (manager_headers, leader_headers):
        todo = _todo_for(client, h, rid, "purchase_request")
        client.post(f"/api/v1/approval/tasks/{todo[0]['id']}/approve", headers=h, json={"comment": "ok"})

    supplier = _create_partner(client, admin_headers, "both", f"pp_供应商C{UUID}")
    customer_only = _create_partner(client, admin_headers, "customer", f"pp_纯客户{UUID}")

    # 非供应商往来单位 → 95002
    r = client.post(
        f"/api/v1/procurement/requests/{rid}/generate-contract",
        headers=admin_headers,
        json={"supplier_id": customer_only["id"], "amount": 13000},
    ).json()
    assert r["code"] == 95002

    # 生成合同草稿
    r = client.post(
        f"/api/v1/procurement/requests/{rid}/generate-contract",
        headers=admin_headers,
        json={"supplier_id": supplier["id"], "amount": 13000, "pay_cycle": "once"},
    ).json()
    assert r["code"] == 0, r
    contract = r["data"]
    cid = contract["id"]
    assert contract["status"] == "draft" and contract["requestId"] == rid
    assert contract["supplierName"].startswith("pp_供应商C")

    # 幂等：再生成返回同一合同
    r = client.post(
        f"/api/v1/procurement/requests/{rid}/generate-contract",
        headers=admin_headers,
        json={"supplier_id": supplier["id"]},
    ).json()
    assert r["code"] == 0 and r["data"]["id"] == cid

    # 申请详情互跳字段
    detail = client.get(f"/api/v1/procurement/requests/{rid}", headers=admin_headers).json()["data"]
    assert detail["contractId"] == cid

    # 提交会签：发 CG 编号；manager1 和 leader1 同时持待办
    r = client.post(
        f"/api/v1/procurement/contracts/{cid}/submit", headers=admin_headers, json={"comment": "会签"}
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "approving"
    assert r["data"]["contractNo"].startswith("CG")
    todo_m = _todo_for(client, manager_headers, cid, "purchase_contract")
    todo_l = _todo_for(client, leader_headers, cid, "purchase_contract")
    assert todo_m and todo_l, "会签节点应同时给两人派待办"

    # manager1 过 → 会签未齐，仍在审批中
    r = client.post(
        f"/api/v1/approval/tasks/{todo_m[0]['id']}/approve", headers=manager_headers, json={"comment": "同意"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "running"
    detail = client.get(f"/api/v1/procurement/contracts/{cid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "approving"

    # leader1 过会签 → 进入终审（leader1 再持一条待办）
    r = client.post(
        f"/api/v1/approval/tasks/{todo_l[0]['id']}/approve", headers=leader_headers, json={"comment": "同意"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "running"
    todo_l2 = _todo_for(client, leader_headers, cid, "purchase_contract")
    assert todo_l2, "终审节点应给 leader1 派新待办"
    r = client.post(
        f"/api/v1/approval/tasks/{todo_l2[0]['id']}/approve", headers=leader_headers, json={"comment": "终审通过"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "approved"

    detail = client.get(f"/api/v1/procurement/contracts/{cid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "approved"

    # counts + q + 排序
    counts = client.get("/api/v1/procurement/contracts/counts", headers=admin_headers).json()["data"]
    assert counts["approved"] >= 1
    r = client.get(
        "/api/v1/procurement/contracts",
        headers=admin_headers,
        params={"q": "pp_", "sort": "amount:desc", "size": 50},
    ).json()
    assert r["data"]["total"] >= 1

    # ---- 出入库 ----
    # 入库登记（关联已通过合同，发 RK 号）
    r = client.post(
        "/api/v1/procurement/stock-orders",
        headers=admin_headers,
        json={
            "order_type": "in",
            "contract_id": cid,
            "warehouse": "wh1",
            "order_date": "2026-10-27",
            "items": [{"item_name": "压力传感器", "spec": "0-1MPa", "unit": "个", "quantity": 3, "price": 4800}],
        },
    ).json()
    assert r["code"] == 0, r
    order = r["data"]
    oid = order["id"]
    assert order["orderNo"].startswith("RK") and order["status"] == "registered"
    assert order["contractNo"].startswith("CG")

    # 确认 → confirmed；二次确认 95001；确认后禁编辑/删除
    r = client.post(f"/api/v1/procurement/stock-orders/{oid}/confirm", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "confirmed"
    r = client.post(f"/api/v1/procurement/stock-orders/{oid}/confirm", headers=admin_headers).json()
    assert r["code"] == 95001
    r = client.put(
        f"/api/v1/procurement/stock-orders/{oid}",
        headers=admin_headers,
        json={"order_type": "in", "warehouse": "wh2", "items": [{"item_name": "x", "quantity": 1}]},
    ).json()
    assert r["code"] == 95001
    r = client.delete(f"/api/v1/procurement/stock-orders/{oid}", headers=admin_headers).json()
    assert r["code"] == 95001

    # 出库登记（不关联合同，发 CK 号）→ 删除 registered 成功
    r = client.post(
        "/api/v1/procurement/stock-orders",
        headers=admin_headers,
        json={
            "order_type": "out",
            "warehouse": "wh1",
            "items": [{"item_name": "数据线", "unit": "根", "quantity": 1}],
        },
    ).json()
    assert r["code"] == 0 and r["data"]["orderNo"].startswith("CK")
    out_id = r["data"]["id"]
    r = client.delete(f"/api/v1/procurement/stock-orders/{out_id}", headers=admin_headers).json()
    assert r["code"] == 0

    # 草稿合同不能登记出入库
    draft = client.post(
        "/api/v1/procurement/contracts",
        headers=admin_headers,
        json={"name": f"pp_草稿合同{UUID}", "supplier_id": supplier["id"], "amount": 100},
    ).json()["data"]
    r = client.post(
        "/api/v1/procurement/stock-orders",
        headers=admin_headers,
        json={"order_type": "in", "contract_id": draft["id"], "items": [{"item_name": "x", "quantity": 1}]},
    ).json()
    assert r["code"] == 95001

    # counts（CK 单已删：confirmed=1、all=1）
    counts = client.get("/api/v1/procurement/stock-orders/counts", headers=admin_headers).json()["data"]
    assert counts["confirmed"] >= 1 and counts["all"] >= counts["confirmed"]

    # 合同详情带出入库互跳
    detail = client.get(f"/api/v1/procurement/contracts/{cid}", headers=admin_headers).json()["data"]
    assert any(o["id"] == oid for o in detail["stockOrders"])

    # 三个导出
    for path in ("requests", "contracts", "stock-orders"):
        resp = client.post(f"/api/v1/procurement/{path}/export", headers=admin_headers)
        assert resp.status_code == 200, path
        wb = load_workbook(io.BytesIO(resp.content))
        assert wb.active.max_row >= 2


def test_procurement_permission_denied(client, admin_headers):
    """无采购权限的用户访问 → 20002。"""
    username = f"pp_noperm_{uuid.uuid4().hex[:6]}"
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": username, "password": "Test@123456", "name": "无权限", "status": "enabled"},
    ).json()
    assert r["code"] == 0, r
    headers = _login(client, username, "Test@123456")
    r = client.get("/api/v1/procurement/requests", headers=headers).json()
    assert r["code"] == 20002
    r = client.get("/api/v1/procurement/stock-orders/counts", headers=headers).json()
    assert r["code"] == 20002

"""样品出入库统一走采购 StockOrder「登记→确认」流程（HTTP 全链）。数据前缀 ps_。

覆盖：登记生成待确认单 / 确认回写 in_stock + 样品流水 / 重复登记拦截 / 取消回退 / 来源筛选。
"""

import uuid

UUID = uuid.uuid4().hex[:8]


def _mk_sample(client, headers, name: str) -> tuple[int, dict]:
    """建任务→提交发号→补登样品（样品即带编号）。"""
    suf = uuid.uuid4().hex[:8]
    r = client.post("/api/v1/task/tasks", headers=headers, json={"task_name": f"ps_任务_{name}_{suf}"}).json()
    assert r["code"] == 0, r
    tid = r["data"]["id"]
    assert client.post(f"/api/v1/task/tasks/{tid}/submit", headers=headers).json()["code"] == 0
    r = client.post(
        f"/api/v1/task/tasks/{tid}/samples",
        headers=headers,
        json={"name": f"ps_{name}_{suf}", "model": "ps_M1", "vin": f"PSVIN{suf}".upper()},
    ).json()
    assert r["code"] == 0, r
    return tid, r["data"]


def _register(client, headers, sid: int, flag: str) -> dict:
    return client.post(f"/api/v1/task/samples/{sid}/{flag}", headers=headers).json()


def _confirm(client, headers, oid: int) -> dict:
    return client.post(f"/api/v1/procurement/stock-orders/{oid}/confirm", headers=headers).json()


def test_register_out_then_confirm_writes_back(client, admin_headers):
    """登记出库 → in_stock 不变、pendingOrder 挂上 → 采购侧确认 → in_stock=out + 流水 + 单据 confirmed。"""
    tid, sample = _mk_sample(client, admin_headers, "样车出库")
    sid = sample["id"]
    assert sample["inStock"] == "in"

    r = _register(client, admin_headers, sid, "out")
    assert r["code"] == 0, r
    assert r["data"]["inStock"] == "in"  # 确认前不翻转
    pending = r["data"]["pendingOrder"]
    assert pending and pending["orderType"] == "out" and pending["status"] == "registered"
    oid = pending["id"]

    # 出入库单详情带来源信息（样品/任务互跳数据）
    r = client.get(f"/api/v1/procurement/stock-orders/{oid}", headers=admin_headers).json()
    assert r["code"] == 0, r
    order = r["data"]
    assert order["sourceType"] == "sample" and order["sourceId"] == sid
    assert order["sampleNo"] == sample["sampleNo"] and order["sampleName"] == sample["name"]
    assert order["taskId"] == tid and order["taskName"]
    assert order["items"][0]["itemName"] == sample["name"]
    assert sample["vin"] in (order["items"][0]["remark"] or "")

    # 样品列表同样派生 pendingOrder 徽标
    r = client.get("/api/v1/task/samples", headers=admin_headers, params={"q": sample["sampleNo"]}).json()
    assert r["code"] == 0, r
    row = next(x for x in r["data"]["items"] if x["id"] == sid)
    assert row["pendingOrder"] and row["pendingOrder"]["id"] == oid

    r = _confirm(client, admin_headers, oid)
    assert r["code"] == 0, r
    assert r["data"]["status"] == "confirmed"

    # 确认后任务详情：in_stock=out、pendingOrder 清空、流水补写
    r = client.get(f"/api/v1/task/tasks/{tid}", headers=admin_headers).json()
    assert r["code"] == 0, r
    s = next(x for x in r["data"]["samples"] if x["id"] == sid)
    assert s["inStock"] == "out" and s["pendingOrder"] is None
    logs = [x for x in r["data"]["logs"] if x["sampleNo"] == sample["sampleNo"]]
    assert logs[0]["action"] == "out" and order["orderNo"] in logs[0]["remark"]

    # 重复确认被拒
    assert _confirm(client, admin_headers, oid)["code"] != 0


def test_duplicate_register_blocked(client, admin_headers):
    """有未确认单时禁止重复登记（同向/反向都拦）。"""
    _, sample = _mk_sample(client, admin_headers, "样车防重")
    sid = sample["id"]
    r = _register(client, admin_headers, sid, "out")
    assert r["code"] == 0, r
    oid = r["data"]["pendingOrder"]["id"]

    assert _register(client, admin_headers, sid, "out")["code"] != 0
    assert _register(client, admin_headers, sid, "in")["code"] != 0

    # 清理：取消登记
    assert client.post(f"/api/v1/task/samples/{sid}/stock-cancel", headers=admin_headers).json()["code"] == 0
    assert client.get(f"/api/v1/procurement/stock-orders/{oid}", headers=admin_headers).json()["code"] != 0


def test_cancel_restores_state(client, admin_headers):
    """取消登记：单据逻辑删、in_stock 保持原状态、可重新登记。"""
    _, sample = _mk_sample(client, admin_headers, "样车取消")
    sid = sample["id"]
    r = _register(client, admin_headers, sid, "out")
    assert r["code"] == 0, r

    r = client.post(f"/api/v1/task/samples/{sid}/stock-cancel", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["inStock"] == "in" and r["data"]["pendingOrder"] is None

    # 无待确认单时再取消 → 业务错误；可重新登记并确认
    assert client.post(f"/api/v1/task/samples/{sid}/stock-cancel", headers=admin_headers).json()["code"] != 0
    r = _register(client, admin_headers, sid, "out")
    assert r["code"] == 0, r
    assert _confirm(client, admin_headers, r["data"]["pendingOrder"]["id"])["code"] == 0

    # 确认后再入库登记 → 确认 → 回到在库
    r = _register(client, admin_headers, sid, "in")
    assert r["code"] == 0, r
    assert _confirm(client, admin_headers, r["data"]["pendingOrder"]["id"])["code"] == 0
    r = client.get("/api/v1/task/samples", headers=admin_headers, params={"q": sample["sampleNo"]}).json()
    row = next(x for x in r["data"]["items"] if x["id"] == sid)
    assert row["inStock"] == "in" and row["pendingOrder"] is None


def test_edit_in_stock_blocked_while_pending(client, admin_headers):
    """有待确认单时 PUT 样品禁止直接翻转 in_stock；改其他字段不受影响。"""
    _, sample = _mk_sample(client, admin_headers, "样车编辑")
    sid = sample["id"]
    r = _register(client, admin_headers, sid, "out")
    assert r["code"] == 0, r
    oid = r["data"]["pendingOrder"]["id"]

    r = client.put(
        f"/api/v1/task/samples/{sid}",
        headers=admin_headers,
        json={"name": sample["name"], "in_stock": "out"},
    ).json()
    assert r["code"] != 0  # 禁止绕过确认流程

    r = client.put(
        f"/api/v1/task/samples/{sid}",
        headers=admin_headers,
        json={"name": sample["name"], "model": "ps_M2", "in_stock": "in"},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["model"] == "ps_M2" and r["data"]["pendingOrder"]["id"] == oid

    # 有待确认单时禁止删除样品
    assert client.delete(f"/api/v1/task/samples/{sid}", headers=admin_headers).json()["code"] != 0

    assert _confirm(client, admin_headers, oid)["code"] == 0


def test_stock_order_source_filter(client, admin_headers):
    """出入库列表按来源筛选：sample 仅样品单；purchase 含历史空来源单、不含样品单。"""
    _, sample = _mk_sample(client, admin_headers, "样车筛选")
    r = _register(client, admin_headers, sample["id"], "out")
    assert r["code"] == 0, r
    oid = r["data"]["pendingOrder"]["id"]

    r = client.get(
        "/api/v1/procurement/stock-orders", headers=admin_headers, params={"filters[source_type]": "sample"}
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["total"] >= 1
    assert all(x["sourceType"] == "sample" for x in r["data"]["items"])
    assert oid in [x["id"] for x in r["data"]["items"]]

    r = client.get(
        "/api/v1/procurement/stock-orders", headers=admin_headers, params={"filters[source_type]": "purchase"}
    ).json()
    assert r["code"] == 0, r
    assert all(x["sourceType"] == "purchase" for x in r["data"]["items"])
    assert oid not in [x["id"] for x in r["data"]["items"]]

    # 清理
    assert client.post(f"/api/v1/task/samples/{sample['id']}/stock-cancel", headers=admin_headers).json()["code"] == 0

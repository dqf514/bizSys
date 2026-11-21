"""资产与库存域 · 进出库管理（仓库/库位/存货档案/采购订单/到货验收/库存台账/库存盘点）HTTP 全链。

数据前缀 as_；每条用例的编码/编号都带 uuid4().hex[:8] 后缀（测试库跨次运行残留）。
覆盖：CRUD、编码重复、状态机（订单 draft→confirmed→closed、验收→台账、盘点 draft→counting→finished）、
库存不足拦截、库位有货不可删、部门/供应商统一框架（sys_dept / crm_customer）、导出、权限点服务端强制。
"""

import uuid

from conftest import post_login

BASE = "/api/v1/asset"


def _sfx() -> str:
    return uuid.uuid4().hex[:8]


def _supplier(client, headers) -> int:
    """供应公司统一走 crm_customer（partner_type=supplier）。"""
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": f"as_供应商_{_sfx()}", "partnerType": "supplier", "status": "enabled"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _dept(client, headers) -> dict:
    """部门统一走 sys_dept。"""
    r = client.get("/api/v1/admin/depts", headers=headers).json()
    assert r["code"] == 0 and r["data"], r
    return r["data"][0]


def _mk_warehouse(client, headers, dept_id: int | None = None, **kw) -> dict:
    body = {"code": f"WH-{_sfx()}", "name": f"as_仓库_{_sfx()}", "address": "A区1号"}
    if dept_id:
        body["deptId"] = dept_id
    body.update(kw)
    r = client.post(f"{BASE}/warehouses", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def _mk_location(client, headers, warehouse_id: int, **kw) -> dict:
    body = {"warehouseId": warehouse_id, "code": f"LO-{_sfx()}", "name": "as_库位", "area": "A区"}
    body.update(kw)
    r = client.post(f"{BASE}/locations", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def _get_location(client, headers, location_id: int, warehouse_id: int) -> dict:
    """库位没有单条详情接口，从该仓库的库位列表里取（仓库是本用例新建的，库位唯一）。"""
    r = client.get(
        f"{BASE}/locations", headers=headers, params={"filters[warehouse_id]": warehouse_id}
    ).json()
    assert r["code"] == 0, r
    for row in r["data"]["items"]:
        if row["id"] == location_id:
            return row
    raise AssertionError(f"库位 {location_id} 不在列表中")


def _mk_item(client, headers, supplier_id: int | None = None, **kw) -> dict:
    body = {"code": f"IT-{_sfx()}", "name": "as_存货", "unit": "个", "unitPrice": 12.5, "safetyStock": 2}
    if supplier_id:
        body["supplierId"] = supplier_id
    body.update(kw)
    r = client.post(f"{BASE}/items", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


# ---------------- 仓库与库位 ----------------


def test_warehouse_crud_with_dept(client, admin_headers):
    """仓库增删改查 + 部门回填（sys_dept 统一框架）+ 编码重复拦截 + 统计卡。"""
    dept = _dept(client, admin_headers)
    wh = _mk_warehouse(client, admin_headers, dept_id=dept["id"], managerName="张三")
    assert wh["deptId"] == dept["id"]
    assert wh["deptName"] == dept["name"]
    assert wh["locationCount"] == 0
    assert wh["status"] == "enabled"

    # 编码重复
    r = client.post(
        f"{BASE}/warehouses", headers=admin_headers, json={"code": wh["code"], "name": "重复"}
    ).json()
    assert r["code"] == 97004, r

    # 详情 + 库位列表挂载
    r = client.get(f"{BASE}/warehouses/{wh['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["locations"] == []

    # 列表检索（q 命中编码）
    r = client.get(f"{BASE}/warehouses", headers=admin_headers, params={"q": wh["code"]}).json()
    assert r["code"] == 0, r
    assert r["data"]["total"] == 1
    assert r["data"]["items"][0]["id"] == wh["id"]

    # 修改
    r = client.put(
        f"{BASE}/warehouses/{wh['id']}",
        headers=admin_headers,
        json={"code": wh["code"], "name": "as_仓库_改名", "status": "disabled", "version": wh["version"]},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["name"] == "as_仓库_改名" and r["data"]["status"] == "disabled"

    # 乐观锁：旧版本号应被拒
    r = client.put(
        f"{BASE}/warehouses/{wh['id']}",
        headers=admin_headers,
        json={"code": wh["code"], "name": "并发写", "version": wh["version"]},
    ).json()
    assert r["code"] == 10003, r

    # 统计卡 / 计数
    r = client.get(f"{BASE}/warehouses/stats", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["warehouseCount"] >= 1
    assert "batchCount" in r["data"] and "stockAmount" in r["data"]
    r = client.get(f"{BASE}/warehouses/counts", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["all"] >= 1, r

    # 删除
    r = client.delete(f"{BASE}/warehouses/{wh['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r
    r = client.get(f"{BASE}/warehouses/{wh['id']}", headers=admin_headers).json()
    assert r["code"] == 10002, r


def test_location_crud_and_warehouse_guard(client, admin_headers):
    """库位增删改查 + 同仓编码唯一 + 仓库下有库位不可删。"""
    wh = _mk_warehouse(client, admin_headers)
    loc = _mk_location(client, admin_headers, wh["id"], capacity=50)
    assert loc["warehouseId"] == wh["id"] and loc["qtyOnHand"] == 0

    # 同仓编码重复
    r = client.post(
        f"{BASE}/locations",
        headers=admin_headers,
        json={"warehouseId": wh["id"], "code": loc["code"], "name": "重复"},
    ).json()
    assert r["code"] == 97004, r

    # 仓库下有库位 → 不可删仓库
    r = client.delete(f"{BASE}/warehouses/{wh['id']}", headers=admin_headers).json()
    assert r["code"] == 97001, r

    # 按仓库过滤库位
    r = client.get(
        f"{BASE}/locations", headers=admin_headers, params={"filters[warehouse_id]": wh["id"]}
    ).json()
    assert r["code"] == 0 and r["data"]["total"] == 1, r

    # 下拉全集
    r = client.get(f"{BASE}/locations/all", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert any(x["id"] == loc["id"] and x["warehouseName"] == wh["name"] for x in r["data"])

    # 修改库位
    r = client.put(
        f"{BASE}/locations/{loc['id']}",
        headers=admin_headers,
        json={
            "warehouseId": wh["id"],
            "code": loc["code"],
            "name": "as_库位_改名",
            "area": "B区",
            "version": loc["version"],
        },
    ).json()
    assert r["code"] == 0 and r["data"]["area"] == "B区", r

    # 删库位 → 再删仓库
    r = client.delete(f"{BASE}/locations/{loc['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r
    r = client.delete(f"{BASE}/warehouses/{wh['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r


def test_location_with_stock_cannot_delete(client, admin_headers):
    """库位有在库数量时不可删除（97001）。"""
    wh = _mk_warehouse(client, admin_headers)
    loc = _mk_location(client, admin_headers, wh["id"])
    item = _mk_item(client, admin_headers)

    r = client.post(
        f"{BASE}/ledger",
        headers=admin_headers,
        json={
            "direction": "in",
            "itemId": item["id"],
            "warehouseId": wh["id"],
            "locationId": loc["id"],
            "quantity": 5,
            "unitPrice": 10,
        },
    ).json()
    assert r["code"] == 0, r

    assert _get_location(client, admin_headers, loc["id"], wh["id"])["qtyOnHand"] == 5

    r = client.delete(f"{BASE}/locations/{loc['id']}", headers=admin_headers).json()
    assert r["code"] == 97001, r


# ---------------- 存货档案 ----------------


def test_item_crud_and_supplier_frame(client, admin_headers):
    """存货档案 CRUD + 供应公司走 crm_customer + 非供应商往来单位拦截 + 低库存筛选。"""
    supplier_id = _supplier(client, admin_headers)
    item = _mk_item(client, admin_headers, supplier_id=supplier_id, safetyStock=100)
    assert item["supplierId"] == supplier_id
    assert item["supplierName"].startswith("as_供应商_")

    # 编码重复
    r = client.post(
        f"{BASE}/items", headers=admin_headers, json={"code": item["code"], "name": "重复"}
    ).json()
    assert r["code"] == 97004, r

    # 客户型往来单位不能当供应商用（97006）
    cust = client.post(
        "/api/v1/crm/customers",
        headers=admin_headers,
        json={"name": f"as_客户_{_sfx()}", "partnerType": "customer"},
    ).json()["data"]["id"]
    r = client.post(
        f"{BASE}/items",
        headers=admin_headers,
        json={"code": f"IT-{_sfx()}", "name": "as_存货", "supplierId": cust},
    ).json()
    assert r["code"] == 97006, r

    # 计数 / 列表检索 / 低库存过滤
    r = client.get(f"{BASE}/items/counts", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["all"] >= 1, r
    r = client.get(f"{BASE}/items", headers=admin_headers, params={"q": item["code"]}).json()
    assert r["code"] == 0 and r["data"]["total"] == 1, r
    r = client.get(
        f"{BASE}/items",
        headers=admin_headers,
        params={"q": item["code"], "filters[low_stock]": "1"},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["total"] == 1 and r["data"]["items"][0]["lowStock"] is True

    # 修改 / 删除
    r = client.put(
        f"{BASE}/items/{item['id']}",
        headers=admin_headers,
        json={"code": item["code"], "name": "as_存货_改名", "unit": "台", "version": item["version"]},
    ).json()
    assert r["code"] == 0 and r["data"]["name"] == "as_存货_改名", r
    r = client.delete(f"{BASE}/items/{item['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r


# ---------------- 采购订单 ----------------


def test_purchase_order_state_machine(client, admin_headers):
    """采购订单 draft→confirmed→closed；非草稿不可编辑/删除；明细回填存货档案。"""
    supplier_id = _supplier(client, admin_headers)
    item = _mk_item(client, admin_headers, supplier_id=supplier_id)

    r = client.post(
        f"{BASE}/purchase-orders",
        headers=admin_headers,
        json={
            "title": f"as_采购单_{_sfx()}",
            "supplierId": supplier_id,
            "totalAmount": 100,
            "items": [{"itemId": item["id"], "itemName": item["name"], "quantity": 10, "price": 10}],
        },
    ).json()
    assert r["code"] == 0, r
    po = r["data"]
    assert po["status"] == "draft"
    assert po["supplierName"].startswith("as_供应商_")
    assert po["items"][0]["itemCode"] == item["code"]
    assert po["items"][0]["unit"] == item["unit"]

    # 草稿可改
    r = client.put(
        f"{BASE}/purchase-orders/{po['id']}",
        headers=admin_headers,
        json={
            "title": f"as_采购单_改_{_sfx()}",
            "supplierId": supplier_id,
            "items": [{"itemId": item["id"], "itemName": item["name"], "quantity": 12, "price": 10}],
            "version": po["version"],
        },
    ).json()
    assert r["code"] == 0 and r["data"]["items"][0]["quantity"] == 12, r
    confirmed_version = r["data"]["version"]

    # 确认
    r = client.post(f"{BASE}/purchase-orders/{po['id']}/confirm", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "confirmed", r

    # 已确认不可编辑 / 不可删除
    r = client.put(
        f"{BASE}/purchase-orders/{po['id']}",
        headers=admin_headers,
        json={
            "title": "不该成功",
            "supplierId": supplier_id,
            "items": [{"itemId": item["id"], "itemName": item["name"], "quantity": 1}],
            "version": confirmed_version,
        },
    ).json()
    assert r["code"] == 97001, r
    r = client.delete(f"{BASE}/purchase-orders/{po['id']}", headers=admin_headers).json()
    assert r["code"] == 97001, r

    # 关闭
    r = client.post(f"{BASE}/purchase-orders/{po['id']}/close", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "closed", r

    # 关闭后不可再确认
    r = client.post(f"{BASE}/purchase-orders/{po['id']}/confirm", headers=admin_headers).json()
    assert r["code"] == 97001, r


def test_purchase_order_delete_draft(client, admin_headers):
    """草稿订单可删除。"""
    supplier_id = _supplier(client, admin_headers)
    r = client.post(
        f"{BASE}/purchase-orders",
        headers=admin_headers,
        json={
            "title": f"as_采购单_{_sfx()}",
            "supplierId": supplier_id,
            "items": [{"itemName": "as_物料", "quantity": 1}],
        },
    ).json()
    assert r["code"] == 0, r
    pid = r["data"]["id"]
    r = client.delete(f"{BASE}/purchase-orders/{pid}", headers=admin_headers).json()
    assert r["code"] == 0, r
    r = client.get(f"{BASE}/purchase-orders/{pid}", headers=admin_headers).json()
    assert r["code"] == 10002, r


# ---------------- 到货验收 ----------------


def test_receipt_accept_writes_ledger(client, admin_headers):
    """验收确认：合格数量写入库存台账，库位在库数量与存货结存同步回写。"""
    supplier_id = _supplier(client, admin_headers)
    wh = _mk_warehouse(client, admin_headers)
    loc = _mk_location(client, admin_headers, wh["id"])
    item = _mk_item(client, admin_headers, supplier_id=supplier_id, unitPrice=20)

    # 先建来源采购订单并确认
    po = client.post(
        f"{BASE}/purchase-orders",
        headers=admin_headers,
        json={
            "title": f"as_采购单_{_sfx()}",
            "supplierId": supplier_id,
            "items": [{"itemId": item["id"], "itemName": item["name"], "quantity": 8, "price": 20}],
        },
    ).json()["data"]
    assert client.post(f"{BASE}/purchase-orders/{po['id']}/confirm", headers=admin_headers).json()["code"] == 0

    # 未确认订单不能验收
    po2 = client.post(
        f"{BASE}/purchase-orders",
        headers=admin_headers,
        json={
            "title": f"as_采购单_{_sfx()}",
            "supplierId": supplier_id,
            "items": [{"itemName": "as_物料", "quantity": 1}],
        },
    ).json()["data"]
    r = client.post(
        f"{BASE}/receipts",
        headers=admin_headers,
        json={
            "orderId": po2["id"],
            "warehouseId": wh["id"],
            "items": [{"itemId": item["id"], "itemName": item["name"], "quantity": 1, "qualifiedQty": 1}],
        },
    ).json()
    assert r["code"] == 97001, r

    # 建验收单
    r = client.post(
        f"{BASE}/receipts",
        headers=admin_headers,
        json={
            "orderId": po["id"],
            "warehouseId": wh["id"],
            "items": [
                {
                    "itemId": item["id"],
                    "itemName": item["name"],
                    "quantity": 8,
                    "qualifiedQty": 6,
                    "locationId": loc["id"],
                    "price": 20,
                }
            ],
        },
    ).json()
    assert r["code"] == 0, r
    rc = r["data"]
    assert rc["status"] == "draft"
    assert rc["orderNo"] == po["orderNo"]
    assert rc["items"][0]["locationCode"] == loc["code"]

    # 来源订单已确认 → 建单即关闭订单
    r = client.get(f"{BASE}/purchase-orders/{po['id']}", headers=admin_headers).json()
    assert r["data"]["status"] == "closed", r

    # 验收（部分合格 → partial）
    r = client.post(f"{BASE}/receipts/{rc['id']}/accept", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "partial"
    assert r["data"]["qualifiedQty"] == 6

    # 台账写入一条入库流水（按单号定位，避免跨次运行残留干扰）
    r = client.get(f"{BASE}/ledger", headers=admin_headers, params={"q": rc["receiptNo"]}).json()
    assert r["code"] == 0, r
    rows = [x for x in r["data"]["items"] if x["bizNo"] == rc["receiptNo"]]
    assert rows, r["data"]["items"]
    assert rows[0]["direction"] == "in" and rows[0]["quantity"] == 6
    assert rows[0]["editable"] is False

    # 库位在库数量 / 存货结存同步
    assert _get_location(client, admin_headers, loc["id"], wh["id"])["qtyOnHand"] == 6
    r = client.get(f"{BASE}/items/{item['id']}", headers=admin_headers).json()
    assert r["data"]["qtyOnHand"] == 6, r

    # 已验收单据只读
    r = client.delete(f"{BASE}/receipts/{rc['id']}", headers=admin_headers).json()
    assert r["code"] == 97001, r


def test_receipt_qualified_qty_validation(client, admin_headers):
    """合格数量不能大于到货数量（入参校验）。"""
    wh = _mk_warehouse(client, admin_headers)
    r = client.post(
        f"{BASE}/receipts",
        headers=admin_headers,
        json={
            "warehouseId": wh["id"],
            "items": [{"itemName": "as_物料", "quantity": 3, "qualifiedQty": 5}],
        },
    ).json()
    assert r["code"] != 0, r


# ---------------- 库存台账 ----------------


def test_ledger_manual_in_out(client, admin_headers):
    """手工出入库：入库增加结存，出库超过结存被拦截（97003），手工流水可改可删。"""
    wh = _mk_warehouse(client, admin_headers)
    loc = _mk_location(client, admin_headers, wh["id"])
    item = _mk_item(client, admin_headers, unitPrice=8)

    r = client.post(
        f"{BASE}/ledger",
        headers=admin_headers,
        json={
            "direction": "in",
            "itemId": item["id"],
            "warehouseId": wh["id"],
            "locationId": loc["id"],
            "quantity": 10,
            "unitPrice": 8,
            "reason": "manual",
        },
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["direction"] == "in" and r["data"]["amount"] == 80
    assert r["data"]["editable"] is True

    # 出库超库存
    r = client.post(
        f"{BASE}/ledger",
        headers=admin_headers,
        json={
            "direction": "out",
            "itemId": item["id"],
            "warehouseId": wh["id"],
            "locationId": loc["id"],
            "quantity": 20,
        },
    ).json()
    assert r["code"] == 97003, r

    # 正常出库
    r = client.post(
        f"{BASE}/ledger",
        headers=admin_headers,
        json={
            "direction": "out",
            "itemId": item["id"],
            "warehouseId": wh["id"],
            "locationId": loc["id"],
            "quantity": 4,
        },
    ).json()
    assert r["code"] == 0, r

    r = client.get(f"{BASE}/items/{item['id']}", headers=admin_headers).json()
    assert r["data"]["qtyOnHand"] == 6, r
    assert _get_location(client, admin_headers, loc["id"], wh["id"])["qtyOnHand"] == 6

    # 台账按存货过滤（该存货的流水只有本用例的两条）
    r = client.get(
        f"{BASE}/ledger", headers=admin_headers, params={"filters[item_id]": item["id"]}
    ).json()
    assert r["code"] == 0 and r["data"]["total"] == 2, r
    out_row = next(x for x in r["data"]["items"] if x["direction"] == "out")

    # 手工流水可编辑（出库数量 4 → 2，库位占用同步回退）
    r = client.put(
        f"{BASE}/ledger/{out_row['id']}",
        headers=admin_headers,
        json={
            "direction": "out",
            "itemId": item["id"],
            "warehouseId": wh["id"],
            "locationId": loc["id"],
            "quantity": 2,
            "version": out_row["version"],
        },
    ).json()
    assert r["code"] == 0 and r["data"]["quantity"] == 2, r
    assert _get_location(client, admin_headers, loc["id"], wh["id"])["qtyOnHand"] == 8

    # 手工流水可删除（回写库位占用）
    r = client.delete(f"{BASE}/ledger/{out_row['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert _get_location(client, admin_headers, loc["id"], wh["id"])["qtyOnHand"] == 10
    r = client.get(f"{BASE}/items/{item['id']}", headers=admin_headers).json()
    assert r["data"]["qtyOnHand"] == 10, r


def test_ledger_system_rows_readonly(client, admin_headers):
    """系统单据产生的流水不可编辑/删除（97001）。"""
    supplier_id = _supplier(client, admin_headers)
    wh = _mk_warehouse(client, admin_headers)
    item = _mk_item(client, admin_headers, supplier_id=supplier_id)
    rc = client.post(
        f"{BASE}/receipts",
        headers=admin_headers,
        json={
            "warehouseId": wh["id"],
            "items": [{"itemId": item["id"], "itemName": item["name"], "quantity": 2, "qualifiedQty": 2}],
        },
    ).json()["data"]
    assert client.post(f"{BASE}/receipts/{rc['id']}/accept", headers=admin_headers).json()["code"] == 0

    r = client.get(f"{BASE}/ledger", headers=admin_headers, params={"q": rc["receiptNo"]}).json()
    rows = [x for x in r["data"]["items"] if x["bizNo"] == rc["receiptNo"]]
    assert rows, r["data"]["items"]
    lid = rows[0]["id"]
    r = client.put(
        f"{BASE}/ledger/{lid}",
        headers=admin_headers,
        json={"direction": "in", "itemId": item["id"], "quantity": 1, "version": rows[0]["version"]},
    ).json()
    assert r["code"] == 97001, r
    r = client.delete(f"{BASE}/ledger/{lid}", headers=admin_headers).json()
    assert r["code"] == 97001, r


# ---------------- 库存盘点 ----------------


def test_stock_count_flow(client, admin_headers):
    """盘点 draft→counting→finished，差异按盘盈/盘亏写入台账。"""
    wh = _mk_warehouse(client, admin_headers)
    loc = _mk_location(client, admin_headers, wh["id"])
    item = _mk_item(client, admin_headers, unitPrice=10)

    # 先入库 10
    assert client.post(
        f"{BASE}/ledger",
        headers=admin_headers,
        json={
            "direction": "in",
            "itemId": item["id"],
            "warehouseId": wh["id"],
            "locationId": loc["id"],
            "quantity": 10,
            "unitPrice": 10,
        },
    ).json()["code"] == 0

    r = client.post(
        f"{BASE}/counts",
        headers=admin_headers,
        json={
            "warehouseId": wh["id"],
            "countDate": "2026-11-20",
            "operatorName": "as_盘点员",
            "items": [
                {
                    "itemId": item["id"],
                    "itemName": item["name"],
                    "locationId": loc["id"],
                    "bookQty": 10,
                    "actualQty": 8,
                    "reason": "as_破损",
                }
            ],
        },
    ).json()
    assert r["code"] == 0, r
    cnt = r["data"]
    assert cnt["status"] == "draft"
    assert cnt["items"][0]["diffQty"] == -2

    # 开始盘点
    r = client.post(f"{BASE}/counts/{cnt['id']}/start", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "counting", r

    # 结盘 → 盘亏写入台账
    r = client.post(f"{BASE}/counts/{cnt['id']}/finish", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "finished"
    assert r["data"]["diffCount"] == 1

    r = client.get(f"{BASE}/ledger", headers=admin_headers, params={"q": cnt["countNo"]}).json()
    rows = [x for x in r["data"]["items"] if x["bizNo"] == cnt["countNo"]]
    assert rows, r["data"]["items"]
    assert rows[0]["direction"] == "out" and rows[0]["quantity"] == 2

    r = client.get(f"{BASE}/items/{item['id']}", headers=admin_headers).json()
    assert r["data"]["qtyOnHand"] == 8, r

    # 已完成盘点不可再编辑/删除
    r = client.delete(f"{BASE}/counts/{cnt['id']}", headers=admin_headers).json()
    assert r["code"] == 97001, r


def test_stock_count_delete_draft(client, admin_headers):
    """草稿盘点单可删除。"""
    wh = _mk_warehouse(client, admin_headers)
    r = client.post(
        f"{BASE}/counts",
        headers=admin_headers,
        json={
            "warehouseId": wh["id"],
            "items": [{"itemName": "as_物料", "bookQty": 1, "actualQty": 1}],
        },
    ).json()
    assert r["code"] == 0, r
    cid = r["data"]["id"]
    r = client.delete(f"{BASE}/counts/{cid}", headers=admin_headers).json()
    assert r["code"] == 0, r


# ---------------- 导出与权限 ----------------


def test_asset_stock_export(client, admin_headers):
    """导出为 xlsx（响应非信封，原样放行）。"""
    for path in (
        "/warehouses/export",
        "/items/export",
        "/purchase-orders/export",
        "/receipts/export",
        "/ledger/export",
        "/counts/export",
    ):
        r = client.post(f"{BASE}{path}", headers=admin_headers)
        assert r.status_code == 200, path
        assert r.content[:2] == b"PK", path


def test_asset_stock_requires_permission(client, admin_headers):
    """无 asset 权限的角色访问库存接口 → 20002（服务端强制）。"""
    from app.core.db import SessionLocal
    from app.core.security import hash_password
    from app.modules.auth.models import User

    username = f"as_noperm_{_sfx()}"
    db = SessionLocal()
    try:
        db.add(User(username=username, password_hash=hash_password("Test@123456"), name="as_无权限", status="enabled"))
        db.commit()
    finally:
        db.close()

    login = post_login(client, username, "Test@123456").json()
    assert login["code"] == 0, login
    headers = {"Authorization": f"Bearer {login['data']['access_token']}"}

    r = client.get(f"{BASE}/warehouses", headers=headers).json()
    assert r["code"] == 20002, r
    r = client.post(
        f"{BASE}/items", headers=headers, json={"code": f"IT-{_sfx()}", "name": "as_存货"}
    ).json()
    assert r["code"] == 20002, r

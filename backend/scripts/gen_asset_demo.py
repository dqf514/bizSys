"""资产与库存域演示数据（真实 API 全链）：仓库库位/物料/采购订单/验收/流水/盘点/固定资产折旧/处置/工具领用/样件借出。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlencode

BASE = "http://127.0.0.1:8000/api/v1"
TOK: dict[str, str] = {}


def req(method, path, token=None, body=None, params=None):
    if params:
        path = f"{path}?{urlencode(params)}"
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            p = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        p = json.loads(e.read() or b"{}")
    if p.get("code") != 0:
        raise RuntimeError(f"{method} {path} -> {p.get('code')} {p.get('message')}")
    return p.get("data")


def login(u, p):
    from app.core.redis import get_redis
    cap = req("GET", "/auth/captcha")
    code = get_redis().get(f"captcha:{cap['captchaId']}")
    if isinstance(code, bytes):
        code = code.decode()
    TOK[u] = req("POST", "/auth/login", body={
        "username": u, "password": p, "captchaId": cap["captchaId"], "captchaText": code})["access_token"]


def step(desc, fn):
    try:
        return fn()
    except RuntimeError as e:
        print(f"{desc} 跳过: {e}")
        return None


login("admin", "Admin@123456")
A = TOK["admin"]

# ---------- 1. 仓库 + 库位 ----------
whs = req("GET", "/asset/warehouses", A, params={"page": 1, "size": 50})["items"]
wh = next((w for w in whs if w.get("code") == "WH01"), None)
if not wh:
    wh = req("POST", "/asset/warehouses", A, body={
        "code": "WH01", "name": "检测中心主料仓", "deptId": None,
        "address": "合肥市高新区汽车检测产业园1号厂房东侧", "managerId": 6, "managerName": "张伟",
        "capacity": 300, "phone": "0551-65881201", "remark": "计量器具、备件与耗材集中存放，危化品独立分区。",
        "status": "enabled"})
    print("仓库:", wh.get("code"), wh.get("name"))
wh_id = wh["id"]

locs = req("GET", "/asset/locations/all", A)
locs = locs if isinstance(locs, list) else locs.get("items", [])
loc_by_code = {l["code"]: l for l in locs}
LOCS = [("A-01-01", "整机存放区", "整机区", 80), ("A-02-01", "备件货架", "备件区", 120), ("B-01-01", "危化品柜", "危化品区", 20)]
loc_ids = {}
for code, name, area, cap in LOCS:
    if code in loc_by_code:
        loc_ids[code] = loc_by_code[code]["id"]
        continue
    l = req("POST", "/asset/locations", A, body={
        "warehouseId": wh_id, "code": code, "name": name, "area": area, "capacity": cap,
        "remark": "", "status": "enabled"})
    loc_ids[code] = l["id"]
    print("库位:", code, name)

# ---------- 2. 存货档案 ----------
items = req("GET", "/asset/items", A, params={"page": 1, "size": 100})["items"]
item_by_code = {i["code"]: i for i in items}
ITEMS = [
    dict(code="WP-001", name="三向应变片 BE120-3AA", spec="120Ω±0.5% 三向45°", unit="片", category="传感器",
         unitPrice=45, safetyStock=50, maxStock=500, defaultLocationId=loc_ids["A-01-01"], supplierId=52,
         manufacturer="中航电测", remark="风洞应变测量主力耗材"),
    dict(code="GS-001", name="标准气体 N2/CO2", spec="8L 混合气 2%±0.2%", unit="瓶", category="标准物质",
         unitPrice=780, safetyStock=20, maxStock=60, defaultLocationId=loc_ids["B-01-01"], supplierId=53,
         manufacturer="中科仪", remark="理化实验室标气，独立气柜存放"),
    dict(code="HO-001", name="液压油 ISO VG46", spec="20L/桶 抗磨型", unit="桶", category="油品",
         unitPrice=560, safetyStock=10, maxStock=40, defaultLocationId=loc_ids["A-02-01"], supplierId=None,
         manufacturer="长城润滑", remark="台架作动器常规换油用"),
    dict(code="CC-001", name="高速数据采集卡备件", spec="64ch PCIe 24bit", unit="块", category="备件",
         unitPrice=12500, safetyStock=6, maxStock=20, defaultLocationId=loc_ids["A-02-01"], supplierId=54,
         manufacturer="迈创", remark="采集系统冗余备件"),
]
item_ids = {}
for it in ITEMS:
    code = it.pop("code")
    if code in item_by_code:
        item_ids[code] = item_by_code[code]["id"]
        print("物料已存在:", code)
        continue
    r = req("POST", "/asset/items", A, body={**it, "code": code, "defaultWarehouseId": wh_id, "status": "enabled"})
    item_ids[code] = r["id"]
    print("物料:", code, r.get("name"))

# 手动入库：液压油4桶（库存4 < 安全10 → 低库存预警）
ledger = step("液压油手工入库", lambda: req("POST", "/asset/ledger", A, body={
    "direction": "in", "itemId": item_ids["HO-001"], "warehouseId": wh_id,
    "locationId": loc_ids["A-02-01"], "quantity": 4, "unitPrice": 560,
    "reason": "manual", "happenAt": "2026-11-05", "remark": "首批补库入账"}))
if ledger:
    print("流水(手工入):", ledger.get("ledgerNo") or ledger.get("id"))

# ---------- 3. 采购订单 → 验收 → 库存 ----------
pos = req("GET", "/asset/purchase-orders", A, params={"page": 1, "size": 50})["items"]
po = next((p for p in pos if (p.get("title") or "").startswith("数据采集备件三季度")), None)
if not po:
    po = req("POST", "/asset/purchase-orders", A, body={
        "title": "数据采集系统备件三季度批量采购", "supplierId": 55,
        "orderDate": "2026-11-05", "arriveDate": "2026-11-09", "totalAmount": 84000,
        "handlerId": 9, "handlerName": "赵敏", "remark": "按框架协议执行，货到验收后付款。",
        "items": [
            {"itemId": item_ids["CC-001"], "itemCode": "CC-001", "itemName": "高速数据采集卡备件",
             "spec": "64ch PCIe 24bit", "unit": "块", "quantity": 6, "price": 12500, "remark": ""},
            {"itemId": item_ids["WP-001"], "itemCode": "WP-001", "itemName": "三向应变片 BE120-3AA",
             "spec": "120Ω±0.5% 三向45°", "unit": "片", "quantity": 200, "price": 45, "remark": ""},
        ]})
    print("采购订单:", po.get("orderNo") or po.get("poNo"), po.get("status"))
po_id = po["id"]
po_now = req("GET", f"/asset/purchase-orders/{po_id}", A)
if po_now.get("status") in ("draft", "pending"):
    step("PO 确认", lambda: req("POST", f"/asset/purchase-orders/{po_id}/confirm", A))
    po_now = req("GET", f"/asset/purchase-orders/{po_id}", A)
    print("PO 确认后:", po_now.get("status"))

rcs = req("GET", "/asset/receipts", A, params={"page": 1, "size": 50})["items"]
rc = next((r for r in rcs if r.get("orderId") == po_id or r.get("order_id") == po_id), None)
if not rc:
    rc = req("POST", "/asset/receipts", A, body={
        "orderId": po_id, "warehouseId": wh_id, "arriveDate": "2026-11-09",
        "inspectorId": 9, "inspectorName": "赵敏", "remark": "到货开箱核验，数量与合同一致。",
        "items": [
            {"itemId": item_ids["CC-001"], "itemCode": "CC-001", "itemName": "高速数据采集卡备件",
             "spec": "64ch PCIe 24bit", "unit": "块", "quantity": 6, "qualifiedQty": 6,
             "locationId": loc_ids["A-02-01"], "price": 12500, "remark": ""},
            {"itemId": item_ids["WP-001"], "itemCode": "WP-001", "itemName": "三向应变片 BE120-3AA",
             "spec": "120Ω±0.5% 三向45°", "unit": "片", "quantity": 200, "qualifiedQty": 198,
             "locationId": loc_ids["A-01-01"], "price": 45, "remark": "2片封装破损，不合格拒收"},
        ]})
    print("验收单:", rc.get("receiptNo") or rc.get("no"), rc.get("status"))
rc_id = rc["id"]
rc_now = req("GET", f"/asset/receipts/{rc_id}", A)
if rc_now.get("status") not in ("accepted", "done"):
    step("验收接受", lambda: req("POST", f"/asset/receipts/{rc_id}/accept", A, body={"remark": "抽检合格，办理入库。"}))
    rc_now = req("GET", f"/asset/receipts/{rc_id}", A)
    print("验收后:", rc_now.get("status"))

# ---------- 4. 盘点 ----------
cnts = req("GET", "/asset/counts", A, params={"page": 1, "size": 50})["items"]
cnt = next((c for c in cnts if (c.get("countNo") or "").startswith("PD")), None)
if not cnt:
    cnt = req("POST", "/asset/counts", A, body={
        "warehouseId": wh_id, "countDate": "2026-11-12", "operatorId": 6, "operatorName": "张伟",
        "remark": "月度循环盘点：应变片账面与实盘差异待复核。",
        "items": [
            {"itemId": item_ids["WP-001"], "itemCode": "WP-001", "itemName": "三向应变片 BE120-3AA",
             "unit": "片", "locationId": loc_ids["A-01-01"], "bookQty": 198, "actualQty": 196,
             "reason": "领用未登记2片，已补出库单"},
            {"itemId": item_ids["CC-001"], "itemCode": "CC-001", "itemName": "高速数据采集卡备件",
             "unit": "块", "locationId": loc_ids["A-02-01"], "bookQty": 6, "actualQty": 6, "reason": ""},
        ]})
    print("盘点单:", cnt.get("countNo") or cnt.get("no"), cnt.get("status"))
cnt_id = cnt["id"]
c_now = req("GET", f"/asset/counts/{cnt_id}", A)
if c_now.get("status") in ("draft", "created", "pending"):
    step("盘点开始", lambda: req("POST", f"/asset/counts/{cnt_id}/start", A))
    c_now = req("GET", f"/asset/counts/{cnt_id}", A)
    print("盘点开始后:", c_now.get("status"))
if c_now.get("status") in ("counting", "started", "in_progress"):
    step("盘点完成", lambda: req("POST", f"/asset/counts/{cnt_id}/finish", A, body={"remark": "差异已复核，盘亏出库入账。"}))
    c_now = req("GET", f"/asset/counts/{cnt_id}", A)
    print("盘点完成后:", c_now.get("status"))

# ---------- 5. 固定资产 + 折旧 ----------
assets = req("GET", "/asset/assets", A, params={"page": 1, "size": 50})["items"]
by_no = {a.get("assetNo") or a.get("asset_no"): a for a in assets}
ASSETS = [
    dict(assetNo="FA-2024-017", name="风洞六分量天平", category="计量设备", model="MK-II6",
         spec="量程±5kN 六分量", deptId=None, custodianId=6, custodianName="王磊",
         location="3号风洞试验区", purchaseDate="2024-06-20", originalValue=286000,
         salvageRate="0.05", usefulLifeMonths=60, remark="进口核心计量设备，年度校准。"),
    dict(assetNo="FA-2025-008", name="试验数据服务器", category="IT设备", model="2U 64G/8T",
         spec="RAID5 双电源", deptId=None, custodianId=4, custodianName="张伟",
         location="数据中心机房A03", purchaseDate="2025-03-10", originalValue=84000,
         salvageRate="0.05", usefulLifeMonths=36, remark="试验数据存储与计算节点。"),
    dict(assetNo="FA-2019-002", name="旧活塞式空压机", category="通用设备", model="V-0.6/8",
         spec="0.6m³/min", deptId=None, custodianId=6, custodianName="王磊",
         location="动力站房", purchaseDate="2019-05-16", originalValue=38000,
         salvageRate="0.05", usefulLifeMonths=120, remark="能效不达标，拟报废处置。"),
]
asset_ids = {}
for a in ASSETS:
    no = a.pop("assetNo")
    if no in by_no:
        asset_ids[no] = by_no[no]["id"]
        print("资产已存在:", no)
        continue
    r = req("POST", "/asset/assets", A, body={**a, "assetNo": no, "status": "in_use"})
    asset_ids[no] = r["id"]
    print("资产:", no, r.get("name"))

# 折旧计提（按期）
for no, periods in (("FA-2024-017", ["2026-09", "2026-10"]), ("FA-2025-008", ["2026-10"]),
                    ("FA-2019-002", ["2026-10"])):
    for per in periods:
        step(f"折旧 {no} {per}", lambda no=no, per=per: req(
            "POST", f"/asset/assets/{asset_ids[no]}/depreciate", A,
            body={"period": per, "method": "straight_line", "remark": "月度计提"}))
print("折旧计提完成")

# ---------- 6. 处置报废（空压机） ----------
disps = req("GET", "/asset/disposals", A, params={"page": 1, "size": 50})["items"]
disp = next((d for d in disps if d.get("assetId") == asset_ids["FA-2019-002"]), None)
if not disp:
    disp = req("POST", "/asset/disposals", A, body={
        "assetId": asset_ids["FA-2019-002"], "disposalType": "scrap", "applyDate": "2026-11-13",
        "disposalAmount": 0, "reason": "能效不达标且维修成本过高，申请报废。",
        "handlerId": 6, "handlerName": "王磊", "remark": ""})
    print("处置单:", disp.get("disposalNo") or disp.get("no"), disp.get("status"))
disp_id = disp["id"]
d_now = req("GET", f"/asset/disposals/{disp_id}", A)
if d_now.get("status") in ("draft", "pending", "applied"):
    step("处置审批", lambda: req("POST", f"/asset/disposals/{disp_id}/approve", A, body={"comment": "同意报废，按流程处置。"}))
    d_now = req("GET", f"/asset/disposals/{disp_id}", A)
    print("处置审批后:", d_now.get("status"))
if d_now.get("status") in ("approved",):
    step("处置完成", lambda: req("POST", f"/asset/disposals/{disp_id}/complete", A, body={"remark": "已交回收商现场拆解。"}))
    d_now = req("GET", f"/asset/disposals/{disp_id}", A)
    print("处置完成后:", d_now.get("status"))

# ---------- 7. 工具 + 领用 ----------
tools = req("GET", "/asset/tools", A, params={"page": 1, "size": 50})["items"]
tool = next((t for t in tools if (t.get("toolNo") or t.get("tool_no")) == "TL-001"), None)
if not tool:
    tool = req("POST", "/asset/tools", A, body={
        "toolNo": "TL-001", "name": "数显卡尺", "spec": "0-150mm 0.01mm", "model": "Mitutoyo150",
        "category": "量具", "unit": "把", "warehouseId": wh_id, "purchaseDate": "2026-05-10",
        "status": "in_stock", "remark": "总装复测常用量具。"})
    print("工具:", tool.get("toolNo"), tool.get("name"))
tool_id = tool["id"]
loans = req("GET", "/asset/tool-loans", A, params={"page": 1, "size": 50})["items"]
tloan = next((l for l in loans if l.get("toolId") == tool_id and l.get("status") != "returned"), None)
if not tloan:
    tloan = req("POST", "/asset/tool-loans", A, body={
        "toolId": tool_id, "borrowerId": 8, "borrowerName": "刘洋",
        "loanDate": "2026-11-06", "dueDate": "2026-12-06", "purpose": "总装车间复测使用",
        "remark": "月底归还校验。"})
    print("工具领用:", tloan.get("loanNo") or tloan.get("no"), tloan.get("status"))

# ---------- 8. 样件 + 借出 ----------
protos = req("GET", "/asset/prototypes", A, params={"page": 1, "size": 50})["items"]
pt = next((p for p in protos if (p.get("code") or "") == "PT-2026-007"), None)
if not pt:
    pt = req("POST", "/asset/prototypes", A, body={
        "code": "PT-2026-007", "name": "PR-02 复装车油泥模型", "kind": "油泥模型",
        "model": "PR-02", "vin": "PR0220260007", "purchaseDate": "2026-04-10", "value": 120000,
        "status": "in_stock", "remark": "第二轮造型评审后留存。"})
    print("样件:", pt.get("code"), pt.get("name"))
pt_id = pt["id"]
ploans = req("GET", "/asset/prototype-loans", A, params={"page": 1, "size": 50})["items"]
ploan = next((l for l in ploans if l.get("prototypeId") == pt_id and l.get("status") != "returned"), None)
if not ploan:
    ploan = req("POST", "/asset/prototype-loans", A, body={
        "prototypeId": pt_id, "borrowerId": 6, "borrowerName": "王磊",
        "loanDate": "2026-11-05", "dueDate": "2026-12-05", "purpose": "造型评审对外展示",
        "handlerId": 4, "handlerName": "张伟", "remark": "专人专车运输。"})
    print("样件借出:", ploan.get("loanNo") or ploan.get("no"), ploan.get("status"))

print("ASSET_DEMO_DONE")

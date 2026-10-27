"""采购管理一期演示数据（真实 API + 审批流驱动）。
输出 JSON 摘要供后续回填脚本使用。"""
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
    TOK[u] = req("POST", "/auth/login", body={"username": u, "password": p})["access_token"]


login("admin", "Admin@123456")
login("manager1", "Test@123456")
login("leader1", "Test@123456")

# ---------------- 供应商（往来单位 partner_type=supplier） ----------------
SUPPLIERS = [
    dict(name="苏州华测精密仪器有限公司", supplyCategory="equipment", supplierRating="A",
         taxNo="91320594MA1MXK2P7L", province="江苏省", city="苏州市",
         address="苏州工业园区星湖街218号生物医药产业园A栋1206室",
         bankName="中国银行苏州工业园区支行", bankAccount="51237894012560013847",
         payOrg="苏州华测精密仪器有限公司", contactPerson="顾建平", contactPhone="13812346621",
         remark="力学传感器与应变测量设备主力供应商，年度框架在册"),
    dict(name="北京中科标准物质科技有限公司", supplyCategory="consumable", supplierRating="A",
         taxNo="91110108MA01G8T35N", province="北京市", city="北京市",
         address="北京市海淀区上地信息路12号院3号楼5层",
         bankName="中国工商银行北京海淀西区支行", bankAccount="0200045309200187654",
         payOrg="北京中科标准物质科技有限公司", contactPerson="邵文娟", contactPhone="13501082247",
         remark="标准气体/标准物质供应商，可提供证书副本"),
    dict(name="深圳市迈创自动化科技有限公司", supplyCategory="equipment", supplierRating="AA",
         taxNo="91440300MA5EF7RQ2X", province="广东省", city="深圳市",
         address="深圳市南山区科技园南区深南大道9678号威新软件园2号楼",
         bankName="招商银行深圳科技园支行", bankAccount="755902338110802",
         payOrg="深圳市迈创自动化科技有限公司", contactPerson="卢俊杰", contactPhone="13798556012",
         remark="高速数据采集系统集成商，供货周期约15个工作日"),
    dict(name="上海安捷实验设备有限公司", supplyCategory="equipment", supplierRating="A",
         taxNo="91310115MA1K2R8N6F", province="上海市", city="上海市",
         address="上海市浦东新区张江高科技园区蔡伦路780号3幢",
         bankName="交通银行上海浦东分行", bankAccount="310066789018800123456",
         payOrg="上海安捷实验设备有限公司", contactPerson="何丽娜", contactPhone="13916224085",
         remark="服务器/存储及实验室通用设备代理"),
    dict(name="成都锐科检测耗材有限公司", supplyCategory="consumable", supplierRating="B",
         taxNo="91510107MA6C1L9T3D", province="四川省", city="成都市",
         address="成都市武侯区武科东四路12号工业总部园C座8楼",
         bankName="中国建设银行成都武侯支行", bankAccount="51001478209052500123",
         payOrg="成都锐科检测耗材有限公司", contactPerson="罗晓峰", contactPhone="13618097743",
         remark="刀具/切削液等机加耗材，支持货到付款"),
    dict(name="武汉科仪计量技术有限公司", supplyCategory="service", supplierRating="A",
         taxNo="91420100MA4KX8P09Y", province="湖北省", city="武汉市",
         address="武汉市东湖新技术开发区高新大道666号光谷生物城B10栋",
         bankName="中国银行武汉光谷支行", bankAccount="568754120001889",
         payOrg="武汉科仪计量技术有限公司", contactPerson="彭志远", contactPhone="13554220168",
         remark="CNAS认可计量校准机构，出具校准证书"),
    dict(name="天津博远玻璃仪器有限公司", supplyCategory="consumable", supplierRating="B",
         taxNo="91120116MA05T3RQ8M", province="天津市", city="天津市",
         address="天津市滨海新区临港经济区渤海16路168号",
         bankName="中国农业银行天津滨海分行", bankAccount="020301040001887",
         payOrg="天津博远玻璃仪器有限公司", contactPerson="马春生", contactPhone="13820556690",
         remark="玻璃器皿与器皿清洗设备供应商"),
    dict(name="广州联仪分析仪器有限公司", supplyCategory="equipment", supplierRating="B",
         taxNo="91440101MA9UY7K52P", province="广东省", city="广州市",
         address="广州市黄埔区科学城开源大道11号A栋8楼",
         bankName="中国银行广州科学城支行", bankAccount="773074568890",
         payOrg="广州联仪分析仪器有限公司", contactPerson="冯雅琪", contactPhone="13710442358",
         remark="理化分析仪器区域代理，含安装调试"),
]

supplier_ids = {}
existing_customers = req("GET", "/crm/customers", TOK["admin"], params={"page": 1, "size": 200})["items"]
for s in SUPPLIERS:
    hit = next((c for c in existing_customers if c.get("name") == s["name"]), None)
    if hit:
        supplier_ids[s["name"]] = hit["id"]
        print(f"复用供应商: {hit.get('customerNo')} {s['name']} -> {hit['id']}")
        continue
    body = dict(s)
    body["partnerType"] = "supplier"
    body["customerType"] = "supplier"
    body["code"] = ""
    body["grade"] = ""
    body["country"] = "中国"
    r = req("POST", "/crm/customers", TOK["admin"], body)
    supplier_ids[s["name"]] = r["id"]
    print(f"供应商: {r.get('customerNo') or r.get('customer_no')} {s['name']} -> {r['id']}")

# ---------------- 任务（任务关联用） ----------------
tasks = req("GET", "/task/tasks", TOK["admin"], params={"page": 1, "size": 8})["items"]
task_ids = [t["id"] for t in tasks[:8]]

# ---------------- 采购申请 ----------------
def items(*rows):
    return [dict(itemName=n, spec=sp, unit=u, quantity=q, estimatePrice=p, remark="")
            for n, sp, u, q, p in rows]


REQUESTS = [
    dict(key="R1", target="approved", taskId=task_ids[0],
         title="风洞应变片与力学传感器年度采购", method="inquiry", expect="2026-11-20",
         reason="3号风洞应变测量通道扩建，现有应变片库存不足，需补充三向应变片与载荷传感器。",
         budget=9000 + 27200,
         items=items(("三向应变片 BE120-3AA", "120Ω±0.5%", "片", 200, 45),
                     ("载荷传感器", "0-50kN 螺纹接口", "台", 4, 6800))),
    dict(key="R2", target="approved", taskId=None,
         title="实验室标准气体与标准物质采购", method="single_source", expect="2026-11-10",
         reason="理化实验室月度标准物质消耗补充，供应商具备CNAS证书，采用单一来源采购。",
         budget=12 * 780 + 6 * 460,
         items=items(("标准气体", "N2/CO2 混合气 8L", "瓶", 12, 780),
                     ("黏度标准液", "GBW(E)130064", "支", 6, 460))),
    dict(key="R3", target="approved", taskId=task_ids[1],
         title="数据采集系统板卡扩容", method="negotiation", expect="2026-11-25",
         reason="整车路试数据采集点位由32通道扩至96通道，需增购高速采集卡及配套线缆。",
         budget=6 * 12500 + 300 * 38,
         items=items(("高速数据采集卡", "64ch PCIe 24bit", "块", 6, 12500),
                     ("屏蔽信号线缆", "低噪声 双屏蔽", "米", 300, 38))),
    dict(key="R4", target="approved", taskId=None,
         title="试验数据服务器与存储备件采购", method="public_bid", expect="2026-12-05",
         reason="试验数据平台扩容，新增计算节点与SSD备件，公开招标采购。",
         budget=2 * 42000 + 6 * 3200,
         items=items(("2U机架服务器", "64G/8T×8 RAID", "台", 2, 42000),
                     ("企业级SSD", "3.84T U.2", "块", 6, 3200))),
    dict(key="R5", target="approved", taskId=task_ids[2],
         title="模型加工中心刀具耗材补货", method="inquiry", expect="2026-11-08",
         reason="油泥模型与检具加工刀具消耗较快，按季度询价补货。",
         budget=20 * 185 + 8 * 560,
         items=items(("硬质合金立铣刀", "φ10 4刃", "支", 20, 185),
                     ("半合成切削液", "20L/桶", "桶", 8, 560))),
    dict(key="R6", target="wait_leader", taskId=None,
         title="环境试验箱年度维保服务采购", method="single_source", expect="2026-11-30",
         reason="高低温湿热试验箱4台年度维保，原厂服务延续，单一来源。",
         budget=36000,
         items=items(("整机维保服务", "含2次上门校准", "年", 1, 36000))),
    dict(key="R7", target="wait_manager", taskId=None,
         title="风洞试验区照明系统LED改造", method="negotiation", expect="2026-12-15",
         reason="试验区照明能耗高，改造为LED并加装分区控制，竞争性谈判。",
         budget=40 * 320,
         items=items(("LED工矿灯", "200W 5000K IP65", "套", 40, 320))),
    dict(key="R8", target="draft", taskId=None,
         title="办公区域工位家具更新", method="inquiry", expect="2026-12-20",
         reason="新入职人员增加，工位不足，拟更新家具（草稿待补预算明细）。",
         budget=10 * 980,
         items=items(("钢木工位桌", "1.4m 含侧柜", "套", 10, 980))),
    dict(key="R9", target="draft", taskId=None,
         title="样品冷藏柜采购", method="single_source", expect="2026-12-10",
         reason="生物样品留样需求，拟购置医用冷藏柜（草稿）。",
         budget=2 * 5600,
         items=items(("医用冷藏柜", "400L 双门 2-8℃", "台", 2, 5600))),
    dict(key="R10", target="rejected", taskId=task_ids[3],
         title="进口六分量天平采购", method="public_bid", expect="2026-12-25",
         reason="气动中心测力系统升级拟采购进口六分量天平。",
         budget=86000,
         items=items(("六分量天平", "量程±5kN 进口", "套", 1, 86000))),
]

req_summary = []
existing_list = req("GET", "/procurement/requests", TOK["admin"], params={"page": 1, "size": 200})["items"]


def find_existing(title):
    return next((x for x in existing_list if x.get("title") == title), None)


def find_todo(user, title):
    todo = req("GET", "/approval/tasks", TOK[user], params={"tab": "todo", "q": title, "size": 50})
    cands = [t for t in todo["items"] if title in (t.get("title") or "")]
    return cands[0]["id"] if cands else None


for r in REQUESTS:
    cur = find_existing(r["title"])
    if cur:
        rid = cur["id"]
        print(f"复用已存在: {r['title']} status={cur.get('status')}")
    else:
        body = dict(title=r["title"], taskId=r["taskId"], purchaseMethod=r["method"],
                    budgetAmount=r["budget"], expectDate=r["expect"], reason=r["reason"],
                    remark="", items=r["items"])
        created = req("POST", "/procurement/requests", TOK["admin"], body)
        rid = created["id"]
    status = (find_existing(r["title"]) or {}).get("status", "draft")
    if status == "draft" and r["target"] != "draft":
        req("POST", f"/procurement/requests/{rid}/submit", TOK["admin"], body={"comment": "请审批。"})
        status = "approving"
    if status == "approving":
        tid = find_todo("manager1", r["title"])
        if r["target"] == "rejected":
            if tid:
                req("POST", f"/approval/tasks/{tid}/reject", TOK["manager1"],
                    body={"comment": "预算超出本年度计划，暂缓采购。"})
                status = "rejected"
        elif tid:
            req("POST", f"/approval/tasks/{tid}/approve", TOK["manager1"], body={"comment": "同意，按询价结果执行。"})
            if r["target"] == "approved":
                tid2 = find_todo("leader1", r["title"])
                if tid2:
                    req("POST", f"/approval/tasks/{tid2}/approve", TOK["leader1"],
                        body={"comment": "同意采购，注意到货验收。"})
                    status = "approved"
                else:
                    status = "approving(wait_leader)"
            else:
                status = "approving(wait_leader)"
        else:
            status = "approving(wait_manager)"
    detail = req("GET", f"/procurement/requests/{rid}", TOK["admin"])
    status = detail.get("status", status)
    req_summary.append(dict(key=r["key"], id=rid, no=detail.get("requestNo"), status=status,
                            title=r["title"], target=r["target"]))
    print(f"申请 {r['key']}: {detail.get('requestNo')} status={status} (target={r['target']})")

# ---------------- 采购合同 ----------------
def find_req(key):
    return next(x for x in req_summary if x["key"] == key)

def find_contract_task(user):
    todo = req("GET", "/approval/tasks", TOK[user], params={"tab": "todo", "size": 50})
    cands = [t for t in todo["items"]
             if (t.get("bizType") == "purchase_contract") or ("采购合同" in (t.get("bizType") or ""))]
    assert cands, f"{user} 无采购合同待办（现有: {[(t.get('bizType'), t.get('title')) for t in todo['items']]}）"
    return cands[0]["id"]


CONTRACT_PLAN = [
    dict(key="C1", gen="R1", supplier="苏州华测精密仪器有限公司", pay="monthly", delivery="送货上门"),
    dict(key="C2", gen="R2", supplier="北京中科标准物质科技有限公司", pay="once", delivery="送货上门"),
    dict(key="C3", gen="R3", supplier="深圳市迈创自动化科技有限公司", pay="quarterly", delivery="安装调试验收"),
    dict(key="C6", gen="R4", supplier="上海安捷实验设备有限公司", pay="once", delivery="送货上门"),
]
con_summary = []
existing_cons = req("GET", "/procurement/contracts", TOK["admin"], params={"page": 1, "size": 200})["items"]


def find_con_by_request(rid):
    return next((c for c in existing_cons if c.get("requestId") == rid), None)


def find_con_by_name(name):
    return next((c for c in existing_cons if c.get("name") == name), None)


for p in CONTRACT_PLAN:
    r = find_req(p["gen"])
    hit = find_con_by_request(r["id"])
    if hit:
        cid = hit["id"]
        print(f"复用合同: {hit.get('contractNo')} <- {p['gen']}")
    else:
        body = dict(supplierId=supplier_ids[p["supplier"]], name="", amount=None,
                    payCycle=p["pay"], delivery=p["delivery"], remark="按申请明细执行，验收合格后付款。")
        c = req("POST", f"/procurement/requests/{r['id']}/generate-contract", TOK["admin"], body)
        cid = c["id"]
        req("POST", f"/procurement/contracts/{cid}/submit", TOK["admin"], body={"comment": "申请已批准，提请会签。"})
        # 会签节点1：manager1 + leader1（and）
        for who, comment in (("manager1", "技术参数与预算核对无误，同意会签。"), ("leader1", "同意会签。")):
            tid = find_contract_task(who)
            req("POST", f"/approval/tasks/{tid}/approve", TOK[who], body={"comment": comment})
        # 节点2：leader1 终审
        tid = find_contract_task("leader1")
        req("POST", f"/approval/tasks/{tid}/approve", TOK["leader1"], body={"comment": "终审通过，可签署。"})
    d = req("GET", f"/procurement/contracts/{cid}", TOK["admin"])
    con_summary.append(dict(key=p["key"], id=cid, no=d.get("contractNo"), status=d.get("status"),
                            supplier=p["supplier"], gen=p["gen"]))
    print(f"合同 {p['key']}: {d.get('contractNo')} status={d.get('status')} <- {p['gen']} {p['supplier']}")

# C4 直接创建 → 会签中（仅 manager1 通过）
c4_name = "计量校准服务年度协议（武汉科仪）"
hit4 = find_con_by_name(c4_name)
if hit4:
    c4 = hit4
    print("复用 C4")
else:
    c4 = req("POST", "/procurement/contracts", TOK["admin"], body=dict(
        name=c4_name, requestId=None, supplierId=supplier_ids["武汉科仪计量技术有限公司"],
        amount=86000, signDate="2026-10-30", startDate="2026-11-01", endDate="2027-10-31",
        payCycle="quarterly", delivery="现场服务", handlerId=None, handlerName="赵敏",
        remark="年度仪器设备外送校准与现场核查服务。"))
    req("POST", f"/procurement/contracts/{c4['id']}/submit", TOK["admin"], body={"comment": "提请会签。"})
    tid = find_contract_task("manager1")
    req("POST", f"/approval/tasks/{tid}/approve", TOK["manager1"], body={"comment": "同意会签。"})
d4 = req("GET", f"/procurement/contracts/{c4['id']}", TOK["admin"])
con_summary.append(dict(key="C4", id=c4["id"], no=d4.get("contractNo"), status=d4.get("status"),
                        supplier="武汉科仪计量技术有限公司", gen=None))
print(f"合同 C4: {d4.get('contractNo')} status={d4.get('status')} (会签中)")

# C5 直接创建草稿
c5_name = "实验室玻璃器皿批量采购合同（博远）"
hit5 = find_con_by_name(c5_name)
if hit5:
    c5 = hit5
    print("复用 C5")
else:
    c5 = req("POST", "/procurement/contracts", TOK["admin"], body=dict(
        name=c5_name, requestId=None, supplierId=supplier_ids["天津博远玻璃仪器有限公司"],
        amount=23800, signDate=None, startDate=None, endDate=None, payCycle="once", delivery="送货上门",
        handlerId=None, handlerName="周雪", remark="玻璃器皿季度批量采购，待比价后签署。"))
d5 = req("GET", f"/procurement/contracts/{c5['id']}", TOK["admin"])
con_summary.append(dict(key="C5", id=c5["id"], no=d5.get("contractNo"), status=d5.get("status"),
                        supplier="天津博远玻璃仪器有限公司", gen=None))
print(f"合同 C5: {d5.get('contractNo')} status={d5.get('status')} (草稿)")

# ---------------- 出入库 ----------------
def items_out(*rows):
    return [dict(itemName=n, spec=sp, unit=u, quantity=q, price=p, remark="") for n, sp, u, q, p in rows]

STOCK_PLAN = [
    dict(key="S1", typ="in", con="C1", wh="wh1", handler="张伟", st="confirmed",
         items=items_out(("三向应变片 BE120-3AA", "120Ω±0.5%", "片", 200, 45),
                         ("载荷传感器", "0-50kN", "台", 4, 6800))),
    dict(key="S2", typ="in", con="C2", wh="wh2", handler="李娜", st="confirmed",
         items=items_out(("标准气体", "N2/CO2 8L", "瓶", 12, 780),
                         ("黏度标准液", "GBW(E)130064", "支", 6, 460))),
    dict(key="S3", typ="in", con="C3", wh="wh1", handler="张伟", st="confirmed",
         items=items_out(("高速数据采集卡", "64ch PCIe", "块", 6, 12500),
                         ("屏蔽信号线缆", "双屏蔽", "米", 300, 38))),
    dict(key="S4", typ="in", con="C6", wh="wh2", handler="陈静", st="confirmed",
         items=items_out(("2U机架服务器", "64G/8T", "台", 2, 42000),
                         ("企业级SSD", "3.84T U.2", "块", 6, 3200))),
    dict(key="S5", typ="in", con="C1", wh="wh1", handler="张伟", st="registered",
         items=items_out(("应变片配套接线端子", "5mm", "个", 500, 3.5))),
    dict(key="S6", typ="out", con="C1", wh="wh1", handler="王磊", st="confirmed",
         items=items_out(("三向应变片 BE120-3AA", "120Ω", "片", 80, 45))),
    dict(key="S7", typ="out", con="C2", wh="wh2", handler="李娜", st="confirmed",
         items=items_out(("标准气体", "N2/CO2 8L", "瓶", 5, 780))),
    dict(key="S8", typ="out", con="C3", wh="wh1", handler="王磊", st="registered",
         items=items_out(("屏蔽信号线缆", "双屏蔽", "米", 120, 38))),
    dict(key="S9", typ="out", con="C6", wh="wh2", handler="陈静", st="registered",
         items=items_out(("企业级SSD", "3.84T U.2", "块", 2, 3200))),
]
con_by_key = {c["key"]: c for c in con_summary}
stock_summary = []
existing_stock = req("GET", "/procurement/stock-orders", TOK["admin"], params={"page": 1, "size": 200})["items"]
for s in STOCK_PLAN:
    c = con_by_key[s["con"]]
    first_item = s["items"][0]["itemName"]
    hit = next((o for o in existing_stock
                if o.get("contractId") == c["id"] and o.get("orderType") == s["typ"]
                and first_item in (o.get("summary") or o.get("title") or "")), None)
    if hit:
        oid = hit["id"]
        print(f"复用出入库: {hit.get('orderNo')}")
    else:
        body = dict(orderType=s["typ"], contractId=c["id"], warehouse=s["wh"],
                    handlerId=None, handlerName=s["handler"], orderDate="2026-11-05",
                    remark="按合同约定批次执行。", items=s["items"])
        o = req("POST", "/procurement/stock-orders", TOK["admin"], body)
        oid = o["id"]
        if s["st"] == "confirmed":
            req("POST", f"/procurement/stock-orders/{oid}/confirm", TOK["admin"],
                body={"comment": "数量与合同一致，验收无误。"})
    d = req("GET", f"/procurement/stock-orders/{oid}", TOK["admin"])
    stock_summary.append(dict(key=s["key"], id=oid, no=d.get("orderNo"), typ=s["typ"],
                              status=d.get("status"), con=s["con"]))
    print(f"出入库 {s['key']}: {d.get('orderNo')} type={s['typ']} status={d.get('status')}")

summary = dict(suppliers=supplier_ids, requests=req_summary, contracts=con_summary, stock=stock_summary)
with open("/tmp/pur_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=1)
print("PROCUREMENT_DEMO_DONE", json.dumps({k: len(v) if isinstance(v, (list, dict)) else v for k, v in summary.items()}, ensure_ascii=False))

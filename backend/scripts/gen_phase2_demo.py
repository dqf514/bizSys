"""采购二期演示数据：招投标全链 + 合作方门户 + 往来单位联系人/附件 + 样品出入库统一。
全部走真实 API（内部 + 门户独立认证），失败即抛。"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000/api/v1"
TOK: dict[str, str] = {}


def req(method, path, token=None, body=None, headers=None, raw=None):
    h = dict(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            p = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        p = json.loads(e.read() or b"{}")
    if p.get("code") != 0:
        raise RuntimeError(f"{method} {path} -> {p.get('code')} {p.get('message')}")
    return p.get("data")


def multipart(fields: dict, file_field: str | None, filename: str | None, content: bytes | None, mime="application/pdf"):
    boundary = "----t" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    if file_field and content is not None:
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {mime}\r\n\r\n").encode()
        out += content + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def min_pdf(title: str) -> bytes:
    text = f"BT /F1 12 Tf 72 720 Td ({title}) Tj ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(buf.tell())
        buf.write(f"{i} 0 obj\n{o}\nendobj\n".encode())
    xref = buf.tell()
    buf.write(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        buf.write(f"{off:010d} 00000 n \n".encode())
    buf.write(f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return buf.getvalue()


def login(u, p):
    TOK[u] = req("POST", "/auth/login", body={"username": u, "password": p})["access_token"]


login("admin", "Admin@123456")
login("manager1", "Test@123456")
login("leader1", "Test@123456")

# ============ 1. 招标项目 ============
tenders = req("GET", "/procurement/tenders", TOK["admin"], body=None) if False else req(
    "GET", "/procurement/tenders?page=1&size=100", TOK["admin"])


def find_tender(name):
    return next((t for t in tenders["items"] if t.get("name") == name), None)


ZB1_NAME = "3号风洞测控系统升级设备采购招标"
ZB2_NAME = "实验室恒温恒湿改造工程招标"
ZB3_NAME = "标准物质采购框架协议招标"
ZB4_NAME = "厂区安防系统运维招标"

def create_or_get(name, **kw):
    hit = find_tender(name)
    if hit:
        print(f"复用招标: {hit.get('tenderNo') or '(草稿)'} {name}")
        return hit
    body = dict(name=name, **kw)
    t = req("POST", "/procurement/tenders", TOK["admin"], body)
    print(f"创建招标: {t.get('tenderNo') or '(草稿)'} {name} status={t.get('status')}")
    return t

# ZB1 全链（截止时间先设未来，回填脚本再改历史）
zb1 = create_or_get(ZB1_NAME, requestId=None, tenderMethod="public", budgetAmount=1860000,
                    regDeadline="2026-11-10 17:00", bidDeadline="2026-11-15 17:00",
                    openTime="2026-11-16 09:30",
                    announcement=("现对3号风洞测控系统升级设备采购项目进行公开招标，欢迎符合条件的供应商报名投标。"
                                  "采购内容：测控机柜、高速采集卡、不间断电源及集成调试服务；"
                                  "投标人须具备独立法人资格并提供近三年同类项目业绩；"
                                  "报名截止后进行资格审查，审查通过方可下载招标文件并投标。"))
if zb1.get("status") == "draft":
    req("POST", f"/procurement/tenders/{zb1['id']}/publish", TOK["admin"])

zb2 = create_or_get(ZB2_NAME, requestId=None, tenderMethod="invite", budgetAmount=640000,
                    regDeadline="2026-10-30 17:00", bidDeadline="2026-11-05 17:00",
                    openTime="2026-11-06 09:30",
                    announcement=("实验室恒温恒湿改造工程采用邀请招标，邀请具备机电安装资质的单位报名，"
                                  "报名时请提交资质证书与类似工程业绩。"))
if zb2.get("status") == "draft":
    req("POST", f"/procurement/tenders/{zb2['id']}/publish", TOK["admin"])

zb3 = create_or_get(ZB3_NAME, requestId=None, tenderMethod="public", budgetAmount=280000,
                    regDeadline=None, bidDeadline=None, openTime=None,
                    announcement="标准物质采购框架协议招标方案编制中，暂未发布。")

zb4 = create_or_get(ZB4_NAME, requestId=None, tenderMethod="public", budgetAmount=150000,
                    regDeadline="2026-11-20 17:00", bidDeadline="2026-11-25 17:00",
                    openTime="2026-11-26 09:30",
                    announcement="厂区安防系统运维服务公开招标（因需求调整，本项目已终止）。")
if zb4.get("status") == "draft":
    req("POST", f"/procurement/tenders/{zb4['id']}/publish", TOK["admin"])
if zb4.get("status") == "published":
    req("POST", f"/procurement/tenders/{zb4['id']}/terminate", TOK["admin"], body={"comment": "需求调整，终止招标。"})

# ============ 2. 合作方门户账号 ============
def ensure_portal(username, password, company, contact, phone, email):
    plist0 = req("GET", "/procurement/partners?page=1&size=100", TOK["admin"])["items"]
    if any(p["username"] == username for p in plist0):
        print(f"门户账号已存在: {username}")
        return
    req("POST", "/portal/auth/register", body={
        "username": username, "password": password, "companyName": company,
        "contactName": contact, "phone": phone, "email": email})
    print(f"注册门户账号: {username} ({company})")


ensure_portal("szhuace", "Portal@2026", "苏州华测精密仪器有限公司", "顾建平", "13812346621", "gujp@szhuace.example.com")
ensure_portal("szmaichuang", "Portal@2026", "深圳市迈创自动化科技有限公司", "卢俊杰", "13798556012", "lujj@maichuang.example.com")
ensure_portal("gzlianyi", "Portal@2026", "广州联仪分析仪器有限公司", "冯雅琪", "13710442358", "fengyq@lianyi.example.com")

# 内部审核：P1→绑定供应商52，P2→绑定54；P3 留待审核
plist = req("GET", "/procurement/partners?page=1&size=100", TOK["admin"])["items"]
by_user = {p["username"]: p for p in plist}
for uname, cid in (("szhuace", 52), ("szmaichuang", 54)):
    p = by_user.get(uname)
    if p and p.get("status") != "enabled":
        req("POST", f"/procurement/partners/{p['id']}/review", TOK["admin"],
            body={"approve": True, "comment": "资质核验通过，绑定供应商档案。", "customerId": cid})
        print(f"审核通过 {uname} -> 绑定往来单位 {cid}")

# 审核通过后再登录
T1 = req("POST", "/portal/auth/login", body={"username": "szhuace", "password": "Portal@2026"})["access_token"]
T2 = req("POST", "/portal/auth/login", body={"username": "szmaichuang", "password": "Portal@2026"})["access_token"]
print("门户登录 OK: szhuace / szmaichuang")

# ============ 3. ZB1 报名/投标 ============
lic = min_pdf("Business License - Suzhou Huace")

def ensure_registration(tid, tken, contact, phone):
    regs = req("GET", f"/procurement/tenders/{tid}", TOK["admin"])  # detail may not include regs; use portal list
    my = req("GET", "/portal/registrations", tken)["items"]
    hit = next((r for r in my if r.get("tenderId") == tid or r.get("tender_id") == tid), None)
    if hit:
        print(f"复用报名: {hit.get('id')}")
        return hit
    body, hdr = multipart({"contact_name": contact, "contact_phone": phone}, "file",
                          "qualification.pdf", min_pdf("Qualification Certificate"))
    r = req("POST", f"/portal/tenders/{tid}/register", tken, headers=hdr, raw=body)
    print(f"门户报名: tender={tid} -> reg {r.get('id')}")
    return r

def ensure_bid(tid, tken, price, comment):
    my = req("GET", "/portal/bids", tken)["items"]
    hit = next((b for b in my if b.get("tenderId") == tid or b.get("tender_id") == tid), None)
    if hit:
        print("复用投标:", hit.get("id"))
        return hit
    body, hdr = multipart({"price": str(price), "comment": comment}, "file", "proposal.pdf",
                          min_pdf(f"Bid Proposal - {price} CNY"))
    r = req("POST", f"/portal/tenders/{tid}/bid", tken, headers=hdr, raw=body)
    print(f"门户投标: tender={tid} price={price} -> bid {r.get('id')}")
    return r

reg1 = ensure_registration(zb1["id"], T1, "顾建平", "13812346621")
reg2 = ensure_registration(zb1["id"], T2, "卢俊杰", "13798556012")

# 内部报名审核
tdetail = req("GET", f"/procurement/tenders/{zb1['id']}", TOK["admin"])
regs = tdetail.get("registrations") or []
for r in regs:
    if r.get("status") == "pending":
        req("POST", f"/procurement/tenders/{zb1['id']}/registrations/{r['id']}/review", TOK["admin"],
            body={"approve": True, "comment": "资质齐全，通过报名审核。"})
        print("报名审核通过:", r.get("id"))

bid1 = ensure_bid(zb1["id"], T1, 1823000, "含集成调试与两年质保，11月底前完成交货。")
bid2 = ensure_bid(zb1["id"], T2, 1905000, "设备原厂供货，安装调试验收后付款。")

# ZB2 报名（留待审核）
ensure_registration(zb2["id"], T1, "顾建平", "13812346621")

# ============ 4. 评标 → 定标 → 生成合同 ============
zb1_now = req("GET", f"/procurement/tenders/{zb1['id']}", TOK["admin"])
if zb1_now.get("status") == "published":
    req("POST", f"/procurement/tenders/{zb1['id']}/start-evaluation", TOK["admin"])
    print("进入评标")

def find_bid_no(tender_detail, portal_items, price):
    # 用门户侧确认自己的 bid id；内部 detail 里也有 bids
    bids = tender_detail.get("bids") or []
    hit = next((b for b in bids if abs(float(b.get("price", 0)) - price) < 0.01), None)
    return hit["id"] if hit else None

b1 = find_bid_no(req("GET", f"/procurement/tenders/{zb1['id']}", TOK["admin"]), None, 1823000)
b2 = find_bid_no(req("GET", f"/procurement/tenders/{zb1['id']}", TOK["admin"]), None, 1905000)
assert b1 and b2, f"未找到投标 {b1},{b2}"

zb1_now = req("GET", f"/procurement/tenders/{zb1['id']}", TOK["admin"])
existing_evals = zb1_now.get("evals") or zb1_now.get("evaluations") or []
if zb1_now.get("status") == "evaluating" and not existing_evals:
    for who, bid, score, rec, cmt in (
        ("manager1", b1, 92, True, "技术方案完整，业绩匹配，价格合理。"),
        ("leader1", b1, 89, True, "服务体系完善，推荐中标。"),
        ("manager1", b2, 84, False, "方案可行但交货期偏长。"),
        ("leader1", b2, 81, False, "报价偏高。"),
    ):
        req("POST", f"/procurement/tenders/{zb1['id']}/evals", TOK[who],
            body={"bidId": bid, "score": score, "comment": cmt, "recommend": rec})
    print("评标完成: 4 条评标记录")

zb1_now = req("GET", f"/procurement/tenders/{zb1['id']}", TOK["admin"])
if zb1_now.get("status") == "evaluating":
    req("POST", f"/procurement/tenders/{zb1['id']}/award", TOK["admin"], body={"bidId": b1, "comment": "综合评分第一，拟中标苏州华测。"})
    print("提交定标审批")
if zb1_now.get("status") in ("evaluating", "awarding"):
    # leader1 定标审批
    todo = req("GET", "/approval/tasks?tab=todo&size=50", TOK["leader1"])
    hit = next((t for t in todo["items"] if t.get("bizType") in ("tender_award",) or "定标" in (t.get("title") or "")), None)
    if hit:
        req("POST", f"/approval/tasks/{hit['id']}/approve", TOK["leader1"], body={"comment": "同意定标。"})
        print("定标审批通过")

zb1_done = req("GET", f"/procurement/tenders/{zb1['id']}", TOK["admin"])
print("ZB1 最终状态:", zb1_done.get("status"), zb1_done.get("tenderNo"))
if zb1_done.get("status") == "awarded":
    try:
        c = req("POST", f"/procurement/tenders/{zb1['id']}/generate-contract", TOK["admin"], body={})
        print("生成采购合同:", c.get("contractNo"), c.get("id"))
    except RuntimeError as e:
        print("生成合同跳过:", e)

# ============ 5. 往来单位联系人 + 附件 ============
CONTACTS = {
    52: ("顾建平", "销售总监", "13812346621", "gujp@szhuace.example.com"),
    54: ("卢俊杰", "大客户经理", "13798556012", "lujj@maichuang.example.com"),
    59: ("冯雅琪", "区域销售", "13710442358", "fengyq@lianyi.example.com"),
}
for cid, (name, pos, phone, email) in CONTACTS.items():
    existing = req("GET", f"/crm/customers/{cid}/contacts", TOK["admin"])["items"]
    if any(c.get("name") == name for c in existing):
        print(f"联系人已存在: {cid}/{name}")
        continue
    req("POST", f"/crm/customers/{cid}/contacts", TOK["admin"],
        body={"name": name, "position": pos, "phone": phone, "email": email, "isPrimary": True, "remark": ""})
    print(f"新增主要联系人: {cid}/{name}")

for cid in (52, 54):
    atts = req("GET", f"/crm/customers/{cid}/attachments", TOK["admin"])["items"]
    if any(a.get("category") == "license" for a in atts):
        print(f"营业执照已存在: {cid}")
        continue
    body, hdr = multipart({"category": "license", "remark": "营业执照复印件（三证合一）"},
                          "file", "business_license.pdf", min_pdf(f"Business License of partner {cid}"))
    req("POST", f"/crm/customers/{cid}/attachments", TOK["admin"], headers=hdr, raw=body)
    print(f"上传营业执照: {cid}")

# ============ 6. 样品出入库统一（source_type=sample） ============
samples = req("GET", "/task/samples?page=1&size=200", TOK["admin"])["items"]
s_out = next((s for s in samples if s.get("inStock") == "in"), None)
s_in = next((s for s in samples if s.get("inStock") == "out"), None)

def sample_stock(sample, direction):
    try:
        r = req("POST", f"/task/samples/{sample['id']}/{direction}", TOK["admin"])
        print(f"样品{direction}登记: {sample.get('sampleNo')} -> 单 {r.get('orderNo') or r.get('id')}")
        return r
    except RuntimeError as e:
        if "未确认" in str(e) or "已存在" in str(e):
            print(f"样品{direction}已有待确认单: {sample.get('sampleNo')}")
            return None
        raise

if s_out:
    o = sample_stock(s_out, "out")
if s_in:
    o2 = sample_stock(s_in, "in")

# 确认所有 source_type=sample 的待确认单
pending = req("GET", "/procurement/stock-orders?page=1&size=200&status=registered", TOK["admin"])["items"]
for o in pending:
    if o.get("sourceType") == "sample" or o.get("source_type") == "sample":
        req("POST", f"/procurement/stock-orders/{o['id']}/confirm", TOK["admin"],
            body={"comment": "样品与单据核对一致，确认。"})
        print("确认样品出入库单:", o.get("orderNo"))

print("PHASE2_DEMO_DONE")

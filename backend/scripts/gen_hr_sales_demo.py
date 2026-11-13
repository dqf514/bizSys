"""人事工时 + 销售报价演示数据（真实 API + 审批流）。输出摘要供回填脚本。"""
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


def login(u: str, p: str) -> None:
    from app.core.redis import get_redis

    cap = req("GET", "/auth/captcha")
    code = get_redis().get(f"captcha:{cap['captchaId']}")
    if isinstance(code, bytes):
        code = code.decode()
    TOK[u] = req("POST", "/auth/login", body={
        "username": u, "password": p,
        "captchaId": cap["captchaId"], "captchaText": code,
    })["access_token"]


login("admin", "Admin@123456")
login("manager1", "Test@123456")
login("leader1", "Test@123456")
for u in ("lina", "wanglei", "liuyang", "zhaomin"):
    login(u, "Staff@2026")

# ============ 1. 工时填报 ============
# (user, task_id, date, hours, content, submit)
TIMESHEETS = [
    ("lina", 2, "2026-11-09", "2", "复装车 PR-02 风洞试验数据采集，整理64 通道麦克风阵列原始数据。", True),
    ("lina", 2, "2026-11-10", "4", "气动声学试验工况复测与背景噪声修正，输出中间数据包。", True),
    ("lina", 6, "2026-11-11", "1.5", "外后视镜风噪优化方案数据初筛（草稿）。", False),
    ("wanglei", 5, "2026-11-10", "6", "油泥模型精修第二轮评审修改，完成A级曲面贴膜处理。", True),
    ("wanglei", 5, "2026-11-11", "7.5", "全尺寸扫描点云采集与缺陷标注，交付扫描报告初稿。", True),
    ("wanglei", 9, "2026-11-12", "4", "产线柔性化改造对标数据整理，竞品6台样车测试数据入库。", True),
    ("liuyang", 4, "2026-11-12", "6", "动力电池型式试验充放电循环测试，记录温升与容量衰减曲线。", True),
    ("liuyang", 4, "2026-11-13", "2", "试验数据复核与报告素材整理（草稿）。", False),
    ("zhaomin", 8, "2026-11-11", "8", "电磁兼容暗室背景场测试与天线标定，出具预测试记录。", True),
]
ts_summary = []
for user, tid, d, h, content, submit in TIMESHEETS:
    body = {"taskId": tid, "workDate": d, "hours": h, "content": content, "remark": "", "submit": submit}
    try:
        r = req("POST", "/hr/timesheets", TOK[user], body)
    except RuntimeError as e:
        if any(k in str(e) for k in ("已存在", "重复", "已填报")):
            print(f"工时已存在，跳过: {user} {d} task{tid}")
            continue
        raise
    print(f"工时 {user} {d} {h}h -> id={r.get('id')} status={r.get('status')}")
    ts_summary.append(dict(id=r.get("id"), user=user, date=d, submit=submit))

# ============ 2. 报价单 ============
# 客户：取两个已有客户
custs = req("GET", "/crm/customers", TOK["admin"], params={"page": 1, "size": 60})["items"]
by_name = {c["name"]: c for c in custs}


def cust(name_part):
    hit = next((c for c in custs if name_part in c["name"]), None)
    assert hit, f"客户未找到: {name_part}"
    return hit


c1 = cust("安徽鑫源")
c2 = cust("昆明德茂")
c3 = cust("重庆产品监督")
raw_tpls = req("GET", "/sales/templates", TOK["admin"], params={"page": 1, "size": 20})
tpls = raw_tpls if isinstance(raw_tpls, list) else raw_tpls.get("items", [])
pub = [t for t in tpls if t.get("status") == "published"]
assert pub, "无已发布模板"
tpl = pub[0]

raw_qs = req("GET", "/sales/quotations", TOK["admin"], params={"page": 1, "size": 100})
qs = raw_qs if isinstance(raw_qs, list) else raw_qs.get("items", [])


def find_q(title):
    return next((x for x in qs if x.get("title") == title), None)


def create_q(title, cust_obj, contact, requirement, row_items, email):
    hit = find_q(title)
    if hit:
        print(f"报价已存在: {hit.get('quoteNo')} {title[:16]} status={hit.get('status')}")
        return hit
    q = req("POST", "/sales/quotations", TOK["admin"], body={
        "title": title, "customerId": cust_obj["id"],
        "contactName": contact[0], "contactPhone": contact[1], "contactEmail": email,
        "templateId": tpl["id"], "taxRate": "6", "validUntil": "2026-12-31",
        "requirement": requirement, "items": row_items,
    })
    print(f"报价创建: {q.get('quoteNo')} {title[:16]}")
    return q


def step(desc, fn):
    try:
        return fn()
    except RuntimeError as e:
        print(f"{desc} 跳过: {e}")
        return None


def find_todo(user, biz="sales_quotation"):
    todo = req("GET", "/approval/tasks", TOK[user], params={"tab": "todo", "size": 50})
    return next((t for t in todo["items"] if t.get("bizType") == biz), None)

def items(*rows):
    return [dict(name=n, spec=s, unit=u, qty=q, unitPrice=p, remark="") for n, s, u, q, p in rows]

# Q1 草稿
q1 = create_q("新能源汽车电池包结构件第三方检测报价", c1, ("邵文娟", "13501082247"),
              "电池包箱体与模组结构件的力学性能与环境可靠性检测，含振动、冲击、温循三项。",
              items(("结构件力学性能检测", "拉伸/弯曲 每组", "组", 12, 850),
                    ("温循试验", "-40℃~85℃ 100循环", "项", 3, 4200),
                    ("报告与工程师解读", "含中文/英文报告", "项", 1, 6000)),
              "shaowj@example.com")

# Q2 全链：提交→审批→发送(print)→反馈接受→转合同
q2 = create_q("整车道路模拟试验台架改造报价", c2, ("顾建平", "13812346621"),
              "四通道道路模拟台架改造：作动器更换、控制系统升级、联调与操作培训。",
              items(("作动器更换", "25kN 液压伺服", "套", 4, 68000),
                    ("控制系统升级", "含控制软件与集成调试", "项", 1, 120000),
                    ("操作培训", "现场2天", "天", 2, 6000)),
              "gujp@example.com")
d2 = req("GET", f"/sales/quotations/{q2['id']}", TOK["admin"])
if d2.get("status") == "draft":
    step("Q2 提交", lambda: req("POST", f"/sales/quotations/{q2['id']}/submit", TOK["admin"],
                                body={"comment": "请审批。"}))
d2 = req("GET", f"/sales/quotations/{q2['id']}", TOK["admin"])
if d2.get("status") == "approving":
    for who, cmt in (("manager1", "方案与报价合理，同意。"), ("leader1", "同意，注意交付节点。")):
        tk = find_todo(who)
        if tk:
            step(f"Q2 审批({who})", lambda tk=tk, cmt=cmt: req(
                "POST", f"/approval/tasks/{tk['id']}/approve", TOK[who], body={"comment": cmt}))
            print(f"  {who} 审批通过: {(tk.get('title') or '')[:36]}")
d2 = req("GET", f"/sales/quotations/{q2['id']}", TOK["admin"])
print("Q2 当前:", d2.get("status"))
if d2.get("status") == "approved":
    step("Q2 发送(print)", lambda: req("POST", f"/sales/quotations/{q2['id']}/send", TOK["admin"],
                                       body={"channel": "print", "recipient": ""}))
d2 = req("GET", f"/sales/quotations/{q2['id']}", TOK["admin"])
if d2.get("status") in ("sent", "approved"):
    step("Q2 反馈接受", lambda: req("POST", f"/sales/quotations/{q2['id']}/feedback", TOK["admin"],
                                   body={"action": "accept", "note": "价格与周期确认，回签。"}))
d2 = req("GET", f"/sales/quotations/{q2['id']}", TOK["admin"])
if d2.get("status") == "accepted":
    ct = step("Q2 转合同", lambda: req("POST", f"/sales/quotations/{q2['id']}/to-contract", TOK["admin"]))
    if ct:
        print("Q2 转合同:", ct.get("id"), ct.get("contractNo") or "(草稿无号)", ct.get("status"))

# Q3 提交后停在审批中
q3 = create_q("零部件盐雾腐蚀试验年度框架报价", c3, ("何丽娜", "13916224085"),
              "年度盐雾腐蚀试验框架服务，按批次结算，含中性盐雾与循环腐蚀试验。",
              items(("中性盐雾试验", "NSS 48h/96h", "批", 20, 950),
                    ("循环腐蚀试验", "CCT 循环", "批", 8, 1600)),
              "heln@example.com")
d3 = req("GET", f"/sales/quotations/{q3['id']}", TOK["admin"])
if d3.get("status") == "draft":
    step("Q3 提交", lambda: req("POST", f"/sales/quotations/{q3['id']}/submit", TOK["admin"],
                                body={"comment": "年度框架，请审批。"}))
d3 = req("GET", f"/sales/quotations/{q3['id']}", TOK["admin"])
print("Q3:", d3.get("quoteNo"), d3.get("status"))

print("HR_SALES_DEMO_DONE", json.dumps({"timesheets": len(ts_summary),
      "quotes": [q1.get('id'), q2.get('id'), q3.get('id')]}))

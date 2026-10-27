"""采购管理二期主链路（HTTP）：招投标全流程 + 合作方门户独立认证。

测试库数据跨用例持久：业务数据带唯一后缀，门户用户名 pt_ 前缀。
"""

import io
import uuid
from datetime import datetime, timedelta

from openpyxl import load_workbook

UUID = uuid.uuid4().hex[:8]


def _portal_register(client, username: str, company: str) -> dict:
    r = client.post(
        "/api/v1/portal/auth/register",
        json={
            "username": username,
            "password": "Portal@123456",
            "company_name": company,
            "contact_name": "测试联系人",
            "phone": "13800000000",
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _portal_login(client, username: str) -> dict:
    r = client.post("/api/v1/portal/auth/login", json={"username": username, "password": "Portal@123456"}).json()
    assert r["code"] == 0, r
    return {"Authorization": f"Bearer {r['data']['access_token']}"}


def _mk_tender(client, headers, name: str, reg_hours: int = 24, bid_hours: int = 48) -> dict:
    now = datetime.now()
    r = client.post(
        "/api/v1/procurement/tenders",
        headers=headers,
        json={
            "name": name,
            "tender_method": "public",
            "budget_amount": 50000,
            "reg_deadline": (now + timedelta(hours=reg_hours)).strftime("%Y-%m-%d %H:%M:%S"),
            "bid_deadline": (now + timedelta(hours=bid_hours)).strftime("%Y-%m-%d %H:%M:%S"),
            "announcement": "测试公告内容",
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _publish(client, headers, tid: int) -> dict:
    r = client.post(f"/api/v1/procurement/tenders/{tid}/publish", headers=headers).json()
    assert r["code"] == 0, r
    return r["data"]


def _portal_register_tender(client, pheaders, tid: int, with_file: bool = True):
    files = {"file": ("资质证明.pdf", b"%PDF-1.4 fake", "application/pdf")} if with_file else None
    return client.post(
        f"/api/v1/portal/tenders/{tid}/register",
        headers=pheaders,
        data={"contact_name": "张三", "contact_phone": "13900000000"},
        files=files,
    ).json()


def _approve_partner(client, headers, pid: int, customer_id: int | None = None) -> dict:
    body: dict = {"approve": True, "comment": "ok"}
    if customer_id:
        body["customer_id"] = customer_id
    r = client.post(f"/api/v1/procurement/partners/{pid}/review", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def _mk_supplier(client, headers, name: str) -> dict:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={
            "name": f"{name}_{suf}",
            "partner_type": "supplier",
            "tax_no": f"913401PT{suf}",
            "customer_type": "enterprise",
            "status": "enabled",
            "supply_category": "equipment",
            "supplier_rating": "A",
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _todo_for(client, headers, biz_id: int, biz_type: str):
    page = client.get("/api/v1/approval/tasks", headers=headers, params={"tab": "todo", "size": 200}).json()
    return [i for i in page["data"]["items"] if i["bizId"] == biz_id and i["bizType"] == biz_type]


def _account_lifecycle(client, admin_headers, suf: str):
    """门户账号：注册(pending) → 未审核不可登录(96004) → 重复注册(96005) → 审核通过(绑供应商) → 可登录。"""
    username = f"pt_vendor1_{suf}"
    supplier = _mk_supplier(client, admin_headers, f"pt_供应商{suf}")

    p = _portal_register(client, username, f"pt_测试公司{suf}")
    assert p["status"] == "pending"

    # 待审核不可登录
    r = client.post("/api/v1/portal/auth/login", json={"username": username, "password": "Portal@123456"})
    assert r.status_code == 401 and r.json()["code"] == 96004

    # 重复注册
    r = client.post(
        "/api/v1/portal/auth/register",
        json={"username": username, "password": "Portal@123456", "company_name": "另一家公司"},
    ).json()
    assert r["code"] == 96005

    # 内部列表可见 + counts
    r = client.get("/api/v1/procurement/partners", headers=admin_headers, params={"q": username}).json()
    assert r["data"]["total"] == 1 and r["data"]["items"][0]["id"] == p["id"]
    counts = client.get("/api/v1/procurement/partners/counts", headers=admin_headers).json()["data"]
    assert counts["pending"] >= 1 and counts["all"] >= counts["pending"]

    # 审核通过并绑定供应商往来单位
    p = _approve_partner(client, admin_headers, p["id"], supplier["id"])
    assert p["status"] == "enabled" and p["customerId"] == supplier["id"]

    # 登录成功 + me
    headers = _portal_login(client, username)
    me = client.get("/api/v1/portal/auth/me", headers=headers).json()["data"]
    assert me["username"] == username and me["customerId"] == supplier["id"]

    # 停用后不可登录
    r = client.post(
        f"/api/v1/procurement/partners/{p['id']}/review", headers=admin_headers, json={"approve": False}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "disabled"
    r = client.post("/api/v1/portal/auth/login", json={"username": username, "password": "Portal@123456"})
    assert r.status_code == 401 and r.json()["code"] == 96004
    return p["id"], supplier["id"]


def test_portal_account_lifecycle(client, admin_headers):
    _account_lifecycle(client, admin_headers, UUID)


def test_partner_list_filter_by_customer(client, admin_headers):
    """往来单位详情"门户账号"tab：/procurement/partners 支持 filters[customer_id] 查绑定账号。"""
    suf = uuid.uuid4().hex[:8]
    supplier = _mk_supplier(client, admin_headers, f"pt_过滤供应商{suf}")
    p = _portal_register(client, f"pt_filter_{suf}", f"pt_过滤公司{suf}")
    _approve_partner(client, admin_headers, p["id"], supplier["id"])

    r = client.get(
        "/api/v1/procurement/partners",
        headers=admin_headers,
        params={"filters[customer_id]": supplier["id"], "size": 50},
    ).json()
    assert r["code"] == 0
    ids = [i["id"] for i in r["data"]["items"]]
    assert p["id"] in ids and r["data"]["total"] == len(ids)
    # 未绑定账号不出现在该单位下
    p2 = _portal_register(client, f"pt_filter2_{suf}", f"pt_过滤公司2_{suf}")
    assert p2["id"] not in ids


def test_tender_full_flow(client, admin_headers, leader_headers):
    """全状态机：建→发布(ZB)→门户报名→审核→投标→评标→定标审批(驳回一次)→通过→生成合同(幂等)→公示。"""
    suf = uuid.uuid4().hex[:8]
    pid, supplier_id = _account_lifecycle(client, admin_headers, suf)
    # 重新启用（上个用例停用了）
    _approve_partner(client, admin_headers, pid, supplier_id)
    username = f"pt_vendor1_{suf}"
    pheaders = _portal_login(client, username)

    # ---- 内部：建招标（关联已通过采购申请）----
    req = client.post(
        "/api/v1/procurement/requests",
        headers=admin_headers,
        json={
            "title": f"pt_关联申请{UUID}",
            "purchase_method": "tender",
            "budget_amount": 50000,
            "items": [{"item_name": "风洞传感器", "unit": "个", "quantity": 2, "estimate_price": 20000}],
        },
    ).json()["data"]
    t = client.post(
        "/api/v1/procurement/tenders",
        headers=admin_headers,
        json={
            "name": f"pt_招标A{UUID}",
            "request_id": req["id"],
            "tender_method": "public",
            "budget_amount": 50000,
            "reg_deadline": (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S"),
            "bid_deadline": (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S"),
            "announcement": "欢迎投标",
        },
    ).json()["data"]
    tid = t["id"]
    assert t["status"] == "draft" and t["tenderNo"] == "" and t["requestId"] == req["id"]

    # 草稿对门户不可见
    r = client.get(f"/api/v1/portal/tenders/{tid}", headers=pheaders).json()
    assert r["code"] == 10002

    # 未设截止时间不可发布：新建一个无截止时间的
    t2 = client.post("/api/v1/procurement/tenders", headers=admin_headers, json={"name": f"pt_无截止{UUID}"}).json()[
        "data"
    ]
    r = client.post(f"/api/v1/procurement/tenders/{t2['id']}/publish", headers=admin_headers).json()
    assert r["code"] == 10001

    # ---- 发布：发 ZB 编号 ----
    t = _publish(client, admin_headers, tid)
    assert t["status"] == "published" and t["tenderNo"].startswith("ZB")
    tender_no = t["tenderNo"]

    # 已发布不可编辑/删除
    r = client.put(f"/api/v1/procurement/tenders/{tid}", headers=admin_headers, json={"name": "x"}).json()
    assert r["code"] == 96001
    r = client.delete(f"/api/v1/procurement/tenders/{tid}", headers=admin_headers).json()
    assert r["code"] == 96001

    # 门户列表可见（公告口径无 winnerName）
    items = client.get("/api/v1/portal/tenders", headers=pheaders).json()["data"]["items"]
    mine = [i for i in items if i["id"] == tid]
    assert mine and mine[0]["tenderNo"] == tender_no and mine[0]["winnerName"] == ""

    # ---- 门户报名（multipart 带附件）----
    reg = _portal_register_tender(client, pheaders, tid)
    assert reg["code"] == 0, reg
    rid = reg["data"]["id"]
    assert reg["data"]["status"] == "pending"

    # 重复报名
    r = _portal_register_tender(client, pheaders, tid)
    assert r["code"] == 10001

    # 报名未审核投标 → 96003
    r = client.post(
        f"/api/v1/portal/tenders/{tid}/bid", headers=pheaders, data={"price": "45000", "comment": "未审核"}
    ).json()
    assert r["code"] == 96003

    # ---- 内部审核报名 ----
    detail = client.get(f"/api/v1/procurement/tenders/{tid}", headers=admin_headers).json()["data"]
    assert detail["registrations"][0]["id"] == rid and detail["registrations"][0]["hasAttachment"]
    r = client.post(
        f"/api/v1/procurement/tenders/{tid}/registrations/{rid}/review",
        headers=admin_headers,
        json={"approve": True, "comment": "资质合格"},
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "approved"

    # 内部下载报名附件
    resp = client.get(f"/api/v1/procurement/tenders/registrations/{rid}/attachment", headers=admin_headers)
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")

    # ---- 门户投标 ----
    r = client.post(
        f"/api/v1/portal/tenders/{tid}/bid",
        headers=pheaders,
        data={"price": "45000", "comment": "含税含运"},
        files={"file": ("投标方案.pdf", b"%PDF-1.4 bid", "application/pdf")},
    ).json()
    assert r["code"] == 0, r
    bid = r["data"]
    assert bid["price"] == 45000 and bid["proposalName"] == "投标方案.pdf"

    # 改标（同项目同供应商覆盖）
    r = client.post(f"/api/v1/portal/tenders/{tid}/bid", headers=pheaders, data={"price": "44000"}).json()
    assert r["code"] == 0 and r["data"]["id"] == bid["id"] and r["data"]["price"] == 44000

    # ---- 进入评标：投标即刻关闭 ----
    r = client.post(f"/api/v1/procurement/tenders/{tid}/start-evaluation", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "evaluating"
    r = client.post(f"/api/v1/portal/tenders/{tid}/bid", headers=pheaders, data={"price": "43000"}).json()
    assert r["code"] == 96001

    # ---- 评标（评分+评语+推荐，重复提交覆盖）----
    detail = client.get(f"/api/v1/procurement/tenders/{tid}", headers=admin_headers).json()["data"]
    bid_id = detail["bids"][0]["id"]
    r = client.post(
        f"/api/v1/procurement/tenders/{tid}/evals",
        headers=admin_headers,
        json={"bid_id": bid_id, "score": 80, "comment": "还行", "recommend": False},
    ).json()
    assert r["code"] == 0
    r = client.post(
        f"/api/v1/procurement/tenders/{tid}/evals",
        headers=admin_headers,
        json={"bid_id": bid_id, "score": 92, "comment": "技术方案优", "recommend": True},
    ).json()
    assert r["code"] == 0 and float(r["data"]["score"]) == 92
    detail = client.get(f"/api/v1/procurement/tenders/{tid}", headers=admin_headers).json()["data"]
    assert detail["bids"][0]["avgScore"] == 92 and len(detail["bids"][0]["evals"]) == 1

    # ---- 定标：审批被驳回 → 回评标 ----
    r = client.post(f"/api/v1/procurement/tenders/{tid}/award", headers=admin_headers, json={"bid_id": bid_id}).json()
    assert r["code"] == 0 and r["data"]["status"] == "awarding"
    # 定标审批中不能终止
    r = client.post(f"/api/v1/procurement/tenders/{tid}/terminate", headers=admin_headers).json()
    assert r["code"] == 96001
    todo = _todo_for(client, leader_headers, tid, "tender_award")
    assert todo, "leader1 应持有定标待办"
    r = client.post(
        f"/api/v1/approval/tasks/{todo[0]['id']}/reject", headers=leader_headers, json={"comment": "价格偏高"}
    ).json()
    assert r["code"] == 0
    detail = client.get(f"/api/v1/procurement/tenders/{tid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "evaluating" and detail["awardBidId"] is None

    # 未定标不能生成合同
    r = client.post(f"/api/v1/procurement/tenders/{tid}/generate-contract", headers=admin_headers).json()
    assert r["code"] == 96006

    # ---- 再次定标 → 审批通过 → awarded ----
    r = client.post(f"/api/v1/procurement/tenders/{tid}/award", headers=admin_headers, json={"bid_id": bid_id}).json()
    assert r["code"] == 0 and r["data"]["status"] == "awarding"
    todo = _todo_for(client, leader_headers, tid, "tender_award")
    r = client.post(
        f"/api/v1/approval/tasks/{todo[0]['id']}/approve", headers=leader_headers, json={"comment": "同意定标"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "approved"
    detail = client.get(f"/api/v1/procurement/tenders/{tid}", headers=admin_headers).json()["data"]
    assert detail["status"] == "awarded"
    assert detail["winnerBidId"] == bid_id and detail["winnerAmount"] == 44000
    assert detail["winnerName"].startswith("pt_测试公司")
    assert [x["action"] for x in detail["timeline"]] == ["start", "agree"]  # timeline 为当前实例口径

    # 门户中标公示
    pub = client.get(f"/api/v1/portal/tenders/{tid}", headers=pheaders).json()["data"]
    assert pub["status"] == "awarded" and pub["winnerName"].startswith("pt_测试公司") and pub["winnerAmount"] == 44000
    assert pub["myBid"]["isWinner"]

    # ---- 生成采购合同：供应商=绑定往来单位、金额=中标价、幂等 ----
    r = client.post(f"/api/v1/procurement/tenders/{tid}/generate-contract", headers=admin_headers).json()
    assert r["code"] == 0, r
    contract = r["data"]
    assert contract["status"] == "draft"
    assert contract["supplierId"] == supplier_id and contract["amount"] == 44000
    assert contract["requestId"] == req["id"]
    r = client.post(f"/api/v1/procurement/tenders/{tid}/generate-contract", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["id"] == contract["id"]
    detail = client.get(f"/api/v1/procurement/tenders/{tid}", headers=admin_headers).json()["data"]
    assert detail["contractId"] == contract["id"]

    # counts + q + 排序 + 导出
    counts = client.get("/api/v1/procurement/tenders/counts", headers=admin_headers).json()["data"]
    assert counts["awarded"] >= 1 and counts["all"] >= counts["awarded"]
    r = client.get("/api/v1/procurement/tenders", headers=admin_headers, params={"q": f"pt_招标A{UUID}"}).json()
    assert r["data"]["total"] == 1
    resp = client.post("/api/v1/procurement/tenders/export", headers=admin_headers)
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.active.cell(1, 1).value == "招标编号" and wb.active.max_row >= 2


def test_tender_deadline_enforced(client, admin_headers, db):
    """截止强制：报名截止后注册 96002；投标截止后（库改时间）投标 96002。"""
    from app.modules.procurement.models import TenderProject

    username = f"pt_vendor2_{UUID}"
    p = _portal_register(client, username, f"pt_公司二{UUID}")
    _approve_partner(client, admin_headers, p["id"])
    pheaders = _portal_login(client, username)

    # 报名截止已过（publish 不强制未来时间，portal 侧才强制）
    past = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    t = client.post(
        "/api/v1/procurement/tenders",
        headers=admin_headers,
        json={"name": f"pt_已过截止{UUID}", "reg_deadline": past, "bid_deadline": past},
    ).json()["data"]
    _publish(client, admin_headers, t["id"])
    r = client.post(f"/api/v1/portal/tenders/{t['id']}/register", headers=pheaders, data={}).json()
    assert r["code"] == 96002

    # 投标截止强制：正常报名审核后，把 bid_deadline 改到过去
    t2 = _mk_tender(client, admin_headers, f"pt_投标截止{UUID}")
    _publish(client, admin_headers, t2["id"])
    reg = _portal_register_tender(client, pheaders, t2["id"], with_file=False)["data"]
    client.post(
        f"/api/v1/procurement/tenders/{t2['id']}/registrations/{reg['id']}/review",
        headers=admin_headers,
        json={"approve": True},
    )
    row = db.get(TenderProject, t2["id"])
    row.bid_deadline = datetime.now() - timedelta(minutes=1)
    db.commit()
    r = client.post(f"/api/v1/portal/tenders/{t2['id']}/bid", headers=pheaders, data={"price": "1000"}).json()
    assert r["code"] == 96002

    # 终止：门户不可见
    r = client.post(f"/api/v1/procurement/tenders/{t2['id']}/terminate", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "terminated"
    r = client.get(f"/api/v1/portal/tenders/{t2['id']}", headers=pheaders).json()
    assert r["code"] == 10002


def test_cross_auth_isolation(client, admin_headers):
    """认证隔离：门户 token 调内部 → 401；内部 token 调门户 → 401；合作方只见本人数据。"""
    ua, ub = f"pt_vendorA_{UUID}", f"pt_vendorB_{UUID}"
    pa = _portal_register(client, ua, f"pt_公司A{UUID}")
    pb = _portal_register(client, ub, f"pt_公司B{UUID}")
    _approve_partner(client, admin_headers, pa["id"])
    _approve_partner(client, admin_headers, pb["id"])
    ha = _portal_login(client, ua)
    hb = _portal_login(client, ub)

    # 双向隔离
    r = client.get("/api/v1/procurement/tenders", headers=ha)
    assert r.status_code == 401
    # 门户公告为公开数据：内部 token 不被门户识别时降级为匿名浏览（my* 字段为空）
    r = client.get("/api/v1/portal/tenders", headers=admin_headers)
    assert r.status_code == 200 and r.json()["code"] == 0
    assert all(not i["myRegistrationStatus"] and i["myBidId"] is None for i in r.json()["data"]["items"])
    # 个人数据仍需门户 token
    r = client.get("/api/v1/portal/registrations", headers=admin_headers)
    assert r.status_code == 401

    # A 报名+投标；B 看不到 A 的数据
    t = _mk_tender(client, admin_headers, f"pt_隔离{UUID}")
    _publish(client, admin_headers, t["id"])
    tid = t["id"]
    reg = _portal_register_tender(client, ha, tid, with_file=False)["data"]
    client.post(
        f"/api/v1/procurement/tenders/{tid}/registrations/{reg['id']}/review",
        headers=admin_headers,
        json={"approve": True},
    )
    bid = client.post(
        f"/api/v1/portal/tenders/{tid}/bid",
        headers=ha,
        data={"price": "30000"},
        files={"file": ("方案A.pdf", b"%PDF A", "application/pdf")},
    ).json()["data"]

    bids_b = client.get("/api/v1/portal/bids", headers=hb).json()["data"]["items"]
    assert all(b["id"] != bid["id"] for b in bids_b)
    regs_b = client.get("/api/v1/portal/registrations", headers=hb).json()["data"]["items"]
    assert all(r_["id"] != reg["id"] for r_ in regs_b)

    # B 无法下载 A 的投标文件
    r = client.get(f"/api/v1/portal/bids/{bid['id']}/proposal", headers=hb).json()
    assert r["code"] == 10002
    # A 可以下载本人的
    resp = client.get(f"/api/v1/portal/bids/{bid['id']}/proposal", headers=ha)
    assert resp.status_code == 200

    # 门户详情不泄露他人投标
    d = client.get(f"/api/v1/portal/tenders/{tid}", headers=hb).json()["data"]
    assert d["myBid"] is None and d["myRegistration"] is None and "bids" not in d


def test_partner_admin_crud(client, admin_headers):
    """管理侧账号 CRUD：新建/编辑(改绑解绑)/重置密码/删除约束。"""
    suf = uuid.uuid4().hex[:8]
    supplier = _mk_supplier(client, admin_headers, f"pt_管理绑定{suf}")
    supplier2 = _mk_supplier(client, admin_headers, f"pt_管理改绑{suf}")

    # ---- 新建（直接启用 + 绑定供应商）----
    username = f"pt_admin_{suf}"
    r = client.post(
        "/api/v1/procurement/partners",
        headers=admin_headers,
        json={
            "username": username,
            "password": "Admin@12345",
            "company_name": f"pt_管理建公司{suf}",
            "contact_name": "李四",
            "phone": "13700000000",
            "customer_id": supplier["id"],
        },
    ).json()
    assert r["code"] == 0, r
    p = r["data"]
    assert p["status"] == "enabled" and p["customerId"] == supplier["id"]
    pid = p["id"]

    # 重名 → 96005；弱密码 → 422
    r = client.post(
        "/api/v1/procurement/partners",
        headers=admin_headers,
        json={"username": username, "password": "Admin@12345", "company_name": "另一家公司"},
    ).json()
    assert r["code"] == 96005
    r = client.post(
        "/api/v1/procurement/partners",
        headers=admin_headers,
        json={"username": f"pt_weak_{suf}", "password": "short", "company_name": "弱密码公司"},
    )
    assert r.status_code == 422

    # 绑定非供应商往来单位 → 95002
    cust = client.post(
        "/api/v1/crm/customers",
        headers=admin_headers,
        json={"name": f"pt_纯客户{suf}", "partner_type": "customer", "tax_no": f"913401CU{suf}"},
    ).json()["data"]
    r = client.post(
        "/api/v1/procurement/partners",
        headers=admin_headers,
        json={
            "username": f"pt_badcust_{suf}",
            "password": "Admin@12345",
            "company_name": "绑错类型",
            "customer_id": cust["id"],
        },
    ).json()
    assert r["code"] == 95002

    # 管理侧新建的账号可直接登录
    headers = _portal_login_raw(client, username, "Admin@12345")

    # ---- 编辑：改资料 + 改绑 ----
    r = client.put(
        f"/api/v1/procurement/partners/{pid}",
        headers=admin_headers,
        json={
            "company_name": f"pt_管理改公司{suf}",
            "contact_name": "王五",
            "phone": "13600000000",
            "email": "a@b.com",
            "customer_id": supplier2["id"],
        },
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["companyName"].startswith("pt_管理改公司") and r["data"]["customerId"] == supplier2["id"]

    # 显式 null 解绑
    r = client.put(
        f"/api/v1/procurement/partners/{pid}",
        headers=admin_headers,
        json={"company_name": f"pt_管理改公司{suf}", "customer_id": None},
    ).json()
    assert r["code"] == 0 and r["data"]["customerId"] is None

    # ---- 重置密码：服务端生成（仅返回一次）→ 新密码可登录 ----
    r = client.post(f"/api/v1/procurement/partners/{pid}/password", headers=admin_headers, json={}).json()
    assert r["code"] == 0, r
    gen_pwd = r["data"]["password"]
    assert len(gen_pwd) >= 8
    _portal_login_raw(client, username, gen_pwd)

    # 指定密码重置 → 旧密码失效
    r = client.post(
        f"/api/v1/procurement/partners/{pid}/password", headers=admin_headers, json={"password": "NewPass@123"}
    ).json()
    assert r["code"] == 0 and r["data"]["password"] == "NewPass@123"
    r = client.post("/api/v1/portal/auth/login", json={"username": username, "password": gen_pwd})
    assert r.status_code == 401
    _portal_login_raw(client, username, "NewPass@123")

    # ---- 删除约束：有报名记录 → 96007 ----
    t = _mk_tender(client, admin_headers, f"pt_删除约束{suf}")
    _publish(client, admin_headers, t["id"])
    reg = client.post(
        f"/api/v1/portal/tenders/{t['id']}/register", headers=headers, data={"contact_name": "李四"}
    ).json()
    assert reg["code"] == 0, reg
    r = client.delete(f"/api/v1/procurement/partners/{pid}", headers=admin_headers).json()
    assert r["code"] == 96007

    # ---- 无记录账号：可软删；删除后不可登录；用户名释放可再注册 ----
    username2 = f"pt_del_{suf}"
    p2 = client.post(
        "/api/v1/procurement/partners",
        headers=admin_headers,
        json={"username": username2, "password": "Admin@12345", "company_name": f"pt_待删公司{suf}"},
    ).json()["data"]
    r = client.delete(f"/api/v1/procurement/partners/{p2['id']}", headers=admin_headers).json()
    assert r["code"] == 0
    r = client.post("/api/v1/portal/auth/login", json={"username": username2, "password": "Admin@12345"})
    assert r.status_code == 401
    r = client.post(
        "/api/v1/procurement/partners",
        headers=admin_headers,
        json={"username": username2, "password": "Admin@12345", "company_name": f"pt_重建公司{suf}"},
    ).json()
    assert r["code"] == 0


def _portal_login_raw(client, username: str, password: str) -> dict:
    r = client.post("/api/v1/portal/auth/login", json={"username": username, "password": password}).json()
    assert r["code"] == 0, r
    return {"Authorization": f"Bearer {r['data']['access_token']}"}


def test_portal_public_anonymous(client, admin_headers):
    """公开公告：无 token 可浏览列表/详情（草稿不可见、my* 字段为空）；操作类端点仍需登录。"""
    suf = uuid.uuid4().hex[:8]
    draft = client.post("/api/v1/procurement/tenders", headers=admin_headers, json={"name": f"pt_草稿{suf}"}).json()[
        "data"
    ]
    t = _mk_tender(client, admin_headers, f"pt_公开{suf}")
    _publish(client, admin_headers, t["id"])

    # 匿名列表：不含草稿；my* 字段为空
    r = client.get("/api/v1/portal/tenders")
    assert r.status_code == 200 and r.json()["code"] == 0
    items = r.json()["data"]["items"]
    ids = [i["id"] for i in items]
    assert t["id"] in ids and draft["id"] not in ids
    mine = [i for i in items if i["id"] == t["id"]][0]
    assert mine["myRegistrationStatus"] == "" and mine["myBidId"] is None and mine["isWinner"] is False

    # 匿名详情：草稿 404；已发布 200 且 my* 为 None
    r = client.get(f"/api/v1/portal/tenders/{draft['id']}").json()
    assert r["code"] == 10002
    r = client.get(f"/api/v1/portal/tenders/{t['id']}")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["myRegistration"] is None and d["myBid"] is None and d["announcement"]

    # 匿名不可报名/投标/查个人数据
    assert client.post(f"/api/v1/portal/tenders/{t['id']}/register", data={}).status_code == 401
    assert client.post(f"/api/v1/portal/tenders/{t['id']}/bid", data={"price": "1"}).status_code == 401
    assert client.get("/api/v1/portal/registrations").status_code == 401
    assert client.get("/api/v1/portal/bids").status_code == 401

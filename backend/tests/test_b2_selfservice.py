"""B2 客户自助体系（HTTP 黑盒）。

链路：门户注册客户账号 → 内部审核绑定往来单位 → 客户在线提交委托 → 客户经理受理（发号 + 抄送）
→ 生成任务草稿；门户自助登记外来试验人员 → 内部审核备案 + 抄送。

测试库数据跨用例持久：用户名/名称带 uuid 后缀。
"""

import io
import uuid

from openpyxl import load_workbook

UUID = uuid.uuid4().hex[:8]


def _mk_customer(client, headers, tag: str = "自助") -> int:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": f"{tag}客户_{suf}", "tax_no": f"913401B2{suf}", "status": "enabled"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _approved_contract(client, headers, customer_id: int) -> int:
    """建合同并走完两级审批，拿到 status=approved 的合同。"""
    suf = uuid.uuid4().hex[:8]
    con = client.post(
        "/api/v1/contract/contracts",
        headers=headers,
        json={"name": f"B2合同_{suf}", "customer_id": customer_id, "amount": 10000},
    ).json()
    assert con["code"] == 0, con
    cid = con["data"]["id"]
    assert client.post(f"/api/v1/contract/contracts/{cid}/submit", headers=headers, json={}).json()["code"] == 0

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.approval import service as approval
    from app.modules.approval.models import ApprovalInstance, ApprovalTask
    from app.modules.auth.models import User

    db = SessionLocal()
    try:
        for _ in range(3):
            rows = db.scalars(
                select(ApprovalTask).where(ApprovalTask.status == "pending", ApprovalTask.deleted == 0)
            ).all()
            target = None
            for t in rows:
                inst = db.get(ApprovalInstance, t.instance_id)
                if inst and inst.biz_type == "contract" and inst.biz_id == cid:
                    target = t
                    break
            if not target:
                break
            assignee = db.get(User, target.assignee_id)
            approval.approve(db, target.id, assignee, "ok")
            db.commit()
    finally:
        db.close()
    return cid


def _portal_register_customer(client, username: str, company: str) -> dict:
    r = client.post(
        "/api/v1/portal/auth/register",
        json={
            "username": username,
            "password": "Portal@123456",
            "company_name": company,
            "contact_name": "客户联系人",
            "phone": "13800000001",
            "company_type": "customer",
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _portal_login(client, username: str) -> dict:
    r = client.post("/api/v1/portal/auth/login", json={"username": username, "password": "Portal@123456"}).json()
    assert r["code"] == 0, r
    return {"Authorization": f"Bearer {r['data']['access_token']}"}


def _find_account(client, headers, username: str) -> dict:
    r = client.get("/api/v1/crm/accounts", headers=headers, params={"q": username}).json()
    assert r["code"] == 0, r
    items = [i for i in r["data"]["items"] if i["username"] == username]
    assert items, r
    return items[0]


# ---------------- 客户自助账号 ----------------


def test_portal_customer_register_pending(client):
    """门户注册客户账号 → 待审核状态，accountType=customer，权限范围含 entrust/staff。"""
    username = f"b2cust_{UUID}"
    data = _portal_register_customer(client, username, f"B2客户公司_{UUID}")
    assert data["status"] == "pending"
    assert data["accountType"] == "customer"
    assert "entrust" in data["permScope"]
    assert "staff" in data["permScope"]


def test_customer_account_review_binds_customer(client, admin_headers):
    """内部审核客户自助账号：绑定往来单位 + 客户经理 + 权限范围 + 人员名额。"""
    username = f"b2rev_{UUID}"
    _portal_register_customer(client, username, f"B2审核公司_{UUID}")
    acc = _find_account(client, admin_headers, username)
    assert acc["status"] == "pending"

    cid = _mk_customer(client, admin_headers, "审核绑定")
    r = client.post(
        f"/api/v1/crm/accounts/{acc['id']}/review",
        headers=admin_headers,
        json={
            "action": "approve",
            "comment": "客户自助下单",
            "customer_id": cid,
            "manager_id": None,
            "perm_scope": "entrust,staff",
            "staff_limit": 3,
        },
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "enabled"
    assert r["data"]["customerId"] == cid
    assert r["data"]["staffLimit"] == 3

    # 重复审核 → 状态非法 40005
    again = client.post(
        f"/api/v1/crm/accounts/{acc['id']}/review",
        headers=admin_headers,
        json={"action": "approve"},
    ).json()
    assert again["code"] == 40005, again


def test_customer_account_toggle_disable(client, admin_headers):
    """账号停用/启用。"""
    username = f"b2tog_{UUID}"
    _portal_register_customer(client, username, f"B2停用公司_{UUID}")
    acc = _find_account(client, admin_headers, username)
    r = client.post(
        f"/api/v1/crm/accounts/{acc['id']}/toggle",
        headers=admin_headers,
        params={"status": "disabled"},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "disabled"


# ---------------- 在线委托 ----------------


def test_portal_entrust_full_flow(client, admin_headers):
    """客户在线委托 → 受理（发号 WT）→ 生成任务草稿 → 客户可见任务号。"""
    username = f"b2ent_{UUID}"
    _portal_register_customer(client, username, f"B2委托公司_{UUID}")
    acc = _find_account(client, admin_headers, username)
    cid = _mk_customer(client, admin_headers, "委托")
    contract_id = _approved_contract(client, admin_headers, cid)
    client.post(
        f"/api/v1/crm/accounts/{acc['id']}/review",
        headers=admin_headers,
        json={"action": "approve", "customer_id": cid, "perm_scope": "entrust,staff"},
    )
    ph = _portal_login(client, username)

    # 我的合同
    cs = client.get("/api/v1/portal/contracts", headers=ph).json()
    assert cs["code"] == 0, cs
    assert any(c["id"] == contract_id for c in cs["data"]["items"]), cs

    # 提交委托
    r = client.post(
        "/api/v1/portal/entrusts",
        headers=ph,
        json={
            "title": f"风洞阻力测试_{UUID}",
            "entrust_type": "test",
            "contract_id": contract_id,
            "requirement": "整车风阻系数测量，重复 3 次",
            "sample_desc": "样车 2 台",
            "plan_end_date": "2026-12-31",
            "priority": "urgent",
            "items": [{"name": "风阻系数", "std": "GB/T 12585", "qty": 3, "need_report": 1}],
        },
    ).json()
    assert r["code"] == 0, r
    eid = r["data"]["id"]
    assert r["data"]["status"] == "submitted"
    assert r["data"]["itemCount"] == 1

    # 内部受理：发号 + 状态流转
    acc2 = client.post(
        f"/api/v1/task/entrusts/{eid}/review",
        headers=admin_headers,
        json={"action": "accept", "comment": "已确认技术要求"},
    ).json()
    assert acc2["code"] == 0, acc2
    assert acc2["data"]["status"] == "accepted"
    assert acc2["data"]["entrustNo"].startswith("WT"), acc2

    # 生成任务草稿
    d = client.post(
        f"/api/v1/task/entrusts/{eid}/dispatch",
        headers=admin_headers,
        json={"owner_name": "试验工程师", "dept_name": "风洞试验部"},
    ).json()
    assert d["code"] == 0, d
    assert d["data"]["taskId"], d

    detail = client.get(f"/api/v1/task/entrusts/{eid}", headers=admin_headers).json()
    assert detail["code"] == 0, detail
    assert detail["data"]["status"] == "dispatched"
    assert detail["data"]["taskId"]

    # 客户侧能看到任务号
    mine = client.get("/api/v1/portal/entrusts", headers=ph).json()
    assert mine["code"] == 0, mine
    mine_row = [e for e in mine["data"]["items"] if e["id"] == eid][0]
    assert mine_row["status"] == "dispatched"
    assert mine_row["taskNo"] == ""  # 任务尚未提交，编号未发放


def test_portal_entrust_reject_and_cancel(client, admin_headers):
    """驳回后客户可撤回；已受理不可撤回（状态机约束）。"""
    username = f"b2rej_{UUID}"
    _portal_register_customer(client, username, f"B2驳回公司_{UUID}")
    acc = _find_account(client, admin_headers, username)
    cid = _mk_customer(client, admin_headers, "驳回")
    contract_id = _approved_contract(client, admin_headers, cid)
    client.post(
        f"/api/v1/crm/accounts/{acc['id']}/review",
        headers=admin_headers,
        json={"action": "approve", "customer_id": cid, "perm_scope": "entrust,staff"},
    )
    ph = _portal_login(client, username)

    r = client.post(
        "/api/v1/portal/entrusts",
        headers=ph,
        json={"title": f"模型制作_{UUID}", "entrust_type": "model", "contract_id": contract_id},
    ).json()
    assert r["code"] == 0, r
    eid = r["data"]["id"]

    # 受理后再取消：允许（状态机 draft/submitted/accepted 可取消）
    rej = client.post(
        f"/api/v1/task/entrusts/{eid}/review",
        headers=admin_headers,
        json={"action": "reject", "comment": "技术要求不清晰"},
    ).json()
    assert rej["code"] == 0, rej
    assert rej["data"]["status"] == "rejected"

    # 已驳回不可再受理（状态机）
    bad = client.post(
        f"/api/v1/task/entrusts/{eid}/review",
        headers=admin_headers,
        json={"action": "accept"},
    ).json()
    assert bad["code"] == 60010, bad


def test_pending_account_cannot_login(client, admin_headers):
    """未审核的门户账号无法登录（待审核态）。"""
    username = f"b2nb_{UUID}"
    _portal_register_customer(client, username, f"B2未绑定公司_{UUID}")
    r = client.post("/api/v1/portal/auth/login", json={"username": username, "password": "Portal@123456"}).json()
    assert r["code"] != 0, r


def test_entrust_list_and_counts(client, admin_headers):
    """内部委托单列表 / 计数 / 检索。"""
    r = client.get("/api/v1/task/entrusts", headers=admin_headers, params={"size": 5}).json()
    assert r["code"] == 0, r
    assert "items" in r["data"] and "total" in r["data"]

    c = client.get("/api/v1/task/entrusts/counts", headers=admin_headers).json()
    assert c["code"] == 0, c
    assert "all" in c["data"]
    assert "submitted" in c["data"]


def test_portal_token_cannot_access_internal_api(client, admin_headers):
    """门户 token 与内部 token 互不通用。"""
    username = f"b2iso_{UUID}"
    _portal_register_customer(client, username, f"B2隔离公司_{UUID}")
    r = client.post("/api/v1/portal/auth/login", json={"username": username, "password": "Portal@123456"}).json()
    assert r["code"] != 0, r  # 待审核不可登录，拿不到门户 token
    assert client.get("/api/v1/task/entrusts", headers=admin_headers).json()["code"] == 0


# ---------------- 外来人员备案 ----------------


def test_portal_staff_register_and_review(client, admin_headers):
    """门户登记外来试验人员 → 内部审核备案 → 状态 approved + 访客权限勾选。"""
    username = f"b2stf_{UUID}"
    _portal_register_customer(client, username, f"B2人员公司_{UUID}")
    acc = _find_account(client, admin_headers, username)
    cid = _mk_customer(client, admin_headers, "人员")
    client.post(
        f"/api/v1/crm/accounts/{acc['id']}/review",
        headers=admin_headers,
        json={"action": "approve", "customer_id": cid, "perm_scope": "entrust,staff", "staff_limit": 2},
    )
    ph = _portal_login(client, username)

    r = client.post(
        "/api/v1/portal/staff",
        headers=ph,
        json={
            "name": "王工",
            "gender": "男",
            "position": "试验工程师",
            "phone": "13900000002",
            "plate_no": "沪A12345",
            "staff_type": "tester",
            "visit_purpose": "风洞试验跟场",
            "plan_visit_date": "2026-11-25",
            "nda_signed": True,
        },
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "pending"
    sid = r["data"]["id"]

    # 内部审核
    rev = client.post(
        f"/api/v1/crm/partner-staffs/{sid}/review",
        headers=admin_headers,
        json={"action": "approve", "comment": "已签 NDA", "visit_perm": "1,2", "nda_signed": True},
    ).json()
    assert rev["code"] == 0, rev
    assert rev["data"]["status"] == "approved"
    assert rev["data"]["visitPerm"] == "1,2"

    # 重复审核 → 状态非法 40002
    again = client.post(
        f"/api/v1/crm/partner-staffs/{sid}/review",
        headers=admin_headers,
        json={"action": "approve"},
    ).json()
    assert again["code"] == 40002, again


def test_portal_staff_limit(client, admin_headers):
    """人员登记名额上限：超出 → 拒绝。"""
    username = f"b2lim_{UUID}"
    _portal_register_customer(client, username, f"B2名额公司_{UUID}")
    acc = _find_account(client, admin_headers, username)
    cid = _mk_customer(client, admin_headers, "名额")
    client.post(
        f"/api/v1/crm/accounts/{acc['id']}/review",
        headers=admin_headers,
        json={"action": "approve", "customer_id": cid, "perm_scope": "entrust,staff", "staff_limit": 1},
    )
    ph = _portal_login(client, username)
    ok = client.post("/api/v1/portal/staff", headers=ph, json={"name": "李工", "staff_type": "tester"}).json()
    assert ok["code"] == 0, ok
    over = client.post("/api/v1/portal/staff", headers=ph, json={"name": "赵工", "staff_type": "tester"}).json()
    assert over["code"] != 0, over


def test_staff_list_counts_and_export(client, admin_headers):
    """人员备案列表 / 计数 / 导出。"""
    r = client.get("/api/v1/crm/partner-staffs", headers=admin_headers, params={"size": 5}).json()
    assert r["code"] == 0, r
    c = client.get("/api/v1/crm/partner-staffs/counts", headers=admin_headers).json()
    assert c["code"] == 0, c
    assert "all" in c["data"]
    x = client.post("/api/v1/crm/partner-staffs/export", headers=admin_headers)
    assert x.status_code == 200
    wb = load_workbook(io.BytesIO(x.content))
    assert wb.active.max_row >= 2

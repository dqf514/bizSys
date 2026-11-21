"""F5：流程驱动 / 事件驱动 与「流程与事件开关」面板（HTTP）。

覆盖：
- ``GET /api/v1/admin/automation``：流程绑定清单 + 事件触发开关清单（权限强制）；
- ``PUT /api/v1/admin/automation``：流程总开关停用 → 提交审批被拒（70006），
  人工直通后门（``require_manual``）恢复；
- 未配置流程定义时按「人工审核」口径直通（pass-through）；
- 事件触发开关停用 → 跨域联动不再执行（任务开始执行不再自动推进项目状态）。
"""

import uuid

from conftest import approve_instance, post_login

BASE = "/api/v1"


def _sfx() -> str:
    return uuid.uuid4().hex[:8]


def _set_flow(client, headers, biz_type: str, enabled: bool) -> dict:
    r = client.put(
        f"{BASE}/admin/automation",
        headers=headers,
        json={"flows": [{"bizType": biz_type, "enabled": enabled}]},
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _set_event(client, headers, key: str, enabled: bool) -> dict:
    r = client.put(
        f"{BASE}/admin/automation",
        headers=headers,
        json={"events": [{"key": key, "enabled": enabled}]},
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _mk_project(client, headers) -> dict:
    suf = _sfx()
    r = client.post(
        f"{BASE}/project/projects",
        headers=headers,
        json={
            "name": f"F5项目_{suf}",
            "customer_name": f"F5客户_{suf}",
            "manager_name": "项目经理",
            "dept_name": "风洞实验室",
            "start_date": "2026-02-01",
            "end_date": "2026-06-30",
            "budget_amount": 100000,
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def _approved_contract(client, headers) -> int:
    """客户 → 合同 → 两级审批通过。"""
    suf = _sfx()
    cust = client.post(
        f"{BASE}/crm/customers",
        headers=headers,
        json={"name": f"F5客户_{suf}", "tax_no": f"913401B6{suf}", "status": "enabled"},
    ).json()
    assert cust["code"] == 0, cust
    con = client.post(
        f"{BASE}/contract/contracts",
        headers=headers,
        json={"name": f"F5合同_{suf}", "customer_id": cust["data"]["id"], "amount": 10000},
    ).json()
    assert con["code"] == 0, con
    cid = con["data"]["id"]
    assert client.post(f"{BASE}/contract/contracts/{cid}/submit", headers=headers, json={}).json()["code"] == 0
    approve_instance("contract", cid, times=2)
    return cid


def _mk_task(client, headers, contract_id: int) -> dict:
    r = client.post(
        f"{BASE}/task/tasks",
        headers=headers,
        json={"task_name": f"F5任务_{_sfx()}", "contract_id": contract_id},
    ).json()
    assert r["code"] == 0, r
    return r["data"]


# ---------------- 开关面板 ----------------


def test_automation_panel_lists_flows_and_events(client, admin_headers):
    d = client.get(f"{BASE}/admin/automation", headers=admin_headers).json()["data"]

    flows = {f["bizType"]: f for f in d["flows"]}
    for bt in ("contract", "project", "timesheet", "payment", "asset_receipt", "asset_disposal", "report_seal"):
        assert bt in flows, bt
        assert flows[bt]["switchKey"] == f"flow.{bt}.enabled"
        assert flows[bt]["enabled"] is True
        assert flows[bt]["submitFrom"]
    # 状态口径对外可见
    assert flows["payment"]["statuses"]["approved"] == "confirmed"
    assert flows["project"]["statuses"]["approved"] == "planning"
    assert flows["report_seal"]["statuses"]["approving"] == "sealing"

    events = {e["event"]: e for e in d["events"]}
    assert "TaskAssigned" in events and "ApprovalCompleted" in events and "FlowStarted" in events
    sw = {s["key"]: s for e in d["events"] for s in e["switches"]}
    assert "event.trigger.TaskAssigned.project.start" in sw
    assert sw["event.trigger.TaskAssigned.project.start"]["enabled"] is True


def test_automation_permission_required(client, admin_headers):
    """无 admin:setting 权限 → 403（读写都拦）。"""
    username = f"noauto_{_sfx()}"
    r = client.post(
        f"{BASE}/admin/users",
        headers=admin_headers,
        json={
            "username": username,
            "password": "Test@123456",
            "name": "无自动化权限",
            "status": "enabled",
            "role_ids": [],
        },
    ).json()
    assert r["code"] == 0, r
    login = post_login(client, username, "Test@123456").json()
    assert login["code"] == 0, login
    h = {"Authorization": f"Bearer {login['data']['access_token']}"}
    assert client.get(f"{BASE}/admin/automation", headers=h).status_code == 403
    resp = client.put(f"{BASE}/admin/automation", headers=h, json={"flows": []})
    assert resp.status_code == 403


def test_flow_capabilities_visible_to_logged_in_user(client, admin_headers):
    """流程能力清单：登录用户可读，供单据页决定「提交审批」还是「人工直通」。"""
    d = client.get(f"{BASE}/approval/flow-capabilities", headers=admin_headers).json()["data"]
    caps = {c["bizType"]: c for c in d["items"]}
    for bt in ("contract", "project", "timesheet", "payment", "asset_receipt", "asset_disposal", "report_seal"):
        assert bt in caps, bt
        assert caps[bt]["enabled"] is True
        assert caps[bt]["submitFrom"]
        assert caps[bt]["statuses"]["approved"]
    assert caps["project"]["statuses"]["approved"] == "planning"
    assert caps["report_seal"]["statuses"]["approving"] == "sealing"


def test_payment_counts_endpoint(client, admin_headers):
    """回款状态页签计数（F5：到账登记 → 复核 → 确认）。"""
    counts = client.get(f"{BASE}/finance/payments/counts", headers=admin_headers).json()["data"]
    for k in ("all", "draft", "approving", "confirmed", "rejected"):
        assert k in counts, counts
    assert counts["all"] == sum(counts[k] for k in ("draft", "approving", "confirmed", "rejected"))


# ---------------- 流程总开关 ----------------


def test_flow_switch_off_blocks_submit(client, admin_headers):
    """流程总开关停用 → 提交审批被拒（70006）；恢复后可提交。"""
    p = _mk_project(client, admin_headers)
    pid = p["id"]
    try:
        _set_flow(client, admin_headers, "project", False)
        r = client.post(f"{BASE}/project/projects/{pid}/submit", headers=admin_headers).json()
        assert r["code"] == 70006, r
        # 面板上开关确实是关的
        d = client.get(f"{BASE}/admin/automation", headers=admin_headers).json()["data"]
        assert {f["bizType"]: f for f in d["flows"]}["project"]["enabled"] is False
    finally:
        _set_flow(client, admin_headers, "project", True)

    r = client.post(f"{BASE}/project/projects/{pid}/submit", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "approving", r


def test_flow_switch_off_reopens_manual_backdoor(client, admin_headers):
    """人工直通后门：流程启用时被拦截（70005），流程停用后恢复直通。"""
    wh = client.post(
        f"{BASE}/asset/warehouses",
        headers=admin_headers,
        json={"code": f"WH-{_sfx()}", "name": f"F5仓库_{_sfx()}", "address": "A区"},
    ).json()["data"]
    item = client.post(
        f"{BASE}/asset/items",
        headers=admin_headers,
        json={"code": f"IT-{_sfx()}", "name": "F5存货", "unit": "个", "unitPrice": 12.5},
    ).json()["data"]
    rc = client.post(
        f"{BASE}/asset/receipts",
        headers=admin_headers,
        json={
            "warehouseId": wh["id"],
            "items": [{"itemId": item["id"], "itemName": item["name"], "quantity": 2, "qualifiedQty": 2}],
        },
    ).json()["data"]

    try:
        # 流程启用：人工直确认被拦截
        r = client.post(f"{BASE}/asset/receipts/{rc['id']}/accept", headers=admin_headers).json()
        assert r["code"] == 70005, r
        # 流程停用：恢复人工直通
        _set_flow(client, admin_headers, "asset_receipt", False)
        r = client.post(f"{BASE}/asset/receipts/{rc['id']}/accept", headers=admin_headers).json()
        assert r["code"] == 0 and r["data"]["status"] == "accepted", r
    finally:
        _set_flow(client, admin_headers, "asset_receipt", True)


def test_missing_definition_falls_back_to_pass_through(client, admin_headers):
    """未配置启用的流程定义 → 按人工审核口径直通（不再等待审批）。"""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.approval.models import ApprovalDefinition

    db = SessionLocal()
    try:
        d = db.scalar(
            select(ApprovalDefinition).where(
                ApprovalDefinition.code == "project_approve", ApprovalDefinition.deleted == 0
            )
        )
        assert d is not None, "种子应已登记 project_approve 流程定义"
        old = d.enabled
        d.enabled = 0
        db.commit()
    finally:
        db.close()

    p = _mk_project(client, admin_headers)
    try:
        r = client.post(f"{BASE}/project/projects/{p['id']}/submit", headers=admin_headers).json()
        assert r["code"] == 0 and r["data"]["status"] == "planning", r
    finally:
        db = SessionLocal()
        try:
            d = db.scalar(
                select(ApprovalDefinition).where(
                    ApprovalDefinition.code == "project_approve", ApprovalDefinition.deleted == 0
                )
            )
            if d is not None:
                d.enabled = old
            db.commit()
        finally:
            db.close()


# ---------------- 事件触发开关 ----------------


def test_event_switch_off_disables_cross_domain_link(client, admin_headers):
    """事件触发开关停用 → 跨域联动不再执行（任务开始执行不再自动推进项目状态）。"""
    key = "event.trigger.TaskAssigned.project.start"
    cid = _approved_contract(client, admin_headers)
    p = _mk_project(client, admin_headers)
    pid = p["id"]

    # 立项审批通过 → planning
    assert client.post(f"{BASE}/project/projects/{pid}/submit", headers=admin_headers).json()["code"] == 0
    approve_instance("project", pid, times=2)
    cur = client.get(f"{BASE}/project/projects/{pid}", headers=admin_headers).json()["data"]
    assert cur["status"] == "planning", cur

    # 任务挂进项目甘特
    t1 = _mk_task(client, admin_headers, cid)
    r = client.post(
        f"{BASE}/project/projects/{pid}/generate-tasks",
        headers=admin_headers,
        json={"task_ids": [t1["id"]]},
    ).json()
    assert r["code"] == 0, r

    try:
        _set_event(client, admin_headers, key, False)
        assert client.post(f"{BASE}/task/tasks/{t1['id']}/submit", headers=admin_headers).json()["code"] == 0
        cur = client.get(f"{BASE}/project/projects/{pid}", headers=admin_headers).json()["data"]
        assert cur["status"] == "planning", cur  # 联动已停用，项目不被自动推进
    finally:
        _set_event(client, admin_headers, key, True)

    # 开关恢复后，同类联动重新生效
    t2 = _mk_task(client, admin_headers, cid)
    assert client.post(
        f"{BASE}/project/projects/{pid}/generate-tasks",
        headers=admin_headers,
        json={"task_ids": [t2["id"]]},
    ).json()["code"] == 0
    assert client.post(f"{BASE}/task/tasks/{t2['id']}/submit", headers=admin_headers).json()["code"] == 0
    cur = client.get(f"{BASE}/project/projects/{pid}", headers=admin_headers).json()["data"]
    assert cur["status"] == "executing", cur

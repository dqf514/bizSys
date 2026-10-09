"""合同主链路（HTTP）：客户 → 合同 → 提交 → 两级审批 → 已通过 → 导出。"""

import io
import uuid

from openpyxl import load_workbook

UUID = uuid.uuid4().hex[:8]


def _create_customer(client, headers):
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={
            "name": f"测试客户_{UUID}",
            "tax_no": f"913401TEST{UUID}",
            "customer_type": "enterprise",
            "grade": "A",
            "status": "enabled",
        },
    ).json()
    assert r["code"] == 0, r
    return r["data"]


def test_contract_full_flow(client, admin_headers, manager_headers, leader_headers):
    cust = _create_customer(client, admin_headers)

    # 税号重复 40001
    r = client.post(
        "/api/v1/crm/customers", headers=admin_headers, json={"name": "dup", "tax_no": f"913401TEST{UUID}"}
    ).json()
    assert r["code"] == 40001

    # 建合同
    r = client.post(
        "/api/v1/contract/contracts",
        headers=admin_headers,
        json={
            "name": f"合同_{UUID}",
            "customer_id": cust["id"],
            "contract_type": "service",
            "amount": 50000,
            "start_date": "2026-10-01",
            "end_date": "2027-09-30",
        },
    ).json()
    assert r["code"] == 0, r
    cid = r["data"]["id"]
    assert r["data"]["contractNo"].startswith("HT")

    # 提交审批
    r = client.post(f"/api/v1/contract/contracts/{cid}/submit", headers=admin_headers, json={"comment": "审批"}).json()
    assert r["code"] == 0 and r["data"]["status"] == "approving"

    # 审批中禁编辑 50002
    r = client.put(
        f"/api/v1/contract/contracts/{cid}",
        headers=admin_headers,
        json={"name": "x", "customer_id": cust["id"], "version": 1},
    ).json()
    assert r["code"] == 50002

    # manager1 同意
    page = client.get("/api/v1/approval/tasks", headers=manager_headers, params={"tab": "todo"}).json()
    todo = [i for i in page["data"]["items"] if i["bizId"] == cid]
    assert todo
    r = client.post(
        f"/api/v1/approval/tasks/{todo[0]['id']}/approve", headers=manager_headers, json={"comment": "ok"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "running"

    # leader1 同意
    page = client.get("/api/v1/approval/tasks", headers=leader_headers, params={"tab": "todo"}).json()
    todo = [i for i in page["data"]["items"] if i["bizId"] == cid]
    assert todo
    r = client.post(
        f"/api/v1/approval/tasks/{todo[0]['id']}/approve", headers=leader_headers, json={"comment": "ok"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "approved"

    # 合同已通过 + 时间线
    r = client.get(f"/api/v1/contract/contracts/{cid}", headers=admin_headers).json()
    assert r["data"]["status"] == "approved"
    assert [x["action"] for x in r["data"]["timeline"]] == ["start", "agree", "agree"]

    # options 可见
    opts = client.get("/api/v1/contract/contracts/options", headers=admin_headers).json()["data"]
    assert any(o["id"] == cid for o in opts)

    # 导出
    resp = client.post("/api/v1/contract/contracts/export", headers=admin_headers)
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.active.max_row >= 2

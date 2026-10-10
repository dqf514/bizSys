"""客户详情 + 汇总（GET /crm/customers/{id}），联系人字段与下拉扩展字段。"""

import uuid


def test_customer_detail_summary(client, admin_headers):
    headers = admin_headers
    suf = uuid.uuid4().hex[:8]

    # 创建客户（含联系人），响应带回联系人字段
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={
            "name": f"详情客户_{suf}",
            "tax_no": f"913401DTL{suf}",
            "pay_org": f"付款单位_{suf}",
            "contact_person": "张三",
            "contact_phone": "13800000000",
            "status": "enabled",
        },
    ).json()
    assert r["code"] == 0, r
    cid = r["data"]["id"]
    assert r["data"]["contactPerson"] == "张三" and r["data"]["contactPhone"] == "13800000000"

    # 更新联系人
    r = client.put(
        f"/api/v1/crm/customers/{cid}",
        headers=headers,
        json={"name": f"详情客户_{suf}", "tax_no": f"913401DTL{suf}", "pay_org": f"付款单位_{suf}",
              "contact_person": "李四", "contact_phone": "13900000000", "status": "enabled"},
    ).json()
    assert r["code"] == 0 and r["data"]["contactPerson"] == "李四", r

    # 下拉扩展字段：payOrg/taxNo/contactPerson/contactPhone（id/label/sub 不变）
    opts = client.get("/api/v1/crm/customers/options", headers=headers, params={"q": f"详情客户_{suf}"}).json()["data"]
    opt = next(o for o in opts if o["id"] == cid)
    assert opt["label"] == f"详情客户_{suf}" and opt["sub"]
    assert opt["payOrg"] == f"付款单位_{suf}" and opt["taxNo"] == f"913401DTL{suf}"
    assert opt["contactPerson"] == "李四" and opt["contactPhone"] == "13900000000"

    # 一份草稿合同 → contractCount/contractTotal
    r = client.post(
        "/api/v1/contract/contracts",
        headers=headers,
        json={"name": f"详情合同_{suf}", "customer_id": cid, "amount": 5000,
              "contact_person": "王五", "contact_phone": "13700000000"},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["contactPerson"] == "王五" and r["data"]["contactPhone"] == "13700000000"

    # 详情 + 汇总
    d = client.get(f"/api/v1/crm/customers/{cid}", headers=headers).json()["data"]
    assert d["id"] == cid and d["contactPerson"] == "李四"
    s = d["summary"]
    assert s["contractCount"] == 1 and s["contractTotal"] == 5000.0
    assert s["taskCount"] == 0 and s["settledTotal"] == 0.0 and s["paidTotal"] == 0.0

    # 不存在 → 10002
    assert client.get("/api/v1/crm/customers/99999999", headers=headers).json()["code"] == 10002

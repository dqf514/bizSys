"""往来单位详情增强（HTTP）：联系人 CRUD/主联系人唯一、附件上传下载删除/魔数校验、供应商采购清单、越权。

测试库数据跨用例持久：业务数据带 pt_ 前缀 + 唯一后缀。
"""

import uuid

UUID = uuid.uuid4().hex[:8]

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.4 fake content"


def _login(client, username: str, password: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    data = r.json()
    assert data["code"] == 0, data
    return {"Authorization": f"Bearer {data['data']['access_token']}"}


def _create_user(client, admin_headers, role_ids: list[int]) -> dict:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": f"pt_{suf}", "password": "Test@123456", "name": "往来详情", "status": "enabled",
              "role_ids": role_ids},
    ).json()
    assert r["code"] == 0, r
    return _login(client, f"pt_{suf}", "Test@123456")


def _mk_partner(client, headers, partner_type="supplier") -> int:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": f"pt_单位_{suf}", "partner_type": partner_type, "tax_no": f"9134PT{suf}".upper()},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


# ---------------- 联系人 ----------------


def test_contact_crud_and_primary_unique(client, admin_headers):
    """联系人增改删查；设置主要联系人自动取消同单位其他主联系人。"""
    cid = _mk_partner(client, admin_headers)

    r = client.post(f"/api/v1/crm/customers/{cid}/contacts", headers=admin_headers,
                    json={"name": "张三", "position": "经理", "phone": "13800000001", "is_primary": True}).json()
    assert r["code"] == 0, r
    c1 = r["data"]
    assert c1["isPrimary"] is True

    r = client.post(f"/api/v1/crm/customers/{cid}/contacts", headers=admin_headers,
                    json={"name": "李四", "email": "lisi@example.com", "is_primary": True}).json()
    assert r["code"] == 0, r
    c2 = r["data"]

    # 主联系人唯一：c1 被取消
    r = client.get(f"/api/v1/crm/customers/{cid}/contacts", headers=admin_headers).json()
    assert r["code"] == 0, r
    items = {x["id"]: x for x in r["data"]["items"]}
    assert items[c1["id"]]["isPrimary"] is False
    assert items[c2["id"]]["isPrimary"] is True
    # 主联系人排最前
    assert r["data"]["items"][0]["id"] == c2["id"]

    # 编辑（取消主联系人）
    r = client.put(f"/api/v1/crm/contacts/{c2['id']}", headers=admin_headers,
                   json={"name": "李四", "phone": "13900000002", "is_primary": False}).json()
    assert r["code"] == 0, r
    assert r["data"]["isPrimary"] is False and r["data"]["phone"] == "13900000002"

    # 删除
    assert client.delete(f"/api/v1/crm/contacts/{c1['id']}", headers=admin_headers).json()["code"] == 0
    r = client.get(f"/api/v1/crm/customers/{cid}/contacts", headers=admin_headers).json()
    assert r["data"]["total"] == 1

    # 非法单位 404
    assert client.post("/api/v1/crm/customers/99999999/contacts", headers=admin_headers,
                       json={"name": "王五"}).json()["code"] != 0


# ---------------- 附件 ----------------


def test_attachment_upload_download_delete(client, admin_headers):
    """附件：上传（魔数/扩展名校验）→ 分类筛选 → 下载字节一致 → 删除后 404。"""
    cid = _mk_partner(client, admin_headers)

    # 伪装扩展名（png 后缀但内容非 PNG）→ 魔数拦截
    r = client.post(f"/api/v1/crm/customers/{cid}/attachments", headers=admin_headers,
                    files={"file": ("fake.png", b"not-a-png", "image/png")}, data={"category": "license"})
    assert r.json()["code"] == 10001

    # 白名单外扩展名
    r = client.post(f"/api/v1/crm/customers/{cid}/attachments", headers=admin_headers,
                    files={"file": ("evil.exe", b"MZ90", "application/octet-stream")}, data={"category": "other"})
    assert r.json()["code"] == 10001

    # 非法分类
    r = client.post(f"/api/v1/crm/customers/{cid}/attachments", headers=admin_headers,
                    files={"file": ("a.png", PNG_BYTES, "image/png")}, data={"category": "bogus"})
    assert r.json()["code"] == 10001

    # 正常上传两类
    r = client.post(f"/api/v1/crm/customers/{cid}/attachments", headers=admin_headers,
                    files={"file": ("pt_营业执照.png", PNG_BYTES, "image/png")},
                    data={"category": "license", "remark": "pt_年检版"}).json()
    assert r["code"] == 0, r
    a1 = r["data"]
    assert a1["category"] == "license" and a1["size"] == len(PNG_BYTES) and a1["uploaderName"]
    r = client.post(f"/api/v1/crm/customers/{cid}/attachments", headers=admin_headers,
                    files={"file": ("pt_资质.pdf", PDF_BYTES, "application/pdf")}, data={"category": "qualification"})
    assert r.json()["code"] == 0

    # 分类筛选
    r = client.get(f"/api/v1/crm/customers/{cid}/attachments", headers=admin_headers).json()
    assert r["data"]["total"] == 2
    r = client.get(f"/api/v1/crm/customers/{cid}/attachments", headers=admin_headers,
                   params={"category": "license"}).json()
    assert r["data"]["total"] == 1 and r["data"]["items"][0]["id"] == a1["id"]

    # 下载字节一致
    r = client.get(f"/api/v1/crm/attachments/{a1['id']}", headers=admin_headers)
    assert r.status_code == 200 and r.content == PNG_BYTES

    # 删除（逻辑删 + 磁盘清理）→ 再下载 404
    assert client.delete(f"/api/v1/crm/attachments/{a1['id']}", headers=admin_headers).json()["code"] == 0
    r = client.get(f"/api/v1/crm/attachments/{a1['id']}", headers=admin_headers)
    assert r.json()["code"] == 10002
    r = client.get(f"/api/v1/crm/customers/{cid}/attachments", headers=admin_headers).json()
    assert r["data"]["total"] == 1


# ---------------- 越权 ----------------


def test_perm_guards(client, admin_headers):
    """无 crm:customer:edit → 联系人/附件写操作 403；无 procurement:contract:list → 采购清单 403。"""
    cid = _mk_partner(client, admin_headers)
    no_perm = _create_user(client, admin_headers, [])
    r = client.post(f"/api/v1/crm/customers/{cid}/contacts", headers=no_perm, json={"name": "张三"})
    assert r.status_code == 403
    r = client.post(f"/api/v1/crm/customers/{cid}/attachments", headers=no_perm,
                    files={"file": ("a.png", PNG_BYTES, "image/png")})
    assert r.status_code == 403
    r = client.get(f"/api/v1/crm/customers/{cid}/procurement", headers=no_perm)
    assert r.status_code == 403
    # 列表/下载同样需要 crm:customer:list
    assert client.get(f"/api/v1/crm/customers/{cid}/contacts", headers=no_perm).status_code == 403


# ---------------- 供应商采购清单 + 统计 ----------------


def test_procurement_overview_and_summary(client, admin_headers):
    """采购清单端点返回该供应商的合同与其关联申请；详情 summary 带采购指标。"""
    cid = _mk_partner(client, admin_headers)

    # 申请 → 合同（draft 即入清单）
    r = client.post("/api/v1/procurement/requests", headers=admin_headers,
                    json={"title": f"pt_申请_{UUID}", "items": [{"itemName": "pt_物资", "quantity": 1}]}).json()
    assert r["code"] == 0, r
    rid = r["data"]["id"]
    r = client.post("/api/v1/procurement/contracts", headers=admin_headers,
                    json={"name": f"pt_合同_{UUID}", "supplier_id": cid, "request_id": rid, "amount": 66000}).json()
    assert r["code"] == 0, r
    pcid = r["data"]["id"]

    r = client.get(f"/api/v1/crm/customers/{cid}/procurement", headers=admin_headers).json()
    assert r["code"] == 0, r
    contracts = r["data"]["contracts"]
    assert any(c["id"] == pcid and c["amount"] == 66000 for c in contracts)
    requests = r["data"]["requests"]
    assert any(q["id"] == rid and q["title"] == f"pt_申请_{UUID}" for q in requests)

    # summary 带供应商指标
    r = client.get(f"/api/v1/crm/customers/{cid}", headers=admin_headers).json()
    assert r["code"] == 0, r
    s = r["data"]["summary"]
    assert s["purchaseContractCount"] >= 1 and s["purchaseTotal"] >= 66000

    # 纯客户类型单位为 0
    cid2 = _mk_partner(client, admin_headers, partner_type="customer")
    r = client.get(f"/api/v1/crm/customers/{cid2}", headers=admin_headers).json()
    assert r["data"]["summary"]["purchaseContractCount"] == 0
    r = client.get(f"/api/v1/crm/customers/{cid2}/procurement", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["contracts"] == []

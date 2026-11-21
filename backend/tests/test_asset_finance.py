"""资产与库存域 · 资产财务与样件/工具（样车样件台账、样件出借归还、资产折旧与价值、处置与报废、工具领用归还）HTTP 全链。

数据前缀 af_；每条用例的编码带 uuid4().hex[:8] 后缀（测试库跨次运行残留）。
覆盖：CRUD、编码重复、借还状态机（未归还不可再借/不可删、归还回写实物状态）、
处置状态机（draft→approved→done，处置完成回写资产状态）、折旧计提（重复期间拦截、报废资产不可计提）、
逾期计算态（借出中 + 应归还日 < 今天）、导出。

F5：资产处置改为流程驱动 —— 人工直批被拦截（70005），必须提交审批通过才可核销。
"""

import uuid
from datetime import date, timedelta

from conftest import approve_instance

BASE = "/api/v1/asset"


def _sfx() -> str:
    return uuid.uuid4().hex[:8]


def _mk_prototype(client, headers, **kw) -> dict:
    body = {"code": f"af_PT-{_sfx()}", "name": "as_样车样件", "kind": "vehicle", "model": "M1", "value": 100000}
    body.update(kw)
    r = client.post(f"{BASE}/prototypes", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def _mk_asset(client, headers, **kw) -> dict:
    body = {
        "assetNo": f"af_FA-{_sfx()}",
        "name": "as_固定资产",
        "category": "equipment",
        "originalValue": 12000,
        "salvageRate": 0.05,
        "usefulLifeMonths": 60,
        "purchaseDate": "2025-01-01",
    }
    body.update(kw)
    r = client.post(f"{BASE}/assets", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def _mk_tool(client, headers, **kw) -> dict:
    body = {"toolNo": f"af_TL-{_sfx()}", "name": "as_工具", "spec": "通用", "unit": "把", "value": 500}
    body.update(kw)
    r = client.post(f"{BASE}/tools", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


# ---------------- 样车样件台账 ----------------


def test_prototype_crud(client, admin_headers):
    """样件台账 CRUD + 编号重复拦截 + 下拉全集 + 计数。"""
    p = _mk_prototype(client, admin_headers)
    assert p["status"] == "in_stock"
    assert p["kindText"]

    # 编号重复
    r = client.post(
        f"{BASE}/prototypes", headers=admin_headers, json={"code": p["code"], "name": "重复"}
    ).json()
    assert r["code"] == 97004, r

    # 列表检索
    r = client.get(f"{BASE}/prototypes", headers=admin_headers, params={"q": p["code"]}).json()
    assert r["code"] == 0 and r["data"]["total"] == 1, r

    # 下拉全集
    r = client.get(f"{BASE}/prototypes/all", headers=admin_headers).json()
    assert r["code"] == 0 and any(x["id"] == p["id"] for x in r["data"]), r

    # 计数
    r = client.get(f"{BASE}/prototypes/counts", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["all"] >= 1, r

    # 修改
    r = client.put(
        f"{BASE}/prototypes/{p['id']}",
        headers=admin_headers,
        json={
            "code": p["code"],
            "name": "as_样车样件_改名",
            "kind": "part",
            "status": "maintenance",
            "version": p["version"],
        },
    ).json()
    assert r["code"] == 0 and r["data"]["name"] == "as_样车样件_改名", r
    assert r["data"]["status"] == "maintenance"

    # 删除
    r = client.delete(f"{BASE}/prototypes/{p['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r
    r = client.get(f"{BASE}/prototypes/{p['id']}", headers=admin_headers).json()
    assert r["code"] == 10002, r


def test_prototype_loan_lifecycle(client, admin_headers):
    """样件借出→样件状态变 loaned→归还→回 in_stock；未归还不可再借（97007）。"""
    p = _mk_prototype(client, admin_headers)

    r = client.post(
        f"{BASE}/prototype-loans",
        headers=admin_headers,
        json={"prototypeId": p["id"], "borrowerName": "as_借用人", "dueDate": "2026-12-31", "purpose": "as_路试"},
    ).json()
    assert r["code"] == 0, r
    loan = r["data"]
    assert loan["status"] == "borrowed"
    assert loan["prototypeCode"] == p["code"]

    # 样件状态随借出变为 loaned
    r = client.get(f"{BASE}/prototypes/{p['id']}", headers=admin_headers).json()
    assert r["data"]["status"] == "loaned", r
    assert len(r["data"]["loans"]) == 1

    # 未归还不可再借
    r = client.post(
        f"{BASE}/prototype-loans", headers=admin_headers, json={"prototypeId": p["id"]}
    ).json()
    assert r["code"] == 97007, r

    # 已归还的记录只读：先借出第二次是不可能的，故验证删除/编辑受状态约束
    r = client.post(f"{BASE}/prototype-loans/{loan['id']}/return", headers=admin_headers, json={}).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "returned"
    assert r["data"]["returnDate"]

    # 归还后样件回到 in_stock
    r = client.get(f"{BASE}/prototypes/{p['id']}", headers=admin_headers).json()
    assert r["data"]["status"] == "in_stock", r

    # 已归还记录不可编辑/删除
    r = client.put(
        f"{BASE}/prototype-loans/{loan['id']}",
        headers=admin_headers,
        json={"prototypeId": p["id"], "version": r["data"]["loans"][0]["version"]},
    ).json()
    assert r["code"] == 97001, r
    r = client.delete(f"{BASE}/prototype-loans/{loan['id']}", headers=admin_headers).json()
    assert r["code"] == 97001, r

    # 归还后可以再次借出
    r = client.post(
        f"{BASE}/prototype-loans", headers=admin_headers, json={"prototypeId": p["id"]}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "borrowed", r


def test_prototype_loan_overdue(client, admin_headers):
    """逾期是计算态：借出中 + 应归还日早于今天 → counts.overdue 与状态文案。"""
    p = _mk_prototype(client, admin_headers)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    loan = client.post(
        f"{BASE}/prototype-loans",
        headers=admin_headers,
        json={"prototypeId": p["id"], "dueDate": yesterday},
    ).json()["data"]

    r = client.get(f"{BASE}/prototype-loans/counts", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["overdue"] >= 1
    assert r["data"]["borrowed"] >= 1

    # 状态列仍是 borrowed，文案体现逾期
    r = client.get(f"{BASE}/prototype-loans/{loan['id']}", headers=admin_headers).json()
    assert r["data"]["status"] == "borrowed"
    assert "逾期" in r["data"]["statusText"], r["data"]["statusText"]

    # 前端「逾期」页签的取数口径：filters[status]=borrowed + range[due_date] 上界
    r = client.get(
        f"{BASE}/prototype-loans",
        headers=admin_headers,
        params={"filters[status]": "borrowed", "range[due_date]": f"|{yesterday}"},
    ).json()
    assert r["code"] == 0, r
    assert any(x["id"] == loan["id"] for x in r["data"]["items"]), r["data"]["items"]


# ---------------- 资产折旧与价值 ----------------


def test_fixed_asset_crud(client, admin_headers):
    """固定资产 CRUD + 编号重复 + 净值随折旧回写。"""
    a = _mk_asset(client, admin_headers)
    assert a["status"] == "in_use"
    # 净值口径：原值 - 累计折旧 - 残值（12000 - 0 - 12000*0.05）
    assert a["netValue"] == 11400
    assert a["accumDepreciation"] == 0

    # 编号重复
    r = client.post(
        f"{BASE}/assets", headers=admin_headers, json={"assetNo": a["assetNo"], "name": "重复"}
    ).json()
    assert r["code"] == 97004, r

    # 列表检索 + 计数
    r = client.get(f"{BASE}/assets", headers=admin_headers, params={"q": a["assetNo"]}).json()
    assert r["code"] == 0 and r["data"]["total"] == 1, r
    r = client.get(f"{BASE}/assets/counts", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["all"] >= 1, r

    # 修改
    r = client.put(
        f"{BASE}/assets/{a['id']}",
        headers=admin_headers,
        json={
            "assetNo": a["assetNo"],
            "name": "as_固定资产_改名",
            "originalValue": 12000,
            "salvageRate": 0.05,
            "usefulLifeMonths": 60,
            "status": "idle",
            "version": a["version"],
        },
    ).json()
    assert r["code"] == 0 and r["data"]["name"] == "as_固定资产_改名", r
    assert r["data"]["status"] == "idle"

    # 删除
    r = client.delete(f"{BASE}/assets/{a['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r
    r = client.get(f"{BASE}/assets/{a['id']}", headers=admin_headers).json()
    assert r["code"] == 97002, r


def test_asset_depreciation(client, admin_headers):
    """计提折旧：写折旧记录 + 回写累计折旧与净值；重复期间拦截（97001）。"""
    a = _mk_asset(client, admin_headers)

    r = client.post(
        f"{BASE}/assets/{a['id']}/depreciate",
        headers=admin_headers,
        json={"period": "2025-01", "method": "straight_line"},
    ).json()
    assert r["code"] == 0, r
    dep = r["data"]
    # (12000 - 12000*0.05) / 60 = 190
    assert dep["amount"] == 190, dep
    assert dep["accumAmount"] == 190
    assert dep["netValue"] == 12000 - 190 - 600
    assert dep["methodText"]

    # 同一期间不可重复计提
    r = client.post(
        f"{BASE}/assets/{a['id']}/depreciate",
        headers=admin_headers,
        json={"period": "2025-01", "method": "straight_line"},
    ).json()
    assert r["code"] == 97001, r

    # 资产侧回写
    r = client.get(f"{BASE}/assets/{a['id']}", headers=admin_headers).json()
    assert r["data"]["accumDepreciation"] == 190, r
    assert r["data"]["netValue"] == 11210
    assert len(r["data"]["depreciations"]) == 1

    # 下一期
    r = client.post(
        f"{BASE}/assets/{a['id']}/depreciate",
        headers=admin_headers,
        json={"period": "2025-02", "method": "straight_line"},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["amount"] == 186.83, r

    # 折旧列表按资产过滤
    r = client.get(
        f"{BASE}/depreciations", headers=admin_headers, params={"filters[asset_id]": a["id"]}
    ).json()
    assert r["code"] == 0 and r["data"]["total"] == 2, r


def test_scrapped_asset_cannot_depreciate(client, admin_headers):
    """已报废资产不能计提折旧（97001）。"""
    a = _mk_asset(client, admin_headers)
    r = client.put(
        f"{BASE}/assets/{a['id']}",
        headers=admin_headers,
        json={
            "assetNo": a["assetNo"],
            "name": a["name"],
            "originalValue": 12000,
            "salvageRate": 0.05,
            "usefulLifeMonths": 60,
            "status": "scrapped",
            "version": a["version"],
        },
    ).json()
    assert r["code"] == 0, r
    r = client.post(
        f"{BASE}/assets/{a['id']}/depreciate",
        headers=admin_headers,
        json={"period": "2025-01"},
    ).json()
    assert r["code"] == 97001, r


def test_manual_depreciation_crud(client, admin_headers):
    """手工补录折旧记录（补录历史期间）→ 同样回写累计折旧与净值，可改可删。"""
    a = _mk_asset(client, admin_headers)
    r = client.post(
        f"{BASE}/depreciations",
        headers=admin_headers,
        json={
            "assetId": a["id"],
            "period": "2024-12",
            "amount": 300,
            "method": "straight_line",
        },
    ).json()
    assert r["code"] == 0, r
    dep = r["data"]
    assert dep["amount"] == 300 and dep["netValue"] == 12000 - 300 - 600

    # 重复期间
    r = client.post(
        f"{BASE}/depreciations",
        headers=admin_headers,
        json={"assetId": a["id"], "period": "2024-12", "amount": 100},
    ).json()
    assert r["code"] == 97001, r

    # 修改
    r = client.put(
        f"{BASE}/depreciations/{dep['id']}",
        headers=admin_headers,
        json={
            "assetId": a["id"],
            "period": "2024-12",
            "amount": 400,
            "method": "straight_line",
            "version": dep["version"],
        },
    ).json()
    assert r["code"] == 0 and r["data"]["amount"] == 400, r
    assert r["data"]["accumAmount"] == 400

    # 删除
    r = client.delete(f"{BASE}/depreciations/{dep['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r


# ---------------- 处置与报废 ----------------


def test_disposal_state_machine(client, admin_headers):
    """处置单 draft→approved→done；完成后资产状态置为 scrapped；未完结处置单挡资产删除。"""
    a = _mk_asset(client, admin_headers)

    r = client.post(
        f"{BASE}/disposals",
        headers=admin_headers,
        json={
            "assetId": a["id"],
            "disposalType": "scrap",
            "applyDate": "2026-11-01",
            "disposalAmount": 1000,
            "reason": "as_老化报废",
        },
    ).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["status"] == "draft"
    assert d["assetNo"] == a["assetNo"]
    assert d["originalValue"] == 12000

    # 同一资产不能重复挂未完结处置单
    r = client.post(
        f"{BASE}/disposals", headers=admin_headers, json={"assetId": a["id"], "disposalType": "scrap"}
    ).json()
    assert r["code"] == 97001, r

    # 未完结处置单 → 资产不可删除
    r = client.delete(f"{BASE}/assets/{a['id']}", headers=admin_headers).json()
    assert r["code"] == 97001, r

    # 批准（F5：处置走审批，人工直批是后门被拦截）
    r = client.post(f"{BASE}/disposals/{d['id']}/approve", headers=admin_headers).json()
    assert r["code"] == 70005, r
    r = client.post(f"{BASE}/disposals/{d['id']}/submit", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "approving", r
    approve_instance("asset_disposal", d["id"], times=2)  # 部门负责人 → 分管领导
    r = client.get(f"{BASE}/disposals/{d['id']}", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "approved", r

    # 已批准不可编辑/删除
    r = client.put(
        f"{BASE}/disposals/{d['id']}",
        headers=admin_headers,
        json={"assetId": a["id"], "disposalType": "sell", "version": d["version"]},
    ).json()
    assert r["code"] == 97001, r
    r = client.delete(f"{BASE}/disposals/{d['id']}", headers=admin_headers).json()
    assert r["code"] == 97001, r

    # 完成处置 → 资产报废
    r = client.post(f"{BASE}/disposals/{d['id']}/complete", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "done", r
    r = client.get(f"{BASE}/assets/{a['id']}", headers=admin_headers).json()
    assert r["data"]["status"] == "scrapped", r
    assert len(r["data"]["disposals"]) == 1

    # 处置单计数
    r = client.get(f"{BASE}/disposals/counts", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["done"] >= 1, r


def test_disposal_transfer_keeps_asset_idle(client, admin_headers):
    """调拨类处置完成后资产状态为 idle（不报废）。"""
    a = _mk_asset(client, admin_headers)
    d = client.post(
        f"{BASE}/disposals",
        headers=admin_headers,
        json={"assetId": a["id"], "disposalType": "transfer"},
    ).json()["data"]
    assert client.post(f"{BASE}/disposals/{d['id']}/submit", headers=admin_headers).json()["code"] == 0
    approve_instance("asset_disposal", d["id"], times=2)
    assert client.post(f"{BASE}/disposals/{d['id']}/complete", headers=admin_headers).json()["code"] == 0
    r = client.get(f"{BASE}/assets/{a['id']}", headers=admin_headers).json()
    assert r["data"]["status"] == "idle", r


def test_disposal_delete_draft(client, admin_headers):
    """草稿处置单可删除。"""
    a = _mk_asset(client, admin_headers)
    d = client.post(
        f"{BASE}/disposals", headers=admin_headers, json={"assetId": a["id"]}
    ).json()["data"]
    r = client.delete(f"{BASE}/disposals/{d['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r
    # 删除后资产可删
    r = client.delete(f"{BASE}/assets/{a['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r


# ---------------- 工具领用归还 ----------------


def test_tool_crud(client, admin_headers):
    """工具台账 CRUD + 编号重复 + 计数 + 下拉全集。"""
    t = _mk_tool(client, admin_headers)
    assert t["status"] == "in_stock"

    r = client.post(
        f"{BASE}/tools", headers=admin_headers, json={"toolNo": t["toolNo"], "name": "重复"}
    ).json()
    assert r["code"] == 97004, r

    r = client.get(f"{BASE}/tools", headers=admin_headers, params={"q": t["toolNo"]}).json()
    assert r["code"] == 0 and r["data"]["total"] == 1, r

    r = client.get(f"{BASE}/tools/all", headers=admin_headers).json()
    assert r["code"] == 0 and any(x["id"] == t["id"] for x in r["data"]), r

    r = client.get(f"{BASE}/tools/counts", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["all"] >= 1, r

    r = client.put(
        f"{BASE}/tools/{t['id']}",
        headers=admin_headers,
        json={
            "toolNo": t["toolNo"],
            "name": "as_工具_改名",
            "status": "maintenance",
            "version": t["version"],
        },
    ).json()
    assert r["code"] == 0 and r["data"]["name"] == "as_工具_改名", r

    r = client.delete(f"{BASE}/tools/{t['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r


def test_tool_loan_lifecycle(client, admin_headers):
    """工具领用→工具状态 loaned→归还→回 in_stock；未归还不可再领（97007）。"""
    t = _mk_tool(client, admin_headers)

    r = client.post(
        f"{BASE}/tool-loans",
        headers=admin_headers,
        json={"toolId": t["id"], "borrowerName": "as_领用人", "purpose": "as_返修"},
    ).json()
    assert r["code"] == 0, r
    loan = r["data"]
    assert loan["status"] == "borrowed"
    assert loan["toolNo"] == t["toolNo"]

    r = client.get(f"{BASE}/tools/{t['id']}", headers=admin_headers).json()
    assert r["data"]["status"] == "loaned", r

    # 未归还不可再领
    r = client.post(f"{BASE}/tool-loans", headers=admin_headers, json={"toolId": t["id"]}).json()
    assert r["code"] == 97007, r

    # 归还
    r = client.post(f"{BASE}/tool-loans/{loan['id']}/return", headers=admin_headers, json={}).json()
    assert r["code"] == 0 and r["data"]["status"] == "returned", r
    r = client.get(f"{BASE}/tools/{t['id']}", headers=admin_headers).json()
    assert r["data"]["status"] == "in_stock", r

    # 已归还不可编辑/删除
    r = client.put(
        f"{BASE}/tool-loans/{loan['id']}",
        headers=admin_headers,
        json={"toolId": t["id"], "version": loan["version"]},
    ).json()
    assert r["code"] == 97001, r
    r = client.delete(f"{BASE}/tool-loans/{loan['id']}", headers=admin_headers).json()
    assert r["code"] == 97001, r

    # 领用单列表按工具过滤
    r = client.get(
        f"{BASE}/tool-loans", headers=admin_headers, params={"filters[tool_id]": t["id"]}
    ).json()
    assert r["code"] == 0 and r["data"]["total"] == 1, r


def test_tool_loan_overdue_counts(client, admin_headers):
    """工具领用逾期计数（借出中 + 应归还日早于今天）。"""
    t = _mk_tool(client, admin_headers)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    client.post(
        f"{BASE}/tool-loans",
        headers=admin_headers,
        json={"toolId": t["id"], "dueDate": yesterday},
    )
    r = client.get(f"{BASE}/tool-loans/counts", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["overdue"] >= 1
    assert r["data"]["borrowed"] >= 1


# ---------------- 导出 ----------------


def test_asset_finance_export(client, admin_headers):
    """导出为 xlsx（响应非信封，原样放行）。"""
    for path in (
        "/assets/export",
        "/disposals/export",
        "/tools/export",
        "/tool-loans/export",
        "/prototypes/export",
        "/prototype-loans/export",
    ):
        r = client.post(f"{BASE}{path}", headers=admin_headers)
        assert r.status_code == 200, path
        assert r.content[:2] == b"PK", path

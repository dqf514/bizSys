"""资产域 B4 补充：BOM 物料清单（父子/版本/用量）+ 呆滞预警筛选 HTTP 全链路。

覆盖：
- BOM 创建/详情/列表/计数（单号 BM 取号）
- 同一父件同一版本号重复 → 97004
- 子件不能是父件本身 → 97001
- 生效 BOM：同父件旧生效版本自动作废；已生效不可改（97001）/ 不可删
- 复制版本 → 新草稿 V1.1
- 多级展开（子件本身是总成，按其生效 BOM 下钻）
- 用量对比：理论需求 vs 实际领用（ast_ledger 出库累计）
- 物料 BOM 引用反查（作为父件 / 作为子件）
- 呆滞预警：闲置天数分级、filters[stagnant] / filters[stagnant_level] / filters[warning] 筛选、
  counts 预警计数、导出带呆滞分级
"""

import uuid
from datetime import datetime, timedelta

BASE = "/api/v1/asset"


def _sfx() -> str:
    return uuid.uuid4().hex[:8]


def _mk_item(client, headers, **kw) -> dict:
    body = {
        "code": f"IT-{_sfx()}",
        "name": f"as_存货_{_sfx()}",
        "spec": "SPEC-A",
        "unit": "件",
        "category": "raw",
        "unitPrice": 10,
        "safetyStock": 0,
        "stagnantDays": 90,
        "status": "enabled",
    }
    body.update(kw)
    r = client.post(f"{BASE}/items", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def _mk_bom(client, headers, parent: dict, lines: list[dict], version: str = "V1.0") -> dict:
    body = {
        "parentItemId": parent["id"],
        "bomVersion": version,
        "remark": "as_BOM",
        "lines": lines,
    }
    r = client.post(f"{BASE}/boms", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def _line(item: dict, qty: float = 2, loss_rate: float = 0) -> dict:
    return {
        "itemId": item["id"],
        "itemCode": item["code"],
        "itemName": item["name"],
        "spec": item["spec"],
        "unit": item["unit"],
        "qty": qty,
        "lossRate": loss_rate,
        "refDesignator": "",
        "position": "装配位",
    }


def test_bom_crud_and_version_rules(client, admin_headers):
    headers = admin_headers
    parent = _mk_item(client, headers)
    child = _mk_item(client, headers)

    bom = _mk_bom(client, headers, parent, [_line(child, qty=3, loss_rate=10)])
    assert bom["bomNo"].startswith("BM"), bom
    assert bom["status"] == "draft"
    assert bom["version"] == "V1.0"
    assert bom["parentItemCode"] == parent["code"]
    assert len(bom["lines"]) == 1
    # 理论用量 = 用量 × (1 + 损耗率)
    assert abs(bom["lines"][0]["requiredQty"] - 3.3) < 1e-6, bom["lines"][0]

    # 同父件同版本号重复 → 97004
    dup = client.post(
        f"{BASE}/boms",
        headers=headers,
        json={"parentItemId": parent["id"], "bomVersion": "V1.0", "lines": [_line(child)]},
    ).json()
    assert dup["code"] == 97004, dup

    # 子件不能是父件本身
    self_ref = client.post(
        f"{BASE}/boms",
        headers=headers,
        json={"parentItemId": parent["id"], "bomVersion": "V9.9", "lines": [_line(parent)]},
    ).json()
    assert self_ref["code"] == 97001, self_ref

    # 列表与计数
    lst = client.get(
        f"{BASE}/boms", headers=headers, params={"q": parent["code"]}
    ).json()
    assert lst["code"] == 0 and lst["data"]["total"] >= 1, lst
    counts = client.get(f"{BASE}/boms/counts", headers=headers).json()
    assert counts["code"] == 0 and counts["data"]["all"] >= 1, counts


def test_bom_activate_obsolete_and_edit_lock(client, admin_headers):
    headers = admin_headers
    parent = _mk_item(client, headers)
    child = _mk_item(client, headers)
    bom = _mk_bom(client, headers, parent, [_line(child)])

    # 草稿可改
    upd = client.put(
        f"{BASE}/boms/{bom['id']}",
        headers=headers,
        json={
            "parentItemId": parent["id"],
            "bomVersion": "V1.0",
            "remark": "已改",
            "lines": [_line(child, qty=5)],
            "version": bom["lockVersion"],
        },
    ).json()
    assert upd["code"] == 0 and upd["data"]["remark"] == "已改", upd
    assert abs(upd["data"]["lines"][0]["qty"] - 5) < 1e-6, upd

    # 生效
    act = client.post(f"{BASE}/boms/{bom['id']}/activate", headers=headers).json()
    assert act["code"] == 0 and act["data"]["status"] == "effective", act
    assert act["data"]["effectiveDate"], act

    # 已生效不可改
    bad = client.put(
        f"{BASE}/boms/{bom['id']}",
        headers=headers,
        json={
            "parentItemId": parent["id"],
            "bomVersion": "V1.0",
            "lines": [_line(child)],
            "version": act["data"]["lockVersion"],
        },
    ).json()
    assert bad["code"] == 97001, bad

    # 已生效不可删
    dele = client.delete(f"{BASE}/boms/{bom['id']}", headers=headers).json()
    assert dele["code"] == 97001, dele

    # 复制为新版本草稿
    cp = client.post(f"{BASE}/boms/{bom['id']}/copy", headers=headers).json()
    assert cp["code"] == 0 and cp["data"]["status"] == "draft", cp
    assert cp["data"]["version"] == "V1.1", cp
    assert len(cp["data"]["lines"]) == 1, cp

    # 新版本生效后，旧版本自动作废
    act2 = client.post(f"{BASE}/boms/{cp['data']['id']}/activate", headers=headers).json()
    assert act2["code"] == 0, act2
    old = client.get(f"{BASE}/boms/{bom['id']}", headers=headers).json()
    assert old["data"]["status"] == "obsolete", old

    # 作废生效中的版本
    obs = client.post(f"{BASE}/boms/{cp['data']['id']}/obsolete", headers=headers).json()
    assert obs["code"] == 0 and obs["data"]["status"] == "obsolete", obs


def test_bom_multilevel_explode_and_usage(client, admin_headers):
    headers = admin_headers
    top = _mk_item(client, headers)
    mid = _mk_item(client, headers)
    leaf = _mk_item(client, headers)

    # mid 作为总成：先建 mid 的 BOM 并生效
    mid_bom = _mk_bom(client, headers, mid, [_line(leaf, qty=4)])
    r = client.post(f"{BASE}/boms/{mid_bom['id']}/activate", headers=headers).json()
    assert r["code"] == 0, r

    top_bom = _mk_bom(client, headers, top, [_line(mid, qty=2)])
    tree = client.get(f"{BASE}/boms/{top_bom['id']}/explode", headers=headers).json()
    assert tree["code"] == 0, tree
    nodes = tree["data"]["tree"]
    assert len(nodes) == 1, nodes
    # 根节点是 top 的直接子件 mid（level 1），mid 的子件 leaf（level 2）
    assert nodes[0]["level"] == 1, nodes
    assert nodes[0]["itemCode"] == mid["code"], nodes
    assert len(nodes[0]["children"]) == 1, nodes
    assert nodes[0]["children"][0]["level"] == 2, nodes
    assert nodes[0]["children"][0]["itemCode"] == leaf["code"], nodes
    assert nodes[0]["children"][0]["children"] == [], nodes

    # 用量对比：理论需求 = 用量 × 父件数量；实际领用取自出库流水
    usage = client.get(
        f"{BASE}/boms/{top_bom['id']}/usage", headers=headers, params={"qty": 10}
    ).json()
    assert usage["code"] == 0, usage
    line = usage["data"]["lines"][0]
    assert abs(line["requiredQty"] - 20) < 1e-6, line
    assert line["actualOutQty"] == 0, line


def test_bom_usage_actual_out_and_item_refs(client, admin_headers):
    headers = admin_headers
    parent = _mk_item(client, headers)
    child = _mk_item(client, headers)
    bom = _mk_bom(client, headers, parent, [_line(child, qty=1)])

    # 手工登记一笔入库 + 一笔出库流水，验证用量对比取实际领用
    led_in = client.post(
        f"{BASE}/ledger",
        headers=headers,
        json={
            "direction": "in",
            "itemId": child["id"],
            "quantity": 10,
            "reason": "manual",
            "happenAt": datetime.now().strftime("%Y-%m-%d"),
            "remark": "as_入库",
        },
    ).json()
    assert led_in["code"] == 0, led_in
    led = client.post(
        f"{BASE}/ledger",
        headers=headers,
        json={
            "direction": "out",
            "itemId": child["id"],
            "quantity": 7,
            "reason": "manual",
            "happenAt": datetime.now().strftime("%Y-%m-%d"),
            "remark": "as_领用",
        },
    ).json()
    assert led["code"] == 0, led

    usage = client.get(f"{BASE}/boms/{bom['id']}/usage", headers=headers).json()
    assert usage["code"] == 0, usage
    line = usage["data"]["lines"][0]
    assert abs(line["actualOutQty"] - 7) < 1e-6, line
    assert abs(line["diffQty"] - 6) < 1e-6, line

    # 物料 BOM 引用反查
    refs = client.get(f"{BASE}/items/{child['id']}/bom-refs", headers=headers).json()
    assert refs["code"] == 0, refs
    assert len(refs["data"]["asChild"]) >= 1, refs
    assert refs["data"]["asChild"][0]["bomNo"] == bom["bomNo"], refs

    pref = client.get(f"{BASE}/items/{parent['id']}/bom-refs", headers=headers).json()
    assert len(pref["data"]["asParent"]) >= 1, pref


def test_stagnant_warning_and_filters(client, admin_headers):
    headers = admin_headers
    stale = _mk_item(client, headers, stagnantDays=30, safetyStock=0, unitPrice=100)
    # 该存货最近一次出入库在 40 天前 → 闲置 40 天 > 阈值 30 天，但 < 2 倍阈值 → 慢动销
    old = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
    led = client.post(
        f"{BASE}/ledger",
        headers=headers,
        json={
            "direction": "in",
            "itemId": stale["id"],
            "quantity": 5,
            "reason": "manual",
            "happenAt": old,
            "remark": "as_历史入库",
        },
    ).json()
    assert led["code"] == 0, led

    detail = client.get(f"{BASE}/items/{stale['id']}", headers=headers).json()
    assert detail["code"] == 0, detail
    assert detail["data"]["idleDays"] >= 39, detail["data"]
    assert detail["data"]["stagnantLevel"] == "slow", detail["data"]
    assert detail["data"]["stagnant"] is True, detail["data"]
    assert detail["data"]["stagnantAmount"] == 500.0, detail["data"]
    assert detail["data"]["lastMoveAt"], detail["data"]

    # 筛选：呆滞
    lst = client.get(f"{BASE}/items", headers=headers, params={"filters[stagnant]": "1"}).json()
    assert lst["code"] == 0, lst
    assert any(i["id"] == stale["id"] for i in lst["data"]["items"]), lst
    assert all(i["stagnant"] for i in lst["data"]["items"]), lst

    # 筛选：呆滞分级
    lvl = client.get(
        f"{BASE}/items", headers=headers, params={"filters[stagnant_level]": "slow"}
    ).json()
    assert lvl["code"] == 0, lvl
    assert all(i["stagnantLevel"] == "slow" for i in lvl["data"]["items"]), lvl

    # 计数含预警
    counts = client.get(f"{BASE}/items/counts", headers=headers).json()
    assert counts["code"] == 0, counts
    assert counts["data"]["stagnant"] >= 1, counts
    assert counts["data"]["stagnantAmount"] > 0, counts

    # 阈值置 0 → 不再预警
    upd = client.put(
        f"{BASE}/items/{stale['id']}",
        headers=headers,
        json={
            "code": stale["code"],
            "name": stale["name"],
            "spec": stale["spec"],
            "unit": stale["unit"],
            "category": stale["category"],
            "unitPrice": stale["unitPrice"],
            "safetyStock": 0,
            "stagnantDays": 0,
            "status": "enabled",
            "version": stale["version"],
        },
    ).json()
    assert upd["code"] == 0, upd
    assert upd["data"]["stagnantLevel"] == "normal", upd
    assert upd["data"]["stagnant"] is False, upd


def test_bom_export_and_permission(client, admin_headers):
    headers = admin_headers
    parent = _mk_item(client, headers)
    child = _mk_item(client, headers)
    _mk_bom(client, headers, parent, [_line(child)])

    r = client.post(
        f"{BASE}/boms/export",
        headers=headers,
        json={"q": parent["code"]},
    )
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers.get("content-type", ""), r.headers

"""B3 访客与安全（HTTP 黑盒）。

链路：建区域 → 登记访客单 → 逐级审批（下发凭证）→ 签入 → 凭证核验（越权区域被拒 + 预警）
→ 签出 → 审计日志只读可查 → 黑名单命中拦截 → NDA 签署 → 样品交接 → 预警处置。

测试库数据跨用例持久：编码 / 名称带 uuid 后缀。
"""

import uuid
from datetime import datetime, timedelta

UUID = uuid.uuid4().hex[:8]


def _mk_zone(client, headers, **kw) -> dict:
    suf = uuid.uuid4().hex[:8]
    payload = {
        "code": f"Z{suf}",
        "name": f"区域_{suf}",
        "zone_type": "test",
        "security_level": 2,
        "need_extra_approval": 0,
        "need_escort": 0,
        "need_nda": 0,
        "need_dual_person": 0,
        "camera_control": 0,
        "capacity": 0,
        "status": "enabled",
        "remark": "",
    }
    payload.update(kw)
    r = client.post("/api/v1/visitor/zones", headers=headers, json=payload).json()
    assert r["code"] == 0, r
    return r["data"]


def _mk_visit(client, headers, **kw) -> dict:
    suf = uuid.uuid4().hex[:8]
    now = datetime.now()
    payload = {
        "visitor_name": f"访客_{suf}",
        "visitor_company": f"单位_{suf}",
        "visitor_type": "customer",
        "id_no": f"ID{suf}",
        "phone": "13900000001",
        "purpose": "陪同试验",
        "source": "web",
        "zone_ids": "",
        # 时间窗取「当前时刻附近」，否则凭证一签发就已过期
        "plan_start": (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "plan_end": (now + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"),
    }
    payload.update(kw)
    r = client.post("/api/v1/visitor/visits", headers=headers, json=payload).json()
    assert r["code"] == 0, r
    return r["data"]


def test_zone_crud_and_counts(client, admin_headers):
    zone = _mk_zone(client, admin_headers)
    assert zone["code"].startswith("Z")
    assert zone["id"] > 0

    lst = client.get("/api/v1/visitor/zones", headers=admin_headers).json()
    assert lst["code"] == 0
    assert lst["data"]["total"] >= 1

    counts = client.get("/api/v1/visitor/zones/counts", headers=admin_headers).json()
    assert counts["code"] == 0
    assert counts["data"]["all"] >= 1
    assert "enabled" in counts["data"]

    upd = client.put(
        f"/api/v1/visitor/zones/{zone['id']}",
        headers=admin_headers,
        json={
            "code": zone["code"],
            "name": f"区域改名_{uuid.uuid4().hex[:6]}",
            "zone_type": "sample",
            "security_level": 3,
            "need_extra_approval": 1,
            "need_escort": 1,
            "need_nda": 1,
            "need_dual_person": 0,
            "camera_control": 1,
            "capacity": 10,
            "status": "enabled",
            "remark": "B3",
        },
    ).json()
    assert upd["code"] == 0
    assert upd["data"]["zoneType"] == "sample"
    assert upd["data"]["needNda"] is True
    assert upd["data"]["securityLevel"] == 3

    off = client.post(
        f"/api/v1/visitor/zones/{zone['id']}/toggle?status=disabled", headers=admin_headers
    ).json()
    assert off["code"] == 0
    assert off["data"]["status"] == "disabled"


def test_zone_duplicate_code_rejected(client, admin_headers):
    zone = _mk_zone(client, admin_headers)
    r = client.post(
        "/api/v1/visitor/zones",
        headers=admin_headers,
        json={"code": zone["code"], "name": "重复编码"},
    ).json()
    assert r["code"] == 98008, r


def test_visit_create_approve_checkin_checkout(client, admin_headers):
    zone = _mk_zone(client, admin_headers)
    visit = _mk_visit(client, admin_headers, zone_ids=str(zone["id"]))
    assert visit["visitNo"].startswith("VT")
    assert visit["status"] == "pending"

    # 审批：host 层通过（区域未要求额外审批 → 只有 host 一层）
    ap = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/approve",
        headers=admin_headers,
        json={"level": "host", "action": "approve", "comment": "同意来访"},
    ).json()
    assert ap["code"] == 0, ap
    assert ap["data"]["status"] == "approved"
    assert ap["data"]["credentialNo"].startswith("VC")

    ci = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/checkin",
        headers=admin_headers,
        json={"method": "qrcode", "device_id": "GATE-01"},
    ).json()
    assert ci["code"] == 0, ci
    assert ci["data"]["status"] == "visiting"

    co = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/checkout",
        headers=admin_headers,
        json={"method": "qrcode", "device_id": "GATE-01"},
    ).json()
    assert co["code"] == 0, co
    assert co["data"]["status"] == "left"
    assert co["data"]["checkoutAt"]

    detail = client.get(f"/api/v1/visitor/visits/{visit['id']}", headers=admin_headers).json()
    assert detail["code"] == 0
    assert len(detail["data"]["approvals"]) == 1
    assert detail["data"]["zoneNames"] == zone["name"]


def test_visit_extra_approval_level_required(client, admin_headers):
    zone = _mk_zone(client, admin_headers, need_extra_approval=1)
    visit = _mk_visit(client, admin_headers, zone_ids=str(zone["id"]))
    assert "zone" in visit["requiredLevels"].split(",")

    # 越级审批（直接审 zone 层）应被拒
    bad = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/approve",
        headers=admin_headers,
        json={"level": "zone", "action": "approve", "comment": "越级"},
    ).json()
    assert bad["code"] == 98001, bad

    ok1 = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/approve",
        headers=admin_headers,
        json={"level": "host", "action": "approve", "comment": "ok"},
    ).json()
    assert ok1["code"] == 0
    assert ok1["data"]["status"] == "pending"

    ok2 = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/approve",
        headers=admin_headers,
        json={"level": "zone", "action": "approve", "comment": "ok"},
    ).json()
    assert ok2["code"] == 0
    assert ok2["data"]["status"] == "approved"


def test_visit_nda_required_blocks_approval(client, admin_headers):
    zone = _mk_zone(client, admin_headers, need_nda=1)
    visit = _mk_visit(client, admin_headers, zone_ids=str(zone["id"]))
    r = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/approve",
        headers=admin_headers,
        json={"level": "host", "action": "approve", "comment": "ok"},
    ).json()
    assert r["code"] == 98007, r

    # 先签 NDA，再审批即通过
    nda = client.post(
        "/api/v1/visitor/nda",
        headers=admin_headers,
        json={
            "title": "访客保密协议",
            "visitor_name": visit["visitorName"],
            "visitor_company": visit["visitorCompany"],
            "id_no": visit["idNo"],
            "signature_data": "data:image/png;base64,AAAA",
            "visit_id": visit["id"],
        },
    ).json()
    assert nda["code"] == 0, nda
    assert nda["data"]["ndaNo"].startswith("ND")
    assert len(nda["data"]["evidenceHash"]) == 64

    ok = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/approve",
        headers=admin_headers,
        json={"level": "host", "action": "approve", "comment": "已签 NDA"},
    ).json()
    assert ok["code"] == 0, ok
    assert ok["data"]["status"] == "approved"


def test_visit_reject_and_cancel(client, admin_headers):
    visit = _mk_visit(client, admin_headers)
    rej = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/approve",
        headers=admin_headers,
        json={"level": "host", "action": "reject", "comment": "资料不全"},
    ).json()
    assert rej["code"] == 0
    assert rej["data"]["status"] == "rejected"

    visit2 = _mk_visit(client, admin_headers)
    cancel = client.post(f"/api/v1/visitor/visits/{visit2['id']}/cancel", headers=admin_headers).json()
    assert cancel["code"] == 0
    assert cancel["data"]["status"] == "cancelled"


def test_blacklist_blocks_checkin(client, admin_headers):
    visit = _mk_visit(client, admin_headers)
    bl = client.post(
        "/api/v1/visitor/blacklist",
        headers=admin_headers,
        json={
            "visitor_name": visit["visitorName"],
            "id_no": visit["idNo"],
            "phone": visit["phone"],
            "company": visit["visitorCompany"],
            "reason": "闯入禁区",
            "status": "enabled",
        },
    ).json()
    assert bl["code"] == 0, bl

    ap = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/approve",
        headers=admin_headers,
        json={"level": "host", "action": "approve", "comment": "ok"},
    ).json()
    assert ap["code"] == 0

    ci = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/checkin",
        headers=admin_headers,
        json={"method": "face", "device_id": "FACE-01"},
    ).json()
    assert ci["code"] == 98004, ci

    # 黑名单命中会落预警
    alerts = client.get("/api/v1/visitor/alerts", headers=admin_headers).json()
    assert alerts["code"] == 0
    types = [a["alertType"] for a in alerts["data"]["items"]]
    assert "blacklist" in types

    # 停用黑名单后放行
    client.post(f"/api/v1/visitor/blacklist/{bl['data']['id']}/toggle?status=disabled", headers=admin_headers)
    ci2 = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/checkin",
        headers=admin_headers,
        json={"method": "face", "device_id": "FACE-01"},
    ).json()
    assert ci2["code"] == 0, ci2
    assert ci2["data"]["status"] == "visiting"


def test_credential_verify_zone_scope(client, admin_headers):
    zone_a = _mk_zone(client, admin_headers)
    zone_b = _mk_zone(client, admin_headers)
    visit = _mk_visit(client, admin_headers, zone_ids=str(zone_a["id"]))
    ap = client.post(
        f"/api/v1/visitor/visits/{visit['id']}/approve",
        headers=admin_headers,
        json={"level": "host", "action": "approve", "comment": "ok"},
    ).json()
    cred_no = ap["data"]["credentialNo"]

    ok = client.post(
        "/api/v1/visitor/credentials/verify",
        headers=admin_headers,
        json={"credential_no": cred_no, "zone_id": zone_a["id"], "method": "qrcode", "device_id": "GATE-A"},
    ).json()
    assert ok["code"] == 0
    assert ok["data"]["pass"] is True

    deny = client.post(
        "/api/v1/visitor/credentials/verify",
        headers=admin_headers,
        json={"credential_no": cred_no, "zone_id": zone_b["id"], "method": "qrcode", "device_id": "GATE-B"},
    ).json()
    assert deny["code"] == 0
    assert deny["data"]["pass"] is False

    missing = client.post(
        "/api/v1/visitor/credentials/verify",
        headers=admin_headers,
        json={"credential_no": "VC-NOT-EXIST", "method": "qrcode", "device_id": "GATE-A"},
    ).json()
    assert missing["data"]["pass"] is False

    creds = client.get("/api/v1/visitor/credentials", headers=admin_headers).json()
    assert creds["code"] == 0
    assert creds["data"]["total"] >= 1


def test_access_log_readonly_and_summary(client, admin_headers):
    logs = client.get("/api/v1/visitor/access-logs", headers=admin_headers).json()
    assert logs["code"] == 0
    assert "items" in logs["data"]

    # 只追加：无任何 update / delete 接口
    from app.modules.visitor import router as visitor_router

    paths = {(r.path, m) for r in visitor_router.router.routes for m in (r.methods or set())}
    assert ("/access-logs", "PUT") not in paths
    assert ("/access-logs", "PATCH") not in paths
    assert ("/access-logs", "DELETE") not in paths

    summary = client.get("/api/v1/visitor/access-logs/summary?days=7", headers=admin_headers).json()
    assert summary["code"] == 0
    assert summary["data"]["total"] >= 0
    assert "byDay" in summary["data"]


def test_access_log_export(client, admin_headers):
    r = client.post("/api/v1/visitor/access-logs/export", headers=admin_headers)
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_visit_export(client, admin_headers):
    r = client.post("/api/v1/visitor/visits/export", headers=admin_headers)
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_handover_create_and_list(client, admin_headers):
    visit = _mk_visit(client, admin_headers)
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/visitor/handovers",
        headers=admin_headers,
        json={
            "visit_id": visit["id"],
            "sample_no": f"SMP-{suf}",
            "sample_name": f"样车_{suf}",
            "barcode": f"BC{suf}",
            "sample_type": "vehicle",
            "qty": 1,
            "handover_user_name": "访客",
            "receive_user_name": "库管",
        },
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["handoverNo"].startswith("SH")

    lst = client.get(f"/api/v1/visitor/handovers?q=SMP-{suf}", headers=admin_headers).json()
    assert lst["code"] == 0
    assert lst["data"]["total"] >= 1


def test_alert_handle_and_scan(client, admin_headers):
    scan = client.post("/api/v1/visitor/alerts/scan", headers=admin_headers).json()
    assert scan["code"] == 0
    assert "scanned" in scan["data"]

    counts = client.get("/api/v1/visitor/alerts/counts", headers=admin_headers).json()
    assert counts["code"] == 0
    assert counts["data"]["all"] >= 0

    lst = client.get("/api/v1/visitor/alerts", headers=admin_headers).json()
    assert lst["code"] == 0
    if lst["data"]["items"]:
        aid = lst["data"]["items"][0]["id"]
        h = client.post(
            f"/api/v1/visitor/alerts/{aid}/handle",
            headers=admin_headers,
            json={"status": "handled", "handle_remark": "已联系安保"},
        ).json()
        assert h["code"] == 0
        assert h["data"]["status"] == "handled"


def test_nda_list_counts_and_revoke(client, admin_headers):
    suf = uuid.uuid4().hex[:8]
    nda = client.post(
        "/api/v1/visitor/nda",
        headers=admin_headers,
        json={
            "title": f"NDA_{suf}",
            "visitor_name": f"签署人_{suf}",
            "signature_data": "data:image/png;base64,BBBB",
        },
    ).json()
    assert nda["code"] == 0

    counts = client.get("/api/v1/visitor/nda/counts", headers=admin_headers).json()
    assert counts["code"] == 0
    assert counts["data"]["all"] >= 1

    rev = client.post(f"/api/v1/visitor/nda/{nda['data']['id']}/revoke", headers=admin_headers).json()
    assert rev["code"] == 0
    assert rev["data"]["status"] == "revoked"


def test_stats_and_counts(client, admin_headers):
    stats = client.get("/api/v1/visitor/visits/stats", headers=admin_headers).json()
    assert stats["code"] == 0
    assert "visiting" in stats["data"]
    assert "openAlerts" in stats["data"]

    counts = client.get("/api/v1/visitor/visits/counts", headers=admin_headers).json()
    assert counts["code"] == 0
    assert counts["data"]["all"] >= 1
    assert "pending" in counts["data"]


def test_permission_required(client, manager_headers):
    """业务角色无访客域权限 → 403。"""
    r = client.get("/api/v1/visitor/visits", headers=manager_headers).json()
    assert r["code"] == 20002, r

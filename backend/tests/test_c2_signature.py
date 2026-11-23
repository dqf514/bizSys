"""B9-C2 电子签名密码学绑定：NDA 签名 / 报告签章签名 / 签章后锁定。

合规原则 2.4「签名需绑定账号、证书或多因子认证，签名后记录锁定；
禁止代签、批量自动签、图片印章」。

与存量口径的差别：存量 `vis_nda.evidence_hash` 是**无密钥 sha256**，
任何人拿得到内容就能离线复算 —— 不能当密码学证据；新签名用服务端密钥的
HMAC-SHA256，绑定签署账号 / 真实 IP / 签署时间 / 内容哈希。
"""

import uuid

from test_report_flow import _act_on_report, _make_task, _upload

from app.core import signature

UUID = uuid.uuid4().hex[:8]


# ---------------- 签名原语 ----------------


def test_sign_verify_round_trip():
    payload = {name: f"v-{i}" for i, name in enumerate(signature.NDA_FIELDS)}
    sig = signature.sign(payload, signature.NDA_FIELDS)
    assert len(sig) == 64
    assert signature.verify(payload, signature.NDA_FIELDS, sig) is True


def test_tampered_payload_fails_verification():
    payload = {name: f"v-{i}" for i, name in enumerate(signature.NDA_FIELDS)}
    sig = signature.sign(payload, signature.NDA_FIELDS)
    payload["visitor_name"] = "张三改"
    assert signature.verify(payload, signature.NDA_FIELDS, sig) is False


def test_field_order_is_fixed():
    """规范化串按固定字段序生成 —— 调换顺序会得到不同签名（防止口径漂移）。"""
    a = {"x": "1", "y": "2"}
    assert signature.canonical(a, ("x", "y")) != signature.canonical(a, ("y", "x"))
    assert signature.canonical(a, ("x", "y")) == "x=1\ny=2\n"


def test_missing_field_is_treated_as_empty():
    """None 与 "" 归一，避免验签方因字段缺失算出不同结果。"""
    assert signature.canonical({"a": None}, ("a",)) == signature.canonical({"a": ""}, ("a",))


# ---------------- NDA ----------------


def _sign_nda(client, headers, **over) -> dict:
    body = {
        "visitor_name": f"访客_{UUID}",
        "visitor_company": "某某检测有限公司",
        "id_no": f"3401{UUID}",
        "title": "保密协议",
        "signature_data": "data:image/png;base64,iVBORw0KGgo=",
    }
    body.update(over)
    r = client.post("/api/v1/visitor/nda", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def test_nda_signature_is_bound_to_account_and_ip(client, admin_headers):
    """新签 NDA：落签名算法 / 签署人 / 真实 IP，验签有效。"""
    data = _sign_nda(client, admin_headers)
    assert data["signAlg"] == "HMAC-SHA256"
    assert data["signVersion"] == "v1"
    assert data["signedByName"], "签署人姓名必须落库"
    assert data["signedIp"], "真实 IP 必须落库（不得硬编码空串）"
    assert len(data["evidenceHash"]) == 64

    r = client.get(f"/api/v1/visitor/nda/{data['id']}/verify", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["valid"] is True, r["data"]
    assert r["data"]["verdict"] == "valid"


def test_nda_content_change_breaks_verification(client, admin_headers, db):
    """签署后改内容 → 验签失败（内容与签名不再对应）。"""
    from app.modules.visitor.models import VisitorNda

    data = _sign_nda(client, admin_headers)
    row = db.get(VisitorNda, data["id"])
    row.visitor_name = "被改过的名字"
    db.commit()

    r = client.get(f"/api/v1/visitor/nda/{data['id']}/verify", headers=admin_headers).json()
    assert r["data"]["valid"] is False
    assert r["data"]["verdict"] == "invalid"


def test_legacy_nda_is_unverifiable(client, admin_headers, db):
    """存量 NDA（无密钥 sha256）不能当密码学证据 —— 返回 legacy-unverifiable。"""
    from app.modules.visitor.models import VisitorNda

    data = _sign_nda(client, admin_headers)
    row = db.get(VisitorNda, data["id"])
    row.sign_version = "legacy-sha256"
    row.signed_by_id = None
    db.commit()

    r = client.get(f"/api/v1/visitor/nda/{data['id']}/verify", headers=admin_headers).json()
    assert r["data"]["valid"] is False
    assert r["data"]["verdict"] == "legacy-unverifiable"


# ---------------- 报告签章 ----------------


def _sealed_report(client, headers, suf: str) -> tuple[int, int]:
    """走完整链路拿一份已签章报告（上传 → 签批 → 用章审批 → 签章）。"""
    tid, item = _make_task(client, headers, suf)
    r = _upload(client, headers, item["id"])
    assert r["code"] == 0, r
    rid = r["data"]["id"]
    assert client.post(f"/api/v1/report/reports/{rid}/submit", headers=headers, json={}).json()["code"] == 0
    _act_on_report("approve", rid)
    assert client.post(f"/api/v1/report/reports/{rid}/seal-apply", headers=headers, json={}).json()["code"] == 0

    from conftest import approve_instance

    approve_instance("report_seal", rid, times=2)
    r2 = client.post(f"/api/v1/report/reports/{rid}/seal", headers=headers, json={}).json()
    assert r2["code"] == 0, r2
    assert r2["data"]["sealAlg"] == "HMAC-SHA256"
    assert r2["data"]["sealContentHash"]
    return tid, rid


def test_report_seal_signature_is_written(client, admin_headers):
    _tid, rid = _sealed_report(client, admin_headers, f"签章_{UUID}")
    r = client.get(f"/api/v1/report/reports/{rid}/seal/verify", headers=admin_headers).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["signatureValid"] is True, d
    assert d["contentMatch"] is True, d
    assert d["sealedBy"], "签章人姓名必须落库"
    assert d["alg"] == "HMAC-SHA256"


def test_report_content_change_after_seal_breaks_content_match(client, admin_headers, db):
    """签章后改结论 → contentMatch=false（绕过 API 直接改库的场景）。"""
    from app.modules.report.models import Report

    _tid, rid = _sealed_report(client, admin_headers, f"改结论_{UUID}")
    row = db.get(Report, rid)
    row.conclusion = "签章后偷偷改掉的结论"
    db.commit()

    r = client.get(f"/api/v1/report/reports/{rid}/seal/verify", headers=admin_headers).json()
    assert r["data"]["signatureValid"] is True, "签名本身仍有效（字段未动）"
    assert r["data"]["contentMatch"] is False, "内容哈希必须对不上"


def test_sealed_report_is_locked(client, admin_headers):
    """签章后锁定：改备注 / 改结论都被拒（61003），只能作废重做。"""
    _tid, rid = _sealed_report(client, admin_headers, f"锁定_{UUID}")
    r = client.put(f"/api/v1/report/reports/{rid}/remark", headers=admin_headers,
                    json={"remark": "签章后再写一条"}).json()
    assert r["code"] == 61003, r
    r = client.put(f"/api/v1/report/reports/{rid}/conclusion", headers=admin_headers,
                    json={"conclusion": "签章后再改结论"}).json()
    assert r["code"] == 61003, r

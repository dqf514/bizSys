"""AI-5：脱敏分级（mask_text/effective_level/网关出网掩码/用量日志级别）+ 模型单价成本估算 + 提示词注册表。"""

import json
import uuid

from sqlalchemy import select


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _enable_ai(client, headers):
    r = client.put(
        "/api/v1/admin/settings",
        headers=headers,
        json={"ai": {"enabled": True, "baseUrl": "https://ai.example.com/v1", "apiKey": "sk-test", "model": "m1"}},
    ).json()
    assert r["code"] == 0 and r["data"]["ai"]["enabled"], r


def _set_center(client, headers, body):
    r = client.put("/api/v1/admin/ai/settings", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def _capture_chat(monkeypatch):
    """mock 网关 HTTP 层并捕获 payload，返回固定用量。"""
    from app.services import ai as ai_svc

    seen: dict = {}

    def fake(url, api_key, payload, timeout):
        seen["payload"] = payload
        return {
            "choices": [{"message": {"content": json.dumps({"title": "t", "items": []}, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        }

    monkeypatch.setattr(ai_svc, "_post_chat", fake)
    return seen


def _create_customer(client, headers, name=None) -> int:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": name or _uniq("AI客户_"), "tax_no": f"913401AI{suf}", "status": "enabled"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _latest_usage(client, headers, feature: str) -> dict:
    r = client.get("/api/v1/admin/ai/usage", headers=headers, params={"feature": feature, "size": 1}).json()
    assert r["code"] == 0 and r["data"]["total"] >= 1, r
    return r["data"]["items"][0]


# ---------------- 脱敏：mask_text 单元 ----------------


def test_mask_text_standard_patterns():
    from app.services import masking

    text = "联系人 13812345678，身份证 110101199003074321，卡号 6222020200112233445，邮箱 zhang.san@corp-example.com"
    out = masking.mask_text(text, "standard")
    assert "13812345678" not in out and "1**********" in out
    assert "110101199003074321" not in out
    assert "6222020200112233445" not in out
    assert "zhang.san@corp-example.com" not in out and "***@***" in out
    # off 原样返回
    assert masking.mask_text(text, "off") == text
    # 金额等普通数字不误伤
    assert masking.mask_text("金额 12500.50 元，数量 100", "standard") == "金额 12500.50 元，数量 100"


def test_mask_text_strict_tax_no():
    from app.services import masking

    text = "税号 91340100MA2T3XYZ4A 开票"
    assert "91340100MA2T3XYZ4A" not in masking.mask_text(text, "strict")
    # standard 不掩码税号
    assert "91340100MA2T3XYZ4A" in masking.mask_text(text, "standard")


def test_mask_text_strict_customer_alias(client, admin_headers, db):
    from app.modules.crm.models import Customer
    from app.services import masking

    name = _uniq("脱敏客户公司")
    db.add(Customer(name=name, customer_no=_uniq("CU"), tax_no="", status="enabled"))
    db.flush()
    out = masking.mask_text(f"与{name}签订检测合同", "strict", db)
    assert name not in out and "客户#" in out
    # standard 不替换客户名
    assert name in masking.mask_text(f"与{name}签订检测合同", "standard", db)


def test_effective_level_forces_personal_features(db):
    from app.modules.settings.service import set_value
    from app.services import masking

    set_value(db, masking.KEY_MASKING_LEVEL, "off", None, "test")
    db.flush()
    assert masking.effective_level(db, "quote") == "off"
    # 个人信息场景强制 standard
    for f in ("hr_prefill", "oa_prefill", "flow_anomaly", "daily_digest", "assistant", "knowledge"):
        assert masking.effective_level(db, f) == "standard", f
    set_value(db, masking.KEY_MASKING_LEVEL, "strict", None, "test")
    db.flush()
    assert masking.effective_level(db, "hr_prefill") == "strict"
    # 非法值回落默认
    set_value(db, masking.KEY_MASKING_LEVEL, "bogus", None, "test")
    db.flush()
    assert masking.configured_level(db) == "standard"


# ---------------- 脱敏：网关集成（payload 掩码 + 日志级别） ----------------


def test_gateway_masks_payload_and_logs_level(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _set_center(client, admin_headers, {"masking": "standard", "features": {"quote": True}})
    seen = _capture_chat(monkeypatch)
    cust = _create_customer(client, admin_headers)
    r = client.post(
        "/api/v1/sales/quotations/ai-generate",
        headers=admin_headers,
        json={"customerId": cust, "requirement": "风洞试验，联系人电话 13812345678，邮箱 qa@test-corp.com"},
    ).json()
    assert r["code"] == 0, r
    sent = json.dumps(seen["payload"]["messages"], ensure_ascii=False)
    assert "13812345678" not in sent and "qa@test-corp.com" not in sent
    assert "1**********" in sent
    row = _latest_usage(client, admin_headers, "quote")
    assert row["status"] == "success" and row["masking"] == "standard"


def test_gateway_off_keeps_payload_but_personal_forced(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _set_center(client, admin_headers, {"masking": "off", "features": {"quote": True, "knowledge": True}})
    seen = _capture_chat(monkeypatch)
    cust = _create_customer(client, admin_headers)
    r = client.post(
        "/api/v1/sales/quotations/ai-generate",
        headers=admin_headers,
        json={"customerId": cust, "requirement": "电话 13812345678"},
    ).json()
    assert r["code"] == 0, r
    assert "13812345678" in json.dumps(seen["payload"]["messages"], ensure_ascii=False)
    assert _latest_usage(client, admin_headers, "quote")["masking"] == "off"

    # knowledge 属个人信息场景：off 仍强制 standard
    r = client.post(
        "/api/v1/ai/knowledge/ask", headers=admin_headers, json={"question": "我的电话 13812345678 怎么报销"}
    ).json()
    assert r["code"] == 0, r
    assert "13812345678" not in json.dumps(seen["payload"]["messages"], ensure_ascii=False)
    assert _latest_usage(client, admin_headers, "knowledge")["masking"] == "standard"
    _set_center(client, admin_headers, {"masking": "standard"})


def test_settings_masking_roundtrip_and_validation(client, admin_headers):
    data = _set_center(client, admin_headers, {"masking": "strict"})
    assert data["masking"] == "strict"
    data = _set_center(client, admin_headers, {"masking": "standard"})
    assert data["masking"] == "standard"
    r = client.put("/api/v1/admin/ai/settings", headers=admin_headers, json={"masking": "bogus"})
    assert r.status_code == 422


# ---------------- 成本：单价配置 + 估算 + 聚合 ----------------


def test_cost_estimated_with_price(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _set_center(client, admin_headers, {
        "features": {"quote": True},
        "modelPrices": [{"model": "m1", "input": 2.0, "output": 6.0}],
    })
    _capture_chat(monkeypatch)
    cust = _create_customer(client, admin_headers)
    r = client.post(
        "/api/v1/sales/quotations/ai-generate",
        headers=admin_headers,
        json={"customerId": cust, "requirement": "成本测试"},
    ).json()
    assert r["code"] == 0, r
    row = _latest_usage(client, admin_headers, "quote")
    assert row["status"] == "success"
    # (12*2 + 7*6)/1000 = 0.066
    assert abs(row["cost"] - 0.066) < 1e-9

    stats = client.get("/api/v1/admin/ai/stats", headers=admin_headers, params={"days": 7}).json()["data"]
    assert stats["cards"]["totalCost"] >= 0.066
    m1 = [m for m in stats["byModel"] if m["model"] == "m1"]
    assert m1 and m1[0]["cost"] >= 0.066

    # 清空单价 → 新调用 cost 为 null
    _set_center(client, admin_headers, {"modelPrices": []})
    r = client.post(
        "/api/v1/sales/quotations/ai-generate",
        headers=admin_headers,
        json={"customerId": cust, "requirement": "无单价"},
    ).json()
    assert r["code"] == 0, r
    assert _latest_usage(client, admin_headers, "quote")["cost"] is None


def test_settings_model_prices_roundtrip(client, admin_headers):
    data = _set_center(client, admin_headers, {
        "modelPrices": [{"model": "m1", "input": 1.5, "output": 3.0}, {"model": "v1-pro", "input": 0.8, "output": 2.4}],
    })
    prices = {p["model"]: p for p in data["modelPrices"]}
    assert prices["m1"] == {"model": "m1", "input": 1.5, "output": 3.0}
    assert prices["v1-pro"]["output"] == 2.4
    # 同模型重复行后者为准
    data = _set_center(client, admin_headers, {
        "modelPrices": [{"model": "m1", "input": 1, "output": 1}, {"model": "m1", "input": 9, "output": 9}],
    })
    assert data["modelPrices"] == [{"model": "m1", "input": 9.0, "output": 9.0}]
    _set_center(client, admin_headers, {"modelPrices": []})


# ---------------- 提示词注册表 ----------------


def test_prompt_registry_covers_all_features():
    from app.services import prompts
    from app.services.ai import FEATURES

    covered = {p["feature"] for p in prompts.list_prompts()}
    assert set(FEATURES) <= covered
    for p in prompts.list_prompts():
        assert p["version"] and p["name"] and p["systemPreview"]
        full = prompts.get(p["key"])
        assert full["system"].strip()
    # 各 feature 版本号一致可取
    for f in FEATURES:
        assert prompts.feature_version(f)


def test_prompts_endpoint(client, admin_headers):
    r = client.get("/api/v1/admin/ai/prompts", headers=admin_headers).json()
    assert r["code"] == 0, r
    items = r["data"]
    assert len(items) >= 19
    keys = {p["key"] for p in items}
    assert {"quote", "report_assist.conclusion", "report_assist.proofread", "report_assist.completeness"} <= keys
    assert all(len(p["systemPreview"]) <= 100 for p in items)


def test_prompts_endpoint_forbidden(client, admin_headers):
    from test_ai_center import _no_perm_headers

    bad = _no_perm_headers(client, admin_headers, "pa5_np")
    r = client.get("/api/v1/admin/ai/prompts", headers=bad).json()
    assert r["code"] == 20002, r

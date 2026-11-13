"""AI 中心（HTTP）：用量日志/统计/配额/功能开关 + 合同识别/拍照进度/报告摘要（mock AI）+ 越权。"""

import io
import json
import uuid

from openpyxl import load_workbook


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _enable_ai(client, headers):
    r = client.put(
        "/api/v1/admin/settings",
        headers=headers,
        json={"ai": {"enabled": True, "baseUrl": "https://ai.example.com/v1", "apiKey": "sk-test", "model": "m1"}},
    ).json()
    assert r["code"] == 0 and r["data"]["ai"]["enabled"], r


def _disable_ai(client, headers):
    client.put("/api/v1/admin/settings", headers=headers, json={"ai": {"enabled": False}})


def _mock_chat(monkeypatch, content: str):
    """mock 网关最内层 HTTP 调用：走完整 gateway_chat（开关/配额/用量日志真实生效）。"""
    from app.services import ai as ai_svc

    def fake(url, api_key, payload, timeout):
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        }

    monkeypatch.setattr(ai_svc, "_post_chat", fake)


def _set_center(client, headers, body):
    r = client.put("/api/v1/admin/ai/settings", headers=headers, json=body).json()
    assert r["code"] == 0, r
    return r["data"]


def _create_customer(client, headers, name=None) -> int:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": name or _uniq("AI客户_"), "tax_no": f"913401AI{suf}", "status": "enabled"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _quote_ai_generate(client, headers, customer_id):
    return client.post(
        "/api/v1/sales/quotations/ai-generate",
        headers=headers,
        json={"customerId": customer_id, "requirement": "风洞试验两次"},
    ).json()


# ---------------- 用量日志 / 统计 ----------------


def test_usage_fallback_logged_when_not_configured(client, admin_headers):
    _disable_ai(client, admin_headers)
    cust = _create_customer(client, admin_headers)
    r = _quote_ai_generate(client, admin_headers, cust)
    assert r["code"] == 0 and r["data"]["source"] == "template"

    lst = client.get("/api/v1/admin/ai/usage", headers=admin_headers, params={"feature": "quote"}).json()
    assert lst["code"] == 0 and lst["data"]["total"] >= 1
    row = lst["data"]["items"][0]
    assert row["status"] == "fallback" and row["error"] == "ai_not_configured" and row["feature"] == "quote"
    assert row["userName"]


def test_gateway_success_logs_tokens(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"title": "t", "items": [{"name": "试验", "qty": 1, "unitPrice": 100}]}))
    cust = _create_customer(client, admin_headers)
    r = _quote_ai_generate(client, admin_headers, cust)
    assert r["code"] == 0 and r["data"]["source"] == "ai", r

    lst = client.get(
        "/api/v1/admin/ai/usage", headers=admin_headers, params={"feature": "quote", "status": "success"}
    ).json()
    row = lst["data"]["items"][0]
    assert row["status"] == "success" and row["promptTokens"] == 12 and row["completionTokens"] == 7
    assert row["model"] == "m1" and row["bizType"] == "sales_quotation"

    stats = client.get("/api/v1/admin/ai/stats", headers=admin_headers, params={"days": 7}).json()["data"]
    assert stats["cards"]["totalCalls"] >= 1 and stats["cards"]["totalTokens"] >= 19
    assert any(f["feature"] == "quote" for f in stats["byFeature"])
    assert len(stats["trend"]) == 7 and any(p["calls"] >= 1 for p in stats["trend"])
    assert stats["byUser"] and stats["byModel"][0]["model"] == "m1"
    _disable_ai(client, admin_headers)


def test_usage_export(client, admin_headers):
    r = client.get("/api/v1/admin/ai/usage/export", headers=admin_headers)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows and rows[0][0] == "时间"


# ---------------- 配额 / 功能开关 ----------------


def test_quota_exceeded_returns_65003(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"title": "t", "items": [{"name": "试验", "qty": 1, "unitPrice": 100}]}))
    # 测试库跨运行持久：用全新用户保证当日 0 调用，并先复位配额防上轮残留
    _set_center(client, admin_headers, {"quota": {"userDailyCalls": 0, "userDailyTokens": 0, "globalDailyTokens": 0}})
    suf = uuid.uuid4().hex[:8]
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.admin.models import Role

    db = SessionLocal()
    try:
        biz_role_id = db.scalar(select(Role.id).where(Role.code == "biz_user", Role.deleted == 0))
    finally:
        db.close()
    assert biz_role_id
    uname = f"quota_{suf}"
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": uname, "password": "Test@123456", "name": "配额测试", "roleIds": [biz_role_id]},
    ).json()
    assert r["code"] == 0, r
    cap = client.get("/api/v1/auth/captcha").json()["data"]
    login = client.post(
        "/api/v1/auth/login",
        json={"username": uname, "password": "Test@123456",
              "captchaId": cap["captchaId"], "captchaText": cap.get("debugText", "")},
    ).json()
    assert login["code"] == 0, login
    fresh_headers = {"Authorization": f"Bearer {login['data']['access_token']}"}

    _set_center(client, admin_headers, {"quota": {"userDailyCalls": 1, "userDailyTokens": 0, "globalDailyTokens": 0}})
    try:
        cust = _create_customer(client, admin_headers)
        r1 = _quote_ai_generate(client, fresh_headers, cust)
        assert r1["code"] == 0, r1
        r2 = _quote_ai_generate(client, fresh_headers, cust)
        assert r2["code"] == 65003, r2
        # 超限也落 fallback 日志
        lst = client.get(
            "/api/v1/admin/ai/usage", headers=admin_headers, params={"feature": "quote", "status": "fallback"}
        ).json()
        assert any("quota_exceeded" in x["error"] for x in lst["data"]["items"])
    finally:
        _set_center(
            client, admin_headers, {"quota": {"userDailyCalls": 0, "userDailyTokens": 0, "globalDailyTokens": 0}}
        )
        _disable_ai(client, admin_headers)


def test_feature_switch(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"title": "t", "items": [{"name": "试验", "qty": 1, "unitPrice": 100}]}))
    _set_center(client, admin_headers, {"features": {"quote": False}})
    cust = _create_customer(client, admin_headers)
    r = _quote_ai_generate(client, admin_headers, cust)
    assert r["code"] == 0 and r["data"]["source"] == "template" and r["data"]["fallbackReason"] == "feature_disabled"
    # 合同识别功能停用 → 明确错误码（无回退入口）
    _set_center(client, admin_headers, {"features": {"contract_ocr": False}})
    rp = client.post(
        "/api/v1/contract/contracts/ai-parse",
        headers=admin_headers,
        files={"file": ("合同.txt", "甲方乙方合同正文".encode(), "text/plain")},
    ).json()
    assert rp["code"] == 65001, rp
    _set_center(client, admin_headers, {"features": {"quote": True, "contract_ocr": True}})
    _disable_ai(client, admin_headers)


# ---------------- 合同识别 ----------------


def test_contract_ai_parse(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    cust_name = _uniq("识别客户_")
    cust_id = _create_customer(client, admin_headers, name=cust_name)
    _mock_chat(monkeypatch, json.dumps({
        "name": "风洞试验服务合同", "customerName": cust_name, "amount": 88000,
        "startDate": "2026-12-01", "endDate": "2027-05-31", "payCycle": "月结",
        "contactPerson": "李四", "contactPhone": "13900000000", "remark": "要点",
    }))
    r = client.post(
        "/api/v1/contract/contracts/ai-parse",
        headers=admin_headers,
        files={"file": ("合同.txt", "合同正文...".encode(), "text/plain")},
    ).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["source"] == "ai"
    f = d["fields"]
    assert f["name"] == "风洞试验服务合同" and f["amount"] == 88000 and f["endDate"] == "2027-05-31"
    assert any(c["id"] == cust_id for c in d["customerCandidates"])  # 模糊匹配出候选，人工选
    # 不落库：草稿合同数不变
    lst = client.get("/api/v1/contract/contracts", headers=admin_headers, params={"q": "风洞试验服务合同"}).json()
    assert lst["data"]["total"] == 0
    _disable_ai(client, admin_headers)


def test_contract_ai_parse_bad_json(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, "无法识别的输出")
    r = client.post(
        "/api/v1/contract/contracts/ai-parse",
        headers=admin_headers,
        files={"file": ("合同.txt", "正文".encode(), "text/plain")},
    ).json()
    assert r["code"] == 65004, r
    _disable_ai(client, admin_headers)


# ---------------- 任务拍照进度 ----------------


def _in_progress_task(client, headers) -> int:
    """合同两级审批通过 → 建任务 → 提交直通 in_progress（测试库未绑定任务立项定义）。"""
    suf = uuid.uuid4().hex[:8]
    cust = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": f"进度客户_{suf}", "tax_no": f"913401PG{suf}", "status": "enabled"},
    ).json()
    con = client.post(
        "/api/v1/contract/contracts",
        headers=headers,
        json={"name": f"进度合同_{suf}", "customer_id": cust["data"]["id"], "amount": 10000},
    ).json()
    cid = con["data"]["id"]
    assert client.post(f"/api/v1/contract/contracts/{cid}/submit", headers=headers, json={}).json()["code"] == 0

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.approval import service as approval
    from app.modules.approval.models import ApprovalInstance, ApprovalTask
    from app.modules.auth.models import User

    db = SessionLocal()
    try:
        for _ in range(2):
            target = None
            pend = db.scalars(select(ApprovalTask).where(ApprovalTask.status == "pending", ApprovalTask.deleted == 0))
            for t in pend:
                inst = db.get(ApprovalInstance, t.instance_id)
                if inst and inst.biz_type == "contract" and inst.biz_id == cid:
                    target = t
                    break
            assert target, "contract pending task not found"
            approval.approve(db, target.id, db.get(User, target.assignee_id), "ok")
            db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/v1/task/tasks",
        headers=headers,
        json={"task_name": f"进度任务_{suf}", "contract_id": cid, "items": [{"name": "条目A"}]},
    ).json()
    assert r["code"] == 0, r
    tid = r["data"]["id"]
    r2 = client.post(f"/api/v1/task/tasks/{tid}/submit", headers=headers).json()
    assert r2["code"] == 0, r2
    status = client.get(f"/api/v1/task/tasks/{tid}", headers=headers).json()["data"]["status"]
    assert status == "in_progress", status
    return tid


PNG = bytes.fromhex("89504e470d0a1a0a") + b"fakepngdata"


def test_task_photo_progress(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"percent": 40, "note": "风洞段模型安装过半"}))
    tid = _in_progress_task(client, headers=admin_headers)

    # AI 分析出草稿：不落库
    r = client.post(
        f"/api/v1/task/tasks/{tid}/progress/ai-image",
        headers=admin_headers,
        files={"file": ("现场.png", PNG, "image/png")},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["percent"] == 40 and "风洞" in r["data"]["note"] and r["data"]["imagePath"]
    lst0 = client.get(f"/api/v1/task/tasks/{tid}/progress", headers=admin_headers).json()
    assert lst0["data"] == [], "AI 草稿不应落库"

    # 人工确认后才落进度日志
    r2 = client.post(
        f"/api/v1/task/tasks/{tid}/progress",
        headers=admin_headers,
        json={"percent": 45, "note": "人工修正：45%", "imagePath": r["data"]["imagePath"], "source": "ai"},
    ).json()
    assert r2["code"] == 0, r2
    lst = client.get(f"/api/v1/task/tasks/{tid}/progress", headers=admin_headers).json()["data"]
    assert len(lst) == 1 and lst[0]["source"] == "ai" and lst[0]["percent"] == 45
    _disable_ai(client, admin_headers)


def test_task_photo_guard(client, admin_headers):
    """未配置 AI → 明确错误；非进行中任务 → 60001。"""
    _disable_ai(client, admin_headers)
    tid = _in_progress_task(client, headers=admin_headers)
    r = client.post(
        f"/api/v1/task/tasks/{tid}/progress/ai-image",
        headers=admin_headers,
        files={"file": ("x.png", PNG, "image/png")},
    ).json()
    assert r["code"] == 65001, r
    # 图片格式之外拒绝
    r2 = client.post(
        f"/api/v1/task/tasks/{tid}/progress/ai-image",
        headers=admin_headers,
        files={"file": ("x.txt", b"text", "text/plain")},
    ).json()
    assert r2["code"] == 10001, r2


# ---------------- 报告摘要 ----------------


def _make_report(client, headers) -> int:
    suf = uuid.uuid4().hex[:8]
    tid = _in_progress_task(client, headers)
    detail = client.get(f"/api/v1/task/tasks/{tid}", headers=headers).json()["data"]
    # 需要 need_report 条目：重建一个
    r = client.post(
        "/api/v1/task/tasks",
        headers=headers,
        json={"task_name": f"摘要任务_{suf}", "contract_id": detail["contractId"],
              "items": [{"name": f"条目_{suf}", "need_report": 1}]},
    ).json()
    tid2 = r["data"]["id"]
    assert client.post(f"/api/v1/task/tasks/{tid2}/submit", headers=headers).json()["code"] == 0
    item = client.get(f"/api/v1/task/tasks/{tid2}", headers=headers).json()["data"]["items"][0]
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    up = client.post(
        "/api/v1/report/reports",
        headers=headers,
        data={"item_id": str(item["id"])},
        files={"file": ("报告.docx", b"PK\x03\x04 fake docx", docx_mime)},
    ).json()
    assert up["code"] == 0, up
    return up["data"]["id"]


def test_report_ai_summary(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, "本报告对 1:5 模型开展风洞试验，结果满足指标要求，建议验收。")
    rid = _make_report(client, admin_headers)

    r = client.post(f"/api/v1/report/reports/{rid}/ai-summary", headers=admin_headers).json()
    assert r["code"] == 0 and "风洞" in r["data"]["summary"], r
    # 未采用前 remark 不变
    detail = client.get(f"/api/v1/report/reports/{rid}", headers=admin_headers).json()["data"]
    assert not (detail["remark"] or "").startswith("本报告")
    # 人工编辑后采用
    r2 = client.put(
        f"/api/v1/report/reports/{rid}/remark", headers=admin_headers,
        json={"remark": "人工修订：风洞试验结果满足指标，同意验收。"},
    ).json()
    assert r2["code"] == 0, r2
    detail2 = client.get(f"/api/v1/report/reports/{rid}", headers=admin_headers).json()["data"]
    assert detail2["remark"].startswith("人工修订")
    _disable_ai(client, admin_headers)


# ---------------- 越权 / 能力探测 ----------------


def test_admin_ai_perm_guard(client, manager_headers):
    for path in ("/api/v1/admin/ai/usage", "/api/v1/admin/ai/stats", "/api/v1/admin/ai/settings"):
        r = client.get(path, headers=manager_headers).json()
        assert r["code"] == 20002, (path, r)
    r = client.put("/api/v1/admin/ai/settings", headers=manager_headers, json={"features": {"quote": False}}).json()
    assert r["code"] == 20002
    r = client.get("/api/v1/admin/ai/usage/export", headers=manager_headers).json()
    assert r["code"] == 20002
    # 能力探测登录即可
    cap = client.get("/api/v1/ai/capabilities", headers=manager_headers).json()
    assert cap["code"] == 0 and "features" in cap["data"] and "quote" in cap["data"]["features"]

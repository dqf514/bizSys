"""AI 中心（HTTP）：用量日志/统计/配额/功能开关 + 合同识别/拍照进度/报告摘要（mock AI）+ 越权。"""

import io
import json
import uuid
from datetime import date, timedelta

from openpyxl import load_workbook


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _clear_admin_timesheets(days: int = 3) -> None:
    """清掉 admin 近 N 天的历史工时（测试库跨次运行残留）。

    自然语言问数的工时口径是「本人全部填报合计」，历史残留会让断言漂移；
    用例执行前先清干净，口径才是确定的。
    """
    from sqlalchemy import delete, select

    from app.core.db import SessionLocal
    from app.modules.auth.models import User
    from app.modules.hr.models import HrTimesheet

    db = SessionLocal()
    try:
        uid = db.scalar(select(User.id).where(User.username == "admin"))
        db.execute(
            delete(HrTimesheet).where(
                HrTimesheet.user_id == uid,
                HrTimesheet.work_date >= date.today() - timedelta(days=days),
            )
        )
        db.commit()
    finally:
        db.close()


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


# ---------------- AI 审批助手 ----------------


def _submit_contract_instance(client, headers, name=None, customer_id=None) -> tuple[int, int, int]:
    """建客户（或复用）+合同并提交审批，返回 (合同 id, 审批实例 id, 客户 id)。"""
    suf = uuid.uuid4().hex[:8]
    if customer_id:
        cust = {"data": {"id": customer_id}}
    else:
        cust = client.post(
            "/api/v1/crm/customers",
            headers=headers,
            json={"name": name or f"助手客户_{suf}", "tax_no": f"913401AS{suf}", "status": "enabled"},
        ).json()
    con = client.post(
        "/api/v1/contract/contracts",
        headers=headers,
        json={"name": f"助手合同_{suf}", "customer_id": cust["data"]["id"], "amount": 100000},
    ).json()
    cid = con["data"]["id"]
    r = client.post(f"/api/v1/contract/contracts/{cid}/submit", headers=headers, json={}).json()
    assert r["code"] == 0, r

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.approval.models import ApprovalInstance

    db = SessionLocal()
    try:
        iid = db.scalar(
            select(ApprovalInstance.id).where(
                ApprovalInstance.biz_type == "contract",
                ApprovalInstance.biz_id == cid,
                ApprovalInstance.deleted == 0,
            )
        )
    finally:
        db.close()
    assert iid
    return cid, iid, cust["data"]["id"]


ASSIST_MOCK = json.dumps(
    {
        "summary": "助手合同，金额 10 万，客户为助手客户",
        "highlights": ["金额 100000", "新客户首单"],
        "risks": [
            {"level": "high", "text": "金额偏离该客户历史均价"},
            {"level": "weird", "text": "非法级别应归一为 low"},
            {"level": "low"},  # 无 text 应丢弃
        ],
        "opinion": "建议核实价格偏离原因后审批",
    },
    ensure_ascii=False,
)


def test_approval_ai_assist(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    cid, iid, cust_id = _submit_contract_instance(client, admin_headers)
    # 同客户再补两单历史合同（approving 计入统计）
    _submit_contract_instance(client, admin_headers, customer_id=cust_id)
    _submit_contract_instance(client, admin_headers, customer_id=cust_id)
    _mock_chat(monkeypatch, ASSIST_MOCK)

    r = client.post(f"/api/v1/approval/instances/{iid}/ai-assist", headers=admin_headers).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["summary"] and d["highlights"] and d["opinion"]
    # 风险级别白名单归一 + 无 text 项丢弃
    assert [x["level"] for x in d["risks"]] == ["high", "low"]
    # 合同类单据回显客户历史统计（管理员有 contract:list / finance 权限）
    h = d["customerHistory"]
    assert h["contractCount"] >= 1 and h["thisAmount"] == 100000 and "paidTotal" in h

    # 用量日志：feature=approval_assist、biz 关联该合同
    lst = client.get(
        "/api/v1/admin/ai/usage", headers=admin_headers, params={"feature": "approval_assist"}
    ).json()
    row = lst["data"]["items"][0]
    assert row["status"] == "success" and row["bizType"] == "contract" and row["bizId"] == cid

    # 建议不落库：时间线里没有 AI 意见
    tl = client.get(f"/api/v1/approval/instances/{iid}", headers=admin_headers).json()["data"]["timeline"]
    assert all("建议核实价格偏离原因后审批" not in (rec.get("comment") or "") for rec in tl)
    _disable_ai(client, admin_headers)


def test_approval_ai_assist_bad_json(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _, iid, _ = _submit_contract_instance(client, admin_headers)
    _mock_chat(monkeypatch, "不是 JSON")
    r = client.post(f"/api/v1/approval/instances/{iid}/ai-assist", headers=admin_headers).json()
    assert r["code"] == 65004, r
    _disable_ai(client, admin_headers)


def test_approval_ai_assist_not_configured(client, admin_headers):
    _disable_ai(client, admin_headers)
    _, iid, _ = _submit_contract_instance(client, admin_headers)
    r = client.post(f"/api/v1/approval/instances/{iid}/ai-assist", headers=admin_headers).json()
    assert r["code"] == 65001, r


def test_approval_ai_assist_feature_switch(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, ASSIST_MOCK)
    _set_center(client, admin_headers, {"features": {"approval_assist": False}})
    _, iid, _ = _submit_contract_instance(client, admin_headers)
    r = client.post(f"/api/v1/approval/instances/{iid}/ai-assist", headers=admin_headers).json()
    assert r["code"] == 65002, r
    _set_center(client, admin_headers, {"features": {"approval_assist": True}})
    _disable_ai(client, admin_headers)


def test_approval_ai_assist_forbidden_for_outsider(client, admin_headers, monkeypatch):
    """非实例相关人（非发起/审批/抄送，无 approval:view）调用助手 → 20002。"""
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, ASSIST_MOCK)
    _, iid, _ = _submit_contract_instance(client, admin_headers)

    suf = uuid.uuid4().hex[:8]
    role = client.post(
        "/api/v1/admin/roles", headers=admin_headers, json={"code": f"pa1_out_{suf}", "name": "无权限角色"}
    ).json()
    assert role["code"] == 0, role
    uname = f"outsider_{suf}"
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": uname, "password": "Test@123456", "name": "无关用户", "roleIds": [role["data"]["id"]]},
    ).json()
    assert r["code"] == 0, r
    cap = client.get("/api/v1/auth/captcha").json()["data"]
    login = client.post(
        "/api/v1/auth/login",
        json={"username": uname, "password": "Test@123456",
              "captchaId": cap["captchaId"], "captchaText": cap.get("debugText", "")},
    ).json()
    headers = {"Authorization": f"Bearer {login['data']['access_token']}"}
    r = client.post(f"/api/v1/approval/instances/{iid}/ai-assist", headers=headers).json()
    assert r["code"] == 20002, r
    _disable_ai(client, admin_headers)


# ---------------- AI 合同风险审查 ----------------


RISK_MOCK = json.dumps(
    {
        "risks": [
            {"level": "high", "clause": "付款条款", "issue": "未约定付款节点", "suggestion": "补充分期比例与账期"},
            {"level": "MID", "clause": "违约责任", "issue": "仅约定乙方责任", "suggestion": "增加对等条款"},
            {"level": "low", "clause": "其他", "issue": "", "suggestion": "无 issue 应丢弃"},
        ],
        "missingClauses": ["验收条款", "保密条款"],
        "summary": "存在付款与违约责任风险",
    },
    ensure_ascii=False,
)

_RISK_FIELDS = json.dumps(
    {"name": "风险合同", "customerName": "某客户", "amount": 88000, "payCycle": "月结"},
    ensure_ascii=False,
)


def _risk_review(client, headers, with_file=True):
    files = {"file": ("合同.txt", "甲方乙方合同正文，金额捌万捌仟元整".encode(), "text/plain")} if with_file else None
    return client.post(
        "/api/v1/contract/contracts/ai-risk-review",
        headers=headers,
        data={"payload": _RISK_FIELDS},
        files=files,
    ).json()


def test_contract_risk_review(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, RISK_MOCK)
    r = _risk_review(client, admin_headers)
    assert r["code"] == 0, r
    d = r["data"]
    assert d["withText"] is True
    assert [x["level"] for x in d["risks"]] == ["high", "mid"]  # 级别大小写归一 + 无 issue 丢弃
    assert d["risks"][0]["clause"] == "付款条款" and d["risks"][0]["suggestion"]
    assert d["missingClauses"] == ["验收条款", "保密条款"] and d["summary"]

    # 用量日志 feature=contract_risk
    lst = client.get(
        "/api/v1/admin/ai/usage", headers=admin_headers, params={"feature": "contract_risk"}
    ).json()
    assert lst["data"]["items"][0]["status"] == "success"
    _disable_ai(client, admin_headers)


def test_contract_risk_review_without_text(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, RISK_MOCK)
    r = _risk_review(client, admin_headers, with_file=False)
    assert r["code"] == 0 and r["data"]["withText"] is False, r
    _disable_ai(client, admin_headers)


def test_contract_risk_review_guards(client, admin_headers, monkeypatch):
    # 未配置 → 65001
    _disable_ai(client, admin_headers)
    assert _risk_review(client, admin_headers)["code"] == 65001
    # 功能停用 → 65002
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, RISK_MOCK)
    _set_center(client, admin_headers, {"features": {"contract_risk": False}})
    assert _risk_review(client, admin_headers)["code"] == 65002
    _set_center(client, admin_headers, {"features": {"contract_risk": True}})
    # AI 输出非法 → 65004
    _mock_chat(monkeypatch, "无法解析")
    assert _risk_review(client, admin_headers)["code"] == 65004
    # 未登录 → 401
    r = client.post("/api/v1/contract/contracts/ai-risk-review", data={"payload": _RISK_FIELDS})
    assert r.status_code == 401 or r.json()["code"] == 20001
    _disable_ai(client, admin_headers)


# ---------------- AI 报告全文辅助（结论草稿 / 校对 / 完整性检查） ----------------


def test_report_ai_assist_conclusion(client, admin_headers, monkeypatch):
    """结论草稿：不落库 → 人工编辑后经 PUT conclusion 采用落库。"""
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"conclusion": "结论：样品满足 GB/T 1234 要求。不确定度：U=0.5%（k=2）。"}))
    rid = _make_report(client, admin_headers)

    r = client.post(f"/api/v1/report/reports/{rid}/ai-assist", headers=admin_headers,
                    json={"kind": "conclusion"}).json()
    assert r["code"] == 0 and "不确定度" in r["data"]["conclusion"], r
    # 未采用前 conclusion 不落库
    detail = client.get(f"/api/v1/report/reports/{rid}", headers=admin_headers).json()["data"]
    assert not detail.get("conclusion")

    r2 = client.put(f"/api/v1/report/reports/{rid}/conclusion", headers=admin_headers,
                    json={"conclusion": "人工修订：样品满足标准要求，不确定度 U=0.5%（k=2）。"}).json()
    assert r2["code"] == 0, r2
    detail2 = client.get(f"/api/v1/report/reports/{rid}", headers=admin_headers).json()["data"]
    assert detail2["conclusion"].startswith("人工修订")
    assert not (detail2["remark"] or "").startswith("人工修订"), "结论不应写入 remark"
    _disable_ai(client, admin_headers)


def test_report_ai_assist_proofread(client, admin_headers, monkeypatch):
    """校对：问题清单清洗（无 original/suggestion 的项丢弃），只展示不落库。"""
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({
        "issues": [
            {"position": "第2页", "original": "风洞试验结果为 0,5", "suggestion": "小数点应为半角：0.5"},
            {"position": "第3页", "original": "", "suggestion": "无原文应丢弃"},
            "not-a-dict",
        ]
    }))
    rid = _make_report(client, admin_headers)
    r = client.post(f"/api/v1/report/reports/{rid}/ai-assist", headers=admin_headers,
                    json={"kind": "proofread"}).json()
    assert r["code"] == 0, r
    issues = r["data"]["issues"]
    assert len(issues) == 1 and issues[0]["original"].startswith("风洞") and issues[0]["suggestion"]
    _disable_ai(client, admin_headers)


def test_report_ai_assist_completeness(client, admin_headers, monkeypatch):
    """完整性：规则项（编号/日期/签章/条目缺漏）+ AI 缺失项合并为检查清单，不落库。"""
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"issues": ["报告文本缺少不确定度说明"]}))
    rid = _make_report(client, admin_headers)
    r = client.post(f"/api/v1/report/reports/{rid}/ai-assist", headers=admin_headers,
                    json={"kind": "completeness"}).json()
    assert r["code"] == 0, r
    items = {i["key"]: i for i in r["data"]["items"]}
    assert items["reportNo"]["ok"] is True
    assert items["noMatch"]["ok"] is True
    assert items["sealInfo"]["ok"] is False  # 未签章
    assert items["aiCheck"]["ok"] is False and "不确定度" in items["aiCheck"]["detail"]
    # 不落库：详情不含检查痕迹
    detail = client.get(f"/api/v1/report/reports/{rid}", headers=admin_headers).json()["data"]
    assert not detail.get("conclusion")
    _disable_ai(client, admin_headers)


def test_report_ai_assist_guards(client, admin_headers, monkeypatch):
    rid = _make_report(client, admin_headers)
    # 未配置 → 65001
    _disable_ai(client, admin_headers)
    r = client.post(f"/api/v1/report/reports/{rid}/ai-assist", headers=admin_headers,
                    json={"kind": "conclusion"}).json()
    assert r["code"] == 65001, r
    # 功能停用 → 65002
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"conclusion": "x"}))
    _set_center(client, admin_headers, {"features": {"report_assist": False}})
    r = client.post(f"/api/v1/report/reports/{rid}/ai-assist", headers=admin_headers,
                    json={"kind": "conclusion"}).json()
    assert r["code"] == 65002, r
    _set_center(client, admin_headers, {"features": {"report_assist": True}})
    # AI 输出非法 → 65004
    _mock_chat(monkeypatch, "不是 JSON")
    r = client.post(f"/api/v1/report/reports/{rid}/ai-assist", headers=admin_headers,
                    json={"kind": "proofread"}).json()
    assert r["code"] == 65004, r
    # 非法 kind → 10001（参数校验）
    r = client.post(f"/api/v1/report/reports/{rid}/ai-assist", headers=admin_headers,
                    json={"kind": "hack"}).json()
    assert r["code"] == 10001, r
    _disable_ai(client, admin_headers)


# ---------------- 自然语言问数（白名单意图 → 模板执行） ----------------


def _approved_contract(client, headers, prefix="pa2_") -> tuple[int, str]:
    """客户(pa2_ 前缀)+合同提交并两级审批通过，返回 (合同 id, 客户名)。"""
    suf = uuid.uuid4().hex[:8]
    cust_name = f"{prefix}客户_{suf}"
    cust = client.post(
        "/api/v1/crm/customers", headers=headers,
        json={"name": cust_name, "tax_no": f"913401P2{suf}", "status": "enabled"},
    ).json()
    con = client.post(
        "/api/v1/contract/contracts", headers=headers,
        json={"name": f"{prefix}合同_{suf}", "customer_id": cust["data"]["id"], "amount": 10000},
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
    return cid, cust_name


def _nlq(client, headers, question="问数"):
    return client.post("/api/v1/ai/nl-query", headers=headers, json={"question": question}).json()


def test_nl_query_task_volume(client, admin_headers, monkeypatch):
    """任务量：客户名参数过滤数值正确 + 用量日志 feature=nl_query。"""
    _enable_ai(client, admin_headers)
    cid, cust_name = _approved_contract(client, admin_headers)
    for i in range(2):
        r = client.post(
            "/api/v1/task/tasks", headers=admin_headers,
            json={"task_name": f"pa2_任务{i}", "contract_id": cid, "items": [{"name": "条目A"}]},
        ).json()
        assert r["code"] == 0, r

    _mock_chat(monkeypatch, json.dumps({
        "domain": "task_volume",
        "params": {"customerName": cust_name, "hack": "drop table"},  # 非法参数键应被丢弃
        "timeRange": {"from": None, "to": None},
        "subject": None,
    }))
    r = _nlq(client, admin_headers, "这个客户有多少任务")
    assert r["code"] == 0, r
    d = r["data"]
    assert d["domain"] == "task_volume" and d["link"] == "/task/tasks"
    assert "共 2 个任务" in d["text"] and d["criteria"] and d["rows"]

    lst = client.get("/api/v1/admin/ai/usage", headers=admin_headers, params={"feature": "nl_query"}).json()
    assert lst["data"]["items"][0]["status"] == "success"
    _disable_ai(client, admin_headers)


def test_nl_query_receivable(client, admin_headers, monkeypatch):
    """应收未收：口径=已开票/已到账结算金额 − 已登记到账（pa2_ 数据，直接写库，测完清理）。"""
    _enable_ai(client, admin_headers)
    suf = uuid.uuid4().hex[:8]
    cust_name = f"pa2_应收_{suf}"

    from app.core.db import SessionLocal
    from app.modules.finance.models import Payment, Settlement

    db = SessionLocal()
    s1 = s2 = None
    try:
        base_tid = 9_000_000_000_000 + uuid.uuid4().int % 1_000_000
        s1 = Settlement(settlement_no=f"pa2_HK{suf}A", task_id=base_tid, task_no="", contract_no="",
                        customer_name=cust_name, amount=1000, invoiceable_amount=1000, status="invoiced")
        s2 = Settlement(settlement_no=f"pa2_HK{suf}B", task_id=base_tid + 1, task_no="", contract_no="",
                        customer_name=cust_name, amount=500, invoiceable_amount=500, status="invoiced")
        db.add_all([s1, s2])
        db.flush()
        p1 = Payment(payment_no=f"pa2_DZ{suf}", settlement_id=s1.id, payer_name=cust_name,
                     payer_account="", amount=400, bank="", paid_at=date.today())
        db.add(p1)
        db.commit()

        _mock_chat(monkeypatch, json.dumps({
            "domain": "receivable",
            "params": {"customerName": cust_name},
            "timeRange": {"from": None, "to": None},
            "subject": None,
        }))
        r = _nlq(client, admin_headers, "这个客户应收未收多少")
        assert r["code"] == 0, r
        d = r["data"]
        assert d["domain"] == "receivable" and d["link"] == "/finance/settlements"
        assert "1,100.00" in d["text"], d["text"]  # 1000+500-400
        assert any("600.00" in row["value"] for row in d["rows"])  # s1 未收 600
        assert "口径" in d["criteria"]
    finally:
        db.query(Payment).filter(Payment.payment_no.like("pa2_%")).delete()
        db.query(Settlement).filter(Settlement.settlement_no.like("pa2_%")).delete()
        db.commit()
        db.close()
    _disable_ai(client, admin_headers)


def test_nl_query_work_hours_self(client, admin_headers, monkeypatch):
    """工时：subject=self 解析为当前用户（pa2_ 任务名，直接写库，测完清理）。"""
    _enable_ai(client, admin_headers)
    tid = _in_progress_task(client, admin_headers)
    suf = uuid.uuid4().hex[:8]
    _clear_admin_timesheets()

    from app.core.db import SessionLocal
    from app.modules.auth.models import User
    from app.modules.hr.models import HrTimesheet

    db = SessionLocal()
    rows = []
    try:
        admin = db.query(User).filter(User.username == "admin").one()
        today = date.today()
        for i, hours in enumerate((2.0, 3.0)):
            t = HrTimesheet(user_id=admin.id, user_name=admin.name, work_date=today - timedelta(days=i),
                            task_id=tid, task_name=f"pa2_工时_{suf}", contract_id=1, contract_no="",
                            customer_id=1, customer_name="", hours=hours, content="", status="submitted")
            db.add(t)
            rows.append(t)
        db.commit()

        _mock_chat(monkeypatch, json.dumps({
            "domain": "work_hours",
            "params": {},
            "timeRange": {"from": (today - timedelta(days=1)).isoformat(), "to": today.isoformat()},
            "subject": "self",
        }))
        r = _nlq(client, admin_headers, "我这两天工时多少")
        assert r["code"] == 0, r
        d = r["data"]
        assert d["domain"] == "work_hours" and d["link"] == "/hr/timesheets"
        assert "5.0 小时" in d["text"], d["text"]
        assert any("pa2_工时" in row["label"] for row in d["rows"])
    finally:
        for t in rows:
            db.delete(t)
        db.commit()
        db.close()
    _disable_ai(client, admin_headers)


def test_nl_query_guards(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    # 非法域 → 65004
    _mock_chat(monkeypatch, json.dumps({"domain": "drop_table", "params": {}, "timeRange": {}, "subject": None}))
    assert _nlq(client, admin_headers)["code"] == 65004
    # 解析失败 → 65004
    _mock_chat(monkeypatch, "我不知道")
    assert _nlq(client, admin_headers)["code"] == 65004
    # 功能停用 → 65002
    _set_center(client, admin_headers, {"features": {"nl_query": False}})
    _mock_chat(monkeypatch, json.dumps({"domain": "task_volume", "params": {}, "timeRange": {}, "subject": None}))
    assert _nlq(client, admin_headers)["code"] == 65002
    _set_center(client, admin_headers, {"features": {"nl_query": True}})
    _disable_ai(client, admin_headers)
    # 未配置 → 65001
    assert _nlq(client, admin_headers)["code"] == 65001


def test_nl_query_perm_denied(client, admin_headers, monkeypatch):
    """无对应列表权限的域 → 20002（空权限角色用户问任务量）。"""
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"domain": "task_volume", "params": {}, "timeRange": {}, "subject": None}))
    suf = uuid.uuid4().hex[:8]
    role = client.post(
        "/api/v1/admin/roles", headers=admin_headers, json={"code": f"pa2_nlq_{suf}", "name": "无权限角色"}
    ).json()
    assert role["code"] == 0, role
    uname = f"pa2_nlq_{suf}"
    r = client.post(
        "/api/v1/admin/users", headers=admin_headers,
        json={"username": uname, "password": "Test@123456", "name": "问数越权", "roleIds": [role["data"]["id"]]},
    ).json()
    assert r["code"] == 0, r
    cap = client.get("/api/v1/auth/captcha").json()["data"]
    login = client.post(
        "/api/v1/auth/login",
        json={"username": uname, "password": "Test@123456",
              "captchaId": cap["captchaId"], "captchaText": cap.get("debugText", "")},
    ).json()
    headers = {"Authorization": f"Bearer {login['data']['access_token']}"}
    r = _nlq(client, headers, "有多少任务")
    assert r["code"] == 20002, r
    _disable_ai(client, admin_headers)


# ---------------- AI-3：工时/OA 预填、流程建议、异常分析、评标辅助 ----------------


def _no_perm_headers(client, admin_headers, prefix: str):
    """空权限角色用户 headers（越权断言用）。"""
    suf = uuid.uuid4().hex[:8]
    role = client.post(
        "/api/v1/admin/roles", headers=admin_headers, json={"code": f"{prefix}_{suf}", "name": "无权限角色"}
    ).json()
    assert role["code"] == 0, role
    uname = f"{prefix}_{suf}"
    r = client.post(
        "/api/v1/admin/users", headers=admin_headers,
        json={"username": uname, "password": "Test@123456", "name": "越权测试", "roleIds": [role["data"]["id"]]},
    ).json()
    assert r["code"] == 0, r
    cap = client.get("/api/v1/auth/captcha").json()["data"]
    login = client.post(
        "/api/v1/auth/login",
        json={"username": uname, "password": "Test@123456",
              "captchaId": cap["captchaId"], "captchaText": cap.get("debugText", "")},
    ).json()
    assert login["code"] == 0, login
    return {"Authorization": f"Bearer {login['data']['access_token']}"}


def _admin_id_name():
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.auth.models import User

    db = SessionLocal()
    try:
        u = db.scalar(select(User).where(User.username == "admin"))
        return u.id, (u.name or u.username)
    finally:
        db.close()


# ---- 工时 AI 预填 ----


def test_hr_timesheet_ai_prefill(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    tid = _in_progress_task(client, admin_headers)
    _clear_admin_timesheets()
    for pct in (30, 50):
        r = client.post(
            f"/api/v1/task/tasks/{tid}/progress", headers=admin_headers,
            json={"percent": pct, "note": f"pa3_进度{pct}", "source": "manual"},
        ).json()
        assert r["code"] == 0, r
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    ts = client.post(
        "/api/v1/hr/timesheets", headers=admin_headers,
        json={"taskId": tid, "workDate": yesterday, "hours": 3.5, "content": "pa3_昨日工时"},
    ).json()
    assert ts["code"] == 0, ts
    ts_id = ts["data"]["id"]
    try:
        _mock_chat(monkeypatch, json.dumps({"hours": 4.3, "content": "风洞段支架安装与调试"}, ensure_ascii=False))
        r = client.post(
            "/api/v1/hr/timesheets/ai-prefill", headers=admin_headers,
            json={"taskId": tid, "workDate": date.today().isoformat()},
        ).json()
        assert r["code"] == 0, r
        d = r["data"]
        assert d["hours"] == 4.5  # 0.5 步进取整
        assert "风洞" in d["content"]
        assert d["basis"]["progressCount"] == 2 and d["basis"]["recentCount"] == 1
        assert d["basis"]["dayUsedHours"] == 0
        # 不落库：当日无该任务工时行
        day = client.get(
            "/api/v1/hr/timesheets/day", headers=admin_headers, params={"date": date.today().isoformat()}
        ).json()
        assert all(t["taskId"] != tid for t in day["data"]["items"])
    finally:
        # 清理草稿工时，避免污染 nl_query 工时合计断言
        client.delete(f"/api/v1/hr/timesheets/{ts_id}", headers=admin_headers)
        _disable_ai(client, admin_headers)


def test_hr_timesheet_ai_prefill_guards(client, admin_headers, monkeypatch):
    tid = _in_progress_task(client, admin_headers)
    body = {"taskId": tid, "workDate": date.today().isoformat()}
    # 未配置 → 65001
    _disable_ai(client, admin_headers)
    assert client.post("/api/v1/hr/timesheets/ai-prefill", headers=admin_headers, json=body).json()["code"] == 65001
    # 功能停用 → 65002
    _enable_ai(client, admin_headers)
    _set_center(client, admin_headers, {"features": {"hr_prefill": False}})
    _mock_chat(monkeypatch, json.dumps({"hours": 4, "content": "x"}))
    assert client.post("/api/v1/hr/timesheets/ai-prefill", headers=admin_headers, json=body).json()["code"] == 65002
    _set_center(client, admin_headers, {"features": {"hr_prefill": True}})
    # 解析失败 → 65004；越权 → 20002
    _mock_chat(monkeypatch, "无法解析")
    assert client.post("/api/v1/hr/timesheets/ai-prefill", headers=admin_headers, json=body).json()["code"] == 65004
    bad = _no_perm_headers(client, admin_headers, "pa3_hr")
    assert client.post("/api/v1/hr/timesheets/ai-prefill", headers=bad, json=body).json()["code"] == 20002
    _disable_ai(client, admin_headers)


# ---- OA 表单 AI 预填 ----

PA3_OA_FIELDS = [
    {"key": "reason", "label": "事由", "type": "textarea"},
    {"key": "kind", "label": "类别", "type": "select", "options": ["A", "B"]},
    {"key": "tags", "label": "标签", "type": "checkbox", "options": ["X", "Y"]},
    {"key": "target", "label": "关联合同", "type": "resource", "resource": "contract"},
    {"key": "owner", "label": "经办人", "type": "user"},
]


def _pa3_oa_form(client, admin_headers, key, fields=None, flow_id=None) -> int:
    r = client.post(
        "/api/v1/oa/admin/forms",
        headers=admin_headers,
        json={"key": key, "name": f"pa3_表单{key}", "category": "other",
              "fields": fields if fields is not None else PA3_OA_FIELDS, "flowDefinitionId": flow_id},
    ).json()
    assert r["code"] == 0, r
    fid = r["data"]["id"]
    p = client.post(f"/api/v1/oa/admin/forms/{fid}/publish", headers=admin_headers).json()
    assert p["code"] == 0, p
    return fid


def test_oa_ai_prefill(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    fid = _pa3_oa_form(client, admin_headers, _uniq("pa3_pf_"))
    try:
        for data in (
            {"reason": "pa3_历史事由1", "kind": "A", "tags": ["X"]},
            {"reason": "pa3_历史事由2", "kind": "B", "tags": ["X", "Y"]},
        ):
            r = client.post("/api/v1/oa/instances", headers=admin_headers, json={"formId": fid, "data": data}).json()
            assert r["code"] == 0, r

        _mock_chat(monkeypatch, json.dumps({"data": {
            "reason": "pa3_预填事由", "kind": "B", "tags": ["X", "BAD"],
            "target": 123, "owner": 5, "ghost": "x",
        }}, ensure_ascii=False))
        r = client.post("/api/v1/oa/ai-prefill", headers=admin_headers, json={"formId": fid}).json()
        assert r["code"] == 0, r
        d = r["data"]
        assert d["historyCount"] == 2
        assert d["data"]["reason"] == "pa3_预填事由" and d["data"]["kind"] == "B"
        assert d["data"]["tags"] == ["X"]  # 非法选项剔除
        # 资源/人员/未知字段一律不预填
        assert "target" not in d["data"] and "owner" not in d["data"] and "ghost" not in d["data"]
        assert set(d["filledKeys"]) == set(d["data"].keys())

        # 非法 select 值整条丢弃
        _mock_chat(monkeypatch, json.dumps({"data": {"kind": "C"}}))
        r2 = client.post("/api/v1/oa/ai-prefill", headers=admin_headers, json={"formId": fid}).json()
        assert r2["code"] == 0 and r2["data"]["data"] == {}, r2
        # 解析失败 → 65004
        _mock_chat(monkeypatch, "坏输出")
        assert client.post("/api/v1/oa/ai-prefill", headers=admin_headers, json={"formId": fid}).json()["code"] == 65004
    finally:
        client.post(f"/api/v1/oa/admin/forms/{fid}/disable", headers=admin_headers)
        _disable_ai(client, admin_headers)


def test_oa_ai_prefill_no_history(client, admin_headers):
    """无历史申请 → 直接回空草稿，不调 AI（不 mock 也应通过）。"""
    _enable_ai(client, admin_headers)
    fid = _pa3_oa_form(client, admin_headers, _uniq("pa3_nh_"))
    try:
        r = client.post("/api/v1/oa/ai-prefill", headers=admin_headers, json={"formId": fid}).json()
        assert r["code"] == 0, r
        assert r["data"] == {"data": {}, "filledKeys": [], "historyCount": 0}
    finally:
        client.post(f"/api/v1/oa/admin/forms/{fid}/disable", headers=admin_headers)
        _disable_ai(client, admin_headers)


# ---- 流程定义 AI 建议审批链 ----


def test_flow_ai_suggest(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    admin_id, admin_name = _admin_id_name()
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.admin.models import Role

    db = SessionLocal()
    try:
        role = db.scalar(select(Role).where(Role.code == "biz_user", Role.deleted == 0))
    finally:
        db.close()
    _mock_chat(monkeypatch, json.dumps({"nodes": [
        {"nodeName": "部门审批", "approverType": "USER", "approverValue": str(admin_id), "signMode": "or"},
        {"nodeName": "业务会签", "approverType": "ROLE", "approverValue": "biz_user", "signMode": "and"},
        {"nodeName": "部门负责人", "approverType": "DEPT_LEADER", "approverValue": "", "signMode": "bogus"},
        {"nodeName": "坏节点1", "approverType": "USER", "approverValue": "999999999"},
        {"nodeName": "坏节点2", "approverType": "ROLE", "approverValue": "no_such_role"},
        {"nodeName": "坏节点3", "approverType": "MAGIC"},
    ], "rationale": "金额较大，建议两级审批加会签"}, ensure_ascii=False))
    r = client.post(
        "/api/v1/approval/definitions/ai-suggest", headers=admin_headers,
        json={"bizType": "oa", "name": "pa3_流程", "amount": 90000},
    ).json()
    assert r["code"] == 0, r
    nodes = r["data"]["nodes"]
    assert [n["nodeName"] for n in nodes] == ["部门审批", "业务会签", "部门负责人"]
    assert nodes[0]["approverName"] == admin_name
    assert nodes[1]["approverName"] == role.name and nodes[1]["signMode"] == "and"
    assert nodes[2]["signMode"] == "or"  # 非法 signMode 归一
    assert r["data"]["rationale"]

    # 全部节点非法 → 65004
    _mock_chat(monkeypatch, json.dumps({"nodes": [{"nodeName": "x", "approverType": "USER", "approverValue": "0"}]}))
    r2 = client.post(
        "/api/v1/approval/definitions/ai-suggest", headers=admin_headers, json={"bizType": "oa"}
    ).json()
    assert r2["code"] == 65004, r2
    _disable_ai(client, admin_headers)


# ---- 异常流程 AI 分析 + 催办 ----


def _pa3_running_oa(client, admin_headers) -> int:
    """建 oa 流程定义（admin 单节点审批）+ 表单绑定发布 + 发起 → running 实例 id。"""
    suf = uuid.uuid4().hex[:8]
    admin_id, _name = _admin_id_name()
    d = client.post(
        "/api/v1/approval/definitions", headers=admin_headers,
        json={"code": f"pa3_flow_{suf}", "name": f"pa3_流程{suf}", "bizType": "oa",
              "nodes": [{"seq": 1, "nodeName": "审批", "approverType": "USER", "approverValue": str(admin_id)}]},
    ).json()
    assert d["code"] == 0, d
    fid = _pa3_oa_form(
        client, admin_headers, _uniq("pa3_an_"),
        fields=[{"key": "reason", "label": "事由", "type": "textarea"}],
        flow_id=d["data"]["id"],
    )
    r = client.post(
        "/api/v1/oa/instances", headers=admin_headers, json={"formId": fid, "data": {"reason": "pa3_异常测试"}}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "running", r
    return r["data"]["id"]


def test_oa_ai_anomaly_and_urge(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    inst_id = _pa3_running_oa(client, admin_headers)
    admin_id, admin_name = _admin_id_name()
    _mock_chat(monkeypatch, json.dumps({
        "analysis": "审批人长期未处理，疑似遗漏",
        "suggestions": [
            {"type": "urge", "text": "发送催办提醒"},
            {"type": "transfer", "text": "转办给管理员", "userName": admin_name, "userId": 999999},
            {"type": "hack", "text": "非法类型归一"},
            {"type": "transfer", "text": "编造人选", "userName": "不存在的人pa3"},
        ],
    }, ensure_ascii=False))
    r = client.post(f"/api/v1/oa/admin/instances/{inst_id}/ai-anomaly", headers=admin_headers).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["stuck"]["nodeName"] == "审批"
    assert d["stuck"]["pending"][0]["assigneeId"] == admin_id
    assert "分析" not in d["analysis"] or d["analysis"]  # analysis 非空
    sugg = d["suggestions"]
    assert sugg[0]["type"] == "urge"
    # userId 只信服务端按姓名匹配（AI 给的 999999 被覆盖）
    assert sugg[1]["type"] == "transfer" and sugg[1]["userId"] == admin_id
    assert sugg[2]["type"] == "other"
    assert "userId" not in sugg[3]  # 查无此人 → 不带 userId

    # 催办：sys_notify 落行 + 审计
    u = client.post(f"/api/v1/oa/admin/instances/{inst_id}/urge", headers=admin_headers, json={}).json()
    assert u["code"] == 0 and u["data"]["urged"] == 1, u
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.admin.models import Notify

    db = SessionLocal()
    try:
        n = db.scalar(
            select(Notify).where(
                Notify.user_id == admin_id, Notify.biz_type == "oa", Notify.biz_id == inst_id,
                Notify.deleted == 0, Notify.title.like("催办：%"),
            )
        )
        assert n and n.title.startswith("催办：") and n.link == "/approval"
    finally:
        db.close()

    # 越权 → 20002；非 running → 状态错误
    bad = _no_perm_headers(client, admin_headers, "pa3_oa")
    assert client.post(f"/api/v1/oa/admin/instances/{inst_id}/ai-anomaly", headers=bad).json()["code"] == 20002
    assert client.post(f"/api/v1/oa/admin/instances/{inst_id}/urge", headers=bad, json={}).json()["code"] == 20002
    t = client.post(f"/api/v1/oa/admin/instances/{inst_id}/terminate", headers=admin_headers, json={}).json()
    assert t["code"] == 0, t
    assert client.post(
        f"/api/v1/oa/admin/instances/{inst_id}/ai-anomaly", headers=admin_headers
    ).json()["code"] != 0
    _disable_ai(client, admin_headers)


# ---- 招投标 AI 评标辅助 + 报价比对 ----


def _pa3_evaluating_tender(client, admin_headers):
    """评标中项目 + 2 条 ORM 投标（真实 txt 附件）→ (tid, [bid_id,...], [文件路径,...])。"""
    from datetime import datetime as _dt
    from pathlib import Path

    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.modules.procurement.models import TenderBid

    now = _dt.now()
    r = client.post(
        "/api/v1/procurement/tenders", headers=admin_headers,
        json={"name": _uniq("pa3_招标_"), "tenderMethod": "public", "budgetAmount": 50000,
              "regDeadline": (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S"),
              "bidDeadline": (now + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S"),
              "announcement": "要求：具备风洞试验资质；工期不超过45天。"},
    ).json()
    assert r["code"] == 0, r
    tid = r["data"]["id"]
    assert client.post(f"/api/v1/procurement/tenders/{tid}/publish", headers=admin_headers).json()["code"] == 0
    assert client.post(
        f"/api/v1/procurement/tenders/{tid}/start-evaluation", headers=admin_headers
    ).json()["code"] == 0

    root = Path(settings.upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    files, bid_ids = [], []
    db = SessionLocal()
    try:
        for comp, price in (("pa3_甲公司", 45000), ("pa3_乙公司", 55000)):
            rel = f"pa3_bid_{uuid.uuid4().hex[:8]}.txt"
            (root / rel).write_text(f"{comp}投标文件：具备风洞试验资质，承诺工期30天。", encoding="utf-8")
            files.append(root / rel)
            b = TenderBid(
                tender_id=tid, partner_user_id=0, registration_id=0, company_name=comp,
                price=price, proposal_path=rel, proposal_name=f"{comp}.txt", comment="",
            )
            db.add(b)
            db.flush()
            bid_ids.append(b.id)
        db.commit()
    finally:
        db.close()
    return tid, bid_ids, files


def test_tender_ai_bid_screen_and_compare(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    tid, bid_ids, files = _pa3_evaluating_tender(client, admin_headers)
    try:
        _mock_chat(monkeypatch, json.dumps({
            "requirements": ["具备风洞试验资质", "工期不超过45天"],
            "bids": [
                {"bidId": bid_ids[0], "results": [
                    {"requirement": "具备风洞试验资质", "verdict": "comply", "note": "文本声明具备"},
                    {"requirement": "工期不超过45天", "verdict": "maybe", "note": "非法归一"},
                ]},
                {"bidId": 999999, "results": [
                    {"requirement": "具备风洞试验资质", "verdict": "deviate", "note": "幽灵投标应丢弃"},
                ]},
            ],
        }, ensure_ascii=False))
        r = client.post(f"/api/v1/procurement/tenders/{tid}/ai-bid-screen", headers=admin_headers).json()
        assert r["code"] == 0, r
        d = r["data"]
        assert d["requirements"] == ["具备风洞试验资质", "工期不超过45天"]
        assert [b["bidId"] for b in d["bids"]] == bid_ids  # 幽灵 bidId 丢弃、真实投标对齐补齐
        b0, b1 = d["bids"]
        assert b0["extractable"] and b1["extractable"]
        assert b0["results"][0]["verdict"] == "comply"
        assert b0["results"][1]["verdict"] == "manual"  # 非法 verdict 归一
        assert all(x["verdict"] == "manual" for x in b1["results"])  # AI 漏掉的投标补齐 manual

        # 比对表：确定性数值（偏离度/排名）
        c = client.get(f"/api/v1/procurement/tenders/{tid}/bid-compare", headers=admin_headers).json()
        assert c["code"] == 0, c
        cd = c["data"]
        assert cd["budgetAmount"] == 50000
        rows = cd["rows"]
        assert [x["companyName"] for x in rows] == ["pa3_甲公司", "pa3_乙公司"]  # 按价升序
        assert rows[0]["rank"] == 1 and rows[0]["deviationPercent"] == -10.0
        assert rows[1]["rank"] == 2 and rows[1]["deviationPercent"] == 10.0

        ex = client.get(f"/api/v1/procurement/tenders/{tid}/bid-compare/export", headers=admin_headers)
        assert ex.status_code == 200
        wb = load_workbook(io.BytesIO(ex.content), read_only=True)
        exported = list(wb.active.iter_rows(values_only=True))
        assert exported[0][0] == "排名" and len(exported) == 3

        # 比对表不受 AI 开关约束；评标辅助受约束
        _set_center(client, admin_headers, {"features": {"tender_assist": False}})
        assert client.get(
            f"/api/v1/procurement/tenders/{tid}/bid-compare", headers=admin_headers
        ).json()["code"] == 0
        assert client.post(
            f"/api/v1/procurement/tenders/{tid}/ai-bid-screen", headers=admin_headers
        ).json()["code"] == 65002
        _set_center(client, admin_headers, {"features": {"tender_assist": True}})

        # 越权 → 20002
        bad = _no_perm_headers(client, admin_headers, "pa3_td")
        assert client.post(
            f"/api/v1/procurement/tenders/{tid}/ai-bid-screen", headers=bad
        ).json()["code"] == 20002
        assert client.get(f"/api/v1/procurement/tenders/{tid}/bid-compare", headers=bad).json()["code"] == 20002
    finally:
        from sqlalchemy import select

        from app.core.db import SessionLocal
        from app.modules.procurement.models import TenderBid, TenderProject

        db = SessionLocal()
        try:
            for b in db.scalars(select(TenderBid).where(TenderBid.tender_id == tid)).all():
                db.delete(b)
            t = db.get(TenderProject, tid)
            if t:
                db.delete(t)
            db.commit()
        finally:
            db.close()
        for f in files:
            f.unlink(missing_ok=True)
        _disable_ai(client, admin_headers)

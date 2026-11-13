"""销售系统-AI 报价（HTTP）：模板 CRUD/版本发布、金额重算、两级审批、AI 回退、发送留痕、转合同幂等、越权。"""

import io
import json
import uuid
from datetime import date, timedelta

from openpyxl import load_workbook

BASE = "/api/v1/sales"
TODAY = date.today()


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _get(client, headers, path, **params):
    return client.get(f"{BASE}/{path}", headers=headers, params=params).json()


def _create_customer(client, headers, name=None) -> int:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": name or f"报价客户_{suf}", "tax_no": f"913401SQ{suf}", "status": "enabled"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _create_template(client, headers, key=None, name="测试报价模板", publish=True) -> int:
    key = key or _uniq("tpl_")
    r = client.post(
        f"{BASE}/templates",
        headers=headers,
        json={
            "key": key,
            "name": name,
            "layout": {
                "headerHtml": "<h2>报价单</h2>",
                "introHtml": "模板默认说明",
                "termsHtml": "模板默认条款",
                "footerHtml": "页脚",
                "validDays": 30,
                "itemColumns": [{"key": "spec", "label": "", "visible": True}],
            },
        },
    ).json()
    assert r["code"] == 0, r
    tid = r["data"]["id"]
    if publish:
        pr = client.post(f"{BASE}/templates/{tid}/publish", headers=headers).json()
        assert pr["code"] == 0, pr
    return tid


def _create_quotation(client, headers, customer_id, template_id=None, **over):
    body = {
        "title": _uniq("报价单_"),
        "customerId": customer_id,
        "contactName": "张三",
        "contactPhone": "13800000000",
        "contactEmail": "zhangsan@example.com",
        "templateId": template_id,
        "validUntil": (TODAY + timedelta(days=30)).isoformat(),
        "items": [
            {"name": "风洞试验", "spec": "1:5 模型", "unit": "次", "qty": 2, "unitPrice": 15000, "remark": ""},
            {"name": "数据处理", "spec": "", "unit": "项", "qty": 1, "unitPrice": 5000, "remark": ""},
        ],
    }
    body.update(over)
    return client.post(f"{BASE}/quotations", headers=headers, json=body).json()


def _drive_approval(biz_id: int, reject_at: int | None = None) -> None:
    """按待办逐节点审批（service 层直调，同 test_hr_timesheet 口径）；reject_at=第几轮驳回。"""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.approval import service as approval
    from app.modules.approval.models import ApprovalInstance, ApprovalTask
    from app.modules.auth.models import User

    db = SessionLocal()
    try:
        round_ = 0
        while True:
            round_ += 1
            target = None
            pending = select(ApprovalTask).where(ApprovalTask.status == "pending", ApprovalTask.deleted == 0)
            for t in db.scalars(pending):
                inst = db.get(ApprovalInstance, t.instance_id)
                if inst and inst.biz_type == "sales_quotation" and inst.biz_id == biz_id:
                    target = t
                    break
            if not target:
                break
            user = db.get(User, target.assignee_id)
            if reject_at == round_:
                approval.reject(db, target.id, user, "测试驳回")
            else:
                approval.approve(db, target.id, user, "ok")
            db.commit()
            if round_ > 10:
                raise AssertionError("approval rounds exceeded")
    finally:
        db.close()


def _approved_quotation(client, headers, **over) -> int:
    cust = _create_customer(client, headers)
    tid = _create_template(client, headers)
    q = _create_quotation(client, headers, cust, tid, **over)
    assert q["code"] == 0, q
    qid = q["data"]["id"]
    r = client.post(f"{BASE}/quotations/{qid}/submit", headers=headers, json={}).json()
    assert r["code"] == 0, r
    _drive_approval(qid)
    return qid


# ---------------- 模板 ----------------


def test_template_crud_version_publish(client, admin_headers):
    key = _uniq("tplc_")
    tid = _create_template(client, admin_headers, key=key, publish=False)
    # 同 key+version=1 冲突 64003
    dup = client.post(f"{BASE}/templates", headers=admin_headers, json={"key": key, "name": "重复"}).json()
    assert dup["code"] == 64003
    # 草稿可编辑
    u = client.put(
        f"{BASE}/templates/{tid}",
        headers=admin_headers,
        json={"key": key, "name": "改名模板", "layout": {"termsHtml": "新条款", "validDays": 10}},
    ).json()
    assert u["code"] == 0 and u["data"]["name"] == "改名模板"
    assert u["data"]["layout"]["termsHtml"] == "新条款"
    # 发布
    p = client.post(f"{BASE}/templates/{tid}/publish", headers=admin_headers).json()
    assert p["code"] == 0 and p["data"]["status"] == "published" and p["data"]["publishedAt"]
    # 已发布不可编辑/不可删
    u2 = client.put(
        f"{BASE}/templates/{tid}", headers=admin_headers, json={"key": key, "name": "x", "layout": {}}
    ).json()
    assert u2["code"] == 64001
    assert client.delete(f"{BASE}/templates/{tid}", headers=admin_headers).json()["code"] == 64001
    # 改版 → v2 草稿；发布 v2 后 v1 自动停用
    v2 = client.post(f"{BASE}/templates/{tid}/new-version", headers=admin_headers).json()
    assert v2["code"] == 0 and v2["data"]["tplVersion"] == 2 and v2["data"]["status"] == "draft"
    v2id = v2["data"]["id"]
    p2 = client.post(f"{BASE}/templates/{v2id}/publish", headers=admin_headers).json()
    assert p2["code"] == 0
    rows = _get(client, admin_headers, "templates")["data"]
    same_key = [t for t in rows if t["key"] == key]
    assert {t["tplVersion"]: t["status"] for t in same_key} == {1: "disabled", 2: "published"}
    # 停用 + options 只剩 published
    d = client.post(f"{BASE}/templates/{v2id}/disable", headers=admin_headers).json()
    assert d["code"] == 0 and d["data"]["status"] == "disabled"
    opts = _get(client, admin_headers, "templates/options")["data"]
    assert all(o["key"] != key for o in opts)


def test_template_permission(client, manager_headers):
    """模板管理默认仅超管：biz_user 403。"""
    assert client.get(f"{BASE}/templates", headers=manager_headers).status_code == 403
    r = client.post(f"{BASE}/templates", headers=manager_headers, json={"key": "x", "name": "x", "layout": {}})
    assert r.status_code == 403


# ---------------- 报价 CRUD / 金额重算 / 校验 ----------------


def test_quotation_create_amounts_recalc(client, admin_headers):
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    r = _create_quotation(client, admin_headers, cust, tid)
    assert r["code"] == 0, r
    d = r["data"]
    # 服务端重算：2×15000 + 1×5000 = 35000；前端传 amount 无效
    assert d["totalAmount"] == 35000.0
    assert d["items"][0]["amount"] == 30000.0
    assert d["quoteNo"] == ""  # 草稿不占号
    assert d["layout"]["termsHtml"] == "模板默认条款"  # 版式快照落行
    assert d["validUntil"] == (TODAY + timedelta(days=30)).isoformat()
    # 客户名快照
    assert d["customerName"].startswith("报价客户_")


def test_quotation_default_valid_until_from_template(client, admin_headers):
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    r = _create_quotation(client, admin_headers, cust, tid, validUntil=None)
    # body 里 validUntil=None 表示不显式传 → 用模板 validDays(30) 推导
    assert r["code"] == 0 and r["data"]["validUntil"] == (TODAY + timedelta(days=30)).isoformat()


def test_submit_validation(client, admin_headers):
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    # 空明细 → 10001
    q1 = _create_quotation(client, admin_headers, cust, tid, items=[])["data"]
    assert client.post(f"{BASE}/quotations/{q1['id']}/submit", headers=admin_headers, json={}).json()["code"] == 10001
    # 有效期已过 → 64001
    q2 = _create_quotation(
        client, admin_headers, cust, tid, validUntil=(TODAY - timedelta(days=1)).isoformat()
    )["data"]
    assert client.post(f"{BASE}/quotations/{q2['id']}/submit", headers=admin_headers, json={}).json()["code"] == 64001
    # 模板未发布（草稿）→ 64002
    draft_tpl = _create_template(client, admin_headers, publish=False)
    q3 = _create_quotation(client, admin_headers, cust, draft_tpl)["data"]
    r = client.post(f"{BASE}/quotations/{q3['id']}/submit", headers=admin_headers, json={}).json()
    assert r["code"] == 64002
    # 全部 0 元 → 合计 0 → 10001
    q4 = _create_quotation(
        client, admin_headers, cust, tid, items=[{"name": "x", "qty": 1, "unitPrice": 0}]
    )["data"]
    assert client.post(f"{BASE}/quotations/{q4['id']}/submit", headers=admin_headers, json={}).json()["code"] == 10001


# ---------------- 审批流 / 编号 / 状态机 ----------------


def test_submit_approve_and_no_reissue(client, admin_headers):
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    q = _create_quotation(client, admin_headers, cust, tid)["data"]
    qid = q["id"]
    r = client.post(f"{BASE}/quotations/{qid}/submit", headers=admin_headers, json={}).json()
    assert r["code"] == 0 and r["data"]["status"] == "approving"
    no1 = r["data"]["quoteNo"]
    assert no1.startswith("BJ")
    # 审批中禁编辑/删除/重复提交
    body = {"title": "改", "customerId": cust, "items": [{"name": "a", "qty": 1, "unitPrice": 1}]}
    assert client.put(f"{BASE}/quotations/{qid}", headers=admin_headers, json=body).json()["code"] == 64001
    assert client.post(f"{BASE}/quotations/{qid}/submit", headers=admin_headers, json={}).json()["code"] == 64001
    _drive_approval(qid)
    d = _get(client, admin_headers, f"quotations/{qid}")["data"]
    assert d["status"] == "approved" and d["flowInstanceId"]
    assert len(d["timeline"]) >= 3  # 发起 + 两级通过


def test_reject_edit_resubmit(client, admin_headers):
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    q = _create_quotation(client, admin_headers, cust, tid)["data"]
    qid = q["id"]
    client.post(f"{BASE}/quotations/{qid}/submit", headers=admin_headers, json={})
    _drive_approval(qid, reject_at=1)
    d = _get(client, admin_headers, f"quotations/{qid}")["data"]
    assert d["status"] == "rejected"
    no1 = d["quoteNo"]
    # 驳回后可改后重提，编号沿用不重发
    u = client.put(
        f"{BASE}/quotations/{qid}",
        headers=admin_headers,
        json={
            "title": "改后重提",
            "customerId": cust,
            "templateId": tid,
            "validUntil": (TODAY + timedelta(days=10)).isoformat(),
            "items": [{"name": "服务", "qty": 1, "unitPrice": 8000}],
        },
    ).json()
    assert u["code"] == 0 and u["data"]["totalAmount"] == 8000.0
    r = client.post(f"{BASE}/quotations/{qid}/submit", headers=admin_headers, json={}).json()
    assert r["code"] == 0 and r["data"]["quoteNo"] == no1
    _drive_approval(qid)
    assert _get(client, admin_headers, f"quotations/{qid}")["data"]["status"] == "approved"


# ---------------- 发送留痕 / 反馈 / 转合同 ----------------


def test_send_email_debug_and_logs(client, admin_headers):
    qid = _approved_quotation(client, admin_headers)
    # SMTP 未配置 → 调试通道留痕
    r = client.post(
        f"{BASE}/quotations/{qid}/send", headers=admin_headers, json={"channel": "email"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "sent"
    assert r["data"]["sentChannel"] == "email" and "zhangsan@example.com" in r["data"]["sentTo"]
    d = _get(client, admin_headers, f"quotations/{qid}")["data"]
    email_logs = [x for x in d["sendLogs"] if x["channel"] == "email"]
    assert email_logs and email_logs[0]["result"] == "debug"
    # print 通道留痕标记
    r2 = client.post(f"{BASE}/quotations/{qid}/send", headers=admin_headers, json={"channel": "print"}).json()
    assert r2["code"] == 0 and r2["data"]["sentChannel"] == "print"
    d2 = _get(client, admin_headers, f"quotations/{qid}")["data"]
    assert any(x["result"] == "marked" and x["channel"] == "print" for x in d2["sendLogs"])


def test_send_requires_approved(client, admin_headers):
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    q = _create_quotation(client, admin_headers, cust, tid)["data"]
    r = client.post(f"{BASE}/quotations/{q['id']}/send", headers=admin_headers, json={"channel": "print"}).json()
    assert r["code"] == 64001


def test_feedback_and_to_contract_idempotent(client, admin_headers):
    qid = _approved_quotation(client, admin_headers)
    # approved 即可登记反馈（无需先发送）
    fb = client.post(
        f"{BASE}/quotations/{qid}/feedback", headers=admin_headers, json={"action": "accept", "note": "客户确认"}
    ).json()
    assert fb["code"] == 0 and fb["data"]["status"] == "accepted" and fb["data"]["feedbackNote"] == "客户确认"
    # 转合同：幂等
    c1 = client.post(f"{BASE}/quotations/{qid}/to-contract", headers=admin_headers).json()
    assert c1["code"] == 0 and c1["data"]["contractId"] and not c1["data"]["duplicated"]
    c2 = client.post(f"{BASE}/quotations/{qid}/to-contract", headers=admin_headers).json()
    assert c2["code"] == 0 and c2["data"]["duplicated"] and c2["data"]["contractId"] == c1["data"]["contractId"]
    # 生成的合同可查到且为草稿
    contract = client.get(f"/api/v1/contract/contracts/{c1['data']['contractId']}", headers=admin_headers).json()
    assert contract["code"] == 0 and contract["data"]["status"] == "draft"
    assert contract["data"]["amount"] == 35000.0 and "报价单" in (contract["data"]["remark"] or "")


def test_feedback_decline_and_state_guard(client, admin_headers):
    qid = _approved_quotation(client, admin_headers)
    fb = client.post(f"{BASE}/quotations/{qid}/feedback", headers=admin_headers, json={"action": "decline"}).json()
    assert fb["code"] == 0 and fb["data"]["status"] == "declined"
    # declined 不能转合同
    r = client.post(f"{BASE}/quotations/{qid}/to-contract", headers=admin_headers).json()
    assert r["code"] == 64001


def test_auto_send_on_approval(client, admin_headers):
    qid = _approved_quotation(client, admin_headers, autoSend=True)
    d = _get(client, admin_headers, f"quotations/{qid}")["data"]
    assert d["status"] == "sent" and d["sentChannel"] == "email"
    auto_logs = [x for x in d["sendLogs"] if x["senderName"] == "auto"]
    assert auto_logs and auto_logs[0]["result"] == "debug"


# ---------------- AI 生成与回退 ----------------


def _enable_ai(client, headers):
    r = client.put(
        "/api/v1/admin/settings",
        headers=headers,
        json={"ai": {"enabled": True, "baseUrl": "https://ai.example.com/v1", "apiKey": "sk-test", "model": "m1"}},
    ).json()
    assert r["code"] == 0 and r["data"]["ai"]["enabled"] and r["data"]["ai"]["apiKeySet"]


def _disable_ai(client, headers):
    r = client.put("/api/v1/admin/settings", headers=headers, json={"ai": {"enabled": False}}).json()
    assert r["code"] == 0 and not r["data"]["ai"]["enabled"]


def test_ai_not_configured_template_fallback(client, admin_headers):
    _disable_ai(client, admin_headers)
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    r = client.post(
        f"{BASE}/quotations/ai-generate",
        headers=admin_headers,
        json={"customerId": cust, "templateId": tid, "requirement": "需要风洞试验报价"},
    ).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["source"] == "template" and d["fallbackReason"] == "ai_not_configured"
    assert d["termsHtml"] == "模板默认条款" and d["items"] == []
    meta = json.loads(d["aiMeta"])
    assert meta["source"] == "template" and meta["fallbackReason"] == "ai_not_configured"


def test_ai_success_structure_recalc(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)

    from app.services import ai as ai_svc

    def fake_chat(db, **kw):
        return json.dumps(
            {
                "title": "AI 报价标题",
                "introHtml": "AI 说明",
                "termsHtml": "AI 条款",
                # 模型算术不可信：amount 故意给错，服务端按 qty×unitPrice 重算
                "items": [{"name": "试验", "spec": "s", "unit": "次", "qty": 3, "unitPrice": 100, "amount": 99999}],
            }
        )

    monkeypatch.setattr(ai_svc, "gateway_chat", fake_chat)
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    r = client.post(
        f"{BASE}/quotations/ai-generate",
        headers=admin_headers,
        json={"customerId": cust, "templateId": tid, "requirement": "三次风洞试验"},
    ).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["source"] == "ai" and d["title"] == "AI 报价标题"
    assert d["items"][0]["amount"] == 300.0  # 重算结果，不是 99999
    assert json.loads(d["aiMeta"])["model"] == "m1"
    _disable_ai(client, admin_headers)


def test_ai_failure_history_fallback(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)

    from app.services import ai as ai_svc

    def boom(db, **kw):
        raise ai_svc.AiUnavailable("timeout")

    monkeypatch.setattr(ai_svc, "gateway_chat", boom)
    # 造一条该客户的历史报价（带明细）
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    _create_quotation(client, admin_headers, cust, tid)  # 该客户的历史报价（带明细）
    r = client.post(
        f"{BASE}/quotations/ai-generate",
        headers=admin_headers,
        json={"customerId": cust, "templateId": tid, "requirement": "再来一单类似的"},
    ).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["source"] == "history" and d["fallbackReason"] == "ai_failed"
    assert len(d["items"]) == 2 and "复制自" in d["items"][0]["remark"]
    assert d["items"][0]["amount"] == 30000.0
    # 无历史客户 → 回退模板默认
    cust2 = _create_customer(client, admin_headers)
    r2 = client.post(
        f"{BASE}/quotations/ai-generate",
        headers=admin_headers,
        json={"customerId": cust2, "templateId": tid, "requirement": "随便"},
    ).json()
    assert r2["data"]["source"] == "template" and r2["data"]["fallbackReason"] == "ai_failed"
    _disable_ai(client, admin_headers)


def test_ai_bad_json_falls_back(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)

    from app.services import ai as ai_svc

    monkeypatch.setattr(ai_svc, "gateway_chat", lambda db, **kw: "这不是 JSON")
    cust = _create_customer(client, admin_headers)
    tid = _create_template(client, admin_headers)
    r = client.post(
        f"{BASE}/quotations/ai-generate",
        headers=admin_headers,
        json={"customerId": cust, "templateId": tid, "requirement": "x"},
    ).json()
    assert r["code"] == 0 and r["data"]["source"] == "template" and r["data"]["fallbackReason"] == "ai_failed"
    _disable_ai(client, admin_headers)


# ---------------- 列表 / counts / 导出 / 越权 ----------------


def test_list_counts_export(client, admin_headers):
    cust = _create_customer(client, admin_headers, name=_uniq("报价检索客户_"))
    tid = _create_template(client, admin_headers)
    title = _uniq("报价列表_")
    _create_quotation(client, admin_headers, cust, tid, title=title)
    _create_quotation(client, admin_headers, cust, tid, title=title)

    counts = _get(client, admin_headers, "quotations/counts")["data"]
    assert counts["draft"] >= 2 and counts["all"] == sum(v for k, v in counts.items() if k != "all")

    r = _get(client, admin_headers, "quotations", q=title[:12])["data"]
    assert r["total"] == 2 and all(title[:12] in i["title"] for i in r["items"])
    # 状态页签过滤 + 客户过滤
    r2 = _get(client, admin_headers, "quotations", q=title[:12], status="draft")["data"]
    assert r2["total"] == 2
    r3 = client.get(
        f"{BASE}/quotations", headers=admin_headers, params={"q": title[:12], "filters[customer_id]": cust}
    ).json()["data"]
    assert r3["total"] == 2 and all(i["customerId"] == cust for i in r3["items"])

    resp = client.get(f"{BASE}/quotations/export", headers=admin_headers, params={"q": title[:12]})
    assert resp.status_code == 200
    ws = load_workbook(io.BytesIO(resp.content)).active
    assert ws.max_row == 3  # 表头 + 2 行


def test_quote_biz_user_allowed(client, manager_headers):
    """biz_user 有报价全套权限（模板管理除外，见 test_template_permission）。"""
    cust = _create_customer(client, manager_headers)
    r = client.post(
        f"{BASE}/quotations",
        headers=manager_headers,
        json={"title": _uniq("业务报价_"), "customerId": cust, "items": [{"name": "a", "qty": 1, "unitPrice": 1}]},
    ).json()
    assert r["code"] == 0
    assert client.get(f"{BASE}/quotations", headers=manager_headers).status_code == 200

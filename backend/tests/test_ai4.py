"""AI-4（HTTP）：样品/发票 OCR、采购价格参考、全局助手、每日摘要、知识库（mock AI）+ 权限开关。"""

import json
import uuid
from datetime import date, timedelta

from tests.test_ai_center import _disable_ai, _enable_ai, _mock_chat, _no_perm_headers, _set_center


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _mock_dispatch(monkeypatch, routes: list[tuple[str, str]]):
    """按 user 消息关键字分流 mock 网关：routes=[(关键字, 返回内容)]，兜底取最后一条。"""
    from app.services import ai as ai_svc

    def fake(url, api_key, payload, timeout):
        user_msg = ""
        for m in reversed(payload.get("messages") or []):
            if m.get("role") == "user":
                c = m.get("content")
                user_msg = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                break
        content = next((c for kw, c in routes if kw in user_msg), routes[-1][1])
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    monkeypatch.setattr(ai_svc, "_post_chat", fake)


# ---------------- 样品 OCR ----------------


def _sample_ocr(client, headers):
    files = {"file": ("标签.png", b"\x89PNG\r\n\x1a\nfake", "image/png")}
    return client.post("/api/v1/task/samples/ai-ocr", headers=headers, files=files).json()


def test_sample_ocr(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _set_center(client, admin_headers, {"features": {"sample_ocr": True}})
    _mock_chat(monkeypatch, json.dumps({
        "name": " 碰撞假人 ", "model": "H3-50M", "vin": "LFV2A21K8P5123456",
        "vehicleType": "SUV", "sampleDate": "2026-11-20",
    }))
    r = _sample_ocr(client, admin_headers)
    assert r["code"] == 0, r
    d = r["data"]
    assert d["name"] == "碰撞假人" and d["model"] == "H3-50M" and d["vin"] == "LFV2A21K8P5123456"
    assert d["vehicleType"] == "SUV" and d["sampleDate"] == "2026-11-20" and d["source"] == "ai"
    _disable_ai(client, admin_headers)


def test_sample_ocr_guards(client, admin_headers, monkeypatch):
    # 未配置 → 65001
    _disable_ai(client, admin_headers)
    assert _sample_ocr(client, admin_headers)["code"] == 65001
    # 功能停用 → 65002
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"name": "x"}))
    _set_center(client, admin_headers, {"features": {"sample_ocr": False}})
    assert _sample_ocr(client, admin_headers)["code"] == 65002
    _set_center(client, admin_headers, {"features": {"sample_ocr": True}})
    # AI 输出非法 → 65004
    _mock_chat(monkeypatch, "看不清")
    assert _sample_ocr(client, admin_headers)["code"] == 65004
    # 非图片类型 → 参数错
    files = {"file": ("标签.txt", b"hello", "text/plain")}
    r = client.post("/api/v1/task/samples/ai-ocr", headers=admin_headers, files=files).json()
    assert r["code"] != 0
    # 越权（无 task:edit）
    _mock_chat(monkeypatch, json.dumps({"name": "x"}))
    assert _sample_ocr(client, _no_perm_headers(client, admin_headers, "pa4_sample"))["code"] == 20002
    _disable_ai(client, admin_headers)


# ---------------- 发票 OCR ----------------


def _make_invoice(settle_amount=50000) -> int:
    """直接落库任务+结算单+发票（绕过审批流，仅造识别对象）。"""
    from app.core.db import SessionLocal
    from app.modules.finance.models import Invoice, Settlement
    from app.modules.task.models import Task

    db = SessionLocal()
    try:
        suf = uuid.uuid4().hex[:8]
        t = Task(task_no=f"PA4-INV-{suf}", task_name=_uniq("pa4任务_"), status="finished")
        db.add(t)
        db.flush()
        s = Settlement(
            settlement_no=f"JS-PA4-{suf}", task_id=t.id, task_no=t.task_no, contract_no="",
            customer_name="pa4客户", amount=settle_amount,
            invoiceable_amount=settle_amount, status="invoiced", confirm_status="confirmed",
        )
        db.add(s)
        db.flush()
        i = Invoice(settlement_id=s.id, amount=settle_amount, status="issued")
        db.add(i)
        db.commit()
        return i.id
    finally:
        db.close()


def _invoice_ocr(client, headers, iid):
    files = {"file": ("发票.png", b"\x89PNG\r\n\x1a\nfake", "image/png")}
    return client.post(f"/api/v1/finance/invoices/{iid}/ai-ocr", headers=headers, files=files).json()


def test_invoice_ocr_and_register(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _set_center(client, admin_headers, {"features": {"invoice_ocr": True}})
    iid = _make_invoice(50000)
    _mock_chat(monkeypatch, json.dumps({
        "invoiceNo": " INV-2026-0001 ", "amount": 50000, "taxRate": 13,
        "buyer": "合肥检测院", "seller": "上海风洞科技", "invoiceDate": "2026-11-20",
    }))
    r = _invoice_ocr(client, admin_headers, iid)
    assert r["code"] == 0, r
    d = r["data"]
    f = d["fields"]
    assert f["invoiceNo"] == "INV-2026-0001" and f["amount"] == 50000 and f["taxRate"] == 13
    assert f["buyer"] == "合肥检测院" and f["seller"] == "上海风洞科技" and f["invoiceDate"] == "2026-11-20"
    # 金额服务端复核：与结算金额一致
    assert d["amountCheck"]["matches"] is True and d["amountCheck"]["settlementAmount"] == 50000

    # 金额不一致 → 复核提示
    _mock_chat(monkeypatch, json.dumps({"invoiceNo": "INV-2", "amount": 45000}))
    r2 = _invoice_ocr(client, admin_headers, iid)
    assert r2["data"]["amountCheck"]["matches"] is False and r2["data"]["amountCheck"]["diff"] == -5000

    # 人工确认后登记落库（含税率/购买方/销售方）
    r3 = client.put(
        f"/api/v1/finance/invoices/{iid}", headers=admin_headers,
        json={"invoiceNo": "INV-2026-0001", "amount": 50000, "taxRate": 13,
              "buyerName": "合肥检测院", "sellerName": "上海风洞科技", "invoiceDate": "2026-11-20"},
    ).json()
    assert r3["code"] == 0, r3
    d3 = r3["data"]
    assert d3["taxRate"] == 13 and d3["buyerName"] == "合肥检测院" and d3["sellerName"] == "上海风洞科技"
    _disable_ai(client, admin_headers)


def test_invoice_ocr_guards(client, admin_headers, monkeypatch):
    iid = _make_invoice(10000)
    _disable_ai(client, admin_headers)
    assert _invoice_ocr(client, admin_headers, iid)["code"] == 65001
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"invoiceNo": "x", "amount": 1}))
    _set_center(client, admin_headers, {"features": {"invoice_ocr": False}})
    assert _invoice_ocr(client, admin_headers, iid)["code"] == 65002
    _set_center(client, admin_headers, {"features": {"invoice_ocr": True}})
    assert _invoice_ocr(client, _no_perm_headers(client, admin_headers, "pa4_inv"), iid)["code"] == 20002
    _disable_ai(client, admin_headers)


# ---------------- 采购价格参考 ----------------


def _make_price_history() -> str:
    """同品名历史：申请明细 2 条（100/120）+ 已确认入库 1 条（110）。返回唯一品名。"""
    from app.core.db import SessionLocal
    from app.modules.procurement.models import (
        PurchaseRequest,
        PurchaseRequestItem,
        StockOrder,
        StockOrderItem,
    )

    item_name = _uniq("pa4_液压油_")
    db = SessionLocal()
    try:
        suf = uuid.uuid4().hex[:8]
        req = PurchaseRequest(request_no=f"PR-PA4-{suf}", title=_uniq("pa4采购_"), status="approved")
        db.add(req)
        db.flush()
        for price in (100, 120):
            db.add(PurchaseRequestItem(
                request_id=req.id, item_name=item_name, spec="46#", unit="桶",
                quantity=1, estimate_price=price,
            ))
        order = StockOrder(order_no=f"IO-PA4-{suf}", order_type="in", status="confirmed")
        db.add(order)
        db.flush()
        db.add(StockOrderItem(order_id=order.id, item_name=item_name, quantity=1, price=110))
        db.commit()
        return item_name
    finally:
        db.close()


def test_price_reference(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    item_name = _make_price_history()
    _mock_chat(monkeypatch, json.dumps({"comment": "当前价高于历史均价 18%，建议议价"}))

    r = client.get(
        "/api/v1/procurement/price-reference",
        headers=admin_headers, params={"itemName": item_name, "price": 130},
    ).json()
    assert r["code"] == 0, r
    d = r["data"]
    s = d["stats"]
    assert s["count"] == 3 and s["avg"] == 110.0 and s["min"] == 100 and s["max"] == 120
    assert s["latestPrice"] and s["latestAt"]
    assert d["deviationPercent"] == 18.2
    assert "议价" in d["comment"]

    # 无历史 → 空统计
    r2 = client.get(
        "/api/v1/procurement/price-reference", headers=admin_headers, params={"itemName": _uniq("pa4无历史_")},
    ).json()
    assert r2["code"] == 0 and r2["data"]["stats"]["count"] == 0 and r2["data"]["stats"]["avg"] is None
    _disable_ai(client, admin_headers)


def test_price_reference_feature_off(client, admin_headers, monkeypatch):
    """功能关闭/AI 未配置：统计照返，点评为空（纯计算不受开关影响）。"""
    _disable_ai(client, admin_headers)
    item_name = _make_price_history()
    r = client.get(
        "/api/v1/procurement/price-reference",
        headers=admin_headers, params={"itemName": item_name, "price": 100},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["stats"]["count"] == 3 and r["data"]["comment"] == ""


# ---------------- 全局助手 ----------------


def test_assistant_navigate(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _mock_chat(monkeypatch, json.dumps({"type": "navigate", "path": "/finance/invoices"}))
    r = client.post(
        "/api/v1/ai/assistant", headers=admin_headers,
        json={"message": "帮我打开发票列表", "menus": [{"title": "发票", "path": "/finance/invoices"}]},
    ).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["type"] == "navigate" and d["path"] == "/finance/invoices" and d["menuName"] == "发票"

    # 幻觉路径（不在候选集）→ 不落导航，降级指引
    _mock_dispatch(monkeypatch, [
        ("候选菜单", json.dumps({"type": "navigate", "path": "/etc/passwd"})),
        ("知识库条目", json.dumps({"answer": "知识库暂无相关内容", "usedIds": []})),
    ])
    r2 = client.post("/api/v1/ai/assistant", headers=admin_headers, json={"message": "打开不存在的页面"}).json()
    assert r2["code"] == 0 and r2["data"]["type"] == "guide", r2
    assert not r2["data"]["path"]
    _disable_ai(client, admin_headers)


def test_assistant_query_and_no_write(client, admin_headers, monkeypatch):
    """问数意图：复用 nl_query 白名单；助手不产生任何业务写操作。"""
    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.modules.admin.models import Notify

    _enable_ai(client, admin_headers)
    _mock_dispatch(monkeypatch, [
        ("候选菜单", json.dumps({"type": "query", "question": "本月有多少任务"})),
        ("问题", json.dumps({"domain": "task_volume", "timeRange": {}, "statuses": []})),
    ])
    db = SessionLocal()
    try:
        before = db.scalar(select(func.count(Notify.id)))
    finally:
        db.close()
    r = client.post("/api/v1/ai/assistant", headers=admin_headers, json={"message": "本月有多少任务"}).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["type"] == "query" and d["data"]["domain"] == "task_volume" and d["text"]
    db = SessionLocal()
    try:
        after = db.scalar(select(func.count(Notify.id)))
    finally:
        db.close()
    assert after == before  # 无站内通知等业务写入
    _disable_ai(client, admin_headers)


def test_assistant_fallback_without_ai(client, admin_headers):
    """AI 未配置：菜单关键词命中 → 导航建议；否则知识库搜索降级。"""
    _disable_ai(client, admin_headers)
    r = client.post(
        "/api/v1/ai/assistant", headers=admin_headers,
        json={"message": "工时填报在哪", "menus": [{"title": "工时填报", "path": "/hr/timesheets"}]},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["type"] == "navigate" and r["data"]["path"] == "/hr/timesheets"
    r2 = client.post("/api/v1/ai/assistant", headers=admin_headers, json={"message": "怎么登记样品"}).json()
    assert r2["code"] == 0 and r2["data"]["type"] == "guide" and r2["data"]["degraded"] is True


# ---------------- 每日摘要 ----------------


def _make_digest_todos(user_id: int):
    """给 admin 造 1 条待审批 + 1 条逾期任务。"""
    from app.core.db import SessionLocal
    from app.modules.approval.models import ApprovalInstance, ApprovalTask
    from app.modules.task.models import Task

    db = SessionLocal()
    try:
        suf = uuid.uuid4().hex[:8]
        inst = ApprovalInstance(
            biz_type="pa4_digest", biz_id=int(suf[:8], 16) % 10**8 + 10**8,
            definition_code="contract", title=f"pa4_摘要合同_{suf}",
            status="running", initiator_id=user_id, initiator_name="admin",
        )
        db.add(inst)
        db.flush()
        db.add(ApprovalTask(
            instance_id=inst.id, seq=1, node_name="部门审批", assignee_id=user_id,
            assignee_name="admin", status="pending",
        ))
        db.add(Task(
            task_no=f"PA4-{suf}", task_name=f"pa4_逾期任务_{suf}", owner_id=user_id, owner_name="admin",
            status="in_progress", plan_finish_date=date.today() - timedelta(days=2),
        ))
        db.commit()
    finally:
        db.close()


def test_daily_digest_and_push(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    _, _ = None, None
    from tests.test_ai_center import _admin_id_name

    admin_id, _name = _admin_id_name()
    _make_digest_todos(admin_id)
    _mock_chat(monkeypatch, json.dumps({
        "summary": "今日有 1 项审批待办，1 项任务已逾期，请优先处理逾期任务。",
        "highlights": ["逾期：pa4_逾期任务", "待审批：pa4_摘要合同"],
    }))
    r = client.get("/api/v1/ai/daily-digest", headers=admin_headers).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["degraded"] is False and "逾期" in d["summary"] and len(d["highlights"]) == 2
    assert d["todos"]["approvalCount"] >= 1 and len(d["todos"]["overdueTasks"]) >= 1

    # 推送：未配置企微 → 站内通知留痕
    r2 = client.post(
        "/api/v1/ai/daily-digest/push", headers=admin_headers,
        json={"summary": d["summary"], "highlights": d["highlights"]},
    ).json()
    assert r2["code"] == 0 and r2["data"]["channel"] == "notify", r2

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.admin.models import Notify

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(Notify).where(Notify.user_id == admin_id, Notify.biz_type == "daily_digest")
        ).all()
        assert rows and "逾期" in rows[-1].content
    finally:
        db.close()
    _disable_ai(client, admin_headers)


def test_daily_digest_degraded(client, admin_headers):
    """AI 未配置：模板摘要降级可用。"""
    _disable_ai(client, admin_headers)
    r = client.get("/api/v1/ai/daily-digest", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["degraded"] is True and "审批待办" in r["data"]["summary"]


# ---------------- 知识库 ----------------


def test_knowledge_crud_and_perm(client, admin_headers):
    title = _uniq("pa4_知识_")
    r = client.post(
        "/api/v1/admin/ai/knowledge", headers=admin_headers,
        json={"title": title, "category": "测试", "content": "pa4 条目正文内容"},
    ).json()
    assert r["code"] == 0, r
    kid = r["data"]["id"]

    r = client.put(
        f"/api/v1/admin/ai/knowledge/{kid}", headers=admin_headers,
        json={"title": title, "category": "测试2", "content": "pa4 更新正文"},
    ).json()
    assert r["code"] == 0, r

    lst = client.get("/api/v1/admin/ai/knowledge", headers=admin_headers, params={"q": "pa4_知识"}).json()
    assert lst["code"] == 0 and lst["data"]["total"] >= 1

    # 附件上传 + 下载
    files = {"file": ("手册.pdf", b"%PDF-1.4 pa4 fake", "application/pdf")}
    up = client.post(f"/api/v1/admin/ai/knowledge/{kid}/attachment", headers=admin_headers, files=files).json()
    assert up["code"] == 0 and up["data"]["attachmentName"] == "手册.pdf", up
    dl = client.get(f"/api/v1/admin/ai/knowledge/{kid}/attachment", headers=admin_headers)
    assert dl.status_code == 200 and b"pa4" in dl.content

    # 无权限 → 20002
    no_perm = _no_perm_headers(client, admin_headers, "pa4_kb")
    assert client.get("/api/v1/admin/ai/knowledge", headers=no_perm).json()["code"] == 20002
    assert client.post(
        "/api/v1/admin/ai/knowledge", headers=no_perm, json={"title": "x"},
    ).json()["code"] == 20002

    r = client.delete(f"/api/v1/admin/ai/knowledge/{kid}", headers=admin_headers)
    assert r.status_code == 204
    lst2 = client.get(
        "/api/v1/admin/ai/knowledge", headers=admin_headers, params={"q": title},
    ).json()
    assert lst2["data"]["total"] == 0


def test_knowledge_ask_with_sources(client, admin_headers, monkeypatch):
    _enable_ai(client, admin_headers)
    title = _uniq("pa4_问答_")
    client.post(
        "/api/v1/admin/ai/knowledge", headers=admin_headers,
        json={"title": title, "category": "样品", "content": "样品入库需在样品列表点击入库按钮并填写备注。"},
    )
    _mock_chat(monkeypatch, json.dumps({"answer": "在样品列表点击入库按钮", "usedIds": []}))
    r = client.post(
        "/api/v1/ai/knowledge/ask", headers=admin_headers, json={"question": f"{title} 样品怎么入库"}
    ).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["degraded"] is False and "入库" in d["answer"]
    # usedIds 为空时兜底标注全部命中来源
    assert d["sources"] and d["sources"][0]["title"] == title
    _disable_ai(client, admin_headers)


def test_knowledge_ask_degraded(client, admin_headers):
    """无 AI：降级为关键词搜索展示原文。"""
    _disable_ai(client, admin_headers)
    title = _uniq("pa4_降级_")
    client.post(
        "/api/v1/admin/ai/knowledge", headers=admin_headers,
        json={"title": title, "category": "采购", "content": "采购申请提交后走会签审批。"},
    )
    r = client.post("/api/v1/ai/knowledge/ask", headers=admin_headers, json={"question": f"{title} 采购审批"}).json()
    assert r["code"] == 0, r
    d = r["data"]
    assert d["degraded"] is True and d["answer"] == ""
    assert d["entries"] and "会签审批" in d["entries"][0]["excerpt"]


def test_knowledge_seed_presets(client, admin_headers):
    """种子预置操作手册条目存在（测试库走 seeds）。"""
    lst = client.get("/api/v1/admin/ai/knowledge", headers=admin_headers, params={"q": "工时填报操作指引"}).json()
    assert lst["code"] == 0 and lst["data"]["total"] >= 1

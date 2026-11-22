"""F6 门户对外业务能力（进度看板 / 报告查阅下载 / 对账单 / 样品交接单）。

重点验证**对外隔离口径**：
- 只看本往来单位（`partner.customer_id`）的单据；
- 报告只暴露"已签章"，不含内部审批意见与审批人；
- 报告下载码**一次性**（校验后即焚），且错码/他人报告一律拒绝；
- 对账单金额口径正确；
- 交接单只暴露本单位的访客单关联记录。
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

SUF = uuid.uuid4().hex[:8]


# ---------------- 工具 ----------------


def _mk_customer(client, headers, tag="F6体验") -> int:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": f"{tag}客户_{suf}", "tax_no": f"913401F6{suf}", "status": "enabled"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _portal_partner(client, admin_headers, customer_id: int, scopes="entrust,staff,visit,tender") -> dict:
    """注册 + 内部审核绑定到指定往来单位，返回门户请求头。"""
    suf = uuid.uuid4().hex[:8]
    username = f"f6exp_{suf}"
    r = client.post(
        "/api/v1/portal/auth/register",
        json={
            "username": username,
            "password": "Portal@123456",
            "company_name": f"F6体验公司_{suf}",
            "contact_name": "体验联系人",
            "phone": "13900000002",
            "company_type": "customer",
        },
    ).json()
    assert r["code"] == 0, r
    accs = client.get("/api/v1/crm/accounts", headers=admin_headers, params={"q": username}).json()
    acc = [i for i in accs["data"]["items"] if i["username"] == username]
    assert acc, accs
    rev = client.post(
        f"/api/v1/crm/accounts/{acc[0]['id']}/review",
        headers=admin_headers,
        json={
            "action": "approve",
            "comment": "F6 体验",
            "customer_id": customer_id,
            "perm_scope": scopes,
            "staff_limit": 3,
        },
    ).json()
    assert rev["code"] == 0, rev
    login = client.post(
        "/api/v1/portal/auth/login", json={"username": username, "password": "Portal@123456"}
    ).json()
    assert login["code"] == 0, login
    return {"Authorization": f"Bearer {login['data']['access_token']}"}


def _mk_task(db, customer_id: int, name: str):
    from app.modules.task.models import Task

    t = Task(
        task_no=f"F6T{uuid.uuid4().hex[:12]}",
        task_name=name,
        customer_id=customer_id,
        customer_name=f"客户{customer_id}",
        status="in_progress",
        progress=40,
    )
    db.add(t)
    db.flush()
    return t


def _mk_settlement(db, task, customer_id: int, amount: str, status="pending"):
    from app.modules.finance.models import Settlement

    s = Settlement(
        settlement_no=f"F6S{SUF}{task.id}",
        task_id=task.id,
        task_no=task.task_no or "",
        customer_id=customer_id,
        customer_name=f"客户{customer_id}",
        amount=Decimal(amount),
        invoiceable_amount=Decimal(amount),
        status=status,
    )
    db.add(s)
    db.flush()
    return s


def _mk_report(db, task, status: str, with_file: bool = False):
    from app.modules.report.models import Report, ReportFile

    file_id = None
    if with_file:
        from app.core.config import settings

        rel = f"report/f6_{SUF}_{task.id}.pdf"
        dest = Path(settings.upload_dir) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF-1.4 f6 portal test")
        f = ReportFile(
            file_name=dest.name,
            size=dest.stat().st_size,
            content_type="application/pdf",
            path=rel,
        )
        db.add(f)
        db.flush()
        file_id = f.id
    r = Report(
        report_no=f"F6B{SUF}{task.id}{status}",
        task_id=task.id,
        task_item_id=0,
        file_id=file_id or 0,
        pdf_file_id=file_id,
        file_name=f"f6_{task.id}.pdf" if with_file else "",
        status=status,
    )
    db.add(r)
    db.flush()
    return r


def _mk_handover(db, customer_id: int, visit_no: str, sample_no: str):
    from app.modules.visitor.models import VisitorSampleHandover, VisitorVisit

    v = VisitorVisit(
        visit_no=visit_no,
        visitor_name="交接访客",
        visitor_company="F6体验公司",
        customer_id=customer_id,
        customer_name=f"客户{customer_id}",
        status="approved",
    )
    db.add(v)
    db.flush()
    h = VisitorSampleHandover(
        handover_no=f"F6H{SUF}{visit_no}",
        visit_id=v.id,
        sample_no=sample_no,
        sample_name="样车 A",
        sample_type="vehicle",
        qty=1,
        handover_user_name="送样人",
        receive_user_name="接收人",
        handover_at=datetime.now(),
        status="done",
    )
    db.add(h)
    db.flush()
    return h


# ---------------- 用例 ----------------


def test_portal_progress_aggregates_only_own_customer(client, admin_headers, db):
    """进度看板只聚合本单位的委托 / 任务 / 结算 / 开票 / 回款。"""
    cid_a = _mk_customer(client, admin_headers, "F6甲")
    cid_b = _mk_customer(client, admin_headers, "F6乙")
    headers = _portal_partner(client, admin_headers, cid_a)

    ta = _mk_task(db, cid_a, f"F6甲任务_{SUF}")
    tb = _mk_task(db, cid_b, f"F6乙任务_{SUF}")
    sa = _mk_settlement(db, ta, cid_a, "1000.00")
    _mk_settlement(db, tb, cid_b, "9999.00")

    from app.modules.finance.models import Invoice, Payment
    from app.modules.task.models import TaskEntrust

    db.add(
        Invoice(
            settlement_id=sa.id,
            invoice_no=f"F6I{SUF}",
            amount=Decimal("600.00"),
            buyer_name="甲方",
            seller_name="卖方",
            invoice_date=date.today(),
            status="issued",
        )
    )
    db.add(
        Payment(
            payment_no=f"F6P{SUF}",
            settlement_id=sa.id,
            payer_name="甲方",
            amount=Decimal("300.00"),
            paid_at=date.today(),
            status="confirmed",
        )
    )
    db.add(
        TaskEntrust(
            entrust_no=f"F6E{SUF}",
            title="F6 委托",
            customer_id=cid_a,
            customer_name="甲",
            status="accepted",
            amount=Decimal("500.00"),
            source="portal",
        )
    )
    db.commit()

    r = client.get("/api/v1/portal/progress", headers=headers).json()
    assert r["code"] == 0, r
    data = r["data"]
    assert data["summary"]["entrustCount"] == 1, data["summary"]
    assert data["summary"]["taskCount"] == 1, data["summary"]
    assert data["summary"]["settledAmount"] == 1000.0, data["summary"]
    assert data["summary"]["invoicedAmount"] == 600.0, data["summary"]
    assert data["summary"]["paidAmount"] == 300.0, data["summary"]

    refs = {s["refNo"] for s in data["stages"]}
    assert sa.settlement_no in refs, refs
    assert not any("9999" in str(s.get("amount")) for s in data["stages"]), data["stages"]
    assert not any("F6乙任务" in str(s.get("title")) for s in data["stages"]), data["stages"]


def test_portal_reports_only_sealed_and_own(client, admin_headers, db):
    """报告列表只暴露本客户任务的已签章报告。"""
    cid_a = _mk_customer(client, admin_headers, "F6报甲")
    cid_b = _mk_customer(client, admin_headers, "F6报乙")
    headers = _portal_partner(client, admin_headers, cid_a)

    ta = _mk_task(db, cid_a, f"F6报甲任务_{SUF}")
    tb = _mk_task(db, cid_b, f"F6报乙任务_{SUF}")
    sealed_a = _mk_report(db, ta, "sealed", with_file=True)
    _mk_report(db, ta, "uploaded")
    _mk_report(db, tb, "sealed")
    db.commit()

    r = client.get("/api/v1/portal/reports", headers=headers).json()
    assert r["code"] == 0, r
    items = r["data"]["items"]
    assert [i["id"] for i in items] == [sealed_a.id], items
    assert items[0]["statusText"] == "已签章", items[0]
    # 对外口径不含内部审批信息
    assert "approval" not in str(items[0]).lower(), items[0]


def test_portal_report_download_code_is_one_time(client, admin_headers, db):
    """下载码一次性：用过即焚；错码、他人报告一律拒绝。"""
    cid_a = _mk_customer(client, admin_headers, "F6下甲")
    cid_b = _mk_customer(client, admin_headers, "F6下乙")
    headers_a = _portal_partner(client, admin_headers, cid_a)
    headers_b = _portal_partner(client, admin_headers, cid_b)

    ta = _mk_task(db, cid_a, f"F6下甲任务_{SUF}")
    tb = _mk_task(db, cid_b, f"F6下乙任务_{SUF}")
    report_a = _mk_report(db, ta, "sealed", with_file=True)
    report_b = _mk_report(db, tb, "sealed", with_file=True)
    db.commit()

    code = client.post(
        f"/api/v1/portal/reports/{report_a.id}/download-code", headers=headers_a
    ).json()
    assert code["code"] == 0, code
    dl = code["data"]["code"]
    assert dl

    # 错码
    bad = client.get(
        f"/api/v1/portal/reports/{report_a.id}/download", headers=headers_a, params={"code": "deadbeef"}
    ).json()
    assert bad["code"] == 98013, bad

    # 正确码 → 下载成功
    ok = client.get(
        f"/api/v1/portal/reports/{report_a.id}/download", headers=headers_a, params={"code": dl}
    )
    assert ok.status_code == 200
    assert b"f6 portal test" in ok.content

    # 一次性：同一码再发 → 无效
    again = client.get(
        f"/api/v1/portal/reports/{report_a.id}/download", headers=headers_a, params={"code": dl}
    ).json()
    assert again["code"] == 98013, again

    # 别人的报告：申请下载码即被拒
    other = client.post(
        f"/api/v1/portal/reports/{report_b.id}/download-code", headers=headers_a
    ).json()
    assert other["code"] == 98011, other

    # 本单位账号访问自己的报告正常
    code_b = client.post(
        f"/api/v1/portal/reports/{report_b.id}/download-code", headers=headers_b
    ).json()
    assert code_b["code"] == 0, code_b


def test_portal_billing_summary(client, admin_headers, db):
    """对账单：结算 / 开票 / 回款金额与待回款口径。"""
    cid = _mk_customer(client, admin_headers, "F6账")
    headers = _portal_partner(client, admin_headers, cid)
    t = _mk_task(db, cid, f"F6账任务_{SUF}")
    s = _mk_settlement(db, t, cid, "2000.00")

    from app.modules.finance.models import Invoice, Payment

    db.add(
        Invoice(
            settlement_id=s.id,
            invoice_no=f"F6I{SUF}B",
            amount=Decimal("2000.00"),
            buyer_name="买方",
            seller_name="卖方",
            invoice_date=date.today(),
            status="issued",
        )
    )
    db.add(
        Payment(
            payment_no=f"F6P{SUF}B",
            settlement_id=s.id,
            payer_name="买方",
            amount=Decimal("1200.00"),
            paid_at=date.today(),
            status="confirmed",
        )
    )
    db.commit()

    r = client.get("/api/v1/portal/billing", headers=headers).json()
    assert r["code"] == 0, r
    data = r["data"]
    assert data["summary"]["totalAmount"] == 2000.0, data["summary"]
    assert data["summary"]["invoicedAmount"] == 2000.0, data["summary"]
    assert data["summary"]["paidAmount"] == 1200.0, data["summary"]
    assert data["summary"]["pendingAmount"] == 800.0, data["summary"]
    assert len(data["items"]) == 1, data["items"]
    item = data["items"][0]
    assert item["invoices"][0]["invoiceNo"] == f"F6I{SUF}B", item
    assert item["payments"][0]["paymentNo"] == f"F6P{SUF}B", item


def test_portal_handovers_only_own_customer(client, admin_headers, db):
    """样品 / 样车交接单只暴露本单位访客单关联的记录。"""
    cid_a = _mk_customer(client, admin_headers, "F6交甲")
    cid_b = _mk_customer(client, admin_headers, "F6交乙")
    headers = _portal_partner(client, admin_headers, cid_a)

    ha = _mk_handover(db, cid_a, f"F6V{SUF}A", f"SP{SUF}A")
    _mk_handover(db, cid_b, f"F6V{SUF}B", f"SP{SUF}B")
    db.commit()

    r = client.get("/api/v1/portal/handovers", headers=headers).json()
    assert r["code"] == 0, r
    items = r["data"]["items"]
    assert [i["id"] for i in items] == [ha.id], items
    assert items[0]["handoverNo"] == ha.handover_no, items[0]
    assert items[0]["statusText"] == "已交接", items[0]

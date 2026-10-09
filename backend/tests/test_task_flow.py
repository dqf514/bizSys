"""任务模块（HTTP）：合同校验 60002 / 状态机 60001 / 编号 / 计数 / 导出。"""

import io
import uuid

from openpyxl import load_workbook

UUID = uuid.uuid4().hex[:8]


def _approved_contract(client, headers):
    suf = uuid.uuid4().hex[:8]  # 每次调用独立后缀：测试库数据跨用例持久
    cust = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": f"任务客户_{suf}", "tax_no": f"913401TSK{suf}", "status": "enabled"},
    ).json()
    assert cust["code"] == 0, cust
    con = client.post(
        "/api/v1/contract/contracts",
        headers=headers,
        json={"name": f"任务合同_{suf}", "customer_id": cust["data"]["id"], "amount": 10000},
    ).json()
    cid = con["data"]["id"]
    assert client.post(f"/api/v1/contract/contracts/{cid}/submit", headers=headers, json={}).json()["code"] == 0

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.approval import service as approval
    from app.modules.approval.models import ApprovalTask

    db = SessionLocal()
    try:
        for _ in range(2):  # 两级依次同意
            rows = db.scalars(
                select(ApprovalTask).where(
                    ApprovalTask.instance_id != 0, ApprovalTask.status == "pending", ApprovalTask.deleted == 0
                )
            ).all()
            mine = [t for t in rows]
            assert mine, "no pending approval task"
            # 找到本合同实例的待办
            from app.modules.approval.models import ApprovalInstance

            target = None
            for t in mine:
                inst = db.get(ApprovalInstance, t.instance_id)
                if inst and inst.biz_type == "contract" and inst.biz_id == cid:
                    target = t
                    break
            assert target, "contract instance task not found"
            from app.modules.auth.models import User

            assignee = db.get(User, target.assignee_id)
            approval.approve(db, target.id, assignee, "ok")
            db.commit()
    finally:
        db.close()
    return cid


def test_task_state_machine_and_errors(client, admin_headers):
    headers = admin_headers
    approved_id = _approved_contract(client, headers)

    # 未通过合同 60002
    draft = client.post(
        "/api/v1/contract/contracts", headers=headers, json={"name": f"草稿_{UUID}", "customer_id": 1, "amount": 1}
    ).json()
    r = client.post(
        "/api/v1/task/tasks", headers=headers, json={"task_name": "x", "contract_id": draft["data"]["id"]}
    ).json()
    assert r["code"] == 60002

    # 建任务（条目带报告编号，样品自动编号）
    r = client.post(
        "/api/v1/task/tasks",
        headers=headers,
        json={
            "task_name": f"任务_{UUID}",
            "task_type": "wind_tunnel",
            "contract_id": approved_id,
            "biz_block": "wind",
            "items": [{"name": "条目1", "need_report": 1}],
            "samples": [{"name": "样车"}],
        },
    ).json()
    assert r["code"] == 0, r
    tid = r["data"]["id"]
    tno = r["data"]["taskNo"]
    assert tno.startswith("RW")
    assert r["data"]["items"][0]["reportNo"].startswith("BG")
    assert r["data"]["samples"][0]["sampleNo"] == f"{tno}-01"
    assert r["data"]["customerName"]

    # 非法流转 60001
    r = client.post(f"/api/v1/task/tasks/{tid}/finish", headers=headers).json()
    assert r["code"] == 60001

    # 全链路流转
    for action, expect in [
        ("submit", "assigning"),
        ("start", "assigned"),
        ("start", "in_progress"),
        ("finish", "finished"),
        ("close", "closed"),
    ]:
        r = client.post(f"/api/v1/task/tasks/{tid}/{action}", headers=headers).json()
        assert r["code"] == 0 and r["data"]["status"] == expect, (action, r)

    # 终态禁改
    r = client.put(f"/api/v1/task/tasks/{tid}", headers=headers, json={"task_name": "y", "version": 1}).json()
    assert r["code"] == 60001

    # 计数 + 检索 + 导出
    counts = client.get("/api/v1/task/tasks/counts", headers=headers).json()["data"]
    assert counts["closed"] >= 1 and counts["all"] >= 1
    lst = client.get("/api/v1/task/tasks", headers=headers, params={"q": f"任务_{UUID}"}).json()["data"]
    assert lst["total"] == 1
    assert lst["items"][0]["taskTypeLabel"]
    resp = client.post("/api/v1/task/tasks/export", headers=headers)
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.active.max_row >= 2


def test_sample_no_unique_after_delete(client, admin_headers):
    """逻辑删除样品后再新增：sample_no 取历史最大位次+1，不撞唯一索引（修复前 500）。"""
    headers = admin_headers
    approved_id = _approved_contract(client, headers)
    r = client.post(
        "/api/v1/task/tasks",
        headers=headers,
        json={"task_name": f"样品_{UUID}", "contract_id": approved_id, "samples": [{"name": "样车A"}]},
    ).json()
    assert r["code"] == 0, r
    tid = r["data"]["id"]
    tno = r["data"]["taskNo"]
    sid = r["data"]["samples"][0]["id"]
    assert r["data"]["samples"][0]["sampleNo"] == f"{tno}-01"

    assert client.delete(f"/api/v1/task/samples/{sid}", headers=headers).json()["code"] == 0
    r = client.post(f"/api/v1/task/tasks/{tid}/samples", headers=headers, json={"name": "样车B"}).json()
    assert r["code"] == 0, r
    assert r["data"]["sampleNo"] == f"{tno}-02"

    # 草稿整体同步（sync_samples）：逻辑删除行留底占位，新样品位次接续不撞号
    r = client.put(
        f"/api/v1/task/tasks/{tid}",
        headers=headers,
        json={"task_name": f"样品_{UUID}", "samples": [{"name": "样车C"}, {"name": "样车D"}]},
    ).json()
    assert r["code"] == 0, r
    nos = [s["sampleNo"] for s in r["data"]["samples"]]
    assert nos == [f"{tno}-02", f"{tno}-03"], nos


def test_invalid_date_filter_is_biz_error(client, admin_headers):
    """非法日期区间 → 10001 业务错误，不再 500。"""
    r = client.get(
        "/api/v1/task/tasks",
        headers=admin_headers,
        params={"range[plan_finish_date]": "not-a-date|2026-12-31"},
    )
    data = r.json()
    assert data["code"] == 10001
    assert r.status_code == 200

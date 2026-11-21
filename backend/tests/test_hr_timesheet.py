"""人事行政-工时填报（HTTP）：填报/防重/未来日期/工时上限/提交审批/撤回/统计三维度/越权。

F5 起工时「提交」= 发起审批：提交后状态 ``approving``，审批通过才 ``approved``，
只有已批准/直通提交的工时才计入项目成本统计。
"""

import io
import uuid
from datetime import date, timedelta

from conftest import approve_instance
from openpyxl import load_workbook

BASE = "/api/v1/hr"
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _get(client, headers, path, **params):
    return client.get(f"{BASE}/{path}", headers=headers, params=params).json()


def _approved_contract(client, headers) -> int:
    """客户 → 合同 → 两级审批通过（沿用 test_task_flow 口径）。"""
    suf = uuid.uuid4().hex[:8]
    cust = client.post(
        "/api/v1/crm/customers",
        headers=headers,
        json={"name": f"工时客户_{suf}", "tax_no": f"913401HR{suf}", "status": "enabled"},
    ).json()
    assert cust["code"] == 0, cust
    con = client.post(
        "/api/v1/contract/contracts",
        headers=headers,
        json={"name": f"工时合同_{suf}", "customer_id": cust["data"]["id"], "amount": 10000},
    ).json()
    assert con["code"] == 0, con
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
            pending = select(ApprovalTask).where(ApprovalTask.status == "pending", ApprovalTask.deleted == 0)
            for t in db.scalars(pending):
                inst = db.get(ApprovalInstance, t.instance_id)
                if inst and inst.biz_type == "contract" and inst.biz_id == cid:
                    target = t
                    break
            assert target, "contract pending task not found"
            approval.approve(db, target.id, db.get(User, target.assignee_id), "ok")
            db.commit()
    finally:
        db.close()
    return cid


def _in_progress_task(client, headers, contract_id: int, name: str) -> int:
    r = client.post(
        "/api/v1/task/tasks",
        headers=headers,
        json={
            "task_name": name,
            "task_type": "windtunnel",
            "contract_id": contract_id,
            "items": [{"name": "条目1"}],
        },
    ).json()
    assert r["code"] == 0, r
    tid = r["data"]["id"]
    r = client.post(f"/api/v1/task/tasks/{tid}/submit", headers=headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "in_progress", r
    return tid


def _create(client, headers, task_id, work_date=TODAY, hours=2.0, content="测试工时内容", submit=False):
    return client.post(
        f"{BASE}/timesheets",
        headers=headers,
        json={
            "taskId": task_id,
            "workDate": work_date.isoformat(),
            "hours": hours,
            "content": content,
            "submit": submit,
        },
    ).json()


# ---------------- 填报校验 ----------------


def test_create_and_day_total(client, admin_headers):
    cid = _approved_contract(client, admin_headers)
    tid = _in_progress_task(client, admin_headers, cid, _uniq("工时任务A_"))
    r = _create(client, admin_headers, tid, hours=2.5)
    assert r["code"] == 0, r
    d = r["data"]
    assert d["status"] == "draft" and d["hours"] == 2.5
    assert d["taskName"] and d["contractNo"].startswith("HT") and d["customerName"]

    # 同日不同任务再填一条 → 当日合计正确
    tid2 = _in_progress_task(client, admin_headers, cid, _uniq("工时任务B_"))
    r2 = _create(client, admin_headers, tid2, hours=1.5, submit=True)
    # F5：提交即发起审批 → approving（审批通过后才 approved）
    assert r2["code"] == 0 and r2["data"]["status"] == "approving" and r2["data"]["submittedAt"]

    day = _get(client, admin_headers, "timesheets/day", date=TODAY.isoformat())["data"]
    mine = [i for i in day["items"] if i["taskId"] in (tid, tid2)]
    assert len(mine) == 2
    assert sum(i["hours"] for i in mine) == 4.0

    week = _get(client, admin_headers, "timesheets/week", date=TODAY.isoformat())["data"]
    assert len(week["days"]) == 7
    today_cell = next(x for x in week["days"] if x["date"] == TODAY.isoformat())
    assert today_cell["totalHours"] >= 4.0 and today_cell["count"] >= 2 and not today_cell["future"]


def test_create_validation(client, admin_headers):
    cid = _approved_contract(client, admin_headers)
    tid = _in_progress_task(client, admin_headers, cid, _uniq("工时任务V_"))
    # 未来日期 63004
    assert _create(client, admin_headers, tid, work_date=TODAY + timedelta(days=1))["code"] == 63004
    # 工时 0 / 超 24 / 非 0.5 步进 → 参数校验 10001
    assert _create(client, admin_headers, tid, hours=0)["code"] == 10001
    assert _create(client, admin_headers, tid, hours=24.5)["code"] == 10001
    assert _create(client, admin_headers, tid, hours=1.3)["code"] == 10001
    assert _create(client, admin_headers, tid, hours=24.0)["code"] == 0
    # 防重：同人同日同任务 63001（撤回草稿后重建仍拦截；删除后可重建）
    assert _create(client, admin_headers, tid)["code"] == 63001
    # 内容必填
    assert _create(client, admin_headers, tid, work_date=YESTERDAY, content="")["code"] == 10001


def test_task_not_fillable(client, admin_headers):
    cid = _approved_contract(client, admin_headers)
    # 草稿任务不可填报
    r = client.post(
        "/api/v1/task/tasks",
        headers=admin_headers,
        json={"task_name": _uniq("工时草稿任务_"), "contract_id": cid, "items": [{"name": "x"}]},
    ).json()
    assert r["code"] == 0
    assert _create(client, admin_headers, r["data"]["id"])["code"] == 63003
    # options 只列进行中任务
    opts = _get(client, admin_headers, "timesheets/options/tasks", contractId=cid)["data"]
    assert all(o["id"] != r["data"]["id"] for o in opts)


def test_options_remote_search(client, admin_headers):
    cid = _approved_contract(client, admin_headers)
    tname = _uniq("工时检索任务_")
    tid = _in_progress_task(client, admin_headers, cid, tname)
    opts = _get(client, admin_headers, "timesheets/options/tasks", contractId=cid, q=tname[:12])["data"]
    assert any(o["id"] == tid and o["customerName"] for o in opts)
    # 合同检索只出 approved
    contracts = _get(client, admin_headers, "timesheets/options/contracts")["data"]
    assert all(c["contractNo"].startswith("HT") or c["contractNo"].startswith("JC") for c in contracts)


# ---------------- 提交只读 / 撤回 / 删除 ----------------


def test_submit_readonly_withdraw_delete(client, admin_headers):
    cid = _approved_contract(client, admin_headers)
    tid = _in_progress_task(client, admin_headers, cid, _uniq("工时任务S_"))
    r = _create(client, admin_headers, tid, submit=True)
    tsid = r["data"]["id"]
    assert r["data"]["status"] == "approving"

    # 审批中只读：改/删 → 63002；重复提交 → 63002
    body = {"taskId": tid, "workDate": TODAY.isoformat(), "hours": 3, "content": "改"}
    assert client.put(f"{BASE}/timesheets/{tsid}", headers=admin_headers, json=body).json()["code"] == 63002
    assert client.delete(f"{BASE}/timesheets/{tsid}", headers=admin_headers).json()["code"] == 63002
    assert client.post(f"{BASE}/timesheets/{tsid}/submit", headers=admin_headers).json()["code"] == 63002

    # 撤回（走审批引擎撤回）→ 退回草稿 → 可改可提交
    w = client.post(f"{BASE}/timesheets/{tsid}/withdraw", headers=admin_headers).json()
    assert w["code"] == 0 and w["data"]["status"] == "draft"
    assert client.post(f"{BASE}/timesheets/{tsid}/withdraw", headers=admin_headers).json()["code"] == 63002
    u = client.put(
        f"{BASE}/timesheets/{tsid}", headers=admin_headers, json={**body, "hours": 3.5, "submit": True}
    ).json()
    assert u["code"] == 0 and u["data"]["status"] == "approving" and u["data"]["hours"] == 3.5

    # 再撤回 → 删除草稿成功 → 同组合可重建（软删不撞唯一键）
    client.post(f"{BASE}/timesheets/{tsid}/withdraw", headers=admin_headers)
    assert client.delete(f"{BASE}/timesheets/{tsid}", headers=admin_headers).json()["code"] == 0
    assert _create(client, admin_headers, tid)["code"] == 0


def test_submit_flow_approve_then_withdraw(client, admin_headers):
    """F5：提交 → 审批通过 → approved；审批中可撤回（引擎撤回，实例终止）。"""
    cid = _approved_contract(client, admin_headers)
    tname = _uniq("工时任务F_")
    tid = _in_progress_task(client, admin_headers, cid, tname)
    r = _create(client, admin_headers, tid, submit=True)
    tsid = r["data"]["id"]
    assert r["data"]["status"] == "approving"

    # 审批通过 → approved（单条工时无 GET 端点，用「我的列表」按任务名回读）
    approve_instance("timesheet", tsid)
    mine = _get(client, admin_headers, "timesheets/my", q=tname[:12])["data"]
    row = next(i for i in mine["items"] if i["id"] == tsid)
    assert row["status"] == "approved"

    # 已批准的工时可自助撤回（改后需重新提交审批）
    w = client.post(f"{BASE}/timesheets/{tsid}/withdraw", headers=admin_headers).json()
    assert w["code"] == 0 and w["data"]["status"] == "draft"


def test_owner_only(client, admin_headers, manager_headers):
    cid = _approved_contract(client, admin_headers)
    tid = _in_progress_task(client, admin_headers, cid, _uniq("工时任务O_"))
    r = _create(client, admin_headers, tid, hours=1.0)
    tsid = r["data"]["id"]
    body = {"taskId": tid, "workDate": TODAY.isoformat(), "hours": 2, "content": "越权改"}
    assert client.put(f"{BASE}/timesheets/{tsid}", headers=manager_headers, json=body).status_code == 403
    assert client.delete(f"{BASE}/timesheets/{tsid}", headers=manager_headers).status_code == 403
    assert client.post(f"{BASE}/timesheets/{tsid}/submit", headers=manager_headers).status_code == 403
    # 我的列表只见本人
    mine = _get(client, manager_headers, "timesheets/my")["data"]
    assert all(i["id"] != tsid for i in mine["items"])


# ---------------- 我的列表 / counts / 导出 ----------------


def test_my_list_counts_export(client, admin_headers):
    cid = _approved_contract(client, admin_headers)
    tname = _uniq("工时列表任务_")
    tid = _in_progress_task(client, admin_headers, cid, tname)
    _create(client, admin_headers, tid, hours=2.0, content="列表测试内容")
    _create(client, admin_headers, tid, work_date=YESTERDAY, hours=4.0, submit=True)

    counts = _get(client, admin_headers, "timesheets/my/counts")["data"]
    # 提交即审批 → 状态 approving；草稿 + 审批中合计 = all
    assert counts["draft"] >= 1 and counts["approving"] >= 1
    assert counts["all"] == sum(counts[k] for k in ("draft", "approving", "approved", "rejected", "submitted"))

    r = _get(client, admin_headers, "timesheets/my", q=tname[:12])["data"]
    assert r["total"] == 2 and all(tname[:12] in i["taskName"] for i in r["items"])
    # 状态页签过滤
    r2 = _get(client, admin_headers, "timesheets/my", q=tname[:12], status="draft")["data"]
    assert r2["total"] == 1 and r2["items"][0]["status"] == "draft"
    # 日期区间过滤（range[work_date]）
    rng = f"{TODAY.isoformat()}|{TODAY.isoformat()}"
    r3 = client.get(
        f"{BASE}/timesheets/my", headers=admin_headers, params={"q": tname[:12], "range[work_date]": rng}
    ).json()["data"]  # range[...] 键含括号，不走 _get 关键字参数
    assert r3["total"] == 1 and r3["items"][0]["workDate"] == TODAY.isoformat()

    resp = client.get(f"{BASE}/timesheets/my/export", headers=admin_headers, params={"q": tname[:12]})
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    assert ws.max_row == 3  # 表头 + 2 行


# ---------------- 统计（管理视角） ----------------


def _stats(client, headers, **params):
    return client.get(f"{BASE}/timesheets/stats", headers=headers, params=params).json()


def test_stats_dimensions(client, admin_headers, manager_headers):
    cid = _approved_contract(client, admin_headers)
    tname = _uniq("工时统计任务_")
    tid = _in_progress_task(client, admin_headers, cid, tname)
    # admin 提交 2h（今天）；manager1 提交 3h（今天）+ 1.5h 草稿（不计入）
    a_ts = _create(client, admin_headers, tid, hours=2.0, submit=True)
    m_ts = _create(client, manager_headers, tid, hours=3.0, submit=True)
    _create(client, manager_headers, tid, work_date=YESTERDAY, hours=1.5)  # draft 不计入
    # F5：审批中的工时不计入成本统计，审批通过后才计入
    approve_instance("timesheet", a_ts["data"]["id"])
    approve_instance("timesheet", m_ts["data"]["id"])

    rng = {"dateStart": TODAY.isoformat(), "dateEnd": TODAY.isoformat(), "taskId": tid}
    # 任务维度：5h / 2 条 / 2 人
    by_task = _stats(client, admin_headers, dimension="task", **rng)["data"]
    row = next(r for r in by_task["rows"] if r["taskId"] == tid)
    assert row["totalHours"] == 5.0 and row["entryCount"] == 2 and row["userCount"] == 2
    assert row["contractNo"].startswith("HT") and row["customerName"]
    # 合同维度：同一合计，任务数 1
    by_contract = _stats(client, admin_headers, dimension="contract", **rng)["data"]
    crow = next(r for r in by_contract["rows"] if r["contractNo"] == row["contractNo"])
    assert crow["totalHours"] == 5.0 and crow["taskCount"] == 1 and crow["userCount"] == 2
    # 人员维度：admin 2h / manager1 3h（草稿 1.5h 不出现）
    by_user = _stats(client, admin_headers, dimension="user", **rng)["data"]
    arow = next(r for r in by_user["rows"] if r["totalHours"] == 2.0)
    mrow = next(r for r in by_user["rows"] if r["totalHours"] == 3.0)
    assert arow["entryCount"] == 1 and mrow["taskCount"] == 1 and mrow["dayCount"] == 1
    # 用户过滤：只看 manager1
    only_m = _stats(client, admin_headers, dimension="user", userId=mrow["userId"], taskId=tid)["data"]
    assert all(r["userId"] == mrow["userId"] for r in only_m["rows"])
    # 部门过滤：user 维度行均带部门名，按部门过滤后只剩该部门人员
    dept_opts = _get(client, admin_headers, "timesheets/stats/options", kind="dept")["data"]
    if dept_opts:
        d0 = dept_opts[0]
        by_dept = _stats(client, admin_headers, dimension="user", deptId=d0["id"], taskId=tid)["data"]
        assert all(r["deptName"] == d0["label"] for r in by_dept["rows"])
    # 人员下钻明细：与汇总口径一致（仅已批准/直通提交）
    detail = _get(client, admin_headers, "timesheets/stats/detail", userId=mrow["userId"], taskId=tid)["data"]
    entries = [i for i in detail["items"] if i["taskId"] == tid]
    assert all(i["status"] in ("approved", "submitted") for i in entries)
    assert sum(i["hours"] for i in entries) == 3.0
    # 统计导出
    resp = client.get(f"{BASE}/timesheets/stats/export", headers=admin_headers, params={"dimension": "task", **rng})
    assert resp.status_code == 200
    ws = load_workbook(io.BytesIO(resp.content)).active
    assert ws.max_row >= 2


def test_stats_permission(client, admin_headers, manager_headers):
    # biz_user（manager1）无 hr:timesheet:stats / stats:export
    assert client.get(f"{BASE}/timesheets/stats", headers=manager_headers).status_code == 403
    assert client.get(f"{BASE}/timesheets/stats/export", headers=manager_headers).status_code == 403
    r1 = client.get(f"{BASE}/timesheets/stats/detail", headers=manager_headers, params={"userId": 1})
    r2 = client.get(f"{BASE}/timesheets/stats/options", headers=manager_headers, params={"kind": "user"})
    assert r1.status_code == 403 and r2.status_code == 403
    assert _stats(client, admin_headers)["data"]["dimension"] == "user"


def test_stats_options(client, admin_headers):
    kinds = _get(client, admin_headers, "timesheets/stats/options", kind="dept")["data"]
    assert isinstance(kinds, list)
    users = _get(client, admin_headers, "timesheets/stats/options", kind="user", q="admin")["data"]
    assert any(u["label"] for u in users)
    tasks = _get(client, admin_headers, "timesheets/stats/options", kind="task", q="工时")["data"]
    assert isinstance(tasks, list)

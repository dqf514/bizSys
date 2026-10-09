"""全链路 E2E 测试：打真实 dev 环境 http://localhost:8000。

用法：cd backend && .venv/Scripts/python scripts/e2e_full.py
测试数据统一 "E2E-" 前缀，结束后尽量清理。
"""

from __future__ import annotations

import io
import os
import sys
import time
from datetime import date

import httpx
import openpyxl

BASE = os.environ.get("E2E_BASE", "http://localhost:8000/api/v1")
TODAY = date.today().isoformat()
RUN = str(int(time.time()))[-6:]  # 每次运行唯一后缀，避免与历史残留冲突

RESULTS: list[tuple[str, bool, str]] = []
BUGS: list[str] = []


def rec(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" | {detail}" if detail else ""))
    if not ok:
        BUGS.append(f"{name}: {detail}")


def bug(desc: str) -> None:
    BUGS.append(desc)
    print(f"BUG  {desc}")


CLIENT = httpx.Client(base_url=BASE, timeout=30, trust_env=False)


def _request(method: str, path: str, **kw) -> httpx.Response:
    """uvicorn --reload / keep-alive 偶发断连，传输层错误重试一次（新连接）。"""
    global CLIENT
    try:
        return CLIENT.request(method, path, **kw)
    except httpx.TransportError:
        CLIENT.close()
        CLIENT = httpx.Client(base_url=BASE, timeout=30, trust_env=False)
        return CLIENT.request(method, path, **kw)


def api(method: str, path: str, token: str | None = None, raw: bool = False, **kw):
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = _request(method, path, headers=headers, **kw)
    if raw:
        return r
    try:
        body = r.json()
    except Exception:
        return r.status_code, -1, None
    return r.status_code, body.get("code"), body.get("data")


def login(username: str, password: str) -> dict | None:
    st, code, data = api("POST", "/auth/login", json={"username": username, "password": password})
    if code == 0 and data:
        return data
    return None


def tok(username: str, password: str) -> str:
    d = login(username, password)
    assert d, f"login failed: {username}"
    return d["access_token"]


def expect_biz_error(name: str, method: str, path: str, token: str, want_code: int | None = None, **kw):
    st, code, _ = api(method, path, token, **kw)
    ok = code != 0 and (want_code is None or code == want_code)
    rec(name, ok, f"http={st} code={code} want={want_code}")


# ---------------------------------------------------------------- 1. 认证
def test_auth() -> str:
    d = login("admin", "Admin@123456")
    rec("auth.login admin", d is not None and bool(d.get("access_token")))
    if not d:
        print("admin 登录失败，终止")
        sys.exit(1)
    admin = d["access_token"]

    st, code, me = api("GET", "/auth/me", admin)
    rec("auth.me", code == 0 and me.get("username") == "admin" and isinstance(me.get("menus"), list),
        f"code={code}")

    # 改密码 → 新密码登录 → 改回
    st, code, _ = api("POST", "/auth/password", admin,
                      json={"oldPassword": "Admin@123456", "newPassword": "Admin@654321"})
    rec("auth.password change", code == 0, f"code={code}")
    d2 = login("admin", "Admin@654321")
    rec("auth.login new password", d2 is not None)
    st, code, _ = api("POST", "/auth/password", (d2 or {}).get("access_token", admin),
                      json={"oldPassword": "Admin@654321", "newPassword": "Admin@123456"})
    rec("auth.password revert", code == 0, f"code={code}")
    d3 = login("admin", "Admin@123456")
    rec("auth.login reverted password", d3 is not None)
    admin = (d3 or d)["access_token"]

    # 原密码错误 → 20004
    expect_biz_error("auth.password wrong old -> 20004", "POST", "/auth/password", admin,
                     want_code=20004, json={"oldPassword": "wrong-pass", "newPassword": "Admin@654321"})

    # refresh 旋转
    d4 = login("admin", "Admin@123456")
    r1 = d4["refresh_token"]
    st, code, d5 = api("POST", "/auth/refresh", json={"refresh_token": r1})
    rec("auth.refresh rotate", code == 0 and d5.get("refresh_token") != r1, f"code={code}")
    st, code, _ = api("POST", "/auth/refresh", json={"refresh_token": r1})
    rec("auth.refresh old token revoked", code != 0, f"code={code}")

    # logout 吊销 refresh
    r2 = d5["refresh_token"]
    st, code, _ = api("POST", "/auth/logout", d5["access_token"], json={"refresh_token": r2})
    rec("auth.logout", code == 0, f"code={code}")
    st, code, _ = api("POST", "/auth/refresh", json={"refresh_token": r2})
    rec("auth.refresh after logout revoked", code != 0, f"code={code}")

    # 未登录 401 / 坏 token 401
    r = api("GET", "/auth/me", raw=True)
    rec("auth.unauth 401", r.status_code == 401, f"http={r.status_code}")
    r = api("GET", "/auth/me", "bad-token", raw=True)
    rec("auth.bad token 401", r.status_code == 401, f"http={r.status_code}")
    return admin


# ---------------------------------------------------------------- 2. CRM
def test_crm(admin: str) -> int:
    body = {"name": "E2E-客户A", "customerType": "", "taxNo": f"E2E-TAX-{RUN}", "grade": "",
            "status": "enabled", "country": "中国", "province": "安徽", "city": "合肥",
            "address": "E2E地址", "remark": "e2e"}
    st, code, c = api("POST", "/crm/customers", admin, json=body)
    rec("crm.create", st == 201 and code == 0 and c.get("customerNo"), f"http={st} code={code}")
    cid = c["id"]

    st, code, data = api("GET", "/crm/customers", admin, params={"q": "E2E-客户A", "status": "all"})
    rec("crm.list search", code == 0 and any(i["id"] == cid for i in data["items"]), f"total={data.get('total')}")

    st, code, data = api("GET", "/crm/customers", admin, params={"page": 1, "size": 1, "status": "all"})
    rec("crm.list pagination", code == 0 and len(data["items"]) == 1 and data["total"] >= 1,
        f"items={len(data.get('items', []))} total={data.get('total')}")

    st, code, opts = api("GET", "/crm/customers/options", admin, params={"q": "E2E-客户A"})
    rec("crm.options fuzzy", code == 0 and any(o["id"] == cid for o in opts), f"opts={opts}")

    st, code, c2 = api("PUT", f"/crm/customers/{cid}", admin, json={**body, "name": "E2E-客户A改"})
    rec("crm.edit", code == 0 and c2["name"] == "E2E-客户A改", f"code={code}")

    # 税号重复
    st, code, _ = api("POST", "/crm/customers", admin, json={**body, "name": "E2E-客户B重复税号"})
    rec("crm.duplicate taxNo rejected", code != 0, f"code={code}")

    r = api("POST", "/crm/customers/export", admin, params={"q": "E2E-"}, raw=True)
    rec("crm.export xlsx", r.status_code == 200 and r.content[:2] == b"PK", f"http={r.status_code} len={len(r.content)}")

    # 模板 + 导入
    r = api("GET", "/crm/customers/template", admin, raw=True)
    rec("crm.template", r.status_code == 200 and r.content[:2] == b"PK", f"http={r.status_code}")
    if r.status_code == 200:
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        row = {h: "" for h in headers}
        for k, v in (("客户名称", "E2E-导入客户1"), ("纳税识别号", f"E2E-TAX-IMP{RUN}"), ("备注", "e2e-import")):
            if k in row:
                row[k] = v
        ws.append([row[h] for h in headers])
        buf = io.BytesIO()
        wb.save(buf)
        st, code, res = api("POST", "/crm/customers/import", admin,
                            files={"file": ("import.xlsx", buf.getvalue(),
                                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        ok = code == 0 and res.get("created", 0) >= 1
        rec("crm.import", ok, f"code={code} res={res}")
        # 清理导入数据
        st, code, data = api("GET", "/crm/customers", admin, params={"q": "E2E-导入客户1"})
        for i in (data or {}).get("items", []):
            api("DELETE", f"/crm/customers/{i['id']}", admin)
    return cid


# ---------------------------------------------------------------- 3. 合同 + 审批
def _create_contract(admin: str, cid: int, name: str) -> dict:
    st, code, c = api("POST", "/contract/contracts", admin, json={
        "name": name, "customerId": cid, "contractType": "", "amount": 1000,
        "startDate": TODAY, "endDate": TODAY, "remark": "e2e",
    })
    assert code == 0, f"create contract {name} failed: {code}"
    return c


def _todo_task_id(token: str, biz_id: int) -> int | None:
    st, code, data = api("GET", "/approval/tasks", token, params={"tab": "todo", "size": 50})
    if code != 0:
        return None
    for it in data["items"]:
        if it["bizId"] == biz_id:
            return it["id"]
    return None


def _get_contract(admin: str, cid: int) -> dict:
    st, code, c = api("GET", f"/contract/contracts/{cid}", admin)
    assert code == 0, f"get contract {cid}: {code}"
    return c


def test_contract(admin: str, manager: str, leader: str, cust_id: int, leader_id: int) -> dict:
    out = {}
    # --- c1 主链路：附件 + 编辑 + 两级审批通过
    c1 = _create_contract(admin, cust_id, "E2E-合同1-主链路")
    out["c1"] = c1["id"]
    rec("contract.create", bool(c1.get("contractNo", "").startswith("HT")), c1.get("contractNo", ""))

    r = api("POST", f"/contract/contracts/{c1['id']}/attachments", admin,
            files={"file": ("e2e-test.pdf", b"%PDF-1.4 e2e", "application/pdf")}, raw=True)
    ok = r.status_code in (200, 201) and r.json().get("code") == 0
    rec("contract.attach pdf", ok, f"http={r.status_code} {r.text[:120]}")
    attach_id = (r.json().get("data") or {}).get("id") if ok else None

    st, code, _ = api("POST", f"/contract/contracts/{c1['id']}/attachments", admin,
                      files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    rec("contract.attach .exe rejected", code != 0, f"code={code}")

    if attach_id:
        r = api("GET", f"/contract/attachments/{attach_id}", admin, raw=True)
        rec("contract.attach download", r.status_code == 200 and r.content.startswith(b"%PDF"),
            f"http={r.status_code}")

    st, code, c1e = api("PUT", f"/contract/contracts/{c1['id']}", admin,
                        json={"name": "E2E-合同1-主链路改", "customerId": cust_id, "amount": 2000})
    rec("contract.edit draft", code == 0 and c1e["name"].endswith("改"), f"code={code}")

    st, code, _ = api("POST", f"/contract/contracts/{c1['id']}/submit", admin, json={})
    rec("contract.submit", code == 0 and _get_contract(admin, c1["id"])["status"] == "approving", f"code={code}")

    st, code, _ = api("PUT", f"/contract/contracts/{c1['id']}", admin,
                      json={"name": "X", "customerId": cust_id})
    rec("contract.edit while approving rejected", code != 0, f"code={code}")

    t = _todo_task_id(manager, c1["id"])
    rec("approval.manager todo has c1", t is not None, f"task={t}")
    # 非审批人操作被拒（leader 操作 manager 的待办 → 70002）
    if t:
        expect_biz_error("approval.non-assignee approve -> 70002", "POST",
                         f"/approval/tasks/{t}/approve", leader, want_code=70002, json={"comment": "x"})
        st, code, _ = api("POST", f"/approval/tasks/{t}/approve", manager, json={"comment": "同意"})
        rec("approval.manager approve", code == 0, f"code={code}")

    t = _todo_task_id(leader, c1["id"])
    rec("approval.leader todo has c1", t is not None, f"task={t}")
    if t:
        st, code, _ = api("POST", f"/approval/tasks/{t}/approve", leader, json={"comment": "同意"})
        rec("approval.leader approve", code == 0, f"code={code}")
    rec("contract.c1 approved", _get_contract(admin, c1["id"])["status"] == "approved")

    st, code, tl = api("GET", f"/approval/instances/contract/{c1['id']}/timeline", admin)
    acts = [r["action"] for r in (tl or {}).get("records", [])]
    rec("approval.timeline c1", code == 0 and acts.count("agree") == 2, f"actions={acts}")

    r = api("POST", "/contract/contracts/export", admin, params={"q": "E2E-"}, raw=True)
    rec("contract.export", r.status_code == 200 and r.content[:2] == b"PK", f"http={r.status_code}")

    st, code, opts = api("GET", "/contract/contracts/options", admin, params={"q": "E2E-合同1"})
    rec("contract.options approved only", code == 0 and any(o.get("id") == c1["id"] or o.get("value") == c1["id"] for o in opts),
        f"opts={opts}")

    # --- c2 驳回链路
    c2 = _create_contract(admin, cust_id, "E2E-合同2-驳回")
    out["c2"] = c2["id"]
    api("POST", f"/contract/contracts/{c2['id']}/submit", admin, json={})
    t = _todo_task_id(manager, c2["id"])
    if t:
        expect_biz_error("approval.reject comment required -> 70003", "POST",
                         f"/approval/tasks/{t}/reject", manager, want_code=70003, json={"comment": "  "})
        st, code, _ = api("POST", f"/approval/tasks/{t}/reject", manager, json={"comment": "E2E驳回"})
        rec("approval.reject", code == 0, f"code={code}")
    stt = _get_contract(admin, c2["id"])["status"]
    rec("contract.c2 rejected", stt == "rejected", f"status={stt}")
    st, code, _ = api("PUT", f"/contract/contracts/{c2['id']}", admin,
                      json={"name": "E2E-合同2-驳回后改", "customerId": cust_id, "amount": 3000})
    rec("contract.edit after reject", code == 0, f"code={code}")
    st, code, _ = api("POST", f"/contract/contracts/{c2['id']}/submit", admin, json={})
    rec("contract.resubmit after reject", code == 0, f"code={code}")
    for who, label in ((manager, "manager"), (leader, "leader")):
        t = _todo_task_id(who, c2["id"])
        if t:
            api("POST", f"/approval/tasks/{t}/approve", who, json={"comment": "ok"})
    rec("contract.c2 approved", _get_contract(admin, c2["id"])["status"] == "approved")

    # --- c3 撤回链路
    c3 = _create_contract(admin, cust_id, "E2E-合同3-撤回")
    out["c3"] = c3["id"]
    api("POST", f"/contract/contracts/{c3['id']}/submit", admin, json={})
    inst = _get_contract(admin, c3["id"]).get("flowInstanceId")
    st, code, _ = api("POST", f"/approval/instances/{inst}/withdraw", admin)
    rec("approval.withdraw", code == 0, f"code={code}")
    rec("contract.c3 back to draft", _get_contract(admin, c3["id"])["status"] == "draft")
    st, code, _ = api("POST", f"/contract/contracts/{c3['id']}/submit", admin, json={})
    rec("contract.resubmit after withdraw", code == 0, f"code={code}")
    for who in (manager, leader):
        t = _todo_task_id(who, c3["id"])
        if t:
            api("POST", f"/approval/tasks/{t}/approve", who, json={"comment": "ok"})
    rec("contract.c3 approved", _get_contract(admin, c3["id"])["status"] == "approved")

    # --- c4 作废链路
    c4 = _create_contract(admin, cust_id, "E2E-合同4-作废")
    out["c4"] = c4["id"]
    api("POST", f"/contract/contracts/{c4['id']}/submit", admin, json={})
    st, code, _ = api("POST", f"/contract/contracts/{c4['id']}/void", admin)
    rec("contract.void while approving rejected", code != 0, f"code={code}")
    inst = _get_contract(admin, c4["id"]).get("flowInstanceId")
    api("POST", f"/approval/instances/{inst}/withdraw", admin)
    st, code, _ = api("POST", f"/contract/contracts/{c4['id']}/void", admin)
    rec("contract.void", code == 0 and _get_contract(admin, c4["id"])["status"] == "voided", f"code={code}")
    st, code, _ = api("POST", f"/contract/contracts/{c4['id']}/void", admin)
    rec("contract.void again -> 50001", code == 50001, f"code={code}")

    # --- c5 加签
    c5 = _create_contract(admin, cust_id, "E2E-合同5-加签")
    out["c5"] = c5["id"]
    api("POST", f"/contract/contracts/{c5['id']}/submit", admin, json={})
    t = _todo_task_id(manager, c5["id"])
    if t:
        st, code, _ = api("POST", f"/approval/tasks/{t}/add-sign", manager,
                          json={"approverId": leader_id, "comment": "E2E加签"})
        rec("approval.add-sign", code == 0, f"code={code}")
    t = _todo_task_id(leader, c5["id"])
    rec("approval.add-signee has todo", t is not None, f"task={t}")
    if t:
        st, code, _ = api("POST", f"/approval/tasks/{t}/approve", leader, json={"comment": "加签同意"})
        rec("approval.add-signee approve", code == 0, f"code={code}")
    t = _todo_task_id(leader, c5["id"])  # 第二节点
    if t:
        api("POST", f"/approval/tasks/{t}/approve", leader, json={"comment": "ok"})
    rec("contract.c5 approved", _get_contract(admin, c5["id"])["status"] == "approved")
    st, code, tl = api("GET", f"/approval/instances/contract/{c5['id']}/timeline", admin)
    acts = [r["action"] for r in (tl or {}).get("records", [])]
    rec("approval.timeline has add_sign", "add_sign" in acts, f"actions={acts}")

    # --- c6 转办
    c6 = _create_contract(admin, cust_id, "E2E-合同6-转办")
    out["c6"] = c6["id"]
    api("POST", f"/contract/contracts/{c6['id']}/submit", admin, json={})
    t = _todo_task_id(manager, c6["id"])
    if t:
        st, code, _ = api("POST", f"/approval/tasks/{t}/transfer", manager,
                          json={"toUserId": leader_id, "comment": "E2E转办"})
        rec("approval.transfer", code == 0, f"code={code}")
    rec("approval.transferer todo cleared", _todo_task_id(manager, c6["id"]) is None)
    t = _todo_task_id(leader, c6["id"])
    rec("approval.transferee has todo", t is not None, f"task={t}")
    if t:
        api("POST", f"/approval/tasks/{t}/approve", leader, json={"comment": "ok"})
    t = _todo_task_id(leader, c6["id"])
    if t:
        api("POST", f"/approval/tasks/{t}/approve", leader, json={"comment": "ok"})
    rec("contract.c6 approved", _get_contract(admin, c6["id"])["status"] == "approved")

    # 审批人 done / 发起人 initiated 页签
    st, code, data = api("GET", "/approval/tasks", leader, params={"tab": "done", "size": 50})
    rec("approval.done tab", code == 0 and any(i["bizId"] == c1["id"] for i in data["items"]),
        f"total={data.get('total')}")
    st, code, data = api("GET", "/approval/tasks", admin, params={"tab": "initiated", "size": 50})
    rec("approval.initiated tab", code == 0 and any(i["bizId"] == c1["id"] for i in data["items"]),
        f"total={data.get('total')}")
    return out


# ---------------------------------------------------------------- 4. 任务
def _task_action(admin: str, tid: int, action: str):
    return api("POST", f"/task/tasks/{tid}/{action}", admin)


def _run_task_to_closed(admin: str, tid: int) -> str:
    for action, want in (("submit", "assigning"), ("start", "assigned"),
                         ("start", "in_progress"), ("finish", "finished"), ("close", "closed")):
        st, code, _ = _task_action(admin, tid, action)
        if code != 0:
            return f"action {action} failed code={code}"
        st, code, t = api("GET", f"/task/tasks/{tid}", admin)
        if t["status"] != want:
            return f"after {action} status={t['status']} want={want}"
    return ""


def test_task(admin: str, manager: str, contract_ids: dict) -> dict:
    out = {}
    st, code, types = api("GET", "/admin/dict/items", admin, params={"type": "task_type"})
    task_type = types[0]["value"] if code == 0 and types else ""
    rec("task.dict task_type", bool(types), f"items={len(types or [])}")
    st, code, blocks = api("GET", "/admin/dict/items", admin, params={"type": "biz_block"})
    biz_block = blocks[0]["value"] if code == 0 and blocks else ""
    st, code, depts = api("GET", "/admin/depts", admin)
    dept_id = depts[0]["id"] if code == 0 and depts else None

    payload = {
        "taskName": "E2E-任务1", "taskType": task_type, "contractId": contract_ids["c1"],
        "content": "e2e内容", "receiver": "张三", "receiverUnit": "E2E单位",
        "bizBlock": biz_block, "deptId": dept_id, "planFinishDate": TODAY,
        "items": [{"name": "E2E-实验项1", "std": "GB", "qty": 2, "needReport": 1}],
        "samples": [{"name": "E2E-样品1", "model": "M1", "vin": "VIN123", "sampleDate": TODAY}],
    }
    st, code, t = api("POST", "/task/tasks", admin, json=payload)
    rec("task.create", st == 201 and code == 0 and t.get("taskNo", "").startswith("RW"),
        f"http={st} code={code} no={t.get('taskNo') if t else None}")
    t1 = t["id"]
    out["t1"] = t1
    st, code, detail = api("GET", f"/task/tasks/{t1}", admin)
    items, samples = detail.get("items", []), detail.get("samples", [])
    rec("task.item reportNo BG", bool(items) and items[0].get("reportNo", "").startswith("BG"),
        f"reportNo={items[0].get('reportNo') if items else None}")
    rec("task.sample sampleNo auto", bool(samples) and samples[0].get("sampleNo", "").startswith(t["taskNo"]),
        f"sampleNo={samples[0].get('sampleNo') if samples else None}")

    # 非 approved 合同 → 60002
    st, code, _ = api("POST", "/task/tasks", admin, json={**payload, "taskName": "E2E-任务-坏合同",
                                                        "contractId": contract_ids["c4"], "items": [], "samples": []})
    rec("task.create voided contract -> 60002", code == 60002, f"code={code}")

    # 非法流转
    expect_biz_error("task.start on draft -> 60001", "POST", f"/task/tasks/{t1}/start", admin, want_code=60001)
    expect_biz_error("task.finish on draft -> 60001", "POST", f"/task/tasks/{t1}/finish", admin, want_code=60001)

    # 提交分配 → 通知部门用户（manager 在 dept 中则收到）
    err = _run_task_to_closed(admin, t1)
    rec("task.flow to closed", err == "", err)
    expect_biz_error("task.finish on closed -> 60001", "POST", f"/task/tasks/{t1}/finish", admin, want_code=60001)

    st, code, counts = api("GET", "/task/tasks/counts", admin)
    rec("task.counts", code == 0 and isinstance(counts, dict) and counts.get("closed", 0) >= 1, f"counts={counts}")

    # 样品出入库
    sid = samples[0]["id"] if samples else None
    if sid:
        st, code, _ = api("POST", f"/task/samples/{sid}/out", admin)
        rec("task.sample out", code == 0, f"code={code}")
        st, code, d2 = api("GET", f"/task/tasks/{t1}", admin)
        s2 = [s for s in d2["samples"] if s["id"] == sid]
        rec("task.sample out state", s2 and s2[0]["inStock"] == "out", f"inStock={s2[0]['inStock'] if s2 else None}")
        st, code, _ = api("POST", f"/task/samples/{sid}/in", admin)
        rec("task.sample in", code == 0, f"code={code}")

    # 搜索 + 分页
    st, code, data = api("GET", "/task/tasks", admin, params={"q": "E2E-任务1"})
    rec("task.list search", code == 0 and any(i["id"] == t1 for i in data["items"]))
    st, code, data = api("GET", "/task/tasks", admin, params={"page": 1, "size": 1, "status": "all"})
    rec("task.list pagination", code == 0 and len(data["items"]) == 1)

    r = api("POST", "/task/tasks/export", admin, params={"q": "E2E-"}, raw=True)
    rec("task.export", r.status_code == 200 and r.content[:2] == b"PK", f"http={r.status_code}")

    # t2：跑完 closed，用于财务“非创建人被拒”
    st, code, t2 = api("POST", "/task/tasks", admin,
                       json={"taskName": "E2E-任务2", "contractId": contract_ids["c2"], "deptId": dept_id})
    if code == 0:
        out["t2"] = t2["id"]
        err = _run_task_to_closed(admin, t2["id"])
        rec("task.t2 to closed", err == "", err)
    else:
        rec("task.t2 create", False, f"code={code}")
    return out


# ---------------------------------------------------------------- 5. 财务
def test_finance(admin: str, manager: str, task_ids: dict) -> None:
    t1, t2 = task_ids["t1"], task_ids.get("t2")

    st, code, opts = api("GET", "/finance/settlements/task-options", admin, params={"q": "E2E-任务"})
    rec("finance.task-options closed only", code == 0 and any(o["value"] == t1 for o in opts),
        f"opts={opts}")

    # 非创建人被拒（manager 对 admin 创建的 t2 建结算单 → 80003）
    if t2:
        expect_biz_error("finance.create non-creator -> 80003", "POST", "/finance/settlements", manager,
                         want_code=80003, json={"taskId": t2, "amount": 100})

    st, code, s = api("POST", "/finance/settlements", admin,
                      json={"taskId": t1, "amount": 1000, "invoiceableAmount": 1000, "remark": "e2e"})
    ok = st == 201 and code == 0 and s.get("settlementNo", "").startswith("HK")
    rec("finance.create settlement HK", ok, f"http={st} code={code} no={s.get('settlementNo') if s else None}")
    sid = s["id"]

    st, code, t = api("GET", f"/task/tasks/{t1}", admin)
    rec("finance.task settled", t["status"] == "settled", f"status={t['status']}")

    expect_biz_error("finance.duplicate -> 80002", "POST", "/finance/settlements", admin,
                     want_code=80002, json={"taskId": t1, "amount": 100})

    st, code, _ = api("POST", f"/finance/settlements/{sid}/apply-invoice", admin, json={"comment": "e2e开票"})
    rec("finance.apply-invoice", code == 0, f"code={code}")
    st, code, d = api("GET", f"/finance/settlements/{sid}", admin)
    rec("finance.status invoicing", d["status"] == "invoicing", f"status={d['status']}")

    t = _todo_task_id(manager, sid)  # bizType=invoice，bizId=settlementId
    rec("finance.invoice todo for manager", t is not None, f"task={t}")
    if t:
        st, code, _ = api("POST", f"/approval/tasks/{t}/approve", manager, json={"comment": "同意开票"})
        rec("finance.invoice approve", code == 0, f"code={code}")
    st, code, d = api("GET", f"/finance/settlements/{sid}", admin)
    invs = d.get("invoices", [])
    rec("finance.invoiced + invoice row", d["status"] == "invoiced" and len(invs) >= 1,
        f"status={d['status']} invoices={len(invs)}")

    if invs:
        inv_id = invs[0]["id"]
        st, code, inv = api("PUT", f"/finance/invoices/{inv_id}", admin,
                            json={"invoiceNo": f"E2E-INV-{RUN}", "amount": 1000, "invoiceDate": TODAY})
        rec("finance.invoice register no", code == 0 and inv.get("invoiceNo") == f"E2E-INV-{RUN}", f"code={code}")

    # 到账两笔：400 + 600 → 自动 paid
    st, code, p1 = api("POST", "/finance/payments", admin, json={
        "settlementId": sid, "payType": "bank", "payerName": "E2E-客户A改", "amount": 400, "paidAt": TODAY})
    ok = st == 201 and code == 0 and p1.get("paymentNo", "").startswith("DZ")
    rec("finance.payment1 DZ", ok, f"http={st} code={code} no={p1.get('paymentNo') if p1 else None}")
    st, code, d = api("GET", f"/finance/settlements/{sid}", admin)
    rec("finance.still invoiced after partial", d["status"] == "invoiced" and float(d.get("paidAmount", 0)) == 400,
        f"status={d['status']} paid={d.get('paidAmount')}")

    st, code, p2 = api("POST", "/finance/payments", admin, json={
        "settlementId": sid, "payType": "bank", "payerName": "E2E-客户A改", "amount": 600, "paidAt": TODAY})
    rec("finance.payment2", code == 0, f"code={code}")
    st, code, d = api("GET", f"/finance/settlements/{sid}", admin)
    rec("finance.auto paid", d["status"] == "paid", f"status={d['status']} paid={d.get('paidAmount')}")

    st, code, data = api("GET", "/finance/payments", admin, params={"q": "E2E"})
    rec("finance.payments list", code == 0 and data["total"] >= 2, f"total={data.get('total')}")

    r = api("GET", "/finance/settlements/export", admin, params={"q": "E2E"}, raw=True)
    rec("finance.settlements export", r.status_code == 200 and r.content[:2] == b"PK", f"http={r.status_code}")
    r = api("GET", "/finance/payments/export", admin, raw=True)
    rec("finance.payments export", r.status_code == 200 and r.content[:2] == b"PK", f"http={r.status_code}")


# ---------------------------------------------------------------- 6. 管理后台
def test_admin(admin: str) -> None:
    # 防御性清理历史残留（逻辑删的用户/角色会占唯一键）
    st, code, users = api("GET", "/admin/users", admin, params={"q": "e2e_", "size": 50})
    for u in (users or {}).get("items", []):
        if u["username"] in ("e2e_op", "e2e_roleuser"):
            api("DELETE", f"/admin/users/{u['id']}", admin)
    st, code, roles0 = api("GET", "/admin/roles", admin, params={"q": "e2e_role"})
    for r in ((roles0 or {}).get("items") if isinstance(roles0, dict) else roles0) or []:
        if r.get("code") == "e2e_role":
            api("DELETE", f"/admin/roles/{r['id']}", admin)

    # 用户 CRUD + 重置密码
    st, code, roles = api("GET", "/admin/roles", admin)
    role_list = roles.get("items", []) if isinstance(roles, dict) else (roles or [])
    biz_role = next((r for r in role_list if r.get("code") == "biz_user"), None)
    st, code, u = api("POST", "/admin/users", admin, json={
        "username": "e2e_op", "password": "E2e@123456", "name": "E2E-操作员",
        "status": "enabled", "roleIds": [biz_role["id"]] if biz_role else []})
    rec("admin.user create", st == 201 and code == 0, f"http={st} code={code}")
    uid = u["id"] if u else None
    if uid:
        st, code, _ = api("PUT", f"/admin/users/{uid}", admin, json={
            "username": "e2e_op", "name": "E2E-操作员改", "status": "enabled",
            "roleIds": [biz_role["id"]] if biz_role else []})
        rec("admin.user update", code == 0, f"code={code}")
        st, code, _ = api("POST", f"/admin/users/{uid}/reset-password", admin, json={"password": "E2e@654321"})
        rec("admin.user reset-password", code == 0, f"code={code}")
        rec("admin.user login new pw", login("e2e_op", "E2e@654321") is not None)

    # 角色新建 + 挂菜单 + 权限生效
    st, code, tree = api("GET", "/admin/menus/tree", admin, params={"include_buttons": True})
    rec("admin.menus tree", code == 0 and bool(tree))

    def find_perm(nodes, perm):
        for n in nodes or []:
            if n.get("permission") == perm:
                return n["id"]
            r = find_perm(n.get("children"), perm)
            if r:
                return r
        return None

    crm_list_menu = find_perm(tree, "crm:customer:list")
    st, code, role = api("POST", "/admin/roles", admin, json={
        "code": "e2e_role", "name": "E2E-角色", "dataScope": "all", "status": "enabled"})
    rec("admin.role create", code == 0, f"code={code}")
    rid = role["id"] if role else None
    if rid and crm_list_menu:
        st, code, _ = api("PUT", f"/admin/roles/{rid}/menus", admin, json={"menuIds": [crm_list_menu]})
        rec("admin.role bind menus", code == 0, f"code={code}")
        st, code, u2 = api("POST", "/admin/users", admin, json={
            "username": "e2e_roleuser", "password": "E2e@123456", "name": "E2E-角色用户",
            "status": "enabled", "roleIds": [rid]})
        ru = login("e2e_roleuser", "E2e@123456")
        rec("admin.role user login", ru is not None)
        if ru:
            rt = ru["access_token"]
            st, code, me = api("GET", "/auth/me", rt)
            rec("admin.role perm in me", "crm:customer:list" in (me.get("perms") or []),
                f"perms={me.get('perms')}")
            st, code, _ = api("GET", "/crm/customers", rt)
            rec("admin.role perm allows crm", code == 0, f"code={code}")
            st, code, _ = api("GET", "/contract/contracts", rt)
            rec("admin.role no contract perm -> 403", code != 0, f"http={st} code={code}")
        if u2:
            api("DELETE", f"/admin/users/{u2['id']}", admin)
        api("DELETE", f"/admin/roles/{rid}", admin)

    # 字典
    def _dict_item_ids():
        st, code, types = api("GET", "/admin/dict/types", admin)
        for t in (types or []):
            if t.get("code") == "e2e_dict":
                return [i["id"] for i in t.get("items", []) if i.get("value") == "v1"]
        return []

    for iid in _dict_item_ids():
        api("DELETE", f"/admin/dict/items/{iid}", admin)
    st, code, dtype = api("POST", "/admin/dict/types", admin,
                          json={"code": "e2e_dict", "name": "E2E字典", "status": "enabled"})
    rec("admin.dict type create", code == 0 or code != 0, f"code={code}（重复视为已存在）")
    st, code, item = api("POST", "/admin/dict/items", admin, json={
        "dictTypeCode": "e2e_dict", "label": "E2E项1", "value": "v1", "sort": 1, "status": "enabled"})
    rec("admin.dict item create", code == 0, f"code={code}")
    st, code, items = api("GET", "/admin/dict/items", admin, params={"type": "e2e_dict"})
    rec("admin.dict items read", code == 0 and any(i["value"] == "v1" for i in (items or [])), f"items={items}")
    # 重复字典值应被拦截（唯一约束兜底为友好错误）
    st, code, _ = api("POST", "/admin/dict/items", admin, json={
        "dictTypeCode": "e2e_dict", "label": "E2E项1重复", "value": "v1", "sort": 2, "status": "enabled"})
    rec("admin.dict duplicate value rejected", code != 0, f"code={code}")
    for iid in _dict_item_ids():
        api("DELETE", f"/admin/dict/items/{iid}", admin)

    # 编号规则
    st, code, rules = api("GET", "/admin/number-rules", admin)
    rec("admin.number-rules", code == 0 and len(rules or []) >= 5 and all("preview" in r for r in rules),
        f"count={len(rules or [])}")

    # 审计日志
    st, code, logs = api("GET", "/admin/audit-logs", admin, params={"page": 1, "size": 10})
    rec("admin.audit-logs", code == 0 and logs.get("total", 0) > 0, f"total={logs.get('total') if logs else None}")

    # 站内通知
    st, code, uc = api("GET", "/admin/notifies/unread-count", admin)
    rec("admin.notifies unread-count", code == 0 and isinstance(uc.get("count"), int), f"count={uc}")
    st, code, ns = api("GET", "/admin/notifies", admin, params={"status": "unread", "size": 5})
    rec("admin.notifies list", code == 0, f"code={code}")
    items = (ns or {}).get("items", [])
    if items:
        st, code, _ = api("POST", f"/admin/notifies/{items[0]['id']}/read", admin)
        rec("admin.notifies read one", code == 0, f"code={code}")
    st, code, _ = api("POST", "/admin/notifies/read-all", admin)
    rec("admin.notifies read-all", code == 0, f"code={code}")
    st, code, uc2 = api("GET", "/admin/notifies/unread-count", admin)
    rec("admin.notifies cleared", code == 0 and uc2.get("count") == 0, f"count={uc2}")

    # 清理用户
    if uid:
        st, code, _ = api("DELETE", f"/admin/users/{uid}", admin)
        rec("admin.user delete", code == 0, f"code={code}")
        rec("admin.deleted user login fails", login("e2e_op", "E2e@654321") is None)


# ---------------------------------------------------------------- main
def main() -> None:
    only = os.environ.get("E2E_ONLY", "")  # 逗号分隔阶段：auth,crm,contract,task,finance,admin
    print(f"target: {BASE} only={only or 'all'}")
    r = _request("GET", "/auth/login")
    print(f"backend alive: http={r.status_code}")

    admin = tok("admin", "Admin@123456")
    if not only or "auth" in only:
        admin = test_auth()
    manager = tok("manager1", "Test@123456")
    leader = tok("leader1", "Test@123456")
    st, code, users = api("GET", "/admin/users", admin, params={"q": "leader1"})
    leader_id = users["items"][0]["id"] if code == 0 and users["items"] else None

    def want(phase: str) -> bool:
        return not only or phase in only

    if want("crm"):
        cust_id = test_crm(admin)
    else:
        st, code, data = api("GET", "/crm/customers", admin, params={"q": "E2E-客户A", "size": 1})
        cust_id = data["items"][0]["id"]
    if want("contract"):
        contract_ids = test_contract(admin, manager, leader, cust_id, leader_id)
    if want("task"):
        if not want("contract"):
            st, code, data = api("GET", "/contract/contracts/options", admin, params={"q": "E2E-合同"})
            ids = [o.get("id") or o.get("value") for o in (data or [])]
            contract_ids = {"c1": ids[0], "c2": ids[1] if len(ids) > 1 else ids[0], "c4": 0}
        task_ids = test_task(admin, manager, contract_ids)
    if want("finance"):
        if not want("task"):
            st, code, opts = api("GET", "/finance/settlements/task-options", admin, params={"q": "E2E-任务"})
            task_ids = {"t1": opts[0]["value"], "t2": opts[1]["value"] if len(opts) > 1 else None}
        test_finance(admin, manager, task_ids)
    if want("admin"):
        test_admin(admin)

    # 通用：分页/401 sanity（crm 已在前面覆盖，这里补 users 分页）
    st, code, data = api("GET", "/admin/users", admin, params={"page": 1, "size": 2})
    rec("common.users pagination", code == 0 and len(data["items"]) <= 2 and data["total"] >= len(data["items"]))

    # 清理：E2E 客户A改 有关联合同，无法删除（验证该保护）
    st, code, _ = api("DELETE", f"/crm/customers/{cust_id}", admin)
    rec("cleanup.customer with contract delete blocked", code != 0, f"code={code}")

    print("\n===== 汇总 =====")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"total={len(RESULTS)} passed={passed} failed={len(RESULTS) - passed}")
    if BUGS:
        print("\n失败/BUG 清单：")
        for b in BUGS:
            print(f"  - {b}")
    sys.exit(0 if not BUGS else 2)


if __name__ == "__main__":
    main()

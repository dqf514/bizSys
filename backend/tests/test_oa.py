"""OA 模块：表单 CRUD/发布校验、发起（引擎 + 变量注入 / 直通）、我的申请、与我相关、统计、异常干预、权限。"""

import uuid

BASE = "/api/v1/oa"


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


FIELDS = [
    {"key": "reason", "label": "事由", "type": "textarea", "required": True, "maxlength": 200},
    {"key": "amount", "label": "金额", "type": "money", "required": True, "exposeVariable": True},
    {"key": "kind", "label": "类别", "type": "select", "required": True, "options": ["A", "B"]},
]


def _create_form(client, admin_headers, key, fields=FIELDS, flow_id=None, publish=True):
    r = client.post(
        f"{BASE}/admin/forms",
        headers=admin_headers,
        json={"key": key, "name": f"表单{key}", "category": "other", "fields": fields, "flowDefinitionId": flow_id},
    ).json()
    assert r["code"] == 0, r
    fid = r["data"]["id"]
    if publish:
        p = client.post(f"{BASE}/admin/forms/{fid}/publish", headers=admin_headers).json()
        assert p["code"] == 0, p
    return fid


def _apply(client, headers, form_id, data):
    return client.post(f"{BASE}/instances", headers=headers, json={"formId": form_id, "data": data}).json()


def _seeded_flow_id(client, admin_headers, code):
    defs = client.get(f"{BASE}/admin/flow-defs", headers=admin_headers).json()["data"]
    return next(d["id"] for d in defs if d["code"] == code)


GOOD_DATA = {"reason": "测试事由", "amount": 88.5, "kind": "A"}


# ---------------- 表单设计 CRUD / 发布 ----------------


def test_form_crud_publish(client, admin_headers):
    key = _uniq("ut_form_")
    # 草稿不出现在目录
    fid = _create_form(client, admin_headers, key, publish=False)
    cat = client.get(f"{BASE}/catalog", headers=admin_headers).json()["data"]
    assert all(f["id"] != fid for g in cat for f in g["forms"])

    # 更新草稿 + 发布 → 目录可见
    body = {"key": key, "name": "改名表单", "category": "leave", "fields": FIELDS, "flowDefinitionId": None}
    r = client.put(f"{BASE}/admin/forms/{fid}", headers=admin_headers, json=body).json()
    assert r["code"] == 0 and r["data"]["name"] == "改名表单"
    p = client.post(f"{BASE}/admin/forms/{fid}/publish", headers=admin_headers).json()
    assert p["code"] == 0 and p["data"]["status"] == "published"
    cat = client.get(f"{BASE}/catalog", headers=admin_headers).json()["data"]
    assert any(f["id"] == fid for g in cat for f in g["forms"])

    # 已发布不可编辑（需新建版本）
    r = client.put(f"{BASE}/admin/forms/{fid}", headers=admin_headers, json=body).json()
    assert r["code"] == 62005
    # 同 key+version 冲突
    dup = client.post(
        f"{BASE}/admin/forms", headers=admin_headers, json={"key": key, "name": "x", "fields": FIELDS}
    ).json()
    assert dup["code"] == 62004
    # 新版本 v2 草稿 → 发布后 v1 自动停用
    v2 = client.post(f"{BASE}/admin/forms/{fid}/new-version", headers=admin_headers).json()["data"]
    assert v2["formVersion"] == 2 and v2["status"] == "draft"
    p2 = client.post(f"{BASE}/admin/forms/{v2['id']}/publish", headers=admin_headers).json()
    assert p2["code"] == 0
    forms = client.get(f"{BASE}/admin/forms", headers=admin_headers).json()["data"]
    v1 = next(f for f in forms if f["id"] == fid)
    assert v1["status"] == "disabled"
    # 已发布不可删除
    d = client.delete(f"{BASE}/admin/forms/{v2['id']}", headers=admin_headers).json()
    assert d["code"] == 62005


def test_publish_schema_validation(client, admin_headers):
    # select 无选项 → 62002；暴露变量类型非法 → 62002
    fid = _create_form(
        client, admin_headers, _uniq("ut_bad_"), fields=[{"key": "k", "label": "k", "type": "select"}], publish=False
    )
    p = client.post(f"{BASE}/admin/forms/{fid}/publish", headers=admin_headers).json()
    assert p["code"] == 62002
    fid2 = _create_form(
        client,
        admin_headers,
        _uniq("ut_bad_"),
        fields=[{"key": "f", "label": "附件", "type": "file", "exposeVariable": True}],
        publish=False,
    )
    assert client.post(f"{BASE}/admin/forms/{fid2}/publish", headers=admin_headers).json()["code"] == 62002
    # 绑定非 oa 流程定义 → 62002
    contract_flow = _seeded_flow_id(client, admin_headers, "contract_approve")
    fid3 = _create_form(client, admin_headers, _uniq("ut_bad_"), flow_id=contract_flow, publish=False)
    assert client.post(f"{BASE}/admin/forms/{fid3}/publish", headers=admin_headers).json()["code"] == 62002


# ---------------- 发起：校验 / 引擎 / 直通 ----------------


def test_apply_data_validation(client, admin_headers, manager_headers):
    fid = _create_form(client, admin_headers, _uniq("ut_val_"))
    # 草稿/未发布不可发起
    draft_id = _create_form(client, admin_headers, _uniq("ut_val_"), publish=False)
    assert _apply(client, manager_headers, draft_id, GOOD_DATA)["code"] == 62001
    # 必填缺失 / 选项非法 / 金额非数字
    assert _apply(client, manager_headers, fid, {"amount": 1, "kind": "A"})["code"] == 62003
    assert _apply(client, manager_headers, fid, {"reason": "x", "amount": 1, "kind": "ZZ"})["code"] == 62003
    assert _apply(client, manager_headers, fid, {"reason": "x", "amount": "abc", "kind": "A"})["code"] == 62003


def test_apply_flow_variables_and_approve(client, admin_headers, manager_headers, leader_headers):
    flow_id = _seeded_flow_id(client, admin_headers, "oa_leave_approve")
    fid = _create_form(client, admin_headers, _uniq("ut_flow_"), flow_id=flow_id)
    # 申请人 admin（D04 普通成员）：DEPT_LEADER → manager1（D04 负责人），PARENT_DEPT_LEADER → leader1（D00）
    r = _apply(client, admin_headers, fid, GOOD_DATA)
    assert r["code"] == 0, r
    inst = r["data"]
    assert inst["displayNo"].startswith("OA") and inst["status"] == "running"
    flow_inst_id = inst["flowInstanceId"]
    assert flow_inst_id > 0

    # 暴露字段注入流程变量
    snap = client.get(f"/api/v1/approval/instances/{flow_inst_id}", headers=manager_headers).json()["data"]
    assert snap["variables"]["amount"] == 88.5 and "kind" not in snap["variables"]

    # 与我相关：manager1 待办可见（仅 oa 业务）
    todo = client.get(f"{BASE}/related", headers=manager_headers, params={"tab": "todo"}).json()["data"]
    hit = [t for t in todo["items"] if t["instanceId"] == flow_inst_id]
    assert hit and hit[0]["bizType"] == "oa"

    # 两级审批走完 → OA 状态回写 approved
    client.post(f"/api/v1/approval/tasks/{hit[0]['id']}/approve", headers=manager_headers, json={"comment": "同意"})
    todo2 = client.get(f"{BASE}/related", headers=leader_headers, params={"tab": "todo"}).json()["data"]
    hit2 = [t for t in todo2["items"] if t["instanceId"] == flow_inst_id]
    assert hit2
    client.post(f"/api/v1/approval/tasks/{hit2[0]['id']}/approve", headers=leader_headers, json={"comment": "同意"})
    detail = client.get(f"{BASE}/instances/{inst['id']}", headers=manager_headers).json()["data"]
    assert detail["status"] == "approved"
    assert detail["formData"]["reason"] == "测试事由"
    assert any(x["action"] == "start" for x in detail["timeline"])
    # 已办页签
    done = client.get(f"{BASE}/related", headers=leader_headers, params={"tab": "done"}).json()["data"]
    assert any(t["instanceId"] == flow_inst_id for t in done["items"])


def test_apply_direct_pass(client, admin_headers, manager_headers):
    fid = _create_form(client, admin_headers, _uniq("ut_direct_"))  # 未绑定流程 → 直通
    r = _apply(client, manager_headers, fid, GOOD_DATA)
    assert r["code"] == 0
    assert r["data"]["status"] == "approved" and r["data"]["flowInstanceId"] == 0


def test_my_instances_filter(client, admin_headers, manager_headers, leader_headers):
    fid = _create_form(client, admin_headers, _uniq("ut_my_"))
    r = _apply(client, manager_headers, fid, GOOD_DATA)
    assert r["code"] == 0
    mine = client.get(f"{BASE}/instances/my", headers=manager_headers).json()["data"]
    assert any(i["id"] == r["data"]["id"] for i in mine["items"])
    approved = client.get(
        f"{BASE}/instances/my", headers=manager_headers, params={"status": "approved"}
    ).json()["data"]
    assert all(i["status"] == "approved" for i in approved["items"])
    # 他人不可见我的单据详情（无关联）
    other = client.get(f"{BASE}/instances/{r['data']['id']}", headers=leader_headers)
    assert other.status_code == 403


def test_withdraw(client, admin_headers, manager_headers):
    flow_id = _seeded_flow_id(client, admin_headers, "oa_leave_approve")
    fid = _create_form(client, admin_headers, _uniq("ut_wd_"), flow_id=flow_id)
    inst = _apply(client, manager_headers, fid, GOOD_DATA)["data"]
    r = client.post(f"{BASE}/instances/{inst['id']}/withdraw", headers=manager_headers).json()
    assert r["code"] == 0
    detail = client.get(f"{BASE}/instances/{inst['id']}", headers=manager_headers).json()["data"]
    assert detail["status"] == "withdrawn"


# ---------------- 统计 ----------------


def test_stats_and_permission(client, admin_headers, manager_headers):
    r = client.get(f"{BASE}/stats", headers=admin_headers).json()
    assert r["code"] == 0
    data = r["data"]
    assert data["total"] >= 1 and len(data["trend"]) == 6
    assert sum(data["byStatus"].values()) == data["total"]
    # 管理员版含积压
    a = client.get(f"{BASE}/admin/stats", headers=admin_headers).json()["data"]
    assert "backlog" in a
    # manager1 无 oa:stats:view / oa:admin:stats
    assert client.get(f"{BASE}/stats", headers=manager_headers).status_code == 403
    assert client.get(f"{BASE}/admin/stats", headers=manager_headers).status_code == 403


# ---------------- 异常流程干预 ----------------


def _apply_running(client, admin_headers, manager_headers, prefix):
    flow_id = _seeded_flow_id(client, admin_headers, "oa_leave_approve")
    fid = _create_form(client, admin_headers, _uniq(prefix), flow_id=flow_id)
    # 申请人 admin：组织节点解析 DEPT_LEADER=manager1 → PARENT_DEPT_LEADER=leader1
    return _apply(client, admin_headers, fid, GOOD_DATA)["data"]


def test_admin_terminate(client, admin_headers, manager_headers):
    inst = _apply_running(client, admin_headers, manager_headers, "ut_term_")
    r = client.post(
        f"{BASE}/admin/instances/{inst['id']}/terminate", headers=admin_headers, json={"comment": "重复申请"}
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "terminated"
    detail = client.get(f"{BASE}/instances/{inst['id']}", headers=manager_headers).json()["data"]
    assert detail["status"] == "terminated"
    assert any(x["action"] == "terminate" for x in detail["timeline"])
    # 直通单不可干预
    direct = _apply(client, manager_headers, _create_form(client, admin_headers, _uniq("ut_term_")), GOOD_DATA)["data"]
    assert (
        client.post(f"{BASE}/admin/instances/{direct['id']}/terminate", headers=admin_headers, json={}).json()["code"]
        == 62005
    )


def test_admin_reassign(client, admin_headers, manager_headers, leader_headers):
    inst = _apply_running(client, admin_headers, manager_headers, "ut_reas_")
    todo = client.get(f"{BASE}/related", headers=manager_headers, params={"tab": "todo"}).json()["data"]
    task = next(t for t in todo["items"] if t["instanceId"] == inst["flowInstanceId"])
    users = client.get("/api/v1/admin/users", headers=admin_headers, params={"q": "leader1"}).json()["data"]
    leader_id = next(u["id"] for u in users["items"] if u["username"] == "leader1")
    r = client.post(
        f"{BASE}/admin/instances/{inst['id']}/reassign",
        headers=admin_headers,
        json={"taskId": task["id"], "toUserId": leader_id, "comment": "负责人休假"},
    ).json()
    assert r["code"] == 0, r
    # leader1 收到待办，manager1 该任务已转办
    todo2 = client.get(f"{BASE}/related", headers=leader_headers, params={"tab": "todo"}).json()["data"]
    assert any(t["instanceId"] == inst["flowInstanceId"] for t in todo2["items"])


def test_admin_restart_after_reject(client, admin_headers, manager_headers, leader_headers):
    inst = _apply_running(client, admin_headers, manager_headers, "ut_rst_")
    todo = client.get(f"{BASE}/related", headers=manager_headers, params={"tab": "todo"}).json()["data"]
    task = next(t for t in todo["items"] if t["instanceId"] == inst["flowInstanceId"])
    r = client.post(
        f"/api/v1/approval/tasks/{task['id']}/reject", headers=manager_headers, json={"comment": "材料不全"}
    ).json()
    assert r["code"] == 0
    detail = client.get(f"{BASE}/instances/{inst['id']}", headers=manager_headers).json()["data"]
    assert detail["status"] == "rejected"
    # 退回到节点 1 重建待办
    rr = client.post(
        f"{BASE}/admin/instances/{inst['id']}/restart", headers=admin_headers, json={"seq": 1, "comment": "补充后重审"}
    ).json()
    assert rr["code"] == 0 and rr["data"]["status"] == "running"
    detail = client.get(f"{BASE}/instances/{inst['id']}", headers=manager_headers).json()["data"]
    assert detail["status"] == "running"
    assert any(x["action"] == "restart" for x in detail["timeline"])
    todo2 = client.get(f"{BASE}/related", headers=manager_headers, params={"tab": "todo"}).json()["data"]
    assert any(t["instanceId"] == inst["flowInstanceId"] for t in todo2["items"])
    # 目标节点非法
    bad = client.post(
        f"{BASE}/admin/instances/{inst['id']}/restart", headers=admin_headers, json={"seq": 99}
    ).json()
    assert bad["code"] == 10001


def test_admin_instances_search_and_perm(client, admin_headers, manager_headers):
    inst = _apply_running(client, admin_headers, manager_headers, "ut_sch_")
    r = client.get(f"{BASE}/admin/instances", headers=admin_headers, params={"keyword": inst["displayNo"]}).json()
    assert r["code"] == 0 and any(i["id"] == inst["id"] for i in r["data"]["items"])
    r2 = client.get(f"{BASE}/admin/instances", headers=admin_headers, params={"status": "running"}).json()["data"]
    assert all(i["status"] == "running" for i in r2["items"])
    # 权限拦截：manager1 无 oa:admin:*
    assert client.get(f"{BASE}/admin/forms", headers=manager_headers).status_code == 403
    assert client.get(f"{BASE}/admin/instances", headers=manager_headers).status_code == 403
    assert client.post(f"{BASE}/admin/forms", headers=manager_headers, json={}).status_code == 403

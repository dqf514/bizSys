"""B5：任务字段扩展 / 工序流转 / 七维分配 / 全过程追溯 / 智能排程 / 项目与甘特。

覆盖：
- task_task 扩展字段落库与角色分组派生（CSV 18/21）；
- 工序流转状态机（同一任务只允许一道工序进行中，CSV 19）；
- 七维分配 CRUD 与全过程追溯节点（CSV 20）；
- 按任务类型解析默认负责人；
- 角色分组可见性（只授予 task:group:<组> 的用户只能看到本组任务）；
- 自动排期 → 人工调整 → 发布（二次冲突校验）与排期回写（CSV 22）；
- 项目全生命周期、甘特自动生成与进度回算（CSV 31）。
"""

import uuid

from tests.conftest import post_login

UUID = uuid.uuid4().hex[:8]


def _create_task(client, headers, **overrides):
    payload = {
        "task_name": f"B5任务_{UUID}_{overrides.get('task_type', '')}",
        "task_type": "cfd",
    }
    payload.update(overrides)
    r = client.post("/api/v1/task/tasks", headers=headers, json=payload).json()
    assert r["code"] == 0, r
    return r["data"]


# ---------------- 任务字段扩展与角色分组 ----------------


def test_task_extension_fields_persist(client, admin_headers):
    task = _create_task(
        client,
        admin_headers,
        task_type="cfd",
        plan_start_date="2026-01-05",
        duration_hours=16,
        priority=2,
        mesh_count=320,
        solver="Fluent",
        compute_resource="CFD-Pool-A",
        compute_cores=256,
        compute_nodes=8,
    )
    assert task["planStartDate"] == "2026-01-05"
    assert float(task["durationHours"]) == 16
    assert task["priority"] == 2
    assert task["meshCount"] == 320
    assert task["solver"] == "Fluent"
    assert task["computeResource"] == "CFD-Pool-A"
    assert task["computeCores"] == 256
    assert task["computeNodes"] == 8
    # 角色分组由任务类型派生：CFD → 仿真
    assert task["roleGroup"] == "sim"
    assert task["roleGroupText"]

    # 部分更新不会冲掉未携带的扩展字段
    r = client.put(
        f"/api/v1/task/tasks/{task['id']}",
        headers=admin_headers,
        json={"task_name": f"改名_{UUID}", "version": task["version"]},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["solver"] == "Fluent"
    assert r["data"]["meshCount"] == 320


def test_owner_suggestion_by_task_type(client, admin_headers):
    task = _create_task(client, admin_headers, task_type="cfd")
    r = client.get(f"/api/v1/task/tasks/{task['id']}/owner-suggestion", headers=admin_headers).json()
    assert r["code"] == 0, r
    data = r["data"]
    assert data["taskType"] == "cfd"
    assert data["roleGroup"] == "sim"
    # 种子字典 task_owner_rule：cfd → sim_engineer，仿真工程师用户存在
    assert data["ownerName"]

    # 未知类型没有规则 → 空
    task2 = _create_task(client, admin_headers, task_type="consulting")
    r2 = client.get(f"/api/v1/task/tasks/{task2['id']}/owner-suggestion", headers=admin_headers).json()
    assert r2["code"] == 0, r2
    assert r2["data"]["ownerName"] == ""


# ---------------- 工序流转 ----------------


def test_task_process_lifecycle(client, admin_headers):
    task = _create_task(client, admin_headers, task_type="cfd")
    tid = task["id"]

    p1 = client.post(
        f"/api/v1/task/tasks/{tid}/processes",
        headers=admin_headers,
        json={"process_code": "design", "process_name": "方案设计", "seq": 1},
    ).json()
    assert p1["code"] == 0, p1
    p2 = client.post(
        f"/api/v1/task/tasks/{tid}/processes",
        headers=admin_headers,
        json={"process_code": "cfd", "process_name": "CFD仿真", "seq": 2},
    ).json()
    assert p2["code"] == 0, p2

    # 开始第一道 → 当前工序同步
    r = client.post(f"/api/v1/task/processes/{p1['data']['id']}/start", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "running", r
    detail = client.get(f"/api/v1/task/tasks/{tid}", headers=admin_headers).json()["data"]
    assert detail["processStage"] == "design"

    # 同一任务同时只允许一道工序进行中
    r = client.post(f"/api/v1/task/processes/{p2['data']['id']}/start", headers=admin_headers).json()
    assert r["code"] == 60020, r

    # 完成第一道 → 第二道成为当前工序
    r = client.post(f"/api/v1/task/processes/{p1['data']['id']}/finish", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "done", r
    detail = client.get(f"/api/v1/task/tasks/{tid}", headers=admin_headers).json()["data"]
    assert detail["processStage"] == "cfd"

    # 跳过第二道
    r = client.post(f"/api/v1/task/processes/{p2['data']['id']}/skip", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "skipped", r

    # 已结束的工序不可修改
    r = client.put(
        f"/api/v1/task/processes/{p1['data']['id']}",
        headers=admin_headers,
        json={"process_name": "改名"},
    ).json()
    assert r["code"] == 60020, r

    lst = client.get(f"/api/v1/task/tasks/{tid}/processes", headers=admin_headers).json()
    assert lst["code"] == 0 and lst["data"]["total"] == 2, lst


# ---------------- 七维分配与全过程追溯 ----------------


def test_task_assignment_crud(client, admin_headers):
    task = _create_task(client, admin_headers, task_type="cfd")
    tid = task["id"]

    a = client.post(
        f"/api/v1/task/tasks/{tid}/assignments",
        headers=admin_headers,
        json={
            "dimension": "equipment",
            "resource_id": 7001,
            "resource_code": "WT-01",
            "resource_name": "1号风洞",
            "qty": 1,
            "unit": "台",
        },
    ).json()
    assert a["code"] == 0, a
    aid = a["data"]["id"]
    assert a["data"]["dimensionText"]

    r = client.put(
        f"/api/v1/task/assignments/{aid}",
        headers=admin_headers,
        json={"status": "confirmed", "qty": 2},
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "confirmed", r
    assert r["data"]["confirmedAt"]

    lst = client.get(f"/api/v1/task/tasks/{tid}/assignments", headers=admin_headers).json()
    assert lst["code"] == 0 and lst["data"]["total"] == 1, lst

    r = client.delete(f"/api/v1/task/assignments/{aid}", headers=admin_headers).json()
    assert r["code"] == 0, r
    lst = client.get(f"/api/v1/task/tasks/{tid}/assignments", headers=admin_headers).json()
    assert lst["data"]["total"] == 0


def test_task_trace_and_operation_flow(client, admin_headers):
    task = _create_task(client, admin_headers, task_type="cfd")
    tid = task["id"]

    client.post(
        f"/api/v1/task/tasks/{tid}/processes",
        headers=admin_headers,
        json={"process_code": "cfd", "process_name": "CFD仿真"},
    )
    tr = client.post(
        f"/api/v1/task/tasks/{tid}/traces",
        headers=admin_headers,
        json={"node_code": "input", "ref_no": "REQ-001"},
    ).json()
    assert tr["code"] == 0, tr
    tid_trace = tr["data"]["id"]

    flow = client.get(f"/api/v1/task/tasks/{tid}/operation-flow", headers=admin_headers).json()
    assert flow["code"] == 0, flow
    nodes = flow["data"]["nodes"]
    assert len(nodes) == 2, nodes
    assert nodes[0]["type"] == "process"
    assert nodes[1]["type"] == "trace"

    r = client.delete(f"/api/v1/task/traces/{tid_trace}", headers=admin_headers).json()
    assert r["code"] == 0, r
    lst = client.get(f"/api/v1/task/tasks/{tid}/traces", headers=admin_headers).json()
    assert lst["data"]["total"] == 0


# ---------------- 角色分组可见性 ----------------


def test_role_group_visibility(client, admin_headers):
    sim_task = _create_task(client, admin_headers, task_type="cfd")
    model_task = _create_task(client, admin_headers, task_type="model")
    assert model_task["roleGroup"] == "model"

    login = post_login(client, "sim1", "Test@123456").json()
    assert login["code"] == 0, login
    headers = {"Authorization": f"Bearer {login['data']['access_token']}"}

    lst = client.get("/api/v1/task/tasks", headers=headers, params={"size": 200}).json()
    assert lst["code"] == 0, lst
    groups = {item.get("roleGroup") for item in lst["data"]["items"]}
    assert "model" not in groups, groups
    assert "sim" in groups, groups

    # 跨组访问详情被拒
    r = client.get(f"/api/v1/task/tasks/{model_task['id']}", headers=headers).json()
    assert r["code"] == 60021, r

    # 本组任务可访问
    r = client.get(f"/api/v1/task/tasks/{sim_task['id']}", headers=headers).json()
    assert r["code"] == 0, r


# ---------------- 智能排程 ----------------

# 测试库跨次运行残留，资源 id 必须每次运行唯一，否则会撞上历史已发布排期
RESOURCE_ID = 700000 + int(UUID[:5], 16)


def _make_schedulable_task(client, headers, resource_id: int, start_date: str, name: str):
    task = _create_task(
        client,
        headers,
        task_type="windtunnel",
        plan_start_date=start_date,
        duration_hours=8,
        task_name=name,
    )
    r = client.post(
        f"/api/v1/task/tasks/{task['id']}/assignments",
        headers=headers,
        json={
            "dimension": "equipment",
            "resource_id": resource_id,
            "resource_code": f"EQ-{resource_id}",
            "resource_name": f"设备{resource_id}",
            "qty": 1,
            "unit": "台",
        },
    ).json()
    assert r["code"] == 0, r
    return task


def test_auto_schedule_publish_and_conflict(client, admin_headers):
    # 没有可排任务 → 99005
    r = client.post(
        "/api/v1/production/plans/auto",
        headers=admin_headers,
        json={"task_ids": [999999999], "name": "空排期"},
    ).json()
    assert r["code"] == 99005, r

    task1 = _make_schedulable_task(client, admin_headers, RESOURCE_ID, "2026-01-05", f"排程任务1_{UUID}")
    r = client.post(
        "/api/v1/production/plans/auto",
        headers=admin_headers,
        json={"task_ids": [task1["id"]], "base_date": "2026-01-05", "name": f"排期方案_{UUID}"},
    ).json()
    assert r["code"] == 0, r
    plan = r["data"]
    assert plan["planNo"].startswith("PL")
    assert plan["status"] == "draft"
    assert plan["taskCount"] == 1
    assert plan["conflictCount"] == 0, plan
    rows = plan["schedules"]
    assert len(rows) == 1, rows
    assert rows[0]["scheduleNo"].startswith("SC")
    assert rows[0]["resourceType"] == "equipment"
    assert rows[0]["status"] == "scheduled"
    assert rows[0]["planStart"] == "2026-01-05 09:00:00"

    # 发布 → 占用资源并回写任务计划日期
    r = client.post(f"/api/v1/production/plans/{plan['id']}/publish", headers=admin_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["status"] == "published"
    detail = client.get(f"/api/v1/task/tasks/{task1['id']}", headers=admin_headers).json()["data"]
    assert detail["planStartDate"] == "2026-01-05"

    # 第二个方案撞同一资源：自动顺延到空档，顺延成功不算冲突
    task2 = _make_schedulable_task(client, admin_headers, RESOURCE_ID, "2026-01-05", f"排程任务2_{UUID}")
    r = client.post(
        "/api/v1/production/plans/auto",
        headers=admin_headers,
        json={"task_ids": [task2["id"]], "base_date": "2026-01-05"},
    ).json()
    assert r["code"] == 0, r
    plan2 = r["data"]
    row2 = plan2["schedules"][0]
    assert row2["planStart"] > plan["schedules"][0]["planStart"], (row2, plan["schedules"][0])
    assert row2["status"] == "scheduled", row2
    assert not row2["conflictReason"], row2
    assert plan2["conflictCount"] == 0, plan2

    # 人工把排期改回与已发布方案重叠 → 发布应被冲突校验拦下 99004
    r = client.put(
        f"/api/v1/production/schedules/{row2['id']}",
        headers=admin_headers,
        json={
            "resource_type": "equipment",
            "resource_id": RESOURCE_ID,
            "plan_start": plan["schedules"][0]["planStart"],
            "plan_end": plan["schedules"][0]["planEnd"],
            "version": row2["version"],
        },
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["source"] == "manual"

    r = client.post(f"/api/v1/production/plans/{plan2['id']}/publish", headers=admin_headers).json()
    assert r["code"] == 99004, r

    # 取消方案
    r = client.post(f"/api/v1/production/plans/{plan2['id']}/cancel", headers=admin_headers).json()
    assert r["code"] == 0 and r["data"]["status"] == "cancelled", r

    # 资源占用视图只统计已发布 / 已确认
    occ = client.get("/api/v1/production/resources/occupancy", headers=admin_headers).json()
    assert occ["code"] == 0, occ
    assert any(o["resourceName"] == f"设备{RESOURCE_ID}" for o in occ["data"]["items"]), occ


def test_material_shortage_marks_conflict(client, admin_headers):
    task = _create_task(
        client,
        admin_headers,
        task_type="cfd",
        plan_start_date="2026-01-06",
        duration_hours=4,
        task_name=f"缺料任务_{UUID}",
    )
    # 引用不存在的物料 → 可用量 0 → 缺料冲突
    r = client.post(
        f"/api/v1/task/tasks/{task['id']}/assignments",
        headers=admin_headers,
        json={
            "dimension": "material",
            "resource_id": RESOURCE_ID + 1,
            "resource_code": "MAT-X",
            "resource_name": "缺料物料",
            "qty": 5,
            "unit": "件",
        },
    ).json()
    assert r["code"] == 0, r

    r = client.post(
        "/api/v1/production/plans/auto",
        headers=admin_headers,
        json={"task_ids": [task["id"]], "base_date": "2026-01-06"},
    ).json()
    assert r["code"] == 0, r
    plan = r["data"]
    assert plan["conflictCount"] >= 1, plan
    assert all(s["status"] == "conflict" for s in plan["schedules"]), plan["schedules"]
    assert plan["schedules"][0]["conflictReason"]


# ---------------- 项目与甘特 ----------------


def test_project_crud_and_gantt(client, admin_headers):
    r = client.post(
        "/api/v1/project/projects",
        headers=admin_headers,
        json={
            "name": f"风洞项目_{UUID}",
            "customer_name": f"客户_{UUID}",
            "manager_name": "项目经理",
            "dept_name": "风洞实验室",
            "start_date": "2026-02-01",
            "end_date": "2026-06-30",
            "budget_amount": 100000,
        },
    ).json()
    assert r["code"] == 0, r
    project = r["data"]
    assert project["projectNo"].startswith("PJ")
    assert project["status"] == "draft"

    pid = project["id"]
    t1 = _create_task(client, admin_headers, task_type="windtunnel", plan_start_date="2026-02-02")
    t2 = _create_task(client, admin_headers, task_type="cfd", plan_start_date="2026-03-02")

    # 从任务输入自动生成甘特
    r = client.post(
        f"/api/v1/project/projects/{pid}/generate-tasks",
        headers=admin_headers,
        json={"task_ids": [t1["id"], t2["id"]]},
    ).json()
    assert r["code"] == 0, r
    gantt = r["data"]
    assert gantt["total"] == 2, gantt
    assert gantt["created"] == 2, gantt
    groups = {i["groupCode"] for i in gantt["items"]}
    assert "test" in groups and "sim" in groups, groups

    # 甘特行起止日期取自任务计划开始日
    row = next(i for i in gantt["items"] if i["taskId"] == t1["id"])
    assert row["startDate"] == "2026-02-02"

    # 手工新增里程碑行
    r = client.post(
        f"/api/v1/project/projects/{pid}/tasks",
        headers=admin_headers,
        json={
            "task_name": "验收里程碑",
            "group_code": "test",
            "start_date": "2026-06-01",
            "end_date": "2026-06-01",
            "milestone": 1,
            "progress": 0,
            "weight": 1,
            "status": "pending",
        },
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["total"] == 3, r["data"]

    # 手工行没有 task_id → 不可作为更新入口
    g = client.get(f"/api/v1/project/projects/{pid}/gantt", headers=admin_headers).json()
    assert g["code"] == 0 and g["data"]["total"] == 3, g

    # 推进某行进度 → 项目进度按权重加权回算
    auto_row = next(i for i in g["data"]["items"] if i["taskId"] == t1["id"])
    r = client.put(
        f"/api/v1/project/project-tasks/{auto_row['id']}",
        headers=admin_headers,
        json={"task_id": t1["id"], "task_name": auto_row["taskName"], "progress": 100, "weight": 1,
              "milestone": 0, "status": "done"},
    ).json()
    assert r["code"] == 0, r

    # 状态流转：立项中 → 执行中
    r = client.put(
        f"/api/v1/project/projects/{pid}",
        headers=admin_headers,
        json={"name": project["name"], "status": "executing", "version": project["version"]},
    ).json()
    assert r["code"] == 0 and r["data"]["status"] == "executing", r

    # 执行中的项目不可删除
    r = client.delete(f"/api/v1/project/projects/{pid}", headers=admin_headers).json()
    assert r["code"] == 99101, r

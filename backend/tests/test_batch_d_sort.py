"""批次D：列表排序白名单回归。

断言：sort=col:asc/desc 真实影响顺序、非法列回退默认不 5xx、
sort 与分页/筛选/导出参数组合语义一致。

测试库 bizsys_test 跨 pytest 运行不重置，造数一律带唯一 tag 前缀保证幂等。
"""

import uuid

import pytest

TAG = uuid.uuid4().hex[:8]


def _get(client, headers, path):
    r = client.get(f"/api/v1{path}", headers=headers)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    data = r.json()
    assert data["code"] == 0, data
    return data["data"]


def _names(items, key):
    return [x[key] for x in items]


@pytest.fixture(scope="module")
def seed_rows(client, admin_headers):
    """造三条客户 + 两个任务 + 两条样品（唯一 tag 前缀），供排序断言。"""
    ids = []
    for n in (f"pd_{TAG}排序甲", f"pd_{TAG}排序乙", f"pd_{TAG}排序丙"):
        r = client.post("/api/v1/crm/customers", json={"name": n, "customerType": "企业"}, headers=admin_headers)
        assert r.json()["code"] == 0
        ids.append(r.json()["data"]["id"])
    task_ids = []
    for n in (f"pd_{TAG}任务B", f"pd_{TAG}任务A"):
        r = client.post(
            "/api/v1/task/tasks",
            json={"taskName": n, "items": [], "samples": [{"name": n + "_样品1"}, {"name": n + "_样品2"}]},
            headers=admin_headers,
        )
        assert r.json()["code"] == 0, r.text
        task_ids.append(r.json()["data"]["id"])
    return {"customer_ids": ids, "task_ids": task_ids}


def test_customer_sort_asc_desc(client, admin_headers, seed_rows):
    q = f"pd_{TAG}排序"
    asc = _get(client, admin_headers, f"/crm/customers?q={q}&sort=name:asc")
    desc = _get(client, admin_headers, f"/crm/customers?q={q}&sort=name:desc")
    assert asc["total"] == 3 and desc["total"] == 3
    assert _names(desc["items"], "name") == list(reversed(_names(asc["items"], "name")))


def test_customer_sort_illegal_falls_back(client, admin_headers, seed_rows):
    data = _get(client, admin_headers, "/crm/customers?sort=password_hash:desc")
    assert data["total"] >= 3


def test_task_sort_name_and_combined(client, admin_headers, seed_rows):
    q = f"pd_{TAG}任务"
    asc = _get(client, admin_headers, f"/task/tasks?q={q}&sort=task_name:asc")
    assert _names(asc["items"], "taskName") == [f"pd_{TAG}任务A", f"pd_{TAG}任务B"]
    desc = _get(client, admin_headers, f"/task/tasks?q={q}&sort=task_name:desc")
    assert _names(desc["items"], "taskName") == [f"pd_{TAG}任务B", f"pd_{TAG}任务A"]
    # sort + status + 分页组合
    combo = _get(client, admin_headers, f"/task/tasks?status=draft&q={q}&sort=task_no:desc&page=1&size=1")
    assert combo["total"] == 2 and len(combo["items"]) == 1


def test_sample_sort_name(client, admin_headers, seed_rows):
    asc = _get(client, admin_headers, f"/task/samples?q=pd_{TAG}任务A&sort=name:asc")
    names = _names(asc["items"], "name")
    assert names == sorted(names) and len(names) == 2
    # JOIN 列排序（任务名）
    data = _get(client, admin_headers, f"/task/samples?q=pd_{TAG}任务&sort=task_name:desc")
    assert data["total"] == 4


def test_oa_my_instances_sort(client, admin_headers, seed_rows):
    cat = _get(client, admin_headers, "/oa/catalog")
    form = next(f for g in cat for f in (g.get("forms") or []) if f["key"] == "leave_application")
    leave_type = next(f for f in form["fields"] if f["key"] == "leave_type")
    opt = leave_type["options"][0]
    opt_value = opt["value"] if isinstance(opt, dict) else opt
    for reason in (f"pd_{TAG}排序一", f"pd_{TAG}排序二"):
        r = client.post(
            "/api/v1/oa/instances",
            json={
                "formId": form["id"],
                "data": {"leave_type": opt_value, "date_range": ["2026-01-01", "2026-01-02"], "reason": reason},
            },
            headers=admin_headers,
        )
        assert r.json()["code"] == 0, r.text
    asc = _get(client, admin_headers, "/oa/instances/my?sort=display_no:asc&size=100")
    nos = _names(asc["items"], "displayNo")
    assert nos == sorted(nos)
    desc = _get(client, admin_headers, "/oa/instances/my?sort=display_no:desc&size=100")
    assert _names(desc["items"], "displayNo") == list(reversed(nos))


def test_approval_tasks_sort_param(client, admin_headers, seed_rows):
    for tab in ("todo", "done", "initiated"):
        _get(client, admin_headers, f"/approval/tasks?tab={tab}&sort=create_time:asc")
        _get(client, admin_headers, f"/approval/tasks?tab={tab}&sort=bogus:desc")
    _get(client, admin_headers, "/approval/cc?sort=create_time:asc")
    _get(client, admin_headers, "/oa/related?tab=todo&sort=create_time:asc")


def test_oa_admin_instances_sort(client, admin_headers, seed_rows):
    _get(client, admin_headers, "/oa/admin/instances?sort=form_name:asc")
    _get(client, admin_headers, "/oa/admin/instances?sort=create_time:desc&status=running")


def test_misc_lists_sort(client, admin_headers, seed_rows):
    for path in (
        "/contract/contracts?sort=amount:asc",
        "/finance/settlements?sort=status:desc",
        "/finance/invoices?sort=invoice_no:asc",
        "/finance/payments?sort=paid_at:desc",
        "/report/reports?sort=status:asc",
        "/admin/users?sort=username:asc",
        "/admin/roles?sort=code:desc",
        "/admin/audit-logs?sort=module:asc",
    ):
        _get(client, admin_headers, path)


def test_export_follows_sort(client, admin_headers, seed_rows):
    """导出与列表同语义：带 sort 参数不报错。"""
    r = client.post(
        "/api/v1/crm/customers/export", json={"q": f"pd_{TAG}排序", "sort": "name:asc"}, headers=admin_headers
    )
    assert r.status_code == 200

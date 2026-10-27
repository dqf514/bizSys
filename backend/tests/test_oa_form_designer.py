"""批次4：OA 表单设计器对标 TPC —— 条件逻辑 / 级联 / 字典数据源 / 资源控件 / 布局控件 / 资源检索端点。"""

import uuid

from conftest import post_login

BASE = "/api/v1/oa"


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _login(client, username: str, password: str) -> dict:
    r = post_login(client, username, password)
    data = r.json()
    assert data["code"] == 0, data
    return {"Authorization": f"Bearer {data['data']['access_token']}"}


def _no_perm_user(client, admin_headers) -> dict:
    suf = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": f"noperm_{suf}", "password": "Test@123456", "name": "无权限", "status": "enabled",
              "role_ids": []},
    ).json()
    assert r["code"] == 0, r
    return _login(client, f"noperm_{suf}", "Test@123456")


def _create_form(client, admin_headers, key, fields, publish=True):
    r = client.post(
        f"{BASE}/admin/forms", headers=admin_headers, json={"key": key, "name": f"表单{key}", "fields": fields}
    ).json()
    assert r["code"] == 0, r
    fid = r["data"]["id"]
    if publish:
        p = client.post(f"{BASE}/admin/forms/{fid}/publish", headers=admin_headers).json()
        assert p["code"] == 0, p
    return fid


def _apply(client, headers, form_id, data):
    return client.post(f"{BASE}/instances", headers=headers, json={"formId": form_id, "data": data}).json()


# 含全部新能力的表单：条件显示/必填/只读 + 级联 + 字典源 + 资源控件（带出映射）+ 布局控件 + span/defaultValue
DESIGNER_FIELDS = [
    {"key": "", "label": "基础信息", "type": "divider"},
    {"key": "title", "label": "标题", "type": "text", "required": True, "span": 12, "defaultValue": "默认标题",
     "description": "请输入标题"},
    {"key": "amount", "label": "金额", "type": "money", "span": 12},
    {"key": "big_reason", "label": "大额说明", "type": "textarea",
     "showWhen": {"logic": "and", "rules": [{"field": "amount", "op": "gt", "value": "1000"}]},
     "requiredWhen": {"logic": "and", "rules": [{"field": "amount", "op": "gt", "value": "1000"}]}},
    {"key": "province", "label": "省份", "type": "select", "options": ["安徽", "江苏", "浙江"]},
    {"key": "city", "label": "城市", "type": "select", "options": ["合肥", "芜湖", "南京", "苏州"],
     "cascade": {"parent": "province", "map": {"安徽": ["合肥", "芜湖"], "江苏": ["南京", "苏州"]}}},
    {"key": "category", "label": "分类", "type": "select", "optionsSource": "dict", "dictType": "oa_category"},
    {"key": "customer", "label": "客户", "type": "resource", "resource": "customer",
     "mappings": [{"from": "customerNo", "to": "customer_no"}, {"from": "taxNo", "to": "tax_no"}]},
    {"key": "customer_no", "label": "客户编号", "type": "text", "readonlyWhen": {"logic": "and", "rules": [
        {"field": "customer", "op": "not_empty"}]}},
    {"key": "tax_no", "label": "纳税识别号", "type": "text"},
    {"key": "", "label": "说明文字", "type": "text_block"},
]


# ---------------- schema 扩展：创建 / 发布 / 编辑 ----------------


def test_designer_schema_roundtrip(client, admin_headers):
    """新字段全集可创建/发布/读回；布局控件 key 允许为空。"""
    fid = _create_form(client, admin_headers, _uniq("ut_d4_"), DESIGNER_FIELDS)
    forms = client.get(f"{BASE}/admin/forms", headers=admin_headers).json()["data"]
    form = next(f for f in forms if f["id"] == fid)
    fields = {f["type"]: f for f in form["fields"]}
    assert fields["divider"]["key"] == ""
    assert fields["resource"]["resource"] == "customer"
    assert fields["resource"]["mappings"][0] == {"from": "customerNo", "to": "customer_no"}
    city = next(f for f in form["fields"] if f["key"] == "city")
    assert city["cascade"]["map"]["安徽"] == ["合肥", "芜湖"]
    reason = next(f for f in form["fields"] if f["key"] == "big_reason")
    assert reason["showWhen"]["rules"][0]["op"] == "gt"
    title = next(f for f in form["fields"] if f["key"] == "title")
    assert title["span"] == 12 and title["defaultValue"] == "默认标题"


def test_legacy_schema_compat(client, admin_headers, manager_headers):
    """存量旧 schema（无新字段）照常发布/发起，向后兼容。"""
    fid = _create_form(client, admin_headers, _uniq("ut_old_"), [
        {"key": "reason", "label": "事由", "type": "textarea", "required": True},
        {"key": "kind", "label": "类别", "type": "select", "required": True, "options": ["A", "B"]},
    ])
    assert _apply(client, manager_headers, fid, {"reason": "x", "kind": "A"})["code"] == 0
    assert _apply(client, manager_headers, fid, {"reason": "x", "kind": "ZZ"})["code"] == 62003


def test_publish_new_schema_validation(client, admin_headers):
    """新配置项的发布前校验：资源类型缺失 / 映射目标不存在 / 级联父控件不存在 / 字典类型缺失 / 条件引用不存在。"""
    bad_cases = [
        [{"key": "c", "label": "客户", "type": "resource"}],  # 未配置 resource
        [{"key": "c", "label": "客户", "type": "resource", "resource": "customer",
          "mappings": [{"from": "name", "to": "ghost"}]}],  # 带出目标不存在
        [{"key": "s", "label": "市", "type": "select", "options": ["x"],
          "cascade": {"parent": "ghost", "map": {"a": ["x"]}}}],  # 级联父控件不存在
        [{"key": "d", "label": "类", "type": "select", "optionsSource": "dict"}],  # 字典源缺 dictType
        [{"key": "t", "label": "t", "type": "text",
          "showWhen": {"logic": "and", "rules": [{"field": "ghost", "op": "eq", "value": "1"}]}}],  # 条件引用不存在
    ]
    for fields in bad_cases:
        fid = _create_form(client, admin_headers, _uniq("ut_bad4_"), fields, publish=False)
        assert client.post(f"{BASE}/admin/forms/{fid}/publish", headers=admin_headers).json()["code"] == 62002, fields


# ---------------- 运行时校验：条件 / 级联 / 资源 ----------------


def test_condition_required_and_hidden(client, admin_headers, manager_headers):
    fid = _create_form(client, admin_headers, _uniq("ut_cond_"), DESIGNER_FIELDS)
    # amount <= 1000：big_reason 隐藏且非必填 → 仅标题即可提交
    ok = _apply(client, manager_headers, fid, {"title": "t", "amount": 500})
    assert ok["code"] == 0, ok
    # amount > 1000：big_reason 必填生效 → 缺失报 62003
    assert _apply(client, manager_headers, fid, {"title": "t", "amount": 2000})["code"] == 62003
    # 补齐 big_reason → 通过
    ok2 = _apply(client, manager_headers, fid, {"title": "t", "amount": 2000, "big_reason": "大额"})
    assert ok2["code"] == 0, ok2


def test_cascade_and_dict_source(client, admin_headers, manager_headers):
    fid = _create_form(client, admin_headers, _uniq("ut_casc_"), DESIGNER_FIELDS)
    base = {"title": "t", "province": "安徽"}
    # 级联：父值映射内合法
    assert _apply(client, manager_headers, fid, {**base, "city": "合肥"})["code"] == 0
    # 级联：父值映射外非法
    assert _apply(client, manager_headers, fid, {**base, "city": "南京"})["code"] == 62003
    # 父值不在 map：回退全选项
    assert _apply(client, manager_headers, fid, {"title": "t", "province": "浙江", "city": "南京"})["code"] == 0
    # 字典源：任意值不做成员校验
    assert _apply(client, manager_headers, fid, {"title": "t", "category": "任意字典值"})["code"] == 0


def test_resource_value_shape(client, admin_headers, manager_headers):
    fid = _create_form(client, admin_headers, _uniq("ut_res_"), DESIGNER_FIELDS)
    # 形状非法：缺 name / id 非 int / 非对象
    assert _apply(client, manager_headers, fid, {"title": "t", "customer": {"id": 1}})["code"] == 62003
    assert _apply(client, manager_headers, fid, {"title": "t", "customer": {"id": "1", "name": "x"}})["code"] == 62003
    assert _apply(client, manager_headers, fid, {"title": "t", "customer": 5})["code"] == 62003
    ok = _apply(client, manager_headers, fid, {"title": "t", "customer": {"id": 1, "name": "某客户"}})
    assert ok["code"] == 0, ok


# ---------------- 资源检索端点 ----------------


def test_resource_meta_and_search(client, admin_headers, manager_headers):
    meta = client.get(f"{BASE}/resources/meta", headers=manager_headers).json()["data"]
    types = {m["type"] for m in meta}
    assert types == {"customer", "contract", "task", "report", "dept", "user", "oa_instance"}
    customer = next(m for m in meta if m["type"] == "customer")
    assert {"key": "customerNo", "label": "客户编号"} in customer["fields"]

    # 用户检索（种子必有 manager1）
    r = client.get(f"{BASE}/resources/user", params={"q": "部门负责人"}, headers=manager_headers).json()
    assert r["code"] == 0 and r["data"]["total"] >= 1
    item = r["data"]["items"][0]
    assert item["id"] and item["label"] and "deptName" in item["fields"]
    # 部门检索
    r2 = client.get(f"{BASE}/resources/dept", headers=manager_headers).json()
    assert r2["code"] == 0 and r2["data"]["total"] >= 1
    # 未知类型 → 10001
    assert client.get(f"{BASE}/resources/ghost", headers=manager_headers).json()["code"] == 10001


def test_resource_perm_and_instance_visibility(client, admin_headers, manager_headers, leader_headers):
    # manager 有 oa:apply 可用；无权限用户 403
    noperm = _no_perm_user(client, admin_headers)
    assert client.get(f"{BASE}/resources/meta", headers=noperm).status_code == 403
    assert client.get(f"{BASE}/resources/user", headers=noperm).status_code == 403

    # oa_instance 只列本人可见：manager 的直通单，leader 检索不到
    fid = _create_form(client, admin_headers, _uniq("ut_vis_"),
                       [{"key": "reason", "label": "事由", "type": "text"}])
    marker = _uniq("可见性")
    inst = _apply(client, manager_headers, fid, {"reason": marker})
    assert inst["code"] == 0, inst
    mine = client.get(f"{BASE}/resources/oa_instance", headers=manager_headers).json()["data"]
    assert any(i["id"] == inst["data"]["id"] for i in mine["items"])
    others = client.get(f"{BASE}/resources/oa_instance", headers=leader_headers).json()["data"]
    assert all(i["id"] != inst["data"]["id"] for i in others["items"])

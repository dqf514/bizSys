"""软删除释放唯一键回归：删除用户/角色/字典条目后，同名重建不应 500。

bug 背景：username / role.code / (dict_type_code, value) 是物理唯一约束，
原实现逻辑删不释放键，重建时 IntegrityError → HTTP 500（code=10005）。
"""


def test_user_delete_frees_username(client, admin_headers):
    r = client.post("/api/v1/admin/users", headers=admin_headers,
                    json={"username": "e2e_del_user", "password": "E2e@123456", "name": "E2E删除用户"})
    assert r.status_code == 201, r.text
    uid = r.json()["data"]["id"]
    r = client.delete(f"/api/v1/admin/users/{uid}", headers=admin_headers)
    assert r.json()["code"] == 0, r.text
    # 同名重建：应是 201 而非 500
    r = client.post("/api/v1/admin/users", headers=admin_headers,
                    json={"username": "e2e_del_user", "password": "E2e@123456", "name": "E2E删除用户2"})
    assert r.status_code == 201 and r.json()["code"] == 0, r.text
    client.delete(f"/api/v1/admin/users/{r.json()['data']['id']}", headers=admin_headers)


def test_role_delete_frees_code(client, admin_headers):
    r = client.post("/api/v1/admin/roles", headers=admin_headers,
                    json={"code": "e2e_del_role", "name": "E2E删除角色"})
    assert r.json()["code"] == 0, r.text
    rid = r.json()["data"]["id"]
    r = client.delete(f"/api/v1/admin/roles/{rid}", headers=admin_headers)
    assert r.json()["code"] == 0, r.text
    r = client.post("/api/v1/admin/roles", headers=admin_headers,
                    json={"code": "e2e_del_role", "name": "E2E删除角色2"})
    assert r.json()["code"] == 0, r.text
    client.delete(f"/api/v1/admin/roles/{r.json()['data']['id']}", headers=admin_headers)


def test_dict_item_delete_frees_value_and_dup_rejected(client, admin_headers):
    client.post("/api/v1/admin/dict/types", headers=admin_headers,
                json={"code": "e2e_del_dict", "name": "E2E删除字典"})

    def _create(value="v1"):
        return client.post("/api/v1/admin/dict/items", headers=admin_headers,
                           json={"dictTypeCode": "e2e_del_dict", "label": "项1", "value": value})

    r = _create()
    assert r.json()["code"] == 0, r.text
    # 活动重复值 → 友好业务错误而非 500
    r = _create()
    assert r.json()["code"] != 0 and r.status_code != 500, r.text
    # 删除后重建同值 → 201
    types = client.get("/api/v1/admin/dict/types", headers=admin_headers).json()["data"]
    iid = next(i["id"] for t in types if t["code"] == "e2e_del_dict" for i in t.get("items", []) if i["value"] == "v1")
    r = client.delete(f"/api/v1/admin/dict/items/{iid}", headers=admin_headers)
    assert r.json()["code"] == 0, r.text
    r = _create()
    assert r.json()["code"] == 0, r.text
    # 清理
    types = client.get("/api/v1/admin/dict/types", headers=admin_headers).json()["data"]
    for t in types:
        if t["code"] == "e2e_del_dict":
            for i in t.get("items", []):
                client.delete(f"/api/v1/admin/dict/items/{i['id']}", headers=admin_headers)

"""知识与文档中心（B11）：分类树 / 空间 / 文件夹 / 上传 / 版本 / 授权 / 外部分享链接。

覆盖：
- 多级可定义分类（建树、改上级重算层级与路径、有子分类不可删）
- 个人空间 / 共享空间、文件夹树
- 单个与批量上传、格式与大小限制（格式/大小在系统管理区可配）
- 在线预览（txt 抽文本）、版本历史与回滚
- 文档授权（内部人员只读 / 可编辑），无授权用户不可见
- 外部分享链接：手机号验证码验证 → 浏览 → 上传；链接关闭后失效
- 删除 → 进回收站 → 恢复
"""

import uuid

import pytest

SUF = uuid.uuid4().hex[:8]
PHONE = "13800001234"


def _txt(name: str, content: str = "hello knowledge"):
    return (name, content.encode("utf-8"), "text/plain")


def _make_space(client, headers, name: str, stype: str = "personal") -> int:
    r = client.post(
        "/api/v1/knowledge/spaces",
        headers=headers,
        json={"name": name, "type": stype, "description": "test"},
    ).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


def _make_folder(client, headers, space_id: int, name: str, parent_id: int | None = None) -> int:
    payload = {"name": name, "spaceId": space_id}
    if parent_id:
        payload["parentId"] = parent_id
    r = client.post("/api/v1/knowledge/folders", headers=headers, json=payload).json()
    assert r["code"] == 0, r
    return r["data"]["id"]


# ---------------- 分类（多级可定义） ----------------


def test_category_multilevel_tree(client, admin_headers):
    top = client.post(
        "/api/v1/knowledge/categories",
        headers=admin_headers,
        json={"name": f"标准与方法库_{SUF}", "code": f"std_{SUF}"},
    ).json()
    assert top["code"] == 0, top
    top_id = top["data"]["id"]
    assert top["data"]["level"] == 1

    mid = client.post(
        "/api/v1/knowledge/categories",
        headers=admin_headers,
        json={"name": f"作业指导书_{SUF}", "parentId": top_id},
    ).json()
    assert mid["code"] == 0, mid
    mid_id = mid["data"]["id"]
    assert mid["data"]["level"] == 2
    assert mid["data"]["path"] == f"/{top_id}/"

    leaf = client.post(
        "/api/v1/knowledge/categories",
        headers=admin_headers,
        json={"name": f"设备操作说明_{SUF}", "parentId": mid_id},
    ).json()
    assert leaf["code"] == 0, leaf
    assert leaf["data"]["level"] == 3

    tree = client.get("/api/v1/knowledge/categories", headers=admin_headers).json()["data"]["items"]
    node = next(n for n in tree if n["id"] == top_id)
    assert [c["id"] for c in node["children"]] == [mid_id]
    assert node["children"][0]["children"][0]["id"] == leaf["data"]["id"]

    # 有子分类不允许删除
    r = client.delete(f"/api/v1/knowledge/categories/{top_id}", headers=admin_headers).json()
    assert r["code"] != 0
    assert r["code"] == 94008  # KNOWLEDGE_CATEGORY_INVALID

    # 叶子可删
    r = client.delete(f"/api/v1/knowledge/categories/{leaf['data']['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r


def test_category_move_recomputes_path(client, admin_headers):
    a = client.post(
        "/api/v1/knowledge/categories", headers=admin_headers, json={"name": f"甲_{SUF}"}
    ).json()["data"]
    b = client.post(
        "/api/v1/knowledge/categories", headers=admin_headers, json={"name": f"乙_{SUF}"}
    ).json()["data"]
    child = client.post(
        "/api/v1/knowledge/categories",
        headers=admin_headers,
        json={"name": f"丙_{SUF}", "parentId": a["id"]},
    ).json()["data"]

    moved = client.put(
        f"/api/v1/knowledge/categories/{child['id']}",
        headers=admin_headers,
        json={"name": child["name"], "parentId": b["id"]},
    ).json()
    assert moved["code"] == 0, moved
    assert moved["data"]["level"] == 2
    assert moved["data"]["path"] == f"/{b['id']}/"

    # 不能移动到自己的子分类下（丁 是 甲 的子孙）
    grand = client.post(
        "/api/v1/knowledge/categories",
        headers=admin_headers,
        json={"name": f"丁_{SUF}", "parentId": a["id"]},
    ).json()["data"]
    r = client.put(
        f"/api/v1/knowledge/categories/{a['id']}",
        headers=admin_headers,
        json={"name": "甲", "parentId": grand["id"]},
    ).json()
    assert r["code"] == 94008  # KNOWLEDGE_CATEGORY_INVALID


# ---------------- 空间 / 文件夹 ----------------


def test_space_and_folder_tree(client, admin_headers):
    space_id = _make_space(client, admin_headers, f"个人空间_{SUF}")
    shared_id = _make_space(client, admin_headers, f"共享空间_{SUF}", "shared")
    assert space_id and shared_id

    root = _make_folder(client, admin_headers, space_id, f"制度_{SUF}")
    child = _make_folder(client, admin_headers, space_id, f"公司制度_{SUF}", root)

    tree = client.get(
        "/api/v1/knowledge/folders/tree", headers=admin_headers, params={"spaceId": space_id}
    ).json()["data"]["items"]
    node = next(n for n in tree if n["id"] == root)
    assert [c["id"] for c in node["children"]] == [child]

    spaces = client.get("/api/v1/knowledge/spaces", headers=admin_headers).json()["data"]["items"]
    assert any(s["id"] == shared_id and s["type"] == "shared" for s in spaces)


# ---------------- 上传 / 预览 ----------------


def test_upload_document_and_preview(client, admin_headers):
    space_id = _make_space(client, admin_headers, f"上传空间_{SUF}")
    r = client.post(
        "/api/v1/knowledge/documents",
        headers=admin_headers,
        data={"title": f"作业指导_{SUF}", "space_id": str(space_id), "docType": "manual"},
        files={"file": _txt("guide.txt", "设备操作说明正文")},
    ).json()
    assert r["code"] == 0, r
    doc = r["data"]
    assert doc["currentVersion"] == 1
    assert doc["perm"] == "manage"

    # 在线预览（服务端抽文本）
    p = client.get(f"/api/v1/knowledge/documents/{doc['id']}/preview", headers=admin_headers).json()
    assert p["code"] == 0, p
    assert p["data"]["kind"] == "text"
    assert "设备操作说明" in p["data"]["text"]

    # 列表按空间过滤
    lst = client.get(
        "/api/v1/knowledge/documents", headers=admin_headers, params={"spaceId": space_id}
    ).json()["data"]
    assert lst["total"] == 1
    assert lst["items"][0]["id"] == doc["id"]


def test_upload_rejects_unsupported_format(client, admin_headers):
    space_id = _make_space(client, admin_headers, f"格式空间_{SUF}")
    r = client.post(
        "/api/v1/knowledge/documents",
        headers=admin_headers,
        data={"title": "非法格式", "space_id": str(space_id)},
        files={"file": ("virus.exe", b"MZ\x00\x00", "application/octet-stream")},
    ).json()
    assert r["code"] != 0
    assert r["code"] == 94003  # KNOWLEDGE_FILE_TYPE_UNSUPPORTED


def test_batch_upload(client, admin_headers):
    space_id = _make_space(client, admin_headers, f"批量空间_{SUF}")
    r = client.post(
        "/api/v1/knowledge/documents/batch",
        headers=admin_headers,
        data={"space_id": str(space_id)},
        files=[
            ("files", _txt(f"a_{SUF}.txt", "A")),
            ("files", _txt(f"b_{SUF}.txt", "B")),
            ("files", ("bad.exe", b"MZ", "application/octet-stream")),
        ],
    ).json()
    assert r["code"] == 0, r
    data = r["data"]
    assert data["total"] == 3
    assert data["success"] == 2
    failed = [i for i in data["items"] if not i["ok"]]
    assert failed and failed[0]["name"] == "bad.exe"


def test_upload_size_limit_configurable(client, admin_headers):
    """格式 / 大小上限在系统管理区可配（影响上传校验）。"""
    space_id = _make_space(client, admin_headers, f"大小空间_{SUF}")
    r = client.put(
        "/api/v1/knowledge/settings",
        headers=admin_headers,
        json={"allowedExt": ["txt"], "maxMb": 1, "previewMaxChars": 5000},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["allowedExt"] == ["txt"]
    assert r["data"]["maxMb"] == 1

    # 大小超限
    big = client.post(
        "/api/v1/knowledge/documents",
        headers=admin_headers,
        data={"title": "大文件", "space_id": str(space_id)},
        files={"file": ("big.txt", b"x" * (1024 * 1024 + 16), "text/plain")},
    ).json()
    assert big["code"] == 94004  # KNOWLEDGE_FILE_TOO_LARGE

    # 恢复默认（放宽格式）
    client.put(
        "/api/v1/knowledge/settings",
        headers=admin_headers,
        json={"allowedExt": [], "maxMb": 100, "previewMaxChars": 20000},
    )


# ---------------- 版本控制 ----------------


def test_version_history_and_rollback(client, admin_headers):
    space_id = _make_space(client, admin_headers, f"版本空间_{SUF}")
    doc = client.post(
        "/api/v1/knowledge/documents",
        headers=admin_headers,
        data={"title": f"版本件_{SUF}", "space_id": str(space_id)},
        files={"file": _txt("v1.txt", "第一版")},
    ).json()["data"]

    r = client.post(
        f"/api/v1/knowledge/documents/{doc['id']}/versions",
        headers=admin_headers,
        data={"comment": "第二版"},
        files={"file": _txt("v2.txt", "第二版")},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["versionNo"] == 2

    versions = client.get(
        f"/api/v1/knowledge/documents/{doc['id']}/versions", headers=admin_headers
    ).json()["data"]["items"]
    assert [v["versionNo"] for v in versions] == [2, 1]

    # 回滚到第 1 版（生成新版本，历史保留）
    first = next(v for v in versions if v["versionNo"] == 1)
    rb = client.post(
        f"/api/v1/knowledge/documents/{doc['id']}/rollback/{first['id']}", headers=admin_headers
    ).json()
    assert rb["code"] == 0, rb
    assert rb["data"]["versionNo"] == 3


# ---------------- 授权 ----------------


def test_document_permission_grant(client, admin_headers, manager_headers):
    space_id = _make_space(client, admin_headers, f"授权空间_{SUF}")
    doc = client.post(
        "/api/v1/knowledge/documents",
        headers=admin_headers,
        data={"title": f"受控文档_{SUF}", "space_id": str(space_id)},
        files={"file": _txt("secret.txt", "secret")},
    ).json()["data"]

    manager_id = client.get("/api/v1/auth/me", headers=manager_headers).json()["data"]["id"]

    # 未授权：manager 不可见 / 不可读
    r = client.get(f"/api/v1/knowledge/documents/{doc['id']}", headers=manager_headers).json()
    assert r["code"] == 94002  # KNOWLEDGE_PERMISSION_DENIED

    # 授权给 manager 只读
    r = client.put(
        f"/api/v1/knowledge/documents/{doc['id']}/permissions",
        headers=admin_headers,
        json=[
            {
                "subjectType": "user",
                "subjectId": manager_id,
                "subjectName": "manager",
                "perm": "read",
            }
        ],
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["items"][0]["perm"] == "read"

    r = client.get(f"/api/v1/knowledge/documents/{doc['id']}", headers=manager_headers).json()
    assert r["code"] == 0, r
    assert r["data"]["perm"] == "read"

    # 授权列表可读可删
    lst = client.get(
        f"/api/v1/knowledge/documents/{doc['id']}/permissions", headers=admin_headers
    ).json()["data"]["items"]
    assert len(lst) == 1
    r = client.delete(f"/api/v1/knowledge/permissions/{lst[0]['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r


# ---------------- 外部分享链接 ----------------


def test_share_link_external_verify_and_upload(client, admin_headers):
    space_id = _make_space(client, admin_headers, f"外部分享空间_{SUF}")
    folder_id = _make_folder(client, admin_headers, space_id, f"外部上传夹_{SUF}")

    r = client.post(
        "/api/v1/knowledge/links",
        headers=admin_headers,
        json={
            "resourceType": "folder",
            "resourceId": folder_id,
            "perm": "upload",
            "requirePhone": 1,
            "expireDays": 7,
            "remark": "外部提交资料",
        },
    ).json()
    assert r["code"] == 0, r
    token = r["data"]["token"]
    assert r["data"]["status"] == "active"

    # 链接信息（公开）
    info = client.get(f"/api/v1/knowledge/public/links/{token}").json()
    assert info["code"] == 0, info
    assert info["data"]["requirePhone"] is True
    assert info["data"]["status"] == "active"
    assert info["data"]["perm"] == "upload"

    # 未验证不能浏览
    r = client.get(f"/api/v1/knowledge/public/links/{token}/documents").json()
    assert r["code"] == 94007  # KNOWLEDGE_LINK_VERIFY_REQUIRED

    # 发验证码（测试环境从 Redis 取）
    from app.core.redis import get_redis

    r = client.post(f"/api/v1/knowledge/public/links/{token}/code", json={"phone": PHONE}).json()
    assert r["code"] == 0, r
    code = get_redis().get(f"kb_link_code:{token}:{PHONE}")
    assert code

    # 错误验证码
    r = client.post(
        f"/api/v1/knowledge/public/links/{token}/verify", json={"phone": PHONE, "code": "000000"}
    ).json()
    assert r["code"] == 94009  # KNOWLEDGE_LINK_CODE_INVALID

    # 正确验证码 → 访问令牌
    r = client.post(
        f"/api/v1/knowledge/public/links/{token}/verify", json={"phone": PHONE, "code": code}
    ).json()
    assert r["code"] == 0, r
    access = r["data"]["token"]
    assert access

    # 浏览清单
    r = client.get(
        f"/api/v1/knowledge/public/links/{token}/documents", params={"access": access}
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["items"] == []

    # 外部上传
    r = client.post(
        f"/api/v1/knowledge/public/links/{token}/upload",
        params={"access": access},
        files={"file": _txt(f"external_{SUF}.txt", "外部提交")},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["id"]

    # 再次浏览可看到上传的文件
    r = client.get(
        f"/api/v1/knowledge/public/links/{token}/documents", params={"access": access}
    ).json()
    assert len(r["data"]["items"]) == 1

    # 关闭链接后失效
    links = client.get("/api/v1/knowledge/links", headers=admin_headers).json()["data"]["items"]
    link = next(x for x in links if x["token"] == token)
    r = client.delete(f"/api/v1/knowledge/links/{link['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r
    r = client.get(f"/api/v1/knowledge/public/links/{token}").json()
    assert r["data"]["status"] == "closed"


def test_share_link_read_only_cannot_upload(client, admin_headers):
    space_id = _make_space(client, admin_headers, f"只读分享空间_{SUF}")
    folder_id = _make_folder(client, admin_headers, space_id, f"只读夹_{SUF}")
    r = client.post(
        "/api/v1/knowledge/links",
        headers=admin_headers,
        json={
            "resourceType": "folder",
            "resourceId": folder_id,
            "perm": "read",
            "requirePhone": 0,
            "expireDays": 1,
        },
    ).json()
    token = r["data"]["token"]

    # 不需要手机号验证即可浏览
    r = client.get(f"/api/v1/knowledge/public/links/{token}/documents").json()
    assert r["code"] == 0, r

    # 只读链接不允许上传
    r = client.post(
        f"/api/v1/knowledge/public/links/{token}/upload",
        files={"file": _txt("x.txt", "x")},
    ).json()
    assert r["code"] == 94002


# ---------------- 删除 → 回收站 → 恢复 ----------------


def test_delete_document_then_restore(client, admin_headers):
    space_id = _make_space(client, admin_headers, f"回收空间_{SUF}")
    doc = client.post(
        "/api/v1/knowledge/documents",
        headers=admin_headers,
        data={"title": f"待删除_{SUF}", "space_id": str(space_id)},
        files={"file": _txt("del.txt", "del")},
    ).json()["data"]

    r = client.delete(f"/api/v1/knowledge/documents/{doc['id']}", headers=admin_headers).json()
    assert r["code"] == 0, r

    # 列表中不可见
    lst = client.get(
        "/api/v1/knowledge/documents", headers=admin_headers, params={"spaceId": space_id}
    ).json()["data"]
    assert all(i["id"] != doc["id"] for i in lst["items"])

    # 出现在回收站
    bin_list = client.get(
        "/api/v1/admin/recycle",
        headers=admin_headers,
        params={"module": "knowledge", "q": f"待删除_{SUF}"},
    ).json()["data"]["items"]
    assert bin_list, bin_list
    entry = bin_list[0]
    assert entry["resourceId"] == doc["id"]
    assert entry["status"] == "recycled"

    # 恢复
    r = client.post(f"/api/v1/admin/recycle/{entry['id']}/restore", headers=admin_headers).json()
    assert r["code"] == 0, r
    lst = client.get(
        "/api/v1/knowledge/documents", headers=admin_headers, params={"spaceId": space_id}
    ).json()["data"]
    assert any(i["id"] == doc["id"] for i in lst["items"])


# ---------------- 微盘式目录浏览（B12） ----------------


def test_browse_mixes_folders_and_documents(client, admin_headers):
    """目录浏览：一次返回「子文件夹 + 文档」，面包屑 / 统计 / 标记齐备。"""
    space_id = _make_space(client, admin_headers, f"微盘空间_{SUF}")
    root = _make_folder(client, admin_headers, space_id, f"制度_{SUF}")
    sub = _make_folder(client, admin_headers, space_id, f"子目录_{SUF}", root)

    # 空间根目录下一个文档 + 根文件夹下一个文档
    doc_root = client.post(
        "/api/v1/knowledge/documents",
        headers=admin_headers,
        data={"title": f"根目录文档_{SUF}", "space_id": str(space_id)},
        files={"file": _txt("root.txt", "根目录")},
    ).json()["data"]
    doc_in_folder = client.post(
        "/api/v1/knowledge/documents",
        headers=admin_headers,
        data={"title": f"夹内文档_{SUF}", "space_id": str(space_id), "folder_id": str(root)},
        files={"file": _txt("in.txt", "夹内")},
    ).json()["data"]

    # 空间根：子文件夹 + 根级文档
    r = client.get(
        "/api/v1/knowledge/browse", headers=admin_headers, params={"spaceId": space_id}
    ).json()
    assert r["code"] == 0, r
    data = r["data"]
    assert data["space"]["id"] == space_id
    assert data["breadcrumb"] == []
    assert [f["id"] for f in data["folders"]] == [root]
    assert data["folders"][0]["docCount"] == 1
    assert [d["id"] for d in data["documents"]["items"]] == [doc_root["id"]]
    assert "updaterName" in data["documents"]["items"][0]
    assert data["stats"]["myDocCount"] >= 2

    # 进子目录：面包屑 = 根目录
    r = client.get(
        "/api/v1/knowledge/browse",
        headers=admin_headers,
        params={"spaceId": space_id, "folderId": root},
    ).json()["data"]
    assert [b["id"] for b in r["breadcrumb"]] == [root]
    assert [f["id"] for f in r["folders"]] == [sub]
    assert [d["id"] for d in r["documents"]["items"]] == [doc_in_folder["id"]]

    # 关键词过滤
    r = client.get(
        "/api/v1/knowledge/browse",
        headers=admin_headers,
        params={"spaceId": space_id, "q": f"根目录文档_{SUF}"},
    ).json()["data"]
    assert [d["id"] for d in r["documents"]["items"]] == [doc_root["id"]]


def test_browse_marks_external_access_and_restricted(client, admin_headers):
    """外部可访问 / 限制成员权限标记。"""
    space_id = _make_space(client, admin_headers, f"标记空间_{SUF}")
    folder_id = _make_folder(client, admin_headers, space_id, f"标记夹_{SUF}")
    doc = client.post(
        "/api/v1/knowledge/documents",
        headers=admin_headers,
        data={"title": f"标记文档_{SUF}", "space_id": str(space_id), "folder_id": str(folder_id)},
        files={"file": _txt("mark.txt", "mark")},
    ).json()["data"]

    r = client.get(
        "/api/v1/knowledge/browse", headers=admin_headers, params={"spaceId": space_id}
    ).json()["data"]
    assert r["folders"][0]["externalAccess"] is False
    assert r["folders"][0]["restricted"] is False

    # 外部分享链接 → 文件夹「外部可访问」
    client.post(
        "/api/v1/knowledge/links",
        headers=admin_headers,
        json={"resourceType": "folder", "resourceId": folder_id, "perm": "read", "expireDays": 1},
    )
    # 文档授权 → 「限制成员权限」
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()["data"]["id"]
    client.put(
        f"/api/v1/knowledge/documents/{doc['id']}/permissions",
        headers=admin_headers,
        json=[{"subjectType": "user", "subjectId": me, "subjectName": "admin", "perm": "read"}],
    )

    r = client.get(
        "/api/v1/knowledge/browse",
        headers=admin_headers,
        params={"spaceId": space_id, "folderId": folder_id},
    ).json()["data"]
    assert r["documents"]["items"][0]["externalAccess"] is False
    assert r["documents"]["items"][0]["restricted"] is True


def test_space_pin_toggle(client, admin_headers):
    """空间置顶 / 取消置顶（微盘左栏「置顶」分组）。"""
    space_id = _make_space(client, admin_headers, f"置顶空间_{SUF}")

    r = client.post(
        f"/api/v1/knowledge/spaces/{space_id}/pin", headers=admin_headers, json={"pinned": 1}
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["pinned"] == 1

    spaces = client.get("/api/v1/knowledge/spaces", headers=admin_headers).json()["data"]["items"]
    assert next(s for s in spaces if s["id"] == space_id)["pinned"] == 1

    r = client.post(
        f"/api/v1/knowledge/spaces/{space_id}/pin", headers=admin_headers, json={"pinned": 0}
    ).json()
    assert r["data"]["pinned"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""消息中心：站内通知的检索（q / 分类）、页签计数与已读操作。

覆盖本轮新增的接口面：
- GET /admin/notifies 支持 q 关键词（标题/正文）与 filters[biz_type] 分类、status=unread；
- GET /admin/notifies/counts 返回 all / unread / byBizType。
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.admin.models import Notify

SUF = uuid.uuid4().hex[:6]


@pytest.fixture()
def seed_notifies(client, admin_headers):
    """造 3 条当前用户的通知 + 1 条他人通知（他人通知不应出现在结果与计数里）。

    测试库跨运行复用，所以先记下"改动前"的计数与既有通知的已读状态，用完还原。
    """
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()["data"]
    uid = me["id"]
    before = client.get("/api/v1/admin/notifies/counts", headers=admin_headers).json()["data"]

    db = SessionLocal()
    ids: list[int] = []
    restore: list[tuple[int, int]] = []
    try:
        restore = [(n.id, n.read_flag) for n in db.scalars(
            select(Notify).where(Notify.user_id == uid, Notify.deleted == 0)
        ).all()]
        rows = [
            Notify(user_id=uid, title=f"合同待签 {SUF}", content="请处理合同审批", biz_type="contract"),
            Notify(user_id=uid, title=f"任务指派 {SUF}", content="新的任务已指派给你", biz_type="task"),
            Notify(user_id=uid, title=f"合同归档 {SUF}", content="合同已归档", biz_type="contract", read_flag=1),
            Notify(user_id=uid + 9999, title=f"他人通知 {SUF}", content="不应出现", biz_type="task"),
        ]
        db.add_all(rows)
        db.commit()
        ids = [r.id for r in rows]
        yield {"user_id": uid, "ids": ids, "before": before}
    finally:
        if ids:
            db.query(Notify).filter(Notify.id.in_(ids)).delete(synchronize_session=False)
        # 还原"全部标为已读"可能改动的既有通知状态
        for nid, flag in restore:
            n = db.get(Notify, nid)
            if n is not None:
                n.read_flag = flag
        db.commit()
        db.close()


def _list(client, headers, **params):
    r = client.get("/api/v1/admin/notifies", headers=headers, params=params).json()["data"]
    return r


def test_notify_list_keyword(client, admin_headers, seed_notifies):
    """q 关键词命中标题/正文，且只返回自己的通知。"""
    r = _list(client, admin_headers, q=SUF)
    assert r["total"] == 3, r
    assert all(SUF in i["title"] or SUF in i["content"] for i in r["items"])
    assert "他人通知" not in [i["title"] for i in r["items"]]


def test_notify_list_biz_type_filter(client, admin_headers, seed_notifies):
    """filters[biz_type] 分类过滤。"""
    both = _list(client, admin_headers, q=SUF)
    contract = _list(client, admin_headers, q=SUF, **{"filters[biz_type]": "contract"})
    assert both["total"] == 3
    assert contract["total"] == 2, contract
    assert {i["bizType"] for i in contract["items"]} == {"contract"}


def test_notify_list_unread_status(client, admin_headers, seed_notifies):
    """status=unread 只返回未读。"""
    r = _list(client, admin_headers, q=SUF, status="unread")
    assert r["total"] == 2, r
    assert all(i["readFlag"] is False for i in r["items"])


def test_notify_counts(client, admin_headers, seed_notifies):
    """counts：all / unread / byBizType 相对改动前的增量。"""
    after = client.get("/api/v1/admin/notifies/counts", headers=admin_headers).json()["data"]
    before = seed_notifies["before"]
    assert after["all"] == before["all"] + 3, after
    assert after["unread"] == before["unread"] + 2, after
    assert after["byBizType"].get("contract", 0) == before["byBizType"].get("contract", 0) + 2
    assert after["byBizType"].get("task", 0) == before["byBizType"].get("task", 0) + 1


def test_notify_mark_read_and_read_all(client, admin_headers, seed_notifies):
    """单条标已读 / 全部标已读后，计数随之下降。"""
    before = seed_notifies["before"]
    nid = seed_notifies["ids"][0]

    r = client.post(f"/api/v1/admin/notifies/{nid}/read", headers=admin_headers).json()
    assert r["code"] == 0, r
    after_one = client.get("/api/v1/admin/notifies/counts", headers=admin_headers).json()["data"]
    assert after_one["unread"] == before["unread"] + 1, after_one

    r = client.post("/api/v1/admin/notifies/read-all", headers=admin_headers).json()
    assert r["code"] == 0, r
    after_all = client.get("/api/v1/admin/notifies/counts", headers=admin_headers).json()["data"]
    assert after_all["unread"] == 0, after_all

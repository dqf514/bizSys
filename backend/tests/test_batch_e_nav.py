"""批次E：企业总导航三区重构。

断言迁移脚本 migrate_nav_batch_e 幂等修复脏状态：
- 顶层恰好为 工作台/业务系统/OA系统/系统管理（+隐藏的流程中心），无重复无残留；
- 各区子项 parent/sort 归一（业务区 报告在样品前；财务 开票→结算→到账）；
- 同名重复目录去重、异名同 path 残留归位；
- 连续执行两次结果一致。
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.admin.models import Menu, RoleMenu
from scripts.migrate_nav_batch_e import main as migrate_nav

SUF = uuid.uuid4().hex[:6]


def _tree(client, admin_headers):
    return client.get("/api/v1/admin/menus/tree", headers=admin_headers).json()["data"]


def _find(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
        r = _find(n.get("children") or [], name)
        if r:
            return r
    return None


@pytest.fixture(scope="module")
def dirty_state():
    """造脏状态：顶层残留（异名同 path）+ 重复 BizSystem 目录 + 错误排序。"""
    db = SessionLocal()
    stray = dup = None
    try:
        stray = Menu(
            name=f"客户管理{SUF}",  # 历史按中文名建的单：name 不稳定、path 相同
            title_key="",
            path="/crm/customers",
            component_key="crm/CustomerList",
            menu_type="menu",
            sort=99,
        )
        dup = Menu(name="BizSystem", title_key="menu.bizSystem", menu_type="dir", sort=99)
        db.add_all([stray, dup])
        db.flush()
        db.add(RoleMenu(role_id=1, menu_id=dup.id))
        db.commit()
        yield {"stray_id": stray.id, "dup_id": dup.id}
    finally:
        # 兜底清理（迁移正常时已软删/解绑，这里硬删保证测试库干净）
        for mid in [stray and stray.id, dup and dup.id]:
            if mid:
                db.query(RoleMenu).filter(RoleMenu.menu_id == mid).delete()
                db.query(Menu).filter(Menu.id == mid).delete()
        db.commit()
        db.close()


def test_zone_structure_and_dirty_repair(client, admin_headers, dirty_state):
    migrate_nav()
    tree = _tree(client, admin_headers)

    # 顶层：工作台 + 三区 + 隐藏流程中心；无重复、无业务残留
    top_names = [n["name"] for n in tree]
    assert top_names == ["Workbench", "BizSystem", "OaSystem", "System", "ApprovalCenter"], top_names
    approval = _find(tree, "ApprovalCenter")
    assert approval and approval["visible"] == 0

    # 业务区：客户/合同/任务/报告/样品/财务；财务内 开票→结算→到账
    biz = _find(tree, "BizSystem")
    assert [c["name"] for c in biz["children"]] == [
        "Customers",
        "Contracts",
        "Tasks",
        "Reports",
        "Samples",
        "Finance",
    ]
    finance = _find(tree, "Finance")
    assert [c["name"] for c in finance["children"]] == [
        "FinanceInvoices",
        "FinanceSettlements",
        "FinancePayments",
    ]

    # OA 区与系统管理区
    oa = _find(tree, "OaSystem")
    assert [c["name"] for c in oa["children"]] == ["OaApply", "OaMy", "OaRelated", "OaStats"]
    sy = _find(tree, "System")
    assert [c["name"] for c in sy["children"]] == ["SysOrg", "SysData", "OaAdmin", "SysOps"]

    # 脏状态修复：异名同 path 残留被改名归位（path 相同只会留一个 Customers）
    db = SessionLocal()
    try:
        stray = db.get(Menu, dirty_state["stray_id"])
        assert stray.deleted == 1  # 目标 Customers 已存在 → 同 path 残留软删
        dup = db.get(Menu, dirty_state["dup_id"])
        assert dup.deleted == 1  # 重复目录软删
        assert not db.scalars(select(RoleMenu).where(RoleMenu.menu_id == dup.id)).all()
        customers = db.scalars(
            select(Menu).where(Menu.deleted == 0, Menu.path == "/crm/customers")
        ).all()
        assert len(customers) == 1 and customers[0].name == "Customers"
    finally:
        db.close()

    # 幂等：再跑一次，结构不变
    migrate_nav()
    tree2 = _tree(client, admin_headers)
    assert [n["name"] for n in tree2] == top_names


def test_nav_me_tree(client, admin_headers, dirty_state):
    """/auth/me 导航树：无隐藏项、无重复顶层。"""
    migrate_nav()
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()["data"]
    nav_names = [n["name"] for n in me["menus"]]
    assert "ApprovalCenter" not in nav_names
    assert len(nav_names) == len(set(nav_names))
    assert "/approval" in me["allMenuPaths"]

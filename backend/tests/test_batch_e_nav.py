"""导航分区重构（7 业务分区 + 底部系统管理）。

断言迁移脚本 migrate_nav_zones 幂等修复脏状态：
- 顶层恰好为 工作台 + 七个业务分区 + 系统管理，无重复无残留；
- 各分区子项 parent/sort 归一（业务中心 报告→项目；生产资源 设备→排程→样品与物料→采购→产能；
  流程与办公 流程待办与消息中心）；
- 同名重复目录去重、异名同 path 残留归位；
- 连续执行两次结果一致。
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.admin.models import Menu, RoleMenu
from scripts.migrate_nav_zones import main as migrate_nav

SUF = uuid.uuid4().hex[:6]

TOP_NAMES = [
    "Workbench",
    "BizSystem",
    "Resources",
    "StockAsset",
    "SalesSystem",
    "Collaboration",
    "HrSystem",
    "OaSystem",
    "VisitorSafety",
    "System",
]


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


def _children(node):
    return [c["name"] for c in node["children"]]


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
        dup = Menu(name="BizSystem", title_key="menu.bizCenter", menu_type="dir", sort=99)
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

    # 顶层：工作台 + 七个业务分区 + 系统管理；无重复、无业务残留
    top_names = [n["name"] for n in tree]
    assert top_names == TOP_NAMES, top_names

    # 业务中心：客户/合同/任务/报告/项目/财务；财务内 开票→结算→到账
    biz = _find(tree, "BizSystem")
    assert _children(biz) == [
        "Customers",
        "Contracts",
        "Tasks",
        "Reports",
        "Projects",
        "Finance",
    ]
    finance = _find(tree, "Finance")
    assert _children(finance) == ["FinanceSettlements", "FinanceInvoices", "FinancePayments"]

    # 生产资源：设备→排程→样品与物料→采购→产能；样品与物料 内 样品 + 物料
    res = _find(tree, "Resources")
    assert _children(res) == [
        "Equipment",
        "ProductionSchedules",
        "AssetsSamples",
        "Procurement",
        "ProductionCapacity",
    ]
    samples_dir = _find(tree, "AssetsSamples")
    assert _children(samples_dir) == ["Samples", "Materials", "Bom"]
    assert _find(tree, "Samples")["parentId"] == samples_dir["id"]

    # 库存与资产：进出库管理（仓储/库存）+ 资产财务（折旧/处置/工具）
    stock = _find(tree, "StockAsset")
    assert _children(stock) == ["StockManagement", "AssetFinance"]
    assert _children(_find(tree, "StockManagement")) == [
        "PurchaseOrders",
        "Receipts",
        "Warehouses",
        "InventoryItems",
        "StockLedger",
        "StockCounts",
        "Prototypes",
        "PrototypeLoans",
    ]
    assert _children(_find(tree, "AssetFinance")) == ["FixedAssets", "Disposals", "ToolLoans"]

    # 销售中心 / 经营与协同 / 行政人事
    assert _children(_find(tree, "SalesSystem")) == ["Quotations", "QuoteTemplates", "SalesRevenue"]
    assert _children(_find(tree, "Collaboration")) == [
        "PortalHome",
        "PortalOrders",
        "EntrustList",
        "CustomerAccounts",
        "PartnerStaff",
        "KnowledgeBase",
    ]
    assert _children(_find(tree, "HrSystem")) == ["TimesheetFill", "TimesheetStats", "Staff"]

    # 流程与办公：流程待办已解除隐藏并挂到本区，消息中心为正式入口
    oa = _find(tree, "OaSystem")
    assert _children(oa) == [
        "OaApply",
        "OaMy",
        "OaRelated",
        "OaStats",
        "WorkApply",
        "ApprovalCenter",
        "Messages",
    ]
    approval = _find(tree, "ApprovalCenter")
    assert approval["visible"] == 1 and approval["parentId"] == oa["id"]

    # 访客与安全 / 系统管理
    assert _children(_find(tree, "VisitorSafety")) == [
        "Visits",
        "VisitorZones",
        "VisitorNda",
        "VisitorCredentials",
        "VisitorBlacklist",
        "VisitorAuditLogs",
        "VisitorHandovers",
        "VisitorAlerts",
        "SafetyInspections",
    ]
    assert _children(_find(tree, "System")) == ["SysOrg", "SysData", "OaAdmin", "SysOps", "AiCenter"]

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
    """/auth/me 导航树：只有可见项、无重复顶层。"""
    migrate_nav()
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()["data"]
    nav_names = [n["name"] for n in me["menus"]]
    assert nav_names == TOP_NAMES, nav_names
    assert len(nav_names) == len(set(nav_names))
    assert "/approval" in me["allMenuPaths"]

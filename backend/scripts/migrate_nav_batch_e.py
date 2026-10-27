"""批次E 企业总导航三区重构的存量库菜单迁移（幂等，可重复执行）。

背景：批次A 的 migrate_nav_batch_a 只处理了"挂到 BizSystem 下"这一件事，且种子
_seed_menus 不回写 parent_id/sort；局部执行/别的库/中文名匹配都会造成残留：
顶层业务菜单没搬走、"业务系统"目录重复、OA/系统两组同 sort 顺序不稳。

本迁移按稳定键（英文 name 为主、path 兜底）修复"已部分迁移"的脏状态：
1. 同名菜单去重（保留最小 id，其余软删并解除角色绑定）；
2. 残留归位：路径与目标子项相同但 name 不同/位置不对的菜单，改名并挂到目标父目录；
   目标子项的同路径重复行软删；
3. 按 TARGET_TREE 归一 parent_id/sort（工作台→业务系统→OA系统→系统管理，
   业务区内 客户/合同/任务/报告/样品/采购/财务，财务内 开票→结算→到账）；
4. ApprovalCenter 强制隐藏（深链 /approval 可用，权限点仍由它承载）；
5. 跑 init_data.main() 补齐缺失菜单与角色权限绑定。

新库由种子直接产出目标结构，无需本脚本。
用法: python scripts/migrate_nav_batch_e.py
"""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.admin.models import Menu, RoleMenu
from app.seeds import init_data

# 目标结构：父目录 name → [子项 name 按 sort 顺序]；None 表示顶层
TARGET_TREE: dict[str | None, list[str]] = {
    None: ["Workbench", "BizSystem", "OaSystem", "System", "ApprovalCenter"],
    "BizSystem": ["Customers", "Contracts", "Tasks", "Reports", "Samples", "Procurement", "Finance"],
    "Finance": ["FinanceInvoices", "FinanceSettlements", "FinancePayments"],
    "OaSystem": ["OaApply", "OaMy", "OaRelated", "OaStats"],
    "System": ["SysOrg", "SysData", "OaAdmin", "SysOps"],
    "SysOrg": ["Users", "Roles", "Depts"],
    "SysData": ["FlowDefs", "Dicts", "NumberRules"],
    "OaAdmin": ["OaFlowStats", "OaFlowHandle"],
    "SysOps": ["Menus", "AuditLogs", "Maintenance", "Settings"],
}

# name → title_key（path 兜底匹配命中后改名的同时补 title_key）
TITLE_KEYS = {
    "Workbench": "menu.workbench",
    "BizSystem": "menu.bizSystem",
    "OaSystem": "menu.oaSystem",
    "System": "menu.system",
    "ApprovalCenter": "menu.approval",
    "Customers": "menu.customer",
    "Contracts": "menu.contract",
    "Tasks": "menu.task",
    "Reports": "menu.report",
    "Samples": "menu.sample",
    "Finance": "menu.finance",
    "FinanceInvoices": "menu.financeInvoice",
    "FinanceSettlements": "menu.financeSettlement",
    "FinancePayments": "menu.financePayment",
    "OaApply": "menu.oaApply",
    "OaMy": "menu.oaMy",
    "OaRelated": "menu.oaRelated",
    "OaStats": "menu.oaStats",
    "SysOrg": "menu.sysOrg",
    "SysData": "menu.sysData",
    "OaAdmin": "menu.oaAdmin",
    "SysOps": "menu.sysOps",
    "Users": "menu.users",
    "Roles": "menu.roles",
    "Depts": "menu.depts",
    "FlowDefs": "menu.flow",
    "Dicts": "menu.dict",
    "NumberRules": "menu.numbering",
    "OaFlowStats": "menu.oaFlowStats",
    "OaFlowHandle": "menu.oaFlowHandle",
    "Menus": "menu.menus",
    "AuditLogs": "menu.audit",
    "Maintenance": "menu.maintenance",
    "Settings": "menu.settings",
}

# 目标子项的规范 path（用于 path 兜底匹配与重复残留识别）
CANON_PATHS = {
    "Workbench": "/workbench",
    "Customers": "/crm/customers",
    "Contracts": "/contract/contracts",
    "Tasks": "/task/tasks",
    "Reports": "/report/reports",
    "Samples": "/task/samples",
    "ApprovalCenter": "/approval",
    "FinanceInvoices": "/finance/invoices",
    "FinanceSettlements": "/finance/settlements",
    "FinancePayments": "/finance/payments",
    "OaApply": "/oa/apply",
    "OaMy": "/oa/my",
    "OaRelated": "/oa/related",
    "OaStats": "/oa/stats",
    "Users": "/admin/users",
    "Roles": "/admin/roles",
    "Depts": "/admin/depts",
    "FlowDefs": "/admin/flowdefs",
    "Dicts": "/admin/dict",
    "NumberRules": "/admin/numbering",
    "OaFlowStats": "/admin/oa/stats",
    "OaFlowHandle": "/admin/oa/instances",
    "Menus": "/admin/menus",
    "AuditLogs": "/admin/audit",
    "Maintenance": "/admin/maintenance",
    "Settings": "/admin/settings",
}

ALL_KNOWN = set(TITLE_KEYS)


def main() -> None:
    db = SessionLocal()
    try:
        rows = list(db.scalars(select(Menu).where(Menu.deleted == 0)).all())
        by_name: dict[str, list[Menu]] = {}
        for m in rows:
            by_name.setdefault(m.name, []).append(m)

        removed: list[int] = []

        def soft_delete(m: Menu, why: str) -> None:
            m.deleted = 1
            removed.append(m.id)
            print(f"soft-deleted #{m.id} {m.name} ({why})")

        # 1. 同名去重：保留最小 id，其余子树并入后软删
        for name, ms in by_name.items():
            if len(ms) <= 1:
                continue
            keep = min(ms, key=lambda m: m.id)
            for dup in ms:
                if dup is keep:
                    continue
                for c in rows:
                    if c.parent_id == dup.id:
                        c.parent_id = keep.id
                soft_delete(dup, f"duplicate of {name}#{keep.id}")

        menus = {m.name: m for m in rows if m.deleted == 0}

        # 2. path 兜底归位：name 不在目标集但 path 命中目标子项（历史按中文名迁移失败的残留）
        canon_paths = {v: k for k, v in CANON_PATHS.items()}
        for m in list(menus.values()):
            if m.deleted or m.name in ALL_KNOWN or not m.path:
                continue
            target = canon_paths.get(m.path)
            if not target:
                continue  # 树外自定义菜单：保留
            if target in menus and menus[target].deleted == 0:
                soft_delete(m, f"duplicate path {m.path} of {target}")
            else:
                m.name = target
                m.title_key = TITLE_KEYS.get(target, m.title_key)
                menus[target] = m
                print(f"renamed #{m.id} -> {target} (matched by path {m.path})")

        # 3. 归一 parent_id/sort
        def parent_id_of(pname: str | None) -> int | None:
            if pname is None:
                return None
            p = menus.get(pname)
            return p.id if p and not p.deleted else None

        moved: list[str] = []
        for pname, children in TARGET_TREE.items():
            pid = parent_id_of(pname)
            for idx, cname in enumerate(children):
                m = menus.get(cname)
                if not m or m.deleted:
                    continue  # 缺失的由种子补建
                sort = idx if cname != "ApprovalCenter" else 9
                if m.parent_id != pid or m.sort != sort:
                    m.parent_id = pid
                    m.sort = sort
                    moved.append(cname)
        if moved:
            print(f"reparented/resorted: {moved}")

        # 4. 隐藏流程中心（权限点载体保留）
        approval = menus.get("ApprovalCenter")
        if approval and not approval.deleted and approval.visible != 0:
            approval.visible = 0
            print("hidden: ApprovalCenter")

        # 5. 顶层残留告警（非目标集、未删、仍在顶层的行）
        top_residue = [
            f"{m.name}#{m.id}"
            for m in menus.values()
            if not m.deleted and m.parent_id is None and m.name not in TARGET_TREE[None]
        ]
        if top_residue:
            print(f"WARN top-level residue kept (custom?): {top_residue}")

        if removed:
            db.query(RoleMenu).filter(RoleMenu.menu_id.in_(removed)).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # 种子幂等补齐缺失菜单/权限绑定（不回写既有 parent_id/sort）
    init_data.main()
    print("done")


if __name__ == "__main__":
    main()

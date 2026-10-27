"""采购管理一期菜单迁移（幂等，可重复执行）。

种子 _seed_menus 只补缺失菜单、不回写 parent_id/sort；本脚本处理存量库：
1. 按 path 兜底归位：name 不在目标集但 path 命中采购子项的残留菜单改名归位；
   目标子项的同路径重复行软删；
2. 归一 parent_id/sort：BizSystem 子区追加 Procurement（客户/合同/任务/报告/样品/采购/财务），
   Procurement 内 申请→合同→出入库；
3. 同名菜单去重（保留最小 id，解除软删行的角色绑定）；
4. 跑 init_data.main() 补齐缺失菜单/字典/编号规则/审批定义/角色权限绑定。

新库由种子直接产出目标结构，无需本脚本。
用法: python scripts/migrate_nav_procurement.py
"""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.admin.models import Menu, RoleMenu
from app.seeds import init_data

# 目标结构：父目录 name → [子项 name 按 sort 顺序]
TARGET_TREE: dict[str, list[str]] = {
    "BizSystem": ["Customers", "Contracts", "Tasks", "Reports", "Samples", "Procurement", "Finance"],
    "Procurement": ["PurchaseRequests", "PurchaseContracts", "StockOrders"],
}

TITLE_KEYS = {
    "Procurement": "menu.procurement",
    "PurchaseRequests": "menu.purchaseRequest",
    "PurchaseContracts": "menu.purchaseContract",
    "StockOrders": "menu.stockOrder",
}

CANON_PATHS = {
    "PurchaseRequests": "/procurement/requests",
    "PurchaseContracts": "/procurement/contracts",
    "StockOrders": "/procurement/stock",
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

        # 2. path 兜底归位
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
        def parent_id_of(pname: str) -> int | None:
            p = menus.get(pname)
            return p.id if p and not p.deleted else None

        moved: list[str] = []
        for pname, children in TARGET_TREE.items():
            pid = parent_id_of(pname)
            if pid is None and pname != "BizSystem":
                continue  # Procurement 目录缺失时由种子补建后再归位（二次执行生效）
            for idx, cname in enumerate(children):
                m = menus.get(cname)
                if not m or m.deleted:
                    continue  # 缺失的由种子补建
                if m.parent_id != pid or m.sort != idx:
                    m.parent_id = pid
                    m.sort = idx
                    moved.append(cname)
        if moved:
            print(f"reparented/resorted: {moved}")

        if removed:
            db.query(RoleMenu).filter(RoleMenu.menu_id.in_(removed)).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # 种子幂等补齐（不覆盖上面的归位结果）
    init_data.main()

    # 第二轮归位：种子新建的 Procurement 目录/子项挂到目标位置
    db = SessionLocal()
    try:
        menus = {m.name: m for m in db.scalars(select(Menu).where(Menu.deleted == 0)).all()}
        moved = []
        for pname, children in TARGET_TREE.items():
            p = menus.get(pname)
            pid = p.id if p else None
            for idx, cname in enumerate(children):
                m = menus.get(cname)
                if not m:
                    continue
                if m.parent_id != pid or m.sort != idx:
                    m.parent_id = pid
                    m.sort = idx
                    moved.append(cname)
        if moved:
            print(f"reparented/resorted (pass 2): {moved}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print("done")


if __name__ == "__main__":
    main()

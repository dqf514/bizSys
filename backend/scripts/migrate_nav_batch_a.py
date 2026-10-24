"""批次A 导航整合的存量库菜单迁移（幂等）。

背景：种子 _seed_menus 只同步代码耦合字段、不回写 parent_id/sort（保留管理员的结构调整），
所以"业务系统"分组的归并需要这个一次性迁移完成；新库由种子直接产出目标结构，无需本脚本。

做的事：
1. 顶层创建"业务系统"目录（name=BizSystem，缺失才建）；
2. 把 Customers/Contracts/Tasks/Reports/Finance 五个业务菜单挂到其下并按既定顺序排 sort；
3. 隐藏 ApprovalCenter（visible=0，权限点 approval:view 仍由它承载）；
4. 跑 init_data.main()：补 Samples 菜单/按钮、给 super/biz_user 角色挂新权限点。

个人顶排偏好 prefs.navOrder 存的是顶层菜单 id 列表，新增的 BizSystem 不在其中时
前端按既有兜底排在末位，不会被破坏。

用法: python scripts/migrate_nav_batch_a.py
"""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.admin.models import Menu
from app.seeds import init_data

# 业务系统分组内的成员与顺序
BIZ_CHILDREN = ["Customers", "Contracts", "Tasks", "Samples", "Reports", "Finance"]


def main() -> None:
    db = SessionLocal()
    try:
        menus = {m.name: m for m in db.scalars(select(Menu).where(Menu.deleted == 0)).all()}

        biz = menus.get("BizSystem")
        if biz is None:
            biz = Menu(
                parent_id=None,
                name="BizSystem",
                title_key="menu.bizSystem",
                path="",
                component_key="",
                icon="Suitcase",
                permission="",
                menu_type="dir",
                sort=1,
            )
            db.add(biz)
            db.flush()
            print("created dir: BizSystem")

        moved = []
        for idx, name in enumerate(BIZ_CHILDREN):
            m = menus.get(name)
            if m is None:
                continue  # Samples 尚不存在，由种子补建
            if m.parent_id != biz.id or m.sort != idx:
                m.parent_id = biz.id
                m.sort = idx
                moved.append(name)
        if moved:
            print(f"reparented under BizSystem: {moved}")

        approval = menus.get("ApprovalCenter")
        if approval and approval.visible != 0:
            approval.visible = 0
            print("hidden: ApprovalCenter")

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # 种子幂等补齐：Samples 菜单、task:sample:* 权限挂载、其余结构不动
    init_data.main()


if __name__ == "__main__":
    main()

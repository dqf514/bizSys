"""导航分区重构的存量库迁移（幂等，可重复执行）。

背景
----
种子 `_seed_menus` 只同步代码耦合字段（title_key/path/component_key/icon/permission/menu_type），
不回写 parent_id/sort（保留管理员在菜单管理里的结构调整），所以"7 业务分区"的搬家与排序
必须靠这个一次性迁移完成；新库由种子直接产出目标结构，无需本脚本。

规范结构**直接从种子的 `MENU_TREE` 推导**，不在本脚本里再抄一份树 ——
种子改了目录结构，这里跟着变，不会出现两套结构各说各话。

做的事：
1. 修脏状态：同名菜单去重（保留最小 id，子树并入），异名同 path 的历史残留改名归位或软删；
2. 跑种子：补出缺失的分区目录与菜单行，同步代码耦合字段；
3. 按规范结构归一 parent_id（含 Samples→样品与物料、Procurement→生产资源、
   ApprovalCenter→流程与办公），并解除"流程待办"的隐藏；
4. 按规范顺序回写各层级的 sort（树外自定义菜单保持原相对顺序，排在末尾）；
5. 再跑一遍种子：给新建/归位的菜单补上角色权限绑定。

个人顶排偏好 prefs.navOrder 存的是顶层菜单 id 列表，分区集合变化后失效 ——
前端 layout/useNavZones.ts::validOrder 已内置失效回退 + SideNav.vue 的陈旧偏好重置，无需额外处理。

用法: uv run python scripts/migrate_nav_zones.py
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.modules.admin.models import Menu, RoleMenu
from app.seeds import init_data


def _spec() -> tuple[dict[str, str | None], dict[str | None, list[str]], dict[str, str]]:
    """从种子的 MENU_TREE 推导规范结构。

    返回 (parent_of, order, path_to_name)：
    - parent_of[name] → 规范父目录 name（顶层为 None）
    - order[parent] → 该父目录下子项的规范顺序（顶层用键 None）
    - path_to_name[path] → 该 path 的规范菜单名（只有非空 path 才有）
    """
    parent_of: dict[str, str | None] = {}
    order: dict[str | None, list[str]] = {}
    path_to_name: dict[str, str] = {}

    def walk(nodes, parent: str | None) -> None:
        for node in nodes:
            name = node[1]
            parent_of[name] = parent
            order.setdefault(parent, []).append(name)
            if node[2]:
                path_to_name[node[2]] = name
            walk(node[6], name)

    walk(init_data.MENU_TREE, None)
    return parent_of, order, path_to_name


PARENT_OF, ORDER, PATH_TO_NAME = _spec()

# 解除隐藏：流程待办曾被"藏起来只留权限点"，现已是流程与办公下的正式入口
UNHIDE = {"ApprovalCenter"}


def _repair(db: Session) -> list[int]:
    """同名去重 + 异名同 path 归位。返回被软删的菜单 id（用于解绑角色）。"""
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

    # 2. path 兜底归位：name 不在规范集里但 path 命中规范菜单 —— 早期按中文名建的残留
    for m in list(menus.values()):
        if m.deleted or m.name in PARENT_OF or not m.path:
            continue
        target = PATH_TO_NAME.get(m.path)
        if not target:
            continue  # 树外自定义菜单：保留
        if target in menus and not menus[target].deleted:
            soft_delete(m, f"duplicate path {m.path} of {target}")
        else:
            m.name = target
            menus[target] = m
            print(f"renamed #{m.id} -> {target} (matched by path {m.path})")

    if removed:
        db.query(RoleMenu).filter(RoleMenu.menu_id.in_(removed)).delete(synchronize_session=False)
    return removed


def _normalize(db: Session) -> None:
    """按规范结构归一 parent_id / visible / sort。"""
    menus = {m.name: m for m in db.scalars(select(Menu).where(Menu.deleted == 0)).all()}

    def pid_of(parent: str | None) -> int | None:
        if parent is None:
            return None
        p = menus.get(parent)
        return p.id if p is not None else None

    # 1. parent_id 归一
    for name, parent in PARENT_OF.items():
        m = menus.get(name)
        if m is None:
            continue
        pid = pid_of(parent)
        if m.parent_id != pid:
            m.parent_id = pid
            print(f"reparented: {name} -> {parent}")

    # 2. 解除隐藏
    for name in UNHIDE:
        m = menus.get(name)
        if m is not None and m.visible != 1:
            m.visible = 1
            print(f"unhidden: {name}")

    # 3. sort 归一：规范子项按目标顺序在前，树外自定义菜单按原相对顺序追加在后
    for parent, names in ORDER.items():
        pid = pid_of(parent)
        children = [m for m in menus.values() if m.parent_id == pid]
        listed = [menus[n] for n in names if n in menus and menus[n].parent_id == pid]
        rest = sorted(
            (m for m in children if m not in listed),
            key=lambda m: (m.sort if m.sort is not None else 0, m.id),
        )
        for idx, m in enumerate(listed + rest):
            if m.sort != idx:
                m.sort = idx


def main() -> None:
    # 1. 修脏状态（先于种子：改名后的规范名才能被种子正确同步字段）
    db = SessionLocal()
    try:
        _repair(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # 2. 种子：补齐缺失的分区目录与菜单行，同步代码耦合字段
    init_data.main()

    # 3. 结构归一：parent_id / visible / sort
    db = SessionLocal()
    try:
        _normalize(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # 4. 再跑一遍种子：新建/归位的菜单补角色权限绑定
    init_data.main()
    print("done")


if __name__ == "__main__":
    main()

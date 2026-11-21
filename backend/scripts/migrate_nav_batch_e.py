"""已废弃：请改用 `scripts/migrate_nav_zones.py`。

历史背景：批次E 曾把总导航重构成"工作台 + 业务系统/OA系统/人事行政/销售系统/系统管理"五区，
当时的迁移脚本 migrate_nav_batch_e.py 负责脏状态修复与 parent_id/sort 归一。

导航分区重构（7 业务分区 + 底部系统管理）之后，本脚本里的 TARGET_TREE 已经过时 ——
再跑它会把 Samples/Procurement 搬回业务系统、把流程待办重新藏回顶层。
因此这里改为转发到新的迁移脚本，保留旧入口以兼容既有的运维手册与测试引用。

新脚本的规范结构直接从种子的 MENU_TREE 推导，并保留了本脚本原有的两项脏状态修复：
同名菜单去重（保留最小 id，子树并入）、异名同 path 残留改名归位或软删。

用法: uv run python scripts/migrate_nav_zones.py
"""

from scripts.migrate_nav_zones import main

__all__ = ["main"]


if __name__ == "__main__":
    main()

"""人事行政区（HrSystem：工时填报/工时统计）存量库菜单迁移（幂等，可重复执行）。

批次E 的 migrate_nav_batch_e 已把 HrSystem 区纳入 TARGET_TREE/TITLE_KEYS/CANON_PATHS
（顶层序：工作台→业务系统→OA系统→人事行政→系统管理，ApprovalCenter 隐藏置尾），
本脚本仅作本批次的部署入口：直接委托批次E 迁移（内部会先修脏状态再跑 init_data 补齐
新菜单与角色权限绑定）。新库由种子直接产出目标结构，无需本脚本。

用法: python scripts/migrate_nav_hr.py
"""

from scripts.migrate_nav_batch_e import main as migrate_nav


def main() -> None:
    migrate_nav()
    print("done")


if __name__ == "__main__":
    main()

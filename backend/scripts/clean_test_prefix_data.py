"""清理 dev 库中 ta_/tb_/tc_ 前缀的三路测试数据（逻辑删除 deleted=1，不 purge）。

用法: python scripts/clean_test_prefix_data.py
"""

from sqlalchemy import text

from app.core.db import engine

LIKE = "LIKE 'ta\\_%' OR {c} LIKE 'tb\\_%' OR {c} LIKE 'tc\\_%'"


def cond(c: str) -> str:
    return f"({c} LIKE 'ta\\_%' OR {c} LIKE 'tb\\_%' OR {c} LIKE 'tc\\_%')"


def main() -> None:
    with engine.begin() as conn:
        def soft(tbl: str, where: str, **params) -> int:
            r = conn.execute(text(f"UPDATE `{tbl}` SET deleted=1 WHERE deleted=0 AND {where}"), params)
            print(f"{tbl}: {r.rowcount}")
            return r.rowcount

        # 业务实体（先取 id 供审批实例级联）
        soft("crm_customer", cond("name"))
        soft("ctr_contract", f"{cond('name')} OR {cond('customer_name')}")
        contract_ids = [r[0] for r in conn.execute(text(
            f"SELECT id FROM ctr_contract WHERE {cond('name')} OR {cond('customer_name')}"))]
        soft("task_task", f"{cond('task_name')} OR {cond('customer_name')}")
        task_ids = [r[0] for r in conn.execute(text(
            f"SELECT id FROM task_task WHERE {cond('task_name')} OR {cond('customer_name')}"))]
        soft("task_item", cond("name"))
        soft("oa_form", f"{cond('`key`')} OR {cond('name')}")
        soft("oa_instance", f"{cond('form_key')} OR {cond('form_name')}")
        oa_ids = [r[0] for r in conn.execute(text(
            f"SELECT id FROM oa_instance WHERE {cond('form_key')} OR {cond('form_name')}"))]
        soft("approval_definition", f"{cond('code')} OR {cond('name')}")

        # 财务/报告
        soft("fin_settlement", cond("customer_name"))
        settle_ids = [r[0] for r in conn.execute(text(f"SELECT id FROM fin_settlement WHERE {cond('customer_name')}"))]
        soft("fin_payment", cond("payer_name"))
        if settle_ids:
            soft("fin_settlement_confirm", f"settlement_id IN ({','.join(str(i) for i in settle_ids)})")
        soft("rpt_report", cond("file_name"))
        soft("rpt_file", cond("file_name"))

        # 用户/角色
        soft("sys_user", f"{cond('username')} OR {cond('name')}")
        user_ids = [r[0] for r in conn.execute(text(f"SELECT id FROM sys_user WHERE {cond('username')}"))]
        soft("sys_role", f"{cond('code')} OR {cond('name')}")
        role_ids = [r[0] for r in conn.execute(text(f"SELECT id FROM sys_role WHERE {cond('code')}"))]
        if user_ids:
            soft("sys_user_role", f"user_id IN ({','.join(str(i) for i in user_ids)})")
        if role_ids:
            soft("sys_user_role", f"role_id IN ({','.join(str(i) for i in role_ids)})")
            soft("sys_role_menu", f"role_id IN ({','.join(str(i) for i in role_ids)})")

        # 审批实例：定义编码命中 或 biz 引用被清理的测试实体
        biz_clauses = [" OR ".join(f"definition_code LIKE '{p}\\_%'" for p in ("ta", "tb", "tc"))]
        for bt, ids in (("contract", contract_ids), ("task", task_ids), ("oa", oa_ids)):
            if ids:
                biz_clauses.append(f"(biz_type='{bt}' AND biz_id IN ({','.join(str(i) for i in ids)}))")
        soft("approval_instance", " OR ".join(f"({c})" for c in biz_clauses))
        inst_ids = [r[0] for r in conn.execute(text(
            "SELECT id FROM approval_instance WHERE deleted=1 AND ("
            + " OR ".join(f"({c})" for c in biz_clauses) + ")"))]
        if inst_ids:
            id_list = ",".join(str(i) for i in inst_ids)
            soft("approval_task", f"instance_id IN ({id_list})")
            soft("approval_record", f"instance_id IN ({id_list})")

        # 登录日志
        soft("sys_login_log", cond("username"))

    print("done")


if __name__ == "__main__":
    main()

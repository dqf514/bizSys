"""B9 合规基线：审计证据链（字段级 + 哈希链）+ 电子签名绑定列

- `sys_audit_log` 改为只追加（物理删 deleted/version/update_*/create_by），
  增补字段级列（field_name/old_value/new_value/reason/user_agent）与
  哈希链列（chain_seq/prev_hash/row_hash/hash_alg）；
  `create_time` 改 DATETIME(3) —— row_hash 含毫秒时间戳，秒精度会导致重算必然不一致；
- 新建 `sys_audit_chain_head`（链头，唯一权威游标）与 `sys_audit_failure`（写入失败台账）；
- `vis_nda` 增补签名绑定列（签署人 / 真实 IP / 算法 / 版本），存量行标 legacy-sha256；
- `rpt_report` 增补签章绑定列（内容哈希 / 签名 / 算法）与三级角色列；
- `sys_audit_log` 加 BEFORE UPDATE / BEFORE DELETE 触发器，物理阻断改删。

手写迁移（`alembic/env.py` 未 import hr/visitor/report 部分表，autogenerate 会试图删表）。

Revision ID: n8a2b3c4d5e6
Revises: n7a2b3c4d5e6
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op

revision = "n8a2b3c4d5e6"
down_revision = "n7a2b3c4d5e6"
branch_labels = None
depends_on = None

_AUDIT_TABLE = "sys_audit_log"


def upgrade() -> None:
    # ---- 1. sys_audit_log：字段级 + 哈希链 ----
    op.add_column(
        _AUDIT_TABLE,
        sa.Column("field_name", sa.String(length=64), nullable=False, server_default="", comment="变更字段名"),
    )
    op.add_column(_AUDIT_TABLE, sa.Column("old_value", sa.Text(), nullable=True, comment="变更前值"))
    op.add_column(_AUDIT_TABLE, sa.Column("new_value", sa.Text(), nullable=True, comment="变更后值"))
    op.add_column(_AUDIT_TABLE, sa.Column("reason", sa.Text(), nullable=True, comment="变更原因"))
    op.add_column(
        _AUDIT_TABLE,
        sa.Column("user_agent", sa.String(length=255), nullable=False, server_default="", comment="终端 UA"),
    )
    op.add_column(
        _AUDIT_TABLE,
        sa.Column("chain_seq", sa.BigInteger(), nullable=True, comment="链上序号（存量行为 NULL）"),
    )
    op.add_column(
        _AUDIT_TABLE, sa.Column("prev_hash", sa.String(length=64), nullable=False, server_default="", comment="上一行哈希")
    )
    op.add_column(
        _AUDIT_TABLE, sa.Column("row_hash", sa.String(length=64), nullable=False, server_default="", comment="本行哈希")
    )
    op.add_column(
        _AUDIT_TABLE,
        sa.Column("hash_alg", sa.String(length=16), nullable=False, server_default="", comment="哈希算法标识"),
    )
    op.create_index("ix_sys_audit_log_chain_seq", _AUDIT_TABLE, ["chain_seq"], unique=True)

    # 毫秒精度：哈希含 create_time，秒精度会让校验方重算出不同结果
    op.execute(
        "ALTER TABLE sys_audit_log "
        "MODIFY COLUMN create_time DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '写入时间'"
    )
    # 只追加：物理删掉可改可删的列
    op.execute(
        "ALTER TABLE sys_audit_log "
        "DROP COLUMN deleted, DROP COLUMN version, DROP COLUMN update_time, "
        "DROP COLUMN update_by, DROP COLUMN create_by"
    )

    # ---- 2. 链头 + 失败台账 ----
    op.create_table(
        "sys_audit_chain_head",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("create_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.Column("update_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("version", sa.Integer(), nullable=True, comment="乐观锁版本"),
        sa.Column("deleted", sa.Integer(), nullable=True, comment="逻辑删除 0/1"),
        sa.Column("chain_key", sa.String(length=32), nullable=False, comment="链标识"),
        sa.Column("last_seq", sa.BigInteger(), nullable=False, server_default="0", comment="链上最后序号"),
        sa.Column("last_hash", sa.String(length=64), nullable=False, server_default="", comment="链上最后哈希"),
        sa.Column("last_row_id", sa.BigInteger(), nullable=False, server_default="0", comment="链上最后一行 id"),
        sa.Column("anchored_seq", sa.BigInteger(), nullable=False, server_default="0", comment="已锚定序号"),
        sa.Column("anchored_hash", sa.String(length=64), nullable=False, server_default="", comment="已锚定哈希"),
        sa.Column("anchored_at", sa.DateTime(), nullable=True, comment="锚定时间"),
        sa.Column("write_failures", sa.Integer(), nullable=False, server_default="0", comment="审计写入失败次数"),
        sa.Column("key_version", sa.String(length=16), nullable=False, server_default="v1", comment="密钥版本"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sys_audit_chain_head_chain_key", "sys_audit_chain_head", ["chain_key"], unique=True)
    op.execute(
        "INSERT INTO sys_audit_chain_head (chain_key, last_seq, last_hash, last_row_id, anchored_seq, "
        "anchored_hash, write_failures, key_version, deleted, version) "
        "VALUES ('main', 0, '', 0, 0, '', 0, 'v1', 0, 0) "
        "ON DUPLICATE KEY UPDATE chain_key = chain_key"
    )

    op.create_table(
        "sys_audit_failure",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="写入时间"),
        sa.Column("user_id", sa.BigInteger(), nullable=True, comment="操作人"),
        sa.Column("module", sa.String(length=32), nullable=False, server_default="", comment="模块"),
        sa.Column("action", sa.String(length=32), nullable=False, server_default="", comment="动作"),
        sa.Column("biz_type", sa.String(length=32), nullable=False, server_default="", comment="业务类型"),
        sa.Column("biz_id", sa.BigInteger(), nullable=True, comment="业务 id"),
        sa.Column("error", sa.String(length=255), nullable=False, server_default="", comment="失败原因"),
        sa.Column("attempted_seq", sa.BigInteger(), nullable=False, server_default="0", comment="尝试写入的链上序号"),
        sa.Column("detail", sa.Text(), nullable=True, comment="明细"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sys_audit_failure_module", "sys_audit_failure", ["module"])
    op.create_index("ix_sys_audit_failure_user_id", "sys_audit_failure", ["user_id"])

    # ---- 3. vis_nda：签名绑定列（存量标 legacy） ----
    op.add_column(
        "vis_nda", sa.Column("signed_by_id", sa.BigInteger(), nullable=True, comment="签署人 id（内部账号）")
    )
    op.add_column(
        "vis_nda",
        sa.Column("signed_by_name", sa.String(length=64), nullable=False, server_default="", comment="签署人姓名"),
    )
    op.add_column(
        "vis_nda", sa.Column("signed_ip", sa.String(length=64), nullable=False, server_default="", comment="签署真实 IP")
    )
    op.add_column(
        "vis_nda", sa.Column("sign_alg", sa.String(length=16), nullable=False, server_default="", comment="签名算法")
    )
    op.add_column(
        "vis_nda",
        sa.Column("sign_version", sa.String(length=16), nullable=False, server_default="", comment="签名版本/口径"),
    )
    op.execute("UPDATE vis_nda SET sign_version = 'legacy-sha256' WHERE signed_by_id IS NULL")

    # ---- 4. rpt_report：签章绑定列 + 三级角色 ----
    op.add_column(
        "rpt_report",
        sa.Column("seal_by_name", sa.String(length=64), nullable=False, server_default="", comment="签章人姓名"),
    )
    op.add_column(
        "rpt_report",
        sa.Column("seal_content_hash", sa.String(length=64), nullable=False, server_default="", comment="签章内容哈希"),
    )
    op.add_column(
        "rpt_report",
        sa.Column("seal_signature", sa.String(length=64), nullable=False, server_default="", comment="签章签名"),
    )
    op.add_column(
        "rpt_report", sa.Column("seal_alg", sa.String(length=16), nullable=False, server_default="", comment="签名算法")
    )
    op.add_column("rpt_report", sa.Column("preparer_id", sa.BigInteger(), nullable=True, comment="编制人 id"))
    op.add_column(
        "rpt_report",
        sa.Column("preparer_name", sa.String(length=64), nullable=False, server_default="", comment="编制人姓名"),
    )
    op.add_column("rpt_report", sa.Column("reviewer_id", sa.BigInteger(), nullable=True, comment="复核人 id"))
    op.add_column(
        "rpt_report",
        sa.Column("reviewer_name", sa.String(length=64), nullable=False, server_default="", comment="复核人姓名"),
    )
    op.add_column("rpt_report", sa.Column("approver_id", sa.BigInteger(), nullable=True, comment="批准人 id"))
    op.add_column(
        "rpt_report",
        sa.Column("approver_name", sa.String(length=64), nullable=False, server_default="", comment="批准人姓名"),
    )

    # ---- 5. 只追加：物理阻断 UPDATE / DELETE ----
    op.execute(
        "CREATE TRIGGER trg_sys_audit_log_no_update BEFORE UPDATE ON sys_audit_log "
        "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = "
        "'sys_audit_log is append-only: UPDATE is forbidden'"
    )
    op.execute(
        "CREATE TRIGGER trg_sys_audit_log_no_delete BEFORE DELETE ON sys_audit_log "
        "FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = "
        "'sys_audit_log is append-only: DELETE is forbidden'"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sys_audit_log_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_sys_audit_log_no_update")

    op.drop_column("rpt_report", "approver_name")
    op.drop_column("rpt_report", "approver_id")
    op.drop_column("rpt_report", "reviewer_name")
    op.drop_column("rpt_report", "reviewer_id")
    op.drop_column("rpt_report", "preparer_name")
    op.drop_column("rpt_report", "preparer_id")
    op.drop_column("rpt_report", "seal_alg")
    op.drop_column("rpt_report", "seal_signature")
    op.drop_column("rpt_report", "seal_content_hash")
    op.drop_column("rpt_report", "seal_by_name")

    op.drop_column("vis_nda", "sign_version")
    op.drop_column("vis_nda", "sign_alg")
    op.drop_column("vis_nda", "signed_ip")
    op.drop_column("vis_nda", "signed_by_name")
    op.drop_column("vis_nda", "signed_by_id")

    op.drop_index("ix_sys_audit_failure_user_id", table_name="sys_audit_failure")
    op.drop_index("ix_sys_audit_failure_module", table_name="sys_audit_failure")
    op.drop_table("sys_audit_failure")

    op.drop_index("ix_sys_audit_chain_head_chain_key", table_name="sys_audit_chain_head")
    op.drop_table("sys_audit_chain_head")

    op.drop_index("ix_sys_audit_log_chain_seq", table_name=_AUDIT_TABLE)
    op.drop_column(_AUDIT_TABLE, "hash_alg")
    op.drop_column(_AUDIT_TABLE, "row_hash")
    op.drop_column(_AUDIT_TABLE, "prev_hash")
    op.drop_column(_AUDIT_TABLE, "chain_seq")
    op.drop_column(_AUDIT_TABLE, "user_agent")
    op.drop_column(_AUDIT_TABLE, "reason")
    op.drop_column(_AUDIT_TABLE, "new_value")
    op.drop_column(_AUDIT_TABLE, "old_value")
    op.drop_column(_AUDIT_TABLE, "field_name")

    # 还原旧的审计表结构
    op.execute(
        "ALTER TABLE sys_audit_log "
        "ADD COLUMN deleted INT NULL COMMENT '逻辑删除 0/1', "
        "ADD COLUMN version INT NULL COMMENT '乐观锁版本', "
        "ADD COLUMN update_time DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间', "
        "ADD COLUMN update_by BIGINT NULL COMMENT '更新人', "
        "ADD COLUMN create_by BIGINT NULL COMMENT '创建人'"
    )
    op.execute(
        "ALTER TABLE sys_audit_log "
        "MODIFY COLUMN create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'"
    )

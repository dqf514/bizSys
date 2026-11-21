"""资产域 B4 补充：BOM 物料清单（ast_bom / ast_bom_line）+ 存货呆滞阈值列

Revision ID: n4a2b3c4d5e6
Revises: n3a2b3c4d5e6
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "n4a2b3c4d5e6"
down_revision = "n3a2b3c4d5e6"
branch_labels = None
depends_on = None


def _create(table: str, cols: list, indexes: list | None = None, fks: list | None = None) -> None:
    op.create_table(
        table,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="创建时间"),
        sa.Column("create_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="更新时间"),
        sa.Column("update_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("version", sa.Integer(), nullable=True, comment="乐观锁版本"),
        sa.Column("deleted", sa.Integer(), nullable=True, comment="逻辑删除 0/1"),
        *cols,
        *(
            [
                sa.ForeignKeyConstraint(
                    [fk["column"]], [fk["target"]], name=fk["name"], ondelete=fk.get("ondelete")
                )
                for fk in (fks or [])
            ]
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    for idx in indexes or []:
        op.create_index(idx["name"], table, idx["cols"], unique=idx.get("unique", False))


def upgrade() -> None:
    # ---------------- BOM 主表 ----------------
    _create(
        "ast_bom",
        [
            sa.Column("bom_no", sa.String(32), nullable=False, comment="BOM 编号 BM..."),
            sa.Column("parent_item_id", sa.BigInteger(), nullable=False, comment="父件 ast_item.id"),
            sa.Column("parent_item_code", sa.String(32), nullable=True, comment="父件编码冗余"),
            sa.Column("parent_item_name", sa.String(128), nullable=True, comment="父件名称冗余"),
            sa.Column("parent_spec", sa.String(255), nullable=True, comment="父件规格冗余"),
            sa.Column("bom_version", sa.String(32), nullable=True, comment="BOM 版本号"),
            sa.Column("status", sa.String(16), nullable=True, comment="draft/effective/obsolete"),
            sa.Column("effective_date", sa.Date(), nullable=True, comment="生效日期"),
            sa.Column("line_count", sa.Integer(), nullable=True, comment="子件行数"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_ast_bom_bom_no", "cols": ["bom_no"], "unique": True},
            {"name": "ix_ast_bom_parent_item_id", "cols": ["parent_item_id"]},
            {"name": "ix_ast_bom_bom_version", "cols": ["bom_version"]},
            {"name": "ix_ast_bom_status", "cols": ["status"]},
        ],
    )

    # ---------------- BOM 子件行 ----------------
    _create(
        "ast_bom_line",
        [
            sa.Column("bom_id", sa.BigInteger(), nullable=False, comment="BOM ast_bom.id"),
            sa.Column("item_id", sa.BigInteger(), nullable=True, comment="子件 ast_item.id"),
            sa.Column("item_code", sa.String(32), nullable=True, comment="子件编码"),
            sa.Column("item_name", sa.String(128), nullable=True, comment="子件名称"),
            sa.Column("spec", sa.String(255), nullable=True, comment="规格"),
            sa.Column("unit", sa.String(16), nullable=True, comment="单位"),
            sa.Column("qty", sa.Numeric(12, 2), nullable=True, comment="单位用量"),
            sa.Column("loss_rate", sa.Numeric(6, 2), nullable=True, comment="损耗率 %"),
            sa.Column("ref_designator", sa.String(128), nullable=True, comment="位号"),
            sa.Column("position", sa.String(64), nullable=True, comment="装配位置/工序"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_ast_bom_line_bom_id", "cols": ["bom_id"]},
            {"name": "ix_ast_bom_line_item_id", "cols": ["item_id"]},
        ],
        [{"name": "fk_ast_bom_line_bom", "column": "bom_id", "target": "ast_bom.id", "ondelete": "CASCADE"}],
    )

    # ---------------- 存货呆滞预警阈值 ----------------
    op.add_column(
        "ast_item",
        sa.Column("stagnant_days", sa.Integer(), nullable=True, comment="呆滞预警阈值（天，0=不预警）"),
    )


def downgrade() -> None:
    op.drop_column("ast_item", "stagnant_days")
    op.drop_index("ix_ast_bom_line_item_id", table_name="ast_bom_line")
    op.drop_index("ix_ast_bom_line_bom_id", table_name="ast_bom_line")
    op.drop_table("ast_bom_line")
    op.drop_index("ix_ast_bom_status", table_name="ast_bom")
    op.drop_index("ix_ast_bom_bom_version", table_name="ast_bom")
    op.drop_index("ix_ast_bom_parent_item_id", table_name="ast_bom")
    op.drop_index("ix_ast_bom_bom_no", table_name="ast_bom")
    op.drop_table("ast_bom")

"""number rule: category_key + structured date digits + seq_start + separator

sys_number_rule 扩展：
- category_key（分类键，空=兜底规则），biz_type+category_key 联合唯一取代 biz_type 单列唯一
- year_digits/month_digits/day_digits 结构化日期位数（由 date_format 迁移解析）
- seq_start 流水起始值、separator 分隔符
- reset_cycle 语义扩展支持 yearly（无需 DDL）

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-10-19
"""

import sqlalchemy as sa

from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None

# 旧 strftime 格式串 → 结构化位数
_DATE_MAP = {
    "%Y%m%d": (4, 2, 2),
    "%Y%m": (4, 2, 0),
    "%Y": (4, 0, 0),
    "%y%m%d": (2, 2, 2),
    "%y%m": (2, 2, 0),
}


def upgrade() -> None:
    op.add_column(
        "sys_number_rule",
        sa.Column(
            "category_key", sa.String(64), nullable=False, server_default="", comment="分类键（字典值），空=兜底规则"
        ),
    )
    op.add_column(
        "sys_number_rule",
        sa.Column("year_digits", sa.Integer, nullable=False, server_default="0", comment="年位数 0/2/4"),
    )
    op.add_column(
        "sys_number_rule",
        sa.Column("month_digits", sa.Integer, nullable=False, server_default="0", comment="月位数 0/2"),
    )
    op.add_column(
        "sys_number_rule",
        sa.Column("day_digits", sa.Integer, nullable=False, server_default="0", comment="日位数 0/2"),
    )
    op.add_column(
        "sys_number_rule",
        sa.Column("seq_start", sa.Integer, nullable=False, server_default="1", comment="流水起始值"),
    )
    op.add_column(
        "sys_number_rule",
        sa.Column("separator", sa.String(4), nullable=False, server_default="", comment="前缀/日期/流水间分隔符"),
    )
    for fmt, (y, m, d) in _DATE_MAP.items():
        # 常量内联（% 号在 text()+bindparams 下与驱动 paramstyle 冲突，实测不生效）；
        # BINARY 强制大小写敏感（utf8mb4_general_ci 下 '%Y' 会误匹配 '%y'）
        op.execute(
            f"UPDATE sys_number_rule SET year_digits={y}, month_digits={m}, day_digits={d} "
            f"WHERE BINARY date_format='{fmt}'"
        )
    op.drop_index("ix_sys_number_rule_biz_type", table_name="sys_number_rule")
    op.create_index("ix_sys_number_rule_biz_type", "sys_number_rule", ["biz_type"], unique=False)
    # 唯一键含 deleted：软删行不阻塞同 biz_type+category_key 重建（应用层只对 deleted=0 判重）
    op.create_unique_constraint(
        "uq_number_rule_biz_category", "sys_number_rule", ["biz_type", "category_key", "deleted"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_number_rule_biz_category", "sys_number_rule", type_="unique")
    op.drop_index("ix_sys_number_rule_biz_type", table_name="sys_number_rule")
    op.create_index("ix_sys_number_rule_biz_type", "sys_number_rule", ["biz_type"], unique=True)
    for col in ("separator", "seq_start", "day_digits", "month_digits", "year_digits", "category_key"):
        op.drop_column("sys_number_rule", col)

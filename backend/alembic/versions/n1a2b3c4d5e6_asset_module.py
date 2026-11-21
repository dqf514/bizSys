"""资产与库存模块（B4）：ast_* 17 张表

Revision ID: n1a2b3c4d5e6
Revises: m1a2b3c4d5e6
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "n1a2b3c4d5e6"
down_revision = "m1a2b3c4d5e6"
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
    # ---------------- 仓库与库位 ----------------
    _create(
        "ast_warehouse",
        [
            sa.Column("code", sa.String(32), nullable=False, comment="仓库编码"),
            sa.Column("name", sa.String(128), nullable=False, comment="仓库名称"),
            sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门 sys_dept.id"),
            sa.Column("dept_name", sa.String(128), nullable=True, comment="部门名冗余"),
            sa.Column("address", sa.String(255), nullable=True, comment="仓库地址"),
            sa.Column("manager_id", sa.BigInteger(), nullable=True, comment="负责人 sys_user.id"),
            sa.Column("manager_name", sa.String(64), nullable=True, comment="负责人姓名"),
            sa.Column("capacity", sa.Integer(), nullable=True, comment="库位总数"),
            sa.Column("phone", sa.String(32), nullable=True, comment="联系电话"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="enabled/disabled"),
        ],
        [
            {"name": "ix_ast_warehouse_code", "cols": ["code"], "unique": True},
            {"name": "ix_ast_warehouse_name", "cols": ["name"]},
            {"name": "ix_ast_warehouse_dept_id", "cols": ["dept_id"]},
            {"name": "ix_ast_warehouse_status", "cols": ["status"]},
        ],
    )
    _create(
        "ast_location",
        [
            sa.Column("warehouse_id", sa.BigInteger(), nullable=False, comment="所属仓库 ast_warehouse.id"),
            sa.Column("code", sa.String(32), nullable=False, comment="库位编码"),
            sa.Column("name", sa.String(128), nullable=True, comment="库位名称"),
            sa.Column("area", sa.String(64), nullable=True, comment="所在区域"),
            sa.Column("capacity", sa.Numeric(12, 2), nullable=True, comment="容量"),
            sa.Column("used", sa.Numeric(12, 2), nullable=True, comment="占用容量"),
            sa.Column("qty_on_hand", sa.Numeric(12, 2), nullable=True, comment="在库数量"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="enabled/disabled"),
        ],
        [
            {"name": "ix_ast_location_warehouse_id", "cols": ["warehouse_id"]},
            {"name": "ix_ast_location_code", "cols": ["code"]},
            {"name": "ix_ast_location_area", "cols": ["area"]},
            {"name": "ix_ast_location_status", "cols": ["status"]},
        ],
        [{"column": "warehouse_id", "target": "ast_warehouse.id", "name": "fk_ast_location_warehouse"}],
    )

    # ---------------- 存货档案 ----------------
    _create(
        "ast_item",
        [
            sa.Column("code", sa.String(32), nullable=False, comment="存货编码"),
            sa.Column("name", sa.String(128), nullable=False, comment="存货名称"),
            sa.Column("spec", sa.String(255), nullable=True, comment="规格型号"),
            sa.Column("unit", sa.String(16), nullable=True, comment="单位"),
            sa.Column("category", sa.String(32), nullable=True, comment="字典 stock_category"),
            sa.Column("unit_price", sa.Numeric(14, 2), nullable=True, comment="参考单价"),
            sa.Column("safety_stock", sa.Numeric(12, 2), nullable=True, comment="安全库存"),
            sa.Column("max_stock", sa.Numeric(12, 2), nullable=True, comment="库存上限"),
            sa.Column("default_warehouse_id", sa.BigInteger(), nullable=True, comment="默认仓库"),
            sa.Column("default_location_id", sa.BigInteger(), nullable=True, comment="默认库位"),
            sa.Column("supplier_id", sa.BigInteger(), nullable=True, comment="供应公司 crm_customer.id"),
            sa.Column("supplier_name", sa.String(128), nullable=True, comment="供应公司名冗余"),
            sa.Column("manufacturer", sa.String(128), nullable=True, comment="生产厂家"),
            sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门 sys_dept.id"),
            sa.Column("dept_name", sa.String(128), nullable=True, comment="部门名冗余"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="enabled/disabled"),
        ],
        [
            {"name": "ix_ast_item_code", "cols": ["code"], "unique": True},
            {"name": "ix_ast_item_name", "cols": ["name"]},
            {"name": "ix_ast_item_category", "cols": ["category"]},
            {"name": "ix_ast_item_default_warehouse_id", "cols": ["default_warehouse_id"]},
            {"name": "ix_ast_item_supplier_id", "cols": ["supplier_id"]},
            {"name": "ix_ast_item_dept_id", "cols": ["dept_id"]},
            {"name": "ix_ast_item_status", "cols": ["status"]},
        ],
    )

    # ---------------- 采购订单 ----------------
    _create(
        "ast_purchase_order",
        [
            sa.Column("order_no", sa.String(32), nullable=False, comment="订单编号 PO..."),
            sa.Column("title", sa.String(255), nullable=False, comment="订单标题"),
            sa.Column("supplier_id", sa.BigInteger(), nullable=False, comment="供应公司 crm_customer.id"),
            sa.Column("supplier_name", sa.String(128), nullable=True, comment="供应公司名冗余"),
            sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门 sys_dept.id"),
            sa.Column("dept_name", sa.String(128), nullable=True, comment="部门名冗余"),
            sa.Column("order_date", sa.Date(), nullable=True, comment="下单日期"),
            sa.Column("arrive_date", sa.Date(), nullable=True, comment="预计到货日期"),
            sa.Column("total_amount", sa.Numeric(14, 2), nullable=True, comment="订单金额"),
            sa.Column("handler_id", sa.BigInteger(), nullable=True, comment="经办人"),
            sa.Column("handler_name", sa.String(64), nullable=True, comment="经办人姓名"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="draft/confirmed/closed"),
        ],
        [
            {"name": "ix_ast_purchase_order_order_no", "cols": ["order_no"], "unique": True},
            {"name": "ix_ast_purchase_order_title", "cols": ["title"]},
            {"name": "ix_ast_purchase_order_supplier_id", "cols": ["supplier_id"]},
            {"name": "ix_ast_purchase_order_dept_id", "cols": ["dept_id"]},
            {"name": "ix_ast_purchase_order_status", "cols": ["status"]},
        ],
    )
    _create(
        "ast_purchase_order_item",
        [
            sa.Column("order_id", sa.BigInteger(), nullable=False, comment="订单 ast_purchase_order.id"),
            sa.Column("item_id", sa.BigInteger(), nullable=True, comment="存货 ast_item.id"),
            sa.Column("item_code", sa.String(32), nullable=True, comment="存货编码"),
            sa.Column("item_name", sa.String(255), nullable=False, comment="存货名称"),
            sa.Column("spec", sa.String(255), nullable=True, comment="规格型号"),
            sa.Column("unit", sa.String(16), nullable=True, comment="单位"),
            sa.Column("quantity", sa.Numeric(12, 2), nullable=True, comment="数量"),
            sa.Column("price", sa.Numeric(14, 2), nullable=True, comment="单价"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_ast_purchase_order_item_order_id", "cols": ["order_id"]},
            {"name": "ix_ast_purchase_order_item_item_id", "cols": ["item_id"]},
        ],
        [
            {
                "column": "order_id",
                "target": "ast_purchase_order.id",
                "name": "fk_ast_purchase_order_item_order",
            }
        ],
    )

    # ---------------- 到货验收 ----------------
    _create(
        "ast_receipt",
        [
            sa.Column("receipt_no", sa.String(32), nullable=False, comment="验收单号 YS..."),
            sa.Column("order_id", sa.BigInteger(), nullable=True, comment="来源采购订单 ast_purchase_order.id"),
            sa.Column("order_no", sa.String(32), nullable=True, comment="采购订单号冗余"),
            sa.Column("warehouse_id", sa.BigInteger(), nullable=True, comment="入库仓库 ast_warehouse.id"),
            sa.Column("warehouse_name", sa.String(128), nullable=True, comment="仓库名冗余"),
            sa.Column("supplier_id", sa.BigInteger(), nullable=True, comment="供应公司 crm_customer.id"),
            sa.Column("supplier_name", sa.String(128), nullable=True, comment="供应公司名冗余"),
            sa.Column("arrive_date", sa.Date(), nullable=True, comment="到货日期"),
            sa.Column("total_qty", sa.Numeric(12, 2), nullable=True, comment="到货数量"),
            sa.Column("qualified_qty", sa.Numeric(12, 2), nullable=True, comment="合格数量"),
            sa.Column("inspector_id", sa.BigInteger(), nullable=True, comment="验收人"),
            sa.Column("inspector_name", sa.String(64), nullable=True, comment="验收人姓名"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="draft/accepted/partial/rejected"),
        ],
        [
            {"name": "ix_ast_receipt_receipt_no", "cols": ["receipt_no"], "unique": True},
            {"name": "ix_ast_receipt_order_id", "cols": ["order_id"]},
            {"name": "ix_ast_receipt_warehouse_id", "cols": ["warehouse_id"]},
            {"name": "ix_ast_receipt_supplier_id", "cols": ["supplier_id"]},
            {"name": "ix_ast_receipt_status", "cols": ["status"]},
        ],
    )
    _create(
        "ast_receipt_item",
        [
            sa.Column("receipt_id", sa.BigInteger(), nullable=False, comment="验收单 ast_receipt.id"),
            sa.Column("item_id", sa.BigInteger(), nullable=True, comment="存货 ast_item.id"),
            sa.Column("item_code", sa.String(32), nullable=True, comment="存货编码"),
            sa.Column("item_name", sa.String(255), nullable=False, comment="存货名称"),
            sa.Column("spec", sa.String(255), nullable=True, comment="规格型号"),
            sa.Column("unit", sa.String(16), nullable=True, comment="单位"),
            sa.Column("quantity", sa.Numeric(12, 2), nullable=True, comment="到货数量"),
            sa.Column("qualified_qty", sa.Numeric(12, 2), nullable=True, comment="合格数量"),
            sa.Column("location_id", sa.BigInteger(), nullable=True, comment="入库库位 ast_location.id"),
            sa.Column("location_code", sa.String(32), nullable=True, comment="库位编码"),
            sa.Column("price", sa.Numeric(14, 2), nullable=True, comment="单价"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_ast_receipt_item_receipt_id", "cols": ["receipt_id"]},
            {"name": "ix_ast_receipt_item_item_id", "cols": ["item_id"]},
            {"name": "ix_ast_receipt_item_location_id", "cols": ["location_id"]},
        ],
        [{"column": "receipt_id", "target": "ast_receipt.id", "name": "fk_ast_receipt_item_receipt"}],
    )

    # ---------------- 库存台账 ----------------
    _create(
        "ast_ledger",
        [
            sa.Column("direction", sa.String(8), nullable=True, comment="in 入库 / out 出库"),
            sa.Column("item_id", sa.BigInteger(), nullable=True, comment="存货 ast_item.id"),
            sa.Column("item_code", sa.String(32), nullable=True, comment="存货编码"),
            sa.Column("item_name", sa.String(128), nullable=True, comment="存货名称"),
            sa.Column("unit", sa.String(16), nullable=True, comment="单位"),
            sa.Column("warehouse_id", sa.BigInteger(), nullable=True, comment="仓库 ast_warehouse.id"),
            sa.Column("warehouse_name", sa.String(128), nullable=True, comment="仓库名冗余"),
            sa.Column("location_id", sa.BigInteger(), nullable=True, comment="库位 ast_location.id"),
            sa.Column("location_code", sa.String(32), nullable=True, comment="库位编码"),
            sa.Column("quantity", sa.Numeric(12, 2), nullable=True, comment="数量（正数）"),
            sa.Column("unit_price", sa.Numeric(14, 2), nullable=True, comment="单价"),
            sa.Column("amount", sa.Numeric(14, 2), nullable=True, comment="金额"),
            sa.Column("reason", sa.String(32), nullable=True, comment="字典 stock_reason"),
            sa.Column("biz_type", sa.String(32), nullable=True, comment="业务来源"),
            sa.Column("biz_id", sa.BigInteger(), nullable=True, comment="来源单据 id"),
            sa.Column("biz_no", sa.String(32), nullable=True, comment="来源单号"),
            sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="操作人"),
            sa.Column("operator_name", sa.String(64), nullable=True, comment="操作人姓名"),
            sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门 sys_dept.id"),
            sa.Column("dept_name", sa.String(128), nullable=True, comment="部门名冗余"),
            sa.Column("happen_at", sa.DateTime(), nullable=True, comment="发生时间"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_ast_ledger_direction", "cols": ["direction"]},
            {"name": "ix_ast_ledger_item_id", "cols": ["item_id"]},
            {"name": "ix_ast_ledger_warehouse_id", "cols": ["warehouse_id"]},
            {"name": "ix_ast_ledger_location_id", "cols": ["location_id"]},
            {"name": "ix_ast_ledger_reason", "cols": ["reason"]},
            {"name": "ix_ast_ledger_biz_type", "cols": ["biz_type"]},
            {"name": "ix_ast_ledger_dept_id", "cols": ["dept_id"]},
            {"name": "ix_ast_ledger_happen_at", "cols": ["happen_at"]},
        ],
    )

    # ---------------- 库存盘点 ----------------
    _create(
        "ast_count",
        [
            sa.Column("count_no", sa.String(32), nullable=False, comment="盘点单号 PD..."),
            sa.Column("warehouse_id", sa.BigInteger(), nullable=True, comment="仓库 ast_warehouse.id"),
            sa.Column("warehouse_name", sa.String(128), nullable=True, comment="仓库名冗余"),
            sa.Column("count_date", sa.Date(), nullable=True, comment="盘点日期"),
            sa.Column("total_qty", sa.Numeric(12, 2), nullable=True, comment="盘点条目数"),
            sa.Column("diff_count", sa.Integer(), nullable=True, comment="差异条目数"),
            sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="盘点人"),
            sa.Column("operator_name", sa.String(64), nullable=True, comment="盘点人姓名"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="draft/counting/finished"),
        ],
        [
            {"name": "ix_ast_count_count_no", "cols": ["count_no"], "unique": True},
            {"name": "ix_ast_count_warehouse_id", "cols": ["warehouse_id"]},
            {"name": "ix_ast_count_status", "cols": ["status"]},
        ],
    )
    _create(
        "ast_count_item",
        [
            sa.Column("count_id", sa.BigInteger(), nullable=False, comment="盘点单 ast_count.id"),
            sa.Column("item_id", sa.BigInteger(), nullable=True, comment="存货 ast_item.id"),
            sa.Column("item_code", sa.String(32), nullable=True, comment="存货编码"),
            sa.Column("item_name", sa.String(128), nullable=False, comment="存货名称"),
            sa.Column("unit", sa.String(16), nullable=True, comment="单位"),
            sa.Column("location_id", sa.BigInteger(), nullable=True, comment="库位 ast_location.id"),
            sa.Column("location_code", sa.String(32), nullable=True, comment="库位编码"),
            sa.Column("book_qty", sa.Numeric(12, 2), nullable=True, comment="账面数量"),
            sa.Column("actual_qty", sa.Numeric(12, 2), nullable=True, comment="实盘数量"),
            sa.Column("diff_qty", sa.Numeric(12, 2), nullable=True, comment="差异数量"),
            sa.Column("price", sa.Numeric(14, 2), nullable=True, comment="单价"),
            sa.Column("diff_amount", sa.Numeric(14, 2), nullable=True, comment="差异金额"),
            sa.Column("reason", sa.String(255), nullable=True, comment="差异原因"),
        ],
        [
            {"name": "ix_ast_count_item_count_id", "cols": ["count_id"]},
            {"name": "ix_ast_count_item_item_id", "cols": ["item_id"]},
        ],
        [{"column": "count_id", "target": "ast_count.id", "name": "fk_ast_count_item_count"}],
    )

    # ---------------- 样车样件 ----------------
    _create(
        "ast_prototype",
        [
            sa.Column("code", sa.String(64), nullable=False, comment="样件编号"),
            sa.Column("name", sa.String(128), nullable=False, comment="样件名称"),
            sa.Column("kind", sa.String(32), nullable=True, comment="字典 prototype_kind"),
            sa.Column("model", sa.String(64), nullable=True, comment="型号"),
            sa.Column("vin", sa.String(64), nullable=True, comment="车架号/识别号"),
            sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门 sys_dept.id"),
            sa.Column("dept_name", sa.String(128), nullable=True, comment="部门名冗余"),
            sa.Column("location_id", sa.BigInteger(), nullable=True, comment="存放库位 ast_location.id"),
            sa.Column("location_name", sa.String(128), nullable=True, comment="存放位置冗余"),
            sa.Column("purchase_date", sa.Date(), nullable=True, comment="购置日期"),
            sa.Column("value", sa.Numeric(14, 2), nullable=True, comment="价值"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="in_stock/loaned/maintenance/scrapped"),
        ],
        [
            {"name": "ix_ast_prototype_code", "cols": ["code"], "unique": True},
            {"name": "ix_ast_prototype_name", "cols": ["name"]},
            {"name": "ix_ast_prototype_kind", "cols": ["kind"]},
            {"name": "ix_ast_prototype_dept_id", "cols": ["dept_id"]},
            {"name": "ix_ast_prototype_status", "cols": ["status"]},
        ],
    )
    _create(
        "ast_prototype_loan",
        [
            sa.Column("loan_no", sa.String(32), nullable=False, comment="借出单号 LJ..."),
            sa.Column("prototype_id", sa.BigInteger(), nullable=False, comment="样件 ast_prototype.id"),
            sa.Column("prototype_code", sa.String(64), nullable=True, comment="样件编号冗余"),
            sa.Column("prototype_name", sa.String(128), nullable=True, comment="样件名称冗余"),
            sa.Column("borrower_id", sa.BigInteger(), nullable=True, comment="借用人 sys_user.id"),
            sa.Column("borrower_name", sa.String(64), nullable=True, comment="借用人姓名"),
            sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门 sys_dept.id"),
            sa.Column("dept_name", sa.String(128), nullable=True, comment="部门名冗余"),
            sa.Column("loan_date", sa.Date(), nullable=True, comment="借出日期"),
            sa.Column("due_date", sa.Date(), nullable=True, comment="应归还日期"),
            sa.Column("return_date", sa.Date(), nullable=True, comment="归还日期"),
            sa.Column("purpose", sa.String(500), nullable=True, comment="用途"),
            sa.Column("handler_id", sa.BigInteger(), nullable=True, comment="经办人"),
            sa.Column("handler_name", sa.String(64), nullable=True, comment="经办人姓名"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="borrowed/returned"),
        ],
        [
            {"name": "ix_ast_prototype_loan_loan_no", "cols": ["loan_no"], "unique": True},
            {"name": "ix_ast_prototype_loan_prototype_id", "cols": ["prototype_id"]},
            {"name": "ix_ast_prototype_loan_borrower_id", "cols": ["borrower_id"]},
            {"name": "ix_ast_prototype_loan_dept_id", "cols": ["dept_id"]},
            {"name": "ix_ast_prototype_loan_status", "cols": ["status"]},
        ],
    )

    # ---------------- 固定资产与折旧 ----------------
    _create(
        "ast_asset",
        [
            sa.Column("asset_no", sa.String(32), nullable=False, comment="资产编号 ZC..."),
            sa.Column("name", sa.String(128), nullable=False, comment="资产名称"),
            sa.Column("category", sa.String(32), nullable=True, comment="字典 asset_category"),
            sa.Column("model", sa.String(64), nullable=True, comment="型号"),
            sa.Column("spec", sa.String(255), nullable=True, comment="规格"),
            sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="使用部门 sys_dept.id"),
            sa.Column("dept_name", sa.String(128), nullable=True, comment="部门名冗余"),
            sa.Column("custodian_id", sa.BigInteger(), nullable=True, comment="使用人 sys_user.id"),
            sa.Column("custodian_name", sa.String(64), nullable=True, comment="使用人姓名"),
            sa.Column("location", sa.String(255), nullable=True, comment="存放地点"),
            sa.Column("purchase_date", sa.Date(), nullable=True, comment="购置日期"),
            sa.Column("original_value", sa.Numeric(14, 2), nullable=True, comment="原值"),
            sa.Column("salvage_rate", sa.Numeric(6, 4), nullable=True, comment="残值率 0-1"),
            sa.Column("useful_life_months", sa.Integer(), nullable=True, comment="预计使用月数"),
            sa.Column("accum_depreciation", sa.Numeric(14, 2), nullable=True, comment="累计折旧"),
            sa.Column("net_value", sa.Numeric(14, 2), nullable=True, comment="净值"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="in_use/idle/repaired/scrapped"),
        ],
        [
            {"name": "ix_ast_asset_asset_no", "cols": ["asset_no"], "unique": True},
            {"name": "ix_ast_asset_name", "cols": ["name"]},
            {"name": "ix_ast_asset_category", "cols": ["category"]},
            {"name": "ix_ast_asset_dept_id", "cols": ["dept_id"]},
            {"name": "ix_ast_asset_status", "cols": ["status"]},
        ],
    )
    _create(
        "ast_depreciation",
        [
            sa.Column("asset_id", sa.BigInteger(), nullable=False, comment="资产 ast_asset.id"),
            sa.Column("asset_no", sa.String(32), nullable=True, comment="资产编号冗余"),
            sa.Column("asset_name", sa.String(128), nullable=True, comment="资产名称冗余"),
            sa.Column("period", sa.String(7), nullable=True, comment="计提期 YYYY-MM"),
            sa.Column("amount", sa.Numeric(14, 2), nullable=True, comment="本期折旧额"),
            sa.Column("accum_amount", sa.Numeric(14, 2), nullable=True, comment="累计折旧额"),
            sa.Column("net_value", sa.Numeric(14, 2), nullable=True, comment="计提后净值"),
            sa.Column("method", sa.String(32), nullable=True, comment="字典 depreciation_method"),
            sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="计提人"),
            sa.Column("operator_name", sa.String(64), nullable=True, comment="计提人姓名"),
            sa.Column("happen_at", sa.DateTime(), nullable=True, comment="计提时间"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_ast_depreciation_asset_id", "cols": ["asset_id"]},
            {"name": "ix_ast_depreciation_period", "cols": ["period"]},
        ],
        [{"column": "asset_id", "target": "ast_asset.id", "name": "fk_ast_depreciation_asset"}],
    )

    # ---------------- 处置与报废 ----------------
    _create(
        "ast_disposal",
        [
            sa.Column("disposal_no", sa.String(32), nullable=False, comment="处置单号 CZ..."),
            sa.Column("asset_id", sa.BigInteger(), nullable=False, comment="资产 ast_asset.id"),
            sa.Column("asset_no", sa.String(32), nullable=True, comment="资产编号冗余"),
            sa.Column("asset_name", sa.String(128), nullable=True, comment="资产名称冗余"),
            sa.Column("disposal_type", sa.String(32), nullable=True, comment="字典 disposal_type"),
            sa.Column("apply_date", sa.Date(), nullable=True, comment="申请日期"),
            sa.Column("original_value", sa.Numeric(14, 2), nullable=True, comment="资产原值"),
            sa.Column("net_value", sa.Numeric(14, 2), nullable=True, comment="处置前净值"),
            sa.Column("disposal_amount", sa.Numeric(14, 2), nullable=True, comment="处置收入"),
            sa.Column("reason", sa.String(1000), nullable=True, comment="处置原因"),
            sa.Column("handler_id", sa.BigInteger(), nullable=True, comment="经办人"),
            sa.Column("handler_name", sa.String(64), nullable=True, comment="经办人姓名"),
            sa.Column("approver_id", sa.BigInteger(), nullable=True, comment="批准人"),
            sa.Column("approver_name", sa.String(64), nullable=True, comment="批准人姓名"),
            sa.Column("approve_at", sa.DateTime(), nullable=True, comment="批准时间"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="draft/approved/done/rejected"),
        ],
        [
            {"name": "ix_ast_disposal_disposal_no", "cols": ["disposal_no"], "unique": True},
            {"name": "ix_ast_disposal_asset_id", "cols": ["asset_id"]},
            {"name": "ix_ast_disposal_disposal_type", "cols": ["disposal_type"]},
            {"name": "ix_ast_disposal_status", "cols": ["status"]},
        ],
    )

    # ---------------- 工具与领用 ----------------
    _create(
        "ast_tool",
        [
            sa.Column("tool_no", sa.String(32), nullable=False, comment="工具编号 GJ..."),
            sa.Column("name", sa.String(128), nullable=False, comment="工具名称"),
            sa.Column("spec", sa.String(255), nullable=True, comment="规格"),
            sa.Column("model", sa.String(64), nullable=True, comment="型号"),
            sa.Column("category", sa.String(32), nullable=True, comment="字典 asset_category"),
            sa.Column("unit", sa.String(16), nullable=True, comment="单位"),
            sa.Column("warehouse_id", sa.BigInteger(), nullable=True, comment="存放仓库 ast_warehouse.id"),
            sa.Column("warehouse_name", sa.String(128), nullable=True, comment="仓库名冗余"),
            sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门 sys_dept.id"),
            sa.Column("dept_name", sa.String(128), nullable=True, comment="部门名冗余"),
            sa.Column("purchase_date", sa.Date(), nullable=True, comment="购置日期"),
            sa.Column("value", sa.Numeric(14, 2), nullable=True, comment="价值"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="in_stock/loaned/maintenance/scrapped"),
        ],
        [
            {"name": "ix_ast_tool_tool_no", "cols": ["tool_no"], "unique": True},
            {"name": "ix_ast_tool_name", "cols": ["name"]},
            {"name": "ix_ast_tool_category", "cols": ["category"]},
            {"name": "ix_ast_tool_warehouse_id", "cols": ["warehouse_id"]},
            {"name": "ix_ast_tool_dept_id", "cols": ["dept_id"]},
            {"name": "ix_ast_tool_status", "cols": ["status"]},
        ],
    )
    _create(
        "ast_tool_loan",
        [
            sa.Column("loan_no", sa.String(32), nullable=False, comment="领用单号 LY..."),
            sa.Column("tool_id", sa.BigInteger(), nullable=False, comment="工具 ast_tool.id"),
            sa.Column("tool_no", sa.String(32), nullable=True, comment="工具编号冗余"),
            sa.Column("tool_name", sa.String(128), nullable=True, comment="工具名称冗余"),
            sa.Column("borrower_id", sa.BigInteger(), nullable=True, comment="领用人 sys_user.id"),
            sa.Column("borrower_name", sa.String(64), nullable=True, comment="领用人姓名"),
            sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门 sys_dept.id"),
            sa.Column("dept_name", sa.String(128), nullable=True, comment="部门名冗余"),
            sa.Column("loan_date", sa.Date(), nullable=True, comment="领用日期"),
            sa.Column("due_date", sa.Date(), nullable=True, comment="应归还日期"),
            sa.Column("return_date", sa.Date(), nullable=True, comment="归还日期"),
            sa.Column("purpose", sa.String(500), nullable=True, comment="用途"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
            sa.Column("status", sa.String(16), nullable=True, comment="borrowed/returned"),
        ],
        [
            {"name": "ix_ast_tool_loan_loan_no", "cols": ["loan_no"], "unique": True},
            {"name": "ix_ast_tool_loan_tool_id", "cols": ["tool_id"]},
            {"name": "ix_ast_tool_loan_borrower_id", "cols": ["borrower_id"]},
            {"name": "ix_ast_tool_loan_dept_id", "cols": ["dept_id"]},
            {"name": "ix_ast_tool_loan_status", "cols": ["status"]},
        ],
    )


def downgrade() -> None:
    for table in (
        "ast_tool_loan",
        "ast_tool",
        "ast_disposal",
        "ast_depreciation",
        "ast_asset",
        "ast_prototype_loan",
        "ast_prototype",
        "ast_count_item",
        "ast_count",
        "ast_ledger",
        "ast_receipt_item",
        "ast_receipt",
        "ast_purchase_order_item",
        "ast_purchase_order",
        "ast_item",
        "ast_location",
        "ast_warehouse",
    ):
        op.drop_table(table)

"""AI-4：ai_knowledge 知识库表（含预置操作手册条目）+ fin_invoice 税率/购买方/销售方列

Revision ID: l1a2b3c4d5e6
Revises: k1a2b3c4d5e6
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "l1a2b3c4d5e6"
down_revision = "k1a2b3c4d5e6"
branch_labels = None
depends_on = None

_BASE_COLS = [
    sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
    sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
    sa.Column("create_by", sa.BigInteger(), nullable=True, comment="创建人"),
    sa.Column("update_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
    sa.Column("update_by", sa.BigInteger(), nullable=True, comment="更新人"),
    sa.Column("version", sa.Integer(), nullable=True, comment="乐观锁版本"),
    sa.Column("deleted", sa.Integer(), nullable=True, comment="逻辑删除 0/1"),
]

# 预置系统操作手册条目（从 docs/ 整理；按标题去重，可重复执行）
_PRESET_ENTRIES = [
    (
        "工时填报操作指引",
        "工时",
        "路径：工作台 → 我的工时 → 填报。选择日期（默认今天），每行选择合同与任务后填写工时（0.5-24 小时）"
        "与工作内容；支持 AI 预填草稿（需人工核对后提交）。草稿可保存，提交后进入审批；"
        "被驳回的工时可修改后重新提交。",
    ),
    (
        "OA 申请操作指引",
        "OA",
        "路径：OA → 发起申请。选择表单类型后填写字段并提交，进入审批流；"
        "同表单支持 AI 预填（参考本人历史已批准申请，需人工核对）。"
        "「我的申请」可查看进度与撤回；审批通过后会回写表单状态。",
    ),
    (
        "合同创建与审批指引",
        "合同",
        "路径：合同 → 新增合同。支持 AI 合同识别（上传 pdf/docx/txt/jpg/png 抽取字段草稿）"
        "与 AI 风险审查（仅提示不拦截）。提交后按审批流逐级审批，通过后发放正式合同编号 HT...。",
    ),
    (
        "开票登记指引",
        "财务",
        "路径：财务 → 发票。结算单经客户确认后发起开票申请，审批通过生成发票记录；"
        "财务在发票列表点「登记」补录发票号/金额/税率/购买方/销售方/日期，"
        "支持上传发票图片或 PDF 进行 AI 识别回填，金额与结算金额不一致时系统会提示核对。",
    ),
    (
        "采购申请操作指引",
        "采购",
        "路径：采购 → 采购申请 → 新增。逐行填写物资名称/规格/单位/数量/预估单价；"
        "每行可用「价格参考」查看同品名历史采购均价/区间/最近价与 AI 点评。"
        "提交后走会签审批，通过后可转采购合同。",
    ),
    (
        "样品管理指引",
        "任务",
        "样品随任务登记：任务编辑页「样品信息」区逐行填写名称/型号/VIN/车型/日期，"
        "支持「拍照识别」上传样品标签照片自动回填（需人工核对）。"
        "任务提交审批时发放样品编号（任务号-01 起）；出入库在样品列表操作并留存流水。",
    ),
    (
        "AI 功能通用说明",
        "AI",
        "全站 AI 能力由管理员在「AI 中心 → AI 设置」统一开关与限配额；"
        "AI 产出均为草稿/建议，须人工确认后才会保存或提交；"
        "AI 未配置或功能停用时，相关入口自动隐藏或降级为手工/搜索模式。",
    ),
]


def upgrade() -> None:
    op.create_table(
        "ai_knowledge",
        sa.Column("title", sa.String(128), nullable=False, comment="条目标题"),
        sa.Column("category", sa.String(64), nullable=False, server_default="", comment="分类"),
        sa.Column("content", sa.Text(), nullable=True, comment="正文"),
        sa.Column("attachment_path", sa.String(255), nullable=False, server_default="", comment="附件相对路径"),
        sa.Column("attachment_name", sa.String(255), nullable=False, server_default="", comment="附件原始文件名"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_knowledge_category", "ai_knowledge", ["category"])

    op.add_column("fin_invoice", sa.Column("tax_rate", sa.Numeric(5, 2), nullable=True, comment="税率 %（登记可选）"))
    op.add_column(
        "fin_invoice",
        sa.Column("buyer_name", sa.String(128), nullable=False, server_default="", comment="购买方名称"),
    )
    op.add_column(
        "fin_invoice",
        sa.Column("seller_name", sa.String(128), nullable=False, server_default="", comment="销售方名称"),
    )

    conn = op.get_bind()
    for title, category, content in _PRESET_ENTRIES:
        exists = conn.execute(
            sa.text("SELECT COUNT(*) FROM ai_knowledge WHERE title = :t"), {"t": title}
        ).scalar()
        if not exists:
            conn.execute(
                sa.text(
                    "INSERT INTO ai_knowledge (title, category, content, attachment_path, attachment_name,"
                    " create_time, update_time, version, deleted)"
                    " VALUES (:t, :c, :b, '', '', now(), now(), 1, 0)"
                ),
                {"t": title, "c": category, "b": content},
            )


def downgrade() -> None:
    op.drop_column("fin_invoice", "seller_name")
    op.drop_column("fin_invoice", "buyer_name")
    op.drop_column("fin_invoice", "tax_rate")
    op.drop_index("ix_ai_knowledge_category", table_name="ai_knowledge")
    op.drop_table("ai_knowledge")

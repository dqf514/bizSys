"""B11 知识与文档中心 + 全站回收站

新增表：
- `sys_recycle_bin`：全站软删登记表（删除人 / 删除时间 / 保留期到期时间 / 恢复快照）；
- `kb_category`：多级可定义的文档分类树（物化路径）；
- `kb_space`：个人空间 / 共享空间；
- `kb_folder`：空间下的文件夹（可单独对外分享）；
- `kb_file`：物理文件登记（软删不删盘，彻底删除时才清）；
- `kb_document`：文档主表；
- `kb_version`：文档版本历史；
- `kb_permission`：授权（内部用户/角色/部门 × 只读/可编辑/可管理）；
- `kb_share_link`：外部分享链接（手机号 + 短信验证码）；
- `kb_link_log`：外部分享访问/上传留痕（只追加）。

Revision ID: ne2b3c4d5e6
Revises: nd2b3c4d5e6
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op

revision = "ne2b3c4d5e6"
down_revision = "nd2b3c4d5e6"
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

_APPEND_ONLY_COLS = [
    sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
    sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="写入时间"),
]


def upgrade() -> None:
    op.create_table(
        "sys_recycle_bin",
        sa.Column("module", sa.String(32), nullable=False, server_default="", comment="业务域"),
        sa.Column("table_name", sa.String(64), nullable=False, server_default="", comment="原表名"),
        sa.Column("resource", sa.String(64), nullable=False, server_default="", comment="模型名"),
        sa.Column("resource_id", sa.BigInteger(), nullable=False, server_default="0", comment="原记录主键"),
        sa.Column("title", sa.String(255), nullable=False, server_default="", comment="冗余标题"),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True, comment="删除人用户 id"),
        sa.Column("deleted_by_name", sa.String(64), nullable=False, server_default="", comment="删除人姓名"),
        sa.Column("deleted_at", sa.DateTime(), nullable=False, comment="删除时间"),
        sa.Column("purge_after", sa.DateTime(), nullable=True, comment="可彻底删除时间"),
        sa.Column("status", sa.String(16), nullable=False, server_default="recycled", comment="recycled/restored/purged"),
        sa.Column("purged_at", sa.DateTime(), nullable=True, comment="彻底删除时间"),
        sa.Column("purged_by", sa.BigInteger(), nullable=True, comment="彻底删除人"),
        # MySQL 不允许 TEXT 列带 DEFAULT，值由 ORM 侧提供
        sa.Column("restore_fields", sa.Text(), nullable=False, comment="恢复时回填的字段（JSON）"),
        sa.Column("meta", sa.Text(), nullable=False, comment="附加信息（JSON）"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sys_recycle_bin_status_deleted", "sys_recycle_bin", ["status", "deleted_at"])
    op.create_index("ix_sys_recycle_bin_module", "sys_recycle_bin", ["module"])
    op.create_index("ix_sys_recycle_bin_resource_id", "sys_recycle_bin", ["resource_id"])
    op.create_index("ix_sys_recycle_bin_deleted_at", "sys_recycle_bin", ["deleted_at"])

    op.create_table(
        "kb_category",
        sa.Column("name", sa.String(128), nullable=False, comment="分类名称"),
        sa.Column("code", sa.String(64), nullable=False, server_default="", comment="分类编码"),
        sa.Column("parent_id", sa.BigInteger(), nullable=True, comment="上级分类 id"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1", comment="层级（1 起）"),
        sa.Column("path", sa.String(255), nullable=False, server_default="", comment="物化路径"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0", comment="排序"),
        sa.Column("description", sa.String(500), nullable=False, server_default="", comment="描述"),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled", comment="状态"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_category_parent", "kb_category", ["parent_id"])
    op.create_index("ix_kb_category_path", "kb_category", ["path"])
    op.create_index("ix_kb_category_name", "kb_category", ["name"])
    op.create_index("ix_kb_category_code", "kb_category", ["code"])

    op.create_table(
        "kb_space",
        sa.Column("name", sa.String(128), nullable=False, comment="空间名称"),
        sa.Column("type", sa.String(16), nullable=False, server_default="personal", comment="personal/shared"),
        sa.Column("owner_id", sa.BigInteger(), nullable=True, comment="空间拥有者"),
        sa.Column("owner_name", sa.String(64), nullable=False, server_default="", comment="拥有者姓名"),
        sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门"),
        sa.Column("description", sa.String(500), nullable=False, server_default="", comment="描述"),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled", comment="状态"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_space_owner", "kb_space", ["owner_id"])
    op.create_index("ix_kb_space_name", "kb_space", ["name"])
    op.create_index("ix_kb_space_type", "kb_space", ["type"])

    op.create_table(
        "kb_folder",
        sa.Column("space_id", sa.BigInteger(), nullable=False, comment="所属空间"),
        sa.Column("category_id", sa.BigInteger(), nullable=True, comment="所属分类"),
        sa.Column("parent_id", sa.BigInteger(), nullable=True, comment="上级文件夹"),
        sa.Column("name", sa.String(128), nullable=False, comment="文件夹名称"),
        sa.Column("path", sa.String(255), nullable=False, server_default="", comment="物化路径"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1", comment="层级"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0", comment="排序"),
        sa.Column("description", sa.String(500), nullable=False, server_default="", comment="描述"),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled", comment="状态"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_folder_space", "kb_folder", ["space_id"])
    op.create_index("ix_kb_folder_parent", "kb_folder", ["parent_id"])
    op.create_index("ix_kb_folder_name", "kb_folder", ["name"])

    op.create_table(
        "kb_file",
        sa.Column("file_name", sa.String(255), nullable=False, server_default="", comment="原始文件名"),
        sa.Column("ext", sa.String(32), nullable=False, server_default="", comment="扩展名"),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0", comment="字节数"),
        sa.Column("path", sa.String(255), nullable=False, server_default="", comment="相对存储路径"),
        sa.Column("content_type", sa.String(128), nullable=False, server_default="", comment="MIME"),
        sa.Column("sha256", sa.String(64), nullable=False, server_default="", comment="内容哈希"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_file_ext", "kb_file", ["ext"])
    op.create_index("ix_kb_file_sha256", "kb_file", ["sha256"])

    op.create_table(
        "kb_document",
        sa.Column("code", sa.String(64), nullable=False, server_default="", comment="文档编号"),
        sa.Column("title", sa.String(255), nullable=False, comment="标题"),
        sa.Column("space_id", sa.BigInteger(), nullable=False, comment="所属空间"),
        sa.Column("folder_id", sa.BigInteger(), nullable=True, comment="所属文件夹"),
        sa.Column("category_id", sa.BigInteger(), nullable=True, comment="所属分类"),
        sa.Column("owner_id", sa.BigInteger(), nullable=True, comment="作者"),
        sa.Column("owner_name", sa.String(64), nullable=False, server_default="", comment="作者姓名"),
        sa.Column("editor_ids", sa.Text(), nullable=False, comment="编辑者 user id 逗号分隔"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0", comment="当前版本号"),
        sa.Column("file_id", sa.BigInteger(), nullable=True, comment="当前版本文件"),
        sa.Column("ext", sa.String(32), nullable=False, server_default="", comment="扩展名"),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0", comment="字节数"),
        sa.Column("tags", sa.String(255), nullable=False, server_default="", comment="标签"),
        sa.Column("doc_type", sa.String(32), nullable=False, server_default="document", comment="文档类型"),
        sa.Column("status", sa.String(16), nullable=False, server_default="published", comment="draft/published/archived"),
        sa.Column("summary", sa.String(1000), nullable=False, server_default="", comment="摘要"),
        sa.Column("source", sa.String(16), nullable=False, server_default="upload", comment="upload/link"),
        sa.Column("published_at", sa.DateTime(), nullable=True, comment="发布时间"),
        sa.Column("expired_at", sa.DateTime(), nullable=True, comment="失效日期"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_document_space", "kb_document", ["space_id"])
    op.create_index("ix_kb_document_folder", "kb_document", ["folder_id"])
    op.create_index("ix_kb_document_category", "kb_document", ["category_id"])
    op.create_index("ix_kb_document_owner", "kb_document", ["owner_id"])
    op.create_index("ix_kb_document_file_id", "kb_document", ["file_id"])
    op.create_index("ix_kb_document_title", "kb_document", ["title"])
    op.create_index("ix_kb_document_code", "kb_document", ["code"])
    op.create_index("ix_kb_document_doc_type", "kb_document", ["doc_type"])
    op.create_index("ix_kb_document_status", "kb_document", ["status"])

    op.create_table(
        "kb_version",
        sa.Column("document_id", sa.BigInteger(), nullable=False, comment="文档 id"),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("file_id", sa.BigInteger(), nullable=True, comment="文件 id"),
        sa.Column("file_name", sa.String(255), nullable=False, server_default="", comment="文件名"),
        sa.Column("ext", sa.String(32), nullable=False, server_default="", comment="扩展名"),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0", comment="字节数"),
        sa.Column("comment", sa.String(500), nullable=False, server_default="", comment="版本说明"),
        sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="操作人"),
        sa.Column("operator_name", sa.String(64), nullable=False, server_default="", comment="操作人姓名"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_version_document", "kb_version", ["document_id"])
    op.create_index("ix_kb_version_file_id", "kb_version", ["file_id"])

    op.create_table(
        "kb_permission",
        sa.Column("resource_type", sa.String(16), nullable=False, comment="document/folder/space"),
        sa.Column("resource_id", sa.BigInteger(), nullable=False, comment="资源 id"),
        sa.Column("subject_type", sa.String(16), nullable=False, comment="user/role/dept/link"),
        sa.Column("subject_id", sa.BigInteger(), nullable=True, comment="主体 id"),
        sa.Column("subject_name", sa.String(64), nullable=False, server_default="", comment="主体名称"),
        sa.Column("perm", sa.String(16), nullable=False, server_default="read", comment="read/edit/manage"),
        sa.Column("is_external", sa.Integer(), nullable=False, server_default="0", comment="1=外部人员"),
        sa.Column("expire_at", sa.DateTime(), nullable=True, comment="授权到期时间"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_permission_resource", "kb_permission", ["resource_type", "resource_id"])
    op.create_index("ix_kb_permission_subject", "kb_permission", ["subject_type", "subject_id"])
    op.create_index("ix_kb_permission_resource_id", "kb_permission", ["resource_id"])
    op.create_index("ix_kb_permission_subject_id", "kb_permission", ["subject_id"])
    op.create_index("ix_kb_permission_perm", "kb_permission", ["perm"])

    op.create_table(
        "kb_share_link",
        sa.Column("token", sa.String(64), nullable=False, comment="链接令牌"),
        sa.Column("title", sa.String(255), nullable=False, server_default="", comment="标题"),
        sa.Column("resource_type", sa.String(16), nullable=False, server_default="folder", comment="folder/document"),
        sa.Column("resource_id", sa.BigInteger(), nullable=False, comment="资源 id"),
        sa.Column("perm", sa.String(16), nullable=False, server_default="read", comment="read/upload/edit"),
        sa.Column("require_phone", sa.Integer(), nullable=False, server_default="1", comment="1=需手机号验证码"),
        sa.Column("expire_at", sa.DateTime(), nullable=True, comment="过期时间"),
        sa.Column("max_upload", sa.Integer(), nullable=False, server_default="0", comment="0=不限"),
        sa.Column("upload_count", sa.Integer(), nullable=False, server_default="0", comment="已上传次数"),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0", comment="已下载次数"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active", comment="active/closed/expired"),
        sa.Column("creator_id", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("creator_name", sa.String(64), nullable=False, server_default="", comment="创建人姓名"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_share_link_token", "kb_share_link", ["token"])
    op.create_index("ix_kb_share_link_resource_id", "kb_share_link", ["resource_id"])
    op.create_index("ix_kb_share_link_resource_type", "kb_share_link", ["resource_type"])
    op.create_index("ix_kb_share_link_status", "kb_share_link", ["status"])
    op.create_index("ix_kb_share_link_expire_at", "kb_share_link", ["expire_at"])

    op.create_table(
        "kb_link_log",
        sa.Column("link_id", sa.BigInteger(), nullable=False, comment="分享链接 id"),
        sa.Column("action", sa.String(16), nullable=False, server_default="", comment="view/download/upload/code"),
        sa.Column("phone", sa.String(32), nullable=False, server_default="", comment="访问者手机号（掩码）"),
        sa.Column("file_name", sa.String(255), nullable=False, server_default="", comment="文件名"),
        sa.Column("ip", sa.String(64), nullable=False, server_default="", comment="客户端 IP"),
        *_APPEND_ONLY_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_link_log_link", "kb_link_log", ["link_id"])


def downgrade() -> None:
    op.drop_table("kb_link_log")
    op.drop_table("kb_share_link")
    op.drop_table("kb_permission")
    op.drop_table("kb_version")
    op.drop_table("kb_document")
    op.drop_table("kb_file")
    op.drop_table("kb_folder")
    op.drop_table("kb_space")
    op.drop_table("kb_category")
    op.drop_table("sys_recycle_bin")

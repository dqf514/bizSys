"""知识库与文档中心模块表：`kb_*` 前缀。

覆盖「标准与方法库 / 体系文件 / 公司制度 / 设备操作说明 / 上墙看板 / 标志标识标牌」等
企业文档共享场景：

- `kb_category` —— **多级可定义**的文档分类树（物化路径，树形浏览）
- `kb_space` —— 个人空间 / 共享空间
- `kb_folder` —— 空间下的文件夹（可单独共享给外部）
- `kb_document` —— 文档主表（作者 / 编辑者 / 当前版本）
- `kb_version` —— 版本历史（可回滚）
- `kb_file` —— 物理文件登记（软删时**不**立即删盘，由回收站到期清理）
- `kb_permission` —— 授权（内部用户/角色/部门 × 只读/可编辑/可管理；内部 or 外部）
- `kb_share_link` —— 外部分享链接（手机号 + 短信验证码后访问/上传）
- `kb_link_log` —— 外部链接访问/上传留痕（只追加）
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import AppendOnlyModel, BaseModel

# 权限档位：数值越大权限越高
PERM_READ = 1
PERM_EDIT = 2
PERM_MANAGE = 3
PERM_LEVELS = {"read": PERM_READ, "edit": PERM_EDIT, "manage": PERM_MANAGE}
PERM_NAMES = {v: k for k, v in PERM_LEVELS.items()}


class Category(BaseModel):
    """文档分类（多级树，管理员可自定义层级）。

    `path` 为物化路径（形如 `/1/3/7/`），便于按子树批量查询（`path.like('/1/3/%')`）。
    """

    __tablename__ = "kb_category"
    __table_args__ = (
        Index("ix_kb_category_parent", "parent_id"),
        Index("ix_kb_category_path", "path"),
    )

    name: Mapped[str] = mapped_column(String(128), index=True, comment="分类名称")
    code: Mapped[str] = mapped_column(String(64), default="", index=True, comment="分类编码")
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="上级分类 id")
    level: Mapped[int] = mapped_column(Integer, default=1, comment="层级（1 起）")
    path: Mapped[str] = mapped_column(String(255), default="", comment="物化路径 /1/3/")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True)


class Space(BaseModel):
    """空间：personal 个人空间 / shared 共享空间。"""

    __tablename__ = "kb_space"
    __table_args__ = (Index("ix_kb_space_owner", "owner_id"),)

    name: Mapped[str] = mapped_column(String(128), index=True, comment="空间名称")
    type: Mapped[str] = mapped_column(String(16), default="personal", index=True, comment="personal/shared")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="空间拥有者")
    owner_name: Mapped[str] = mapped_column(String(64), default="")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="归属部门")
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True)
    pinned: Mapped[int] = mapped_column(Integer, default=0, index=True, comment="是否置顶（微盘式左栏「置顶」）")


class Folder(BaseModel):
    """文件夹（归属一个空间，可挂在分类下）。"""

    __tablename__ = "kb_folder"
    __table_args__ = (
        Index("ix_kb_folder_space", "space_id"),
        Index("ix_kb_folder_parent", "parent_id"),
    )

    space_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属空间")
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="所属分类")
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="上级文件夹")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="文件夹名称")
    path: Mapped[str] = mapped_column(String(255), default="", comment="物化路径")
    level: Mapped[int] = mapped_column(Integer, default=1)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True)


class File(BaseModel):
    """物理文件登记（正文本体）。软删文档时**不删盘**，由回收站到期清理。"""

    __tablename__ = "kb_file"

    file_name: Mapped[str] = mapped_column(String(255), default="", comment="原始文件名")
    ext: Mapped[str] = mapped_column(String(32), default="", index=True, comment="扩展名（小写）")
    size: Mapped[int] = mapped_column(BigInteger, default=0, comment="字节数")
    path: Mapped[str] = mapped_column(String(255), default="", comment="相对存储路径")
    content_type: Mapped[str] = mapped_column(String(128), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True, comment="内容哈希（去重/校验）")


class Document(BaseModel):
    """文档主表。"""

    __tablename__ = "kb_document"
    __table_args__ = (
        Index("ix_kb_document_space", "space_id"),
        Index("ix_kb_document_folder", "folder_id"),
        Index("ix_kb_document_category", "category_id"),
        Index("ix_kb_document_owner", "owner_id"),
    )

    code: Mapped[str] = mapped_column(String(64), default="", index=True, comment="文档编号")
    title: Mapped[str] = mapped_column(String(255), index=True, comment="标题")
    space_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属空间")
    folder_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="所属文件夹")
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="所属分类")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="作者")
    owner_name: Mapped[str] = mapped_column(String(64), default="")
    editor_ids: Mapped[str] = mapped_column(Text, default="", comment="编辑者 user id 逗号分隔")
    current_version: Mapped[int] = mapped_column(Integer, default=0, comment="当前版本号")
    file_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="当前版本文件")
    ext: Mapped[str] = mapped_column(String(32), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    tags: Mapped[str] = mapped_column(String(255), default="")
    doc_type: Mapped[str] = mapped_column(
        String(32), default="document", index=True, comment="document/system/board/sign"
    )
    status: Mapped[str] = mapped_column(String(16), default="published", index=True, comment="draft/published/archived")
    summary: Mapped[str] = mapped_column(String(1000), default="")
    source: Mapped[str] = mapped_column(String(16), default="upload", comment="upload/link")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="制度失效日期")


class Version(BaseModel):
    """文档版本历史（可回滚到任一历史版本）。"""

    __tablename__ = "kb_version"
    __table_args__ = (Index("ix_kb_version_document", "document_id"),)

    document_id: Mapped[int] = mapped_column(BigInteger, index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    file_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    ext: Mapped[str] = mapped_column(String(32), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    comment: Mapped[str] = mapped_column(String(500), default="", comment="版本说明")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")


class Permission(BaseModel):
    """文档 / 文件夹 / 空间的授权条目。"""

    __tablename__ = "kb_permission"
    __table_args__ = (
        Index("ix_kb_permission_resource", "resource_type", "resource_id"),
        Index("ix_kb_permission_subject", "subject_type", "subject_id"),
    )

    resource_type: Mapped[str] = mapped_column(String(16), index=True, comment="document/folder/space")
    resource_id: Mapped[int] = mapped_column(BigInteger, index=True)
    subject_type: Mapped[str] = mapped_column(String(16), index=True, comment="user/role/dept/link")
    subject_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="主体 id（link 时为 0）"
    )
    subject_name: Mapped[str] = mapped_column(String(64), default="")
    perm: Mapped[str] = mapped_column(String(16), default="read", index=True, comment="read/edit/manage")
    is_external: Mapped[int] = mapped_column(Integer, default=0, comment="1=外部人员")
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ShareLink(BaseModel):
    """外部分享链接（手机号 + 短信验证码后访问 / 上传）。"""

    __tablename__ = "kb_share_link"

    token: Mapped[str] = mapped_column(String(64), index=True, comment="链接令牌")
    title: Mapped[str] = mapped_column(String(255), default="")
    resource_type: Mapped[str] = mapped_column(String(16), default="folder", index=True, comment="folder/document")
    resource_id: Mapped[int] = mapped_column(BigInteger, index=True)
    perm: Mapped[str] = mapped_column(String(16), default="read", comment="read/upload/edit")
    require_phone: Mapped[int] = mapped_column(Integer, default=1, comment="1=需手机号验证码")
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    max_upload: Mapped[int] = mapped_column(Integer, default=0, comment="0=不限")
    upload_count: Mapped[int] = mapped_column(Integer, default=0)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True, comment="active/closed/expired")
    creator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    creator_name: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")


class LinkLog(AppendOnlyModel):
    """外部链接访问 / 上传留痕（只追加，合规要求不可删改）。"""

    __tablename__ = "kb_link_log"
    __table_args__ = (Index("ix_kb_link_log_link", "link_id"),)

    link_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(16), default="", comment="view/download/upload/code")
    phone: Mapped[str] = mapped_column(String(32), default="", comment="访问者手机号（掩码后存）")
    file_name: Mapped[str] = mapped_column(String(255), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")

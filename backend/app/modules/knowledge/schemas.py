"""知识库与文档中心入参（camelCase 别名）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.schemas import CamelModel


class CategoryIn(CamelModel):
    """文档分类（多级树）。"""

    name: str = Field(min_length=1, max_length=128)
    code: str = Field(default="", max_length=64)
    parent_id: int | None = None
    sort: int = 0
    description: str = Field(default="", max_length=500)
    status: str = "enabled"


class SpaceIn(CamelModel):
    """空间（个人 / 共享）。"""

    name: str = Field(min_length=1, max_length=128)
    type: str = "personal"
    owner_id: int | None = None
    dept_id: int | None = None
    description: str = Field(default="", max_length=500)
    status: str = "enabled"
    pinned: int = 0


class FolderIn(CamelModel):
    """文件夹。"""

    name: str = Field(min_length=1, max_length=128)
    space_id: int = Field(ge=1)
    category_id: int | None = None
    parent_id: int | None = None
    description: str = Field(default="", max_length=500)
    status: str = "enabled"


class DocumentIn(CamelModel):
    """文档元信息。"""

    title: str = Field(min_length=1, max_length=255)
    space_id: int = Field(ge=1)
    folder_id: int | None = None
    category_id: int | None = None
    doc_type: str = "document"
    tags: str = Field(default="", max_length=255)
    summary: str = Field(default="", max_length=1000)
    status: str = "published"
    expired_at: datetime | None = None


class PermissionIn(CamelModel):
    """授权条目。"""

    subject_type: str = Field(default="user")
    subject_id: int | None = None
    subject_name: str = Field(default="", max_length=64)
    perm: str = Field(default="read")
    is_external: int = 0
    expire_at: datetime | None = None


class ShareLinkIn(CamelModel):
    """外部分享链接。"""

    resource_type: str = Field(default="folder")
    resource_id: int = Field(ge=1)
    perm: str = Field(default="read")
    require_phone: int = 1
    expire_days: int = Field(default=7, ge=0, le=365)
    max_upload: int = Field(default=0, ge=0)
    remark: str = Field(default="", max_length=500)


class KnowledgeSettingIn(CamelModel):
    """知识中心设置（格式 / 大小上限）。"""

    allowed_ext: list[str] = Field(default_factory=list)
    max_mb: int = Field(default=100, ge=1, le=2048)
    preview_max_chars: int = Field(default=20000, ge=1000, le=200000)

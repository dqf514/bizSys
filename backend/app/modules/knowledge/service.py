"""知识库与文档中心业务逻辑。

要点：
- **分类是多级可定义树**（`kb_category.parent_id + path`），树形浏览用 `path.like` 取子树。
- **空间**分个人 / 共享；共享空间对有文档浏览权限的人默认只读，个人空间只有本人与被授权者可见。
- **授权**（`kb_permission`）三档：只读 / 可编辑 / 可管理；主体支持用户 / 角色 / 部门；
  `is_external=1` 表示外部人员（外部人员只能通过分享链接进入，不进内部权限计算）。
- **版本控制**：每次上传新版本写 `kb_version`，可回滚（回滚 = 以历史版本内容生成新版本，保留历史）。
- **在线浏览**：服务端抽取文本（pdf/docx/xlsx/txt/md/csv），图片直接回源。
- **外部分享**：链接 + 手机号 + 短信验证码（Redis），验证通过后拿到短时令牌才能浏览/上传。
"""

from __future__ import annotations

import csv
import hashlib
import io
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.config import settings
from app.core.exceptions import BizException
from app.modules.knowledge.models import (
    PERM_EDIT,
    PERM_LEVELS,
    PERM_MANAGE,
    PERM_NAMES,
    PERM_READ,
    Category,
    Document,
    File,
    Folder,
    LinkLog,
    Permission,
    ShareLink,
    Space,
    Version,
)

# ---------------- 配置 ----------------

CFG_ALLOWED_EXT = "knowledge.upload.allowed_ext"
CFG_MAX_MB = "knowledge.upload.max_mb"
CFG_PREVIEW_CHARS = "knowledge.preview.max_chars"

DEFAULT_ALLOWED_EXT = [
    "pdf", "doc", "docx", "wps", "xls", "xlsx", "et", "ppt", "pptx", "dps",
    "txt", "md", "csv", "rtf",
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "zip", "rar", "7z",
]

# 可在线预览（服务端抽文本 / 图片直出）
PREVIEW_TEXT_EXT = {"txt", "md", "csv", "log", "json"}
PREVIEW_IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "bmp", "webp"}

DOC_TYPES = {"document", "system", "board", "sign", "manual"}
PERM_VALUES = {"read", "edit", "manage"}


def allowed_ext(db: Session) -> list[str]:
    from app.modules.settings.service import get_value

    raw = get_value(db, CFG_ALLOWED_EXT, "").strip()
    if not raw:
        return list(DEFAULT_ALLOWED_EXT)
    items = [e.strip().lower().lstrip(".") for e in raw.split(",") if e.strip()]
    return items or list(DEFAULT_ALLOWED_EXT)


def max_mb(db: Session) -> int:
    from app.modules.settings.service import get_value

    try:
        val = int(get_value(db, CFG_MAX_MB, "") or 0)
    except (TypeError, ValueError):
        val = 0
    return val if val > 0 else settings.upload_max_mb


def preview_max_chars(db: Session) -> int:
    from app.modules.settings.service import get_value

    try:
        val = int(get_value(db, CFG_PREVIEW_CHARS, "") or 0)
    except (TypeError, ValueError):
        val = 0
    return val if val > 0 else 20000


# ---------------- 通用 ----------------


def _now() -> datetime:
    return datetime.now()


def _mask_phone(phone: str) -> str:
    p = (phone or "").strip()
    if len(p) < 7:
        return p
    return p[:3] + "*" * (len(p) - 7) + p[-4:]


def _err(code: int, msg: str = "") -> BizException:
    return BizException(code, msg)


def out_space(row: Space) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "ownerId": row.owner_id,
        "ownerName": row.owner_name,
        "deptId": row.dept_id,
        "description": row.description,
        "status": row.status,
        "pinned": int(row.pinned or 0),
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
    }


def out_folder(row: Folder) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "spaceId": row.space_id,
        "categoryId": row.category_id,
        "parentId": row.parent_id,
        "path": row.path,
        "level": row.level,
        "description": row.description,
        "status": row.status,
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
    }


def out_permission(row: Permission) -> dict:
    return {
        "id": row.id,
        "resourceType": row.resource_type,
        "resourceId": row.resource_id,
        "subjectType": row.subject_type,
        "subjectId": row.subject_id,
        "subjectName": row.subject_name,
        "perm": row.perm,
        "permLevel": PERM_LEVELS.get(row.perm, PERM_READ),
        "isExternal": row.is_external,
        "expireAt": row.expire_at.strftime("%Y-%m-%d %H:%M:%S") if row.expire_at else "",
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
    }


def out_version(row: Version) -> dict:
    return {
        "id": row.id,
        "documentId": row.document_id,
        "versionNo": row.version_no,
        "fileId": row.file_id,
        "fileName": row.file_name,
        "ext": row.ext,
        "size": row.size,
        "comment": row.comment,
        "operatorId": row.operator_id,
        "operatorName": row.operator_name,
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
    }


def out_document(row: Document, perm: int = PERM_READ, extra: dict | None = None) -> dict:
    data = {
        "id": row.id,
        "code": row.code,
        "title": row.title,
        "spaceId": row.space_id,
        "folderId": row.folder_id,
        "categoryId": row.category_id,
        "ownerId": row.owner_id,
        "ownerName": row.owner_name,
        "editorIds": [int(x) for x in (row.editor_ids or "").split(",") if x.strip()],
        "currentVersion": row.current_version,
        "fileId": row.file_id,
        "ext": row.ext,
        "size": row.size,
        "tags": row.tags,
        "docType": row.doc_type,
        "status": row.status,
        "summary": row.summary,
        "source": row.source,
        "publishedAt": row.published_at.strftime("%Y-%m-%d %H:%M:%S") if row.published_at else "",
        "expiredAt": row.expired_at.strftime("%Y-%m-%d") if row.expired_at else "",
        "perm": PERM_NAMES.get(perm, "read"),
        "permLevel": perm,
        "createBy": row.create_by,
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
        "updateTime": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else "",
    }
    if extra:
        data.update(extra)
    return data


# ---------------- 分类（多级树） ----------------


def category_tree(db: Session) -> list[dict]:
    stmt = select(Category).where(Category.deleted == 0).order_by(Category.level, Category.sort, Category.id)
    rows = db.scalars(stmt).all()
    nodes: dict[int, dict] = {}
    for r in rows:
        nodes[r.id] = {
            "id": r.id,
            "name": r.name,
            "code": r.code,
            "parentId": r.parent_id,
            "level": r.level,
            "path": r.path,
            "sort": r.sort,
            "description": r.description,
            "status": r.status,
            "docCount": 0,
            "children": [],
        }
    roots: list[dict] = []
    for r in rows:
        node = nodes[r.id]
        parent = nodes.get(r.parent_id) if r.parent_id else None
        if parent is not None:
            parent["children"].append(node)
        else:
            roots.append(node)
    # 每个分类下的文档数（含子树）
    doc_rows = db.execute(
        select(Document.category_id, func.count())
        .where(Document.deleted == 0, Document.category_id.isnot(None))
        .group_by(Document.category_id)
    ).all()
    counts = {int(cid): int(c) for cid, c in doc_rows}

    def accumulate(node: dict) -> int:
        total = counts.get(node["id"], 0)
        for child in node["children"]:
            total += accumulate(child)
        node["docCount"] = total
        return total

    for node in roots:
        accumulate(node)
    return roots


def category_path(db: Session, category_id: int | None) -> str:
    """返回分类的物化路径（用于子树查询）。"""
    if not category_id:
        return ""
    cat = db.get(Category, category_id)
    return cat.path if cat else ""


def category_descendants(db: Session, category_id: int) -> list[int]:
    """某分类的全部后代 id（含自身）。"""
    cat = db.get(Category, category_id)
    if not cat:
        return []
    prefix = f"{cat.path}{category_id}/"
    rows = db.scalars(select(Category.id).where(Category.path.like(f"{prefix}%"))).all()
    return [category_id, *list(rows)]


def create_category(db: Session, body: Any, user: Any) -> Category:
    parent: Category | None = None
    if body.parent_id:
        parent = db.get(Category, body.parent_id)
        if not parent or parent.deleted:
            raise _err(R.KNOWLEDGE_CATEGORY_INVALID, "上级分类不存在")
    level = (parent.level + 1) if parent else 1
    path = f"{parent.path}{parent.id}/" if parent else "/"
    row = Category(
        name=body.name,
        code=body.code or "",
        parent_id=body.parent_id or None,
        level=level,
        path=path,
        sort=body.sort or 0,
        description=body.description,
        status=body.status,
        create_by=getattr(user, "id", None),
    )
    db.add(row)
    db.flush()
    return row


def update_category(db: Session, row: Category, body: Any) -> Category:
    if body.parent_id and body.parent_id != row.id:
        if body.parent_id in category_descendants(db, row.id):
            raise _err(R.KNOWLEDGE_CATEGORY_INVALID, "不能把分类移动到自己的子分类下")
        parent = db.get(Category, body.parent_id)
        if not parent or parent.deleted:
            raise _err(R.KNOWLEDGE_CATEGORY_INVALID, "上级分类不存在")
    row.name = body.name or row.name
    if body.code:
        row.code = body.code
    row.sort = body.sort if body.sort is not None else row.sort
    row.description = body.description if body.description is not None else row.description
    row.status = body.status or row.status
    row.parent_id = body.parent_id or None
    _rebuild_category_path(db, row)
    return row


def _rebuild_category_path(db: Session, row: Category) -> None:
    parent = db.get(Category, row.parent_id) if row.parent_id else None
    if parent:
        row.level = parent.level + 1
        row.path = f"{parent.path}{parent.id}/"
    else:
        row.level = 1
        row.path = "/"
    db.flush()
    for child in db.scalars(select(Category).where(Category.parent_id == row.id)).all():
        _rebuild_category_path(db, child)


def delete_category(db: Session, row: Category) -> None:
    if db.scalar(select(func.count()).select_from(Category).where(Category.parent_id == row.id, Category.deleted == 0)):
        raise _err(R.KNOWLEDGE_CATEGORY_INVALID, "该分类下还有子分类，不能删除")
    used = db.scalar(
        select(func.count()).select_from(Document).where(Document.category_id == row.id, Document.deleted == 0)
    )
    if used:
        raise _err(R.KNOWLEDGE_CATEGORY_INVALID, "该分类下还有文档，不能删除")


# ---------------- 空间 / 文件夹 ----------------


def space_visible(db: Session, user: Any) -> list[Space]:
    """可见空间：共享空间 + 自己拥有的空间（置顶优先）。"""
    stmt = select(Space).where(Space.deleted == 0, Space.status == "enabled")
    stmt = stmt.where(or_(Space.type == "shared", Space.owner_id == getattr(user, "id", None)))
    return list(db.scalars(stmt.order_by(Space.pinned.desc(), Space.type, Space.id)).all())


def create_space(db: Session, body: Any, user: Any) -> Space:
    owner_id = body.owner_id or getattr(user, "id", None)
    owner = db.get(type(user), owner_id) if owner_id else None
    row = Space(
        name=body.name,
        type=body.type if body.type in ("personal", "shared") else "personal",
        owner_id=owner_id,
        owner_name=getattr(owner, "name", "") or "",
        dept_id=body.dept_id,
        description=body.description,
        status=body.status,
        pinned=1 if getattr(body, "pinned", 0) else 0,
        create_by=getattr(user, "id", None),
    )
    db.add(row)
    db.flush()
    return row


def delete_space(db: Session, row: Space) -> None:
    if db.scalar(select(func.count()).select_from(Document).where(Document.space_id == row.id, Document.deleted == 0)):
        raise _err(R.KNOWLEDGE_INVALID_STATE, "空间内还有文档，不能删除")


def folder_children(db: Session, space_id: int | None, parent_id: int | None) -> list[Folder]:
    stmt = select(Folder).where(Folder.deleted == 0)
    if space_id:
        stmt = stmt.where(Folder.space_id == space_id)
    if parent_id:
        stmt = stmt.where(Folder.parent_id == parent_id)
    else:
        stmt = stmt.where(Folder.parent_id.is_(None))
    return list(db.scalars(stmt.order_by(Folder.sort, Folder.id)).all())


def folder_tree(db: Session, space_id: int) -> list[dict]:
    rows = list(db.scalars(select(Folder).where(Folder.deleted == 0, Folder.space_id == space_id)).all())
    nodes = {r.id: {**out_folder(r), "children": []} for r in rows}
    roots: list[dict] = []
    for r in rows:
        node = nodes[r.id]
        parent = nodes.get(r.parent_id) if r.parent_id else None
        (parent["children"] if parent else roots).append(node)
    return roots


def create_folder(db: Session, body: Any, user: Any) -> Folder:
    space = db.get(Space, body.space_id)
    if not space or space.deleted:
        raise _err(R.KNOWLEDGE_NOT_FOUND, "空间不存在")
    parent: Folder | None = None
    if body.parent_id:
        parent = db.get(Folder, body.parent_id)
        if not parent or parent.deleted or parent.space_id != body.space_id:
            raise _err(R.KNOWLEDGE_NOT_FOUND, "上级文件夹不存在")
    row = Folder(
        name=body.name,
        space_id=body.space_id,
        category_id=body.category_id,
        parent_id=body.parent_id or None,
        level=(parent.level + 1) if parent else 1,
        path=f"{parent.path}{parent.id}/" if parent else f"/{body.space_id}/",
        description=body.description,
        status=body.status,
        create_by=getattr(user, "id", None),
    )
    db.add(row)
    db.flush()
    return row


def delete_folder(db: Session, row: Folder) -> None:
    if db.scalar(select(func.count()).select_from(Document).where(Document.folder_id == row.id, Document.deleted == 0)):
        raise _err(R.KNOWLEDGE_INVALID_STATE, "文件夹内还有文档，不能删除")
    if db.scalar(select(func.count()).select_from(Folder).where(Folder.parent_id == row.id, Folder.deleted == 0)):
        raise _err(R.KNOWLEDGE_INVALID_STATE, "该文件夹下还有子文件夹，不能删除")


# ---------------- 文件存取 ----------------


def store_file(db: Session, filename: str, data: bytes, user_id: int | None = None) -> File:
    """落盘 + 登记 `kb_file`（格式 / 大小按系统管理区设置校验）。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = allowed_ext(db)
    if ext not in allowed:
        raise _err(
            R.KNOWLEDGE_FILE_TYPE_UNSUPPORTED,
            f"不支持的文件格式：{ext or '无扩展名'}（允许：{', '.join(allowed)}）",
        )
    if not data:
        raise _err(R.KNOWLEDGE_FILE_TYPE_UNSUPPORTED, "文件为空")
    limit = max_mb(db)
    if len(data) > limit * 1024 * 1024:
        raise _err(R.KNOWLEDGE_FILE_TOO_LARGE, f"文件超过大小上限 {limit}MB")
    rel = Path("knowledge") / f"{uuid.uuid4().hex}{('.' + ext) if ext else ''}"
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    row = File(
        file_name=filename or "file",
        ext=ext,
        size=len(data),
        path=str(rel).replace("\\", "/"),
        content_type=_guess_content_type(ext),
        sha256=hashlib.sha256(data).hexdigest(),
        create_by=user_id,
    )
    db.add(row)
    db.flush()
    return row


def file_abs_path(row: File) -> Path:
    return Path(settings.upload_dir) / row.path


def _guess_content_type(ext: str) -> str:
    return {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "txt": "text/plain",
        "md": "text/markdown",
        "csv": "text/csv",
        "zip": "application/zip",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")


# ---------------- 权限解析 ----------------


def _user_role_ids(db: Session, user_id: int) -> set[int]:
    from app.modules.admin.models import UserRole

    rows = db.scalars(select(UserRole).where(UserRole.user_id == user_id)).all()
    return {r.role_id for r in rows}


def _user_dept_ids(db: Session, user_id: int) -> set[int]:
    from app.modules.admin.models import UserDept

    rows = db.scalars(select(UserDept).where(UserDept.user_id == user_id)).all()
    return {r.dept_id for r in rows if r.dept_id}


def _subject_matches(db: Session, perm_row: Permission, user: Any, role_ids: set[int], dept_ids: set[int]) -> bool:
    if perm_row.subject_type == "user":
        return perm_row.subject_id == getattr(user, "id", None)
    if perm_row.subject_type == "role":
        return bool(perm_row.subject_id) and perm_row.subject_id in role_ids
    if perm_row.subject_type == "dept":
        return bool(perm_row.subject_id) and perm_row.subject_id in dept_ids
    return False


def perm_chain(db: Session, doc: Document) -> list[tuple[str, int]]:
    """文档 → 文件夹 → … → 空间 的授权继承链。"""
    chain: list[tuple[str, int]] = [("document", doc.id)]
    folder_id = doc.folder_id
    guard = 0
    while folder_id and guard < 20:
        guard += 1
        folder = db.get(Folder, folder_id)
        if not folder or folder.deleted:
            break
        chain.append(("folder", folder.id))
        folder_id = folder.parent_id
    chain.append(("space", doc.space_id))
    return chain


def perm_of_document(db: Session, user: Any, doc: Document) -> int:
    """计算某用户对某文档的权限档位（0 = 无权）。"""
    uid = getattr(user, "id", None)
    if not uid:
        return 0
    if doc.owner_id == uid:
        return PERM_MANAGE
    editor_ids = {int(x) for x in (doc.editor_ids or "").split(",") if x.strip()}
    if uid in editor_ids:
        return PERM_EDIT
    role_ids = _user_role_ids(db, uid)
    dept_ids = _user_dept_ids(db, uid)
    best = 0
    now = _now()
    for rtype, rid in perm_chain(db, doc):
        rows = db.scalars(
            select(Permission).where(
                Permission.deleted == 0,
                Permission.resource_type == rtype,
                Permission.resource_id == rid,
            )
        ).all()
        for row in rows:
            if row.expire_at and row.expire_at < now:
                continue
            if not _subject_matches(db, row, user, role_ids, dept_ids):
                continue
            best = max(best, PERM_LEVELS.get(row.perm, PERM_READ))
        if best >= PERM_MANAGE:
            break
    if best == 0:
        space = db.get(Space, doc.space_id)
        if space and space.deleted == 0 and space.type == "shared":
            best = PERM_READ
    return best


def assert_perm(db: Session, user: Any, doc: Document, need: int) -> int:
    perm = perm_of_document(db, user, doc)
    if perm < need:
        raise _err(R.KNOWLEDGE_PERMISSION_DENIED)
    return perm


def visible_document_ids(db: Session, user: Any) -> dict:
    """当前用户可见范围（供列表 SQL 过滤）。"""
    uid = getattr(user, "id", None)
    role_ids = _user_role_ids(db, uid)
    dept_ids = _user_dept_ids(db, uid)
    now = _now()
    perm_rows = db.scalars(select(Permission).where(Permission.deleted == 0)).all()
    doc_ids: set[int] = set()
    folder_ids: set[int] = set()
    space_ids: set[int] = set()
    for row in perm_rows:
        if row.expire_at and row.expire_at < now:
            continue
        if not _subject_matches(db, row, user, role_ids, dept_ids):
            continue
        if row.resource_type == "document":
            doc_ids.add(row.resource_id)
        elif row.resource_type == "folder":
            folder_ids.add(row.resource_id)
        elif row.resource_type == "space":
            space_ids.add(row.resource_id)
    shared_spaces = {s.id for s in db.scalars(select(Space).where(Space.deleted == 0, Space.type == "shared")).all()}
    return {
        "docIds": doc_ids,
        "folderIds": folder_ids,
        "spaceIds": space_ids | shared_spaces,
        "ownerId": uid,
    }


# ---------------- 文档 ----------------


def next_document_code(db: Session) -> str:
    prefix = "KB"
    today = _now().strftime("%Y%m%d")
    like = f"{prefix}{today}"
    count = db.scalar(select(func.count()).select_from(Document).where(Document.code.like(f"{like}%"))) or 0
    return f"{like}{count + 1:04d}"


def create_document(
    db: Session,
    *,
    title: str,
    space_id: int,
    user: Any,
    file_row: File | None = None,
    folder_id: int | None = None,
    category_id: int | None = None,
    doc_type: str = "document",
    tags: str = "",
    summary: str = "",
    status: str = "published",
    expired_at: datetime | None = None,
    version_comment: str = "初始版本",
) -> Document:
    space = db.get(Space, space_id)
    if not space or space.deleted:
        raise _err(R.KNOWLEDGE_NOT_FOUND, "空间不存在")
    doc = Document(
        code=next_document_code(db),
        title=title,
        space_id=space_id,
        folder_id=folder_id,
        category_id=category_id,
        owner_id=getattr(user, "id", None),
        owner_name=getattr(user, "name", "") or "",
        editor_ids="",
        current_version=0,
        doc_type=doc_type if doc_type in DOC_TYPES else "document",
        tags=tags,
        summary=summary,
        status=status,
        source="upload",
        published_at=_now() if status == "published" else None,
        expired_at=expired_at,
        create_by=getattr(user, "id", None),
    )
    db.add(doc)
    db.flush()
    if file_row is not None:
        add_version(db, doc, file_row, user=user, comment=version_comment)
    return doc


def add_version(db: Session, doc: Document, file_row: File, user: Any, comment: str = "") -> Version:
    no = (doc.current_version or 0) + 1
    ver = Version(
        document_id=doc.id,
        version_no=no,
        file_id=file_row.id,
        file_name=file_row.file_name,
        ext=file_row.ext,
        size=file_row.size,
        comment=comment,
        operator_id=getattr(user, "id", None),
        operator_name=getattr(user, "name", "") or "",
    )
    db.add(ver)
    db.flush()
    doc.current_version = no
    doc.file_id = file_row.id
    doc.ext = file_row.ext
    doc.size = file_row.size
    doc.update_time = _now()
    return ver


def versions_of(db: Session, doc_id: int) -> list[Version]:
    return list(
        db.scalars(
            select(Version)
            .where(Version.deleted == 0, Version.document_id == doc_id)
            .order_by(Version.version_no.desc())
        ).all()
    )


def rollback_version(db: Session, doc: Document, ver: Version, user: Any) -> Version:
    """回滚到历史版本 —— 以历史内容生成新版本（历史不被抹掉）。"""
    if not ver.file_id:
        raise _err(R.KNOWLEDGE_INVALID_STATE, "该版本没有文件，无法回滚")
    file_row = db.get(File, ver.file_id)
    if not file_row or file_row.deleted:
        raise _err(R.KNOWLEDGE_INVALID_STATE, "该版本文件已删除，无法回滚")
    return add_version(db, doc, file_row, user=user, comment=f"回滚到 v{ver.version_no}")


def document_preview(db: Session, doc: Document) -> dict:
    """服务端抽取文本，用于在线浏览。"""
    limit = preview_max_chars(db)
    file_row = db.get(File, doc.file_id) if doc.file_id else None
    if not file_row:
        return {"kind": "none", "text": "", "message": "该文档没有可预览的正文"}
    ext = (file_row.ext or "").lower()
    if ext in PREVIEW_IMAGE_EXT:
        return {"kind": "image", "ext": ext, "text": "", "url": f"/api/v1/knowledge/documents/{doc.id}/raw"}
    path = file_abs_path(file_row)
    if not path.exists():
        return {"kind": "none", "text": "", "message": "文件已不存在"}
    try:
        if ext == "pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts = [(p.extract_text() or "") for p in reader.pages]
            text = "\n".join(parts)
            return {"kind": "text", "ext": ext, "text": text[:limit], "pages": len(reader.pages)}
        if ext == "docx":
            import docx  # python-docx

            d = docx.Document(str(path))
            lines = [p.text for p in d.paragraphs]
            for table in d.tables:
                for row in table.rows:
                    lines.append(" | ".join(cell.text for cell in row.cells))
            return {"kind": "text", "ext": ext, "text": "\n".join(lines)[:limit]}
        if ext == "xlsx":
            from openpyxl import load_workbook

            wb = load_workbook(str(path), data_only=True, read_only=True)
            blocks: list[str] = []
            for ws in wb.worksheets:
                blocks.append(f"# {ws.title}")
                for row in ws.iter_rows(values_only=True):
                    blocks.append(",".join("" if v is None else str(v) for v in row))
            wb.close()
            return {"kind": "text", "ext": ext, "text": "\n".join(blocks)[:limit]}
        if ext in PREVIEW_TEXT_EXT:
            raw = path.read_bytes()
            for enc in ("utf-8", "gbk", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:  # pragma: no cover - latin-1 永不抛错
                text = raw.decode("utf-8", errors="replace")
            if ext == "csv":
                try:
                    text = "\n".join(
                        ",".join(row) for row in list(csv.reader(io.StringIO(text)))[:2000]
                    )
                except csv.Error:
                    pass
            return {"kind": "text", "ext": ext, "text": text[:limit]}
    except Exception as exc:  # noqa: BLE001 — 预览失败不应报错，返回提示即可
        return {"kind": "none", "ext": ext, "text": "", "message": f"该格式暂不支持在线预览（{type(exc).__name__}）"}
    return {
        "kind": "none",
        "ext": ext,
        "text": "",
        "message": "该格式暂不支持在线预览，请下载后查看",
    }


# ---------------- 微盘式目录浏览 ----------------

# 目录浏览支持的排序列（微盘「名称 / 最近更新 / 大小」）
BROWSE_SORTS = {"name": Document.title, "updateTime": Document.update_time, "size": Document.size}


def visible_document_where(db: Session, user: Any):
    """当前用户可见文档的 SQL 条件（文档列表与目录浏览共用同一口径）。"""
    scope = visible_document_ids(db, user)
    ors = [Document.space_id.in_(scope["spaceIds"]), Document.owner_id == scope["ownerId"]]
    if scope["docIds"]:
        ors.append(Document.id.in_(scope["docIds"]))
    if scope["folderIds"]:
        ors.append(Document.folder_id.in_(scope["folderIds"]))
    return or_(*ors), scope


def folder_breadcrumb(db: Session, folder_id: int | None) -> list[dict]:
    """文件夹的祖先链（根 → 当前），用于面包屑导航。"""
    chain: list[dict] = []
    cur = db.get(Folder, folder_id) if folder_id else None
    guard = 0
    while cur is not None and guard < 20:
        guard += 1
        chain.append({"id": cur.id, "name": cur.name, "spaceId": cur.space_id})
        cur = db.get(Folder, cur.parent_id) if cur and cur.parent_id else None
    chain.reverse()
    return chain


def _folder_ancestors(db: Session, folder_ids: set[int]) -> set[int]:
    """把文件夹 id 展开为「含全部祖先」的集合。"""
    out = set(folder_ids)
    for fid in list(folder_ids):
        guard = 0
        cur = db.get(Folder, fid)
        while cur is not None and cur.parent_id and guard < 20:
            guard += 1
            if cur.parent_id in out:
                break
            out.add(cur.parent_id)
            cur = db.get(Folder, cur.parent_id)
    return out


def _updater_names(db: Session, doc_ids: list[int]) -> dict[int, str]:
    """文档最近一次更新的操作人（取版本号最大的那条）。"""
    if not doc_ids:
        return {}
    rows = db.execute(
        select(Version.document_id, Version.operator_name, Version.version_no)
        .where(Version.deleted == 0, Version.document_id.in_(doc_ids))
        .order_by(Version.document_id, Version.version_no.desc())
    ).all()
    out: dict[int, str] = {}
    for doc_id, name, _no in rows:
        out.setdefault(int(doc_id), name or "")
    return out


def _external_resource_ids(db: Session, resource_type: str, ids: list[int]) -> set[int]:
    """存在生效外部分享链接的资源 id（微盘「外部可访问」标签）。"""
    if not ids:
        return set()
    now = _now()
    rows = db.scalars(
        select(ShareLink.resource_id).where(
            ShareLink.deleted == 0,
            ShareLink.status == "active",
            ShareLink.resource_type == resource_type,
            ShareLink.resource_id.in_(ids),
            or_(ShareLink.expire_at.is_(None), ShareLink.expire_at > now),
        )
    ).all()
    return {int(r) for r in rows}


def _restricted_resource_ids(db: Session, resource_type: str, ids: list[int]) -> set[int]:
    """设置了成员权限的资源 id（微盘「限制成员权限」标签）。"""
    if not ids:
        return set()
    rows = db.scalars(
        select(Permission.resource_id).where(
            Permission.deleted == 0,
            Permission.resource_type == resource_type,
            Permission.resource_id.in_(ids),
        )
    ).all()
    return {int(r) for r in rows}


def browse(
    db: Session,
    user: Any,
    *,
    space_id: int | None = None,
    folder_id: int | None = None,
    category_id: int | None = None,
    q: str = "",
    page: int = 1,
    size: int = 50,
    sort: str = "updateTime",
    order: str = "desc",
) -> dict:
    """微盘式目录浏览：一次返回「子文件夹 + 文档」。

    - 子文件夹不分页（目录层级浅），文档按页返回；
    - 可见范围与文档列表完全一致（`visible_document_where`）；
    - 每个条目附带 `externalAccess`（存在生效的外部分享链接）与 `restricted`
      （设置了成员权限），对应微盘的「外部可访问 / 限制成员权限」标签。
    """
    doc_where, scope = visible_document_where(db, user)
    visible_space_ids = {s.id for s in space_visible(db, user)} | set(scope["spaceIds"])

    # ---- 子文件夹 ----
    fstmt = select(Folder).where(Folder.deleted == 0)
    if space_id:
        fstmt = fstmt.where(Folder.space_id == space_id)
    if folder_id:
        fstmt = fstmt.where(Folder.parent_id == folder_id)
    else:
        fstmt = fstmt.where(Folder.parent_id.is_(None))
    if category_id:
        fstmt = fstmt.where(Folder.category_id == category_id)
    if q:
        fstmt = fstmt.where(Folder.name.like(f"%{q}%"))
    folder_rows = list(db.scalars(fstmt.order_by(Folder.name, Folder.id)).all())

    # 文件夹可见性：所属空间可见 / 自身或祖先链有授权 / 其下存在可见文档
    doc_folder_ids = set(
        db.scalars(
            select(Document.folder_id).where(
                Document.deleted == 0, doc_where, Document.folder_id.isnot(None)
            ).distinct()
        ).all()
    )
    visible_folder_ids = _folder_ancestors(db, set(scope["folderIds"]) | doc_folder_ids)
    folder_rows = [
        f for f in folder_rows if f.space_id in visible_space_ids or f.id in visible_folder_ids
    ]

    # ---- 文档 ----
    dstmt = select(Document).where(Document.deleted == 0, doc_where)
    if space_id:
        dstmt = dstmt.where(Document.space_id == space_id)
    if folder_id:
        dstmt = dstmt.where(Document.folder_id == folder_id)
    else:
        dstmt = dstmt.where(Document.folder_id.is_(None))
    if category_id:
        dstmt = dstmt.where(Document.category_id.in_(category_descendants(db, category_id)))
    if q:
        like = f"%{q}%"
        dstmt = dstmt.where(
            or_(Document.title.like(like), Document.tags.like(like), Document.code.like(like))
        )
    total = db.scalar(select(func.count()).select_from(dstmt.subquery())) or 0
    col = BROWSE_SORTS.get(sort, Document.update_time)
    dstmt = dstmt.order_by(col.desc() if order == "desc" else col.asc(), Document.id.desc())
    dstmt = dstmt.offset((page - 1) * size).limit(size)
    doc_rows = list(db.scalars(dstmt).all())

    # ---- 附加标记 ----
    folder_ids = [f.id for f in folder_rows]
    doc_ids = [d.id for d in doc_rows]
    updaters = _updater_names(db, doc_ids)
    ext_docs = _external_resource_ids(db, "document", doc_ids)
    ext_folders = _external_resource_ids(db, "folder", folder_ids)
    res_docs = _restricted_resource_ids(db, "document", doc_ids)
    res_folders = _restricted_resource_ids(db, "folder", folder_ids)
    counts: dict[int, int] = {}
    if folder_ids:
        for cid, c in db.execute(
            select(Document.folder_id, func.count())
            .where(
                Document.deleted == 0,
                doc_where,
                Document.folder_id.in_(folder_ids),
            )
            .group_by(Document.folder_id)
        ).all():
            counts[int(cid)] = int(c)

    space = db.get(Space, space_id) if space_id else None
    my_count, my_size = db.execute(
        select(func.count(), func.coalesce(func.sum(Document.size), 0)).where(
            Document.deleted == 0, Document.owner_id == scope["ownerId"]
        )
    ).one()
    return {
        "space": out_space(space) if space is not None and space.deleted == 0 else None,
        "breadcrumb": folder_breadcrumb(db, folder_id),
        "stats": {"myDocCount": int(my_count or 0), "mySize": int(my_size or 0)},
        "folders": [
            {
                **out_folder(f),
                "docCount": counts.get(f.id, 0),
                "externalAccess": f.id in ext_folders,
                "restricted": f.id in res_folders,
            }
            for f in folder_rows
        ],
        "documents": {
            "items": [
                {
                    **out_document(d, perm_of_document(db, user, d)),
                    "updaterName": updaters.get(d.id, ""),
                    "externalAccess": d.id in ext_docs,
                    "restricted": d.id in res_docs,
                }
                for d in doc_rows
            ],
            "total": total,
            "page": page,
            "size": size,
        },
    }


# ---------------- 外部分享链接 ----------------

LINK_CODE_TTL_SEC = 600
LINK_TOKEN_TTL_SEC = 7200
LINK_SEND_COOLDOWN_SEC = 60
LINK_CODE_FAIL_LIMIT = 5


def create_link(db: Session, body: Any, user: Any) -> ShareLink:
    if body.resource_type not in ("folder", "document"):
        raise _err(R.GENERIC_PARAM, "resourceType 只支持 folder / document")
    if body.perm not in ("read", "upload", "edit"):
        raise _err(R.GENERIC_PARAM, "perm 只支持 read / upload / edit")
    if body.resource_type == "folder":
        folder = db.get(Folder, body.resource_id)
        if not folder or folder.deleted:
            raise _err(R.KNOWLEDGE_NOT_FOUND, "文件夹不存在")
        title = folder.name
    else:
        doc = db.get(Document, body.resource_id)
        if not doc or doc.deleted:
            raise _err(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
        title = doc.title
    expire_at = _now() + timedelta(days=body.expire_days) if body.expire_days else None
    row = ShareLink(
        token=uuid.uuid4().hex + secrets.token_hex(4),
        title=title,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        perm=body.perm,
        require_phone=1 if body.require_phone else 0,
        expire_at=expire_at,
        max_upload=body.max_upload,
        status="active",
        creator_id=getattr(user, "id", None),
        creator_name=getattr(user, "name", "") or "",
        remark=body.remark,
        create_by=getattr(user, "id", None),
    )
    db.add(row)
    db.flush()
    return row


def link_status(db: Session, link: ShareLink) -> str:
    if link.status != "active":
        return link.status
    if link.expire_at and link.expire_at < _now():
        return "expired"
    return "active"


def link_send_code(db: Session, link: ShareLink, phone: str) -> dict:
    """发送短信验证码（Redis 暂存，60s 冷却）。"""
    from app.core.redis import get_redis
    from app.modules.settings import notify

    if link_status(db, link) != "active":
        raise _err(R.KNOWLEDGE_LINK_EXPIRED)
    phone = (phone or "").strip()
    if len(phone) < 6:
        raise _err(R.GENERIC_PARAM, "请输入正确的手机号")
    r = get_redis()
    cool_key = f"kb_link_send:{link.token}"
    if r.get(cool_key):
        raise _err(R.AUTH_MFA_SEND_TOO_OFTEN, "发送过于频繁，请稍后再试")
    r.setex(cool_key, LINK_SEND_COOLDOWN_SEC, "1")
    code = f"{secrets.randbelow(1000000):06d}"
    r.setex(f"kb_link_code:{link.token}:{phone}", LINK_CODE_TTL_SEC, code)
    r.delete(f"kb_link_fail:{link.token}:{phone}")
    mode = notify.send_sms(db, phone, code)
    out: dict = {"sent": True, "cooldown": LINK_SEND_COOLDOWN_SEC, "mode": mode}
    if settings.is_dev:
        out["debugCode"] = code
    return out


def link_verify(db: Session, link: ShareLink, phone: str, code: str) -> str:
    """校验验证码 → 返回短时访问令牌（后续浏览 / 上传凭它）。"""
    from app.core.redis import get_redis

    if link_status(db, link) != "active":
        raise _err(R.KNOWLEDGE_LINK_EXPIRED)
    r = get_redis()
    key = f"kb_link_code:{link.token}:{phone}"
    stored = r.get(key)
    if not stored:
        raise _err(R.KNOWLEDGE_LINK_CODE_INVALID, "请先获取验证码")
    if stored != code:
        fail_key = f"kb_link_fail:{link.token}:{phone}"
        n = r.incr(fail_key)
        r.expire(fail_key, LINK_CODE_TTL_SEC)
        if n >= LINK_CODE_FAIL_LIMIT:
            r.delete(key)
            raise _err(R.KNOWLEDGE_LINK_CODE_INVALID, "错误次数过多，请重新获取验证码")
        raise _err(R.KNOWLEDGE_LINK_CODE_INVALID)
    r.delete(key)
    token = secrets.token_urlsafe(24)
    r.setex(f"kb_link_token:{link.token}", LINK_TOKEN_TTL_SEC, f"{token}|{phone}")
    return token


def link_check_token(db: Session, link: ShareLink, token: str) -> str:
    """校验访问令牌，返回手机号。"""
    from app.core.redis import get_redis

    if link_status(db, link) != "active":
        raise _err(R.KNOWLEDGE_LINK_EXPIRED)
    if not link.require_phone:
        return ""
    r = get_redis()
    raw = r.get(f"kb_link_token:{link.token}")
    if not raw:
        raise _err(R.KNOWLEDGE_LINK_VERIFY_REQUIRED)
    parts = raw.split("|", 1)
    if len(parts) != 2 or parts[0] != token:
        raise _err(R.KNOWLEDGE_LINK_VERIFY_REQUIRED)
    return parts[1]


def link_log(db: Session, link: ShareLink, action: str, phone: str = "", file_name: str = "", ip: str = "") -> None:
    db.add(
        LinkLog(
            link_id=link.id,
            action=action,
            phone=_mask_phone(phone),
            file_name=file_name,
            ip=ip,
        )
    )


def public_out_document(row: Document) -> dict:
    """外部分享的文档摘要（不暴露内部作者 / 编辑者 / 空间结构）。"""
    return {
        "id": row.id,
        "title": row.title,
        "ext": row.ext,
        "size": row.size,
        "docType": row.doc_type,
        "version": row.current_version,
        "updateTime": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else "",
    }


def link_content(db: Session, link: ShareLink) -> list[dict]:
    """分享链接下的文档清单。"""
    if link.resource_type == "document":
        doc = db.get(Document, link.resource_id)
        if not doc or doc.deleted:
            raise _err(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
        return [public_out_document(doc)]
    folder = db.get(Folder, link.resource_id)
    if not folder or folder.deleted:
        raise _err(R.KNOWLEDGE_NOT_FOUND, "文件夹不存在")
    docs = db.scalars(
        select(Document).where(Document.deleted == 0, Document.folder_id == folder.id).order_by(Document.id.desc())
    ).all()
    return [public_out_document(d) for d in docs]


# ---------------- 彻底删除钩子 ----------------


def _drop_file(db: Session, file_row: File) -> None:
    """删磁盘文件 + 逻辑删 `kb_file` 行。"""
    path = file_abs_path(file_row)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
    if not file_row.deleted:
        file_row.deleted = 1


def _purge_document(db: Session, doc_id: int) -> None:
    """文档被彻底删除时，连同各版本的磁盘文件一起清掉。"""
    doc = db.get(Document, doc_id)
    if doc is None:
        return
    for ver in db.scalars(select(Version).where(Version.document_id == doc_id)).all():
        if ver.file_id:
            f = db.get(File, ver.file_id)
            if f is not None:
                _drop_file(db, f)
        ver.deleted = 1
    if doc.file_id:
        f = db.get(File, doc.file_id)
        if f is not None:
            _drop_file(db, f)


def _purge_file(db: Session, file_id: int) -> None:
    f = db.get(File, file_id)
    if f is not None:
        _drop_file(db, f)


def register_purge_hooks() -> None:
    """注册回收站彻底删除钩子（文档 / 文件 → 删磁盘文件）。"""
    from app.common import recycle

    recycle.register_purge_hook("kb_document", _purge_document)
    recycle.register_purge_hook("kb_file", _purge_file)


register_purge_hooks()

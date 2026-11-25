"""知识库与文档中心路由 `/api/v1/knowledge`。

内部端点（需登录）：
- 分类树：`GET/POST/PUT/DELETE /knowledge/categories`
- 空间：`GET/POST/PUT/DELETE /knowledge/spaces`
- 文件夹：`GET/POST/PUT/DELETE /knowledge/folders`
- 文档：列表 / 详情 / 单个与批量上传 / 元信息 / 新版本 / 版本历史 / 回滚 / 预览 / 下载
- 授权：`GET/PUT /knowledge/documents/{id}/permissions`、`DELETE /knowledge/permissions/{id}`
- 分享链接：`GET/POST /knowledge/links`、`DELETE /knowledge/links/{id}`
- 设置：`GET/PUT /knowledge/settings`

外部分享端点（**无需登录**，凭手机号 + 短信验证码）：
- `GET  /knowledge/public/links/{token}` 链接信息
- `POST /knowledge/public/links/{token}/code`   发送验证码
- `POST /knowledge/public/links/{token}/verify` 校验验证码 → 访问令牌
- `GET  /knowledge/public/links/{token}/documents` 文档清单
- `GET  /knowledge/public/links/{token}/raw/{docId}` 文件下载
- `POST /knowledge/public/links/{token}/upload`   上传（perm=upload/edit）
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common import recycle
from app.common.audit import record as audit
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.client_ip import client_ip
from app.core.db import get_db
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.knowledge import service as svc
from app.modules.knowledge.models import (
    Category,
    Document,
    Folder,
    Permission,
    ShareLink,
    Space,
    Version,
)
from app.modules.knowledge.models import File as KbFile
from app.modules.knowledge.schemas import (
    CategoryIn,
    DocumentIn,
    FolderIn,
    KnowledgeSettingIn,
    PermissionIn,
    ShareLinkIn,
    SpaceIn,
)

router = APIRouter(prefix="/knowledge", tags=["知识与文档"], route_class=EnvelopeRoute)


# ---------------- 分类 ----------------


@router.get("/categories")
def list_categories(
    current: User = Depends(require_perm("knowledge:category:list")),
    db: Session = Depends(get_db),
):
    """文档分类树（多级可定义）。"""
    return {"items": svc.category_tree(db)}


@router.post("/categories")
def create_category(
    body: CategoryIn,
    current: User = Depends(require_perm("knowledge:category:edit")),
    db: Session = Depends(get_db),
):
    row = svc.create_category(db, body, current)
    audit(db, user_id=current.id, module="knowledge", action="category_create", biz_type="kb_category", biz_id=row.id)
    db.commit()
    return {"id": row.id, "name": row.name, "path": row.path, "level": row.level}


@router.put("/categories/{cid}")
def update_category(
    cid: int,
    body: CategoryIn,
    current: User = Depends(require_perm("knowledge:category:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(Category, cid)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "分类不存在")
    svc.update_category(db, row, body)
    audit(db, user_id=current.id, module="knowledge", action="category_update", biz_type="kb_category", biz_id=cid)
    db.commit()
    return {"id": row.id, "name": row.name, "path": row.path, "level": row.level}


@router.delete("/categories/{cid}")
def delete_category(
    cid: int,
    current: User = Depends(require_perm("knowledge:category:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(Category, cid)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "分类不存在")
    svc.delete_category(db, row)
    recycle.soft_delete(db, Category, row, user=current, module="knowledge", resource="Category")
    audit(db, user_id=current.id, module="knowledge", action="category_delete", biz_type="kb_category", biz_id=cid)
    db.commit()
    return None


# ---------------- 空间 ----------------


@router.get("/spaces")
def list_spaces(
    current: User = Depends(require_perm("knowledge:space:list")),
    db: Session = Depends(get_db),
):
    rows = svc.space_visible(db, current)
    return {"items": [svc.out_space(r) for r in rows]}


@router.post("/spaces")
def create_space(
    body: SpaceIn,
    current: User = Depends(require_perm("knowledge:space:edit")),
    db: Session = Depends(get_db),
):
    row = svc.create_space(db, body, current)
    audit(db, user_id=current.id, module="knowledge", action="space_create", biz_type="kb_space", biz_id=row.id)
    db.commit()
    return svc.out_space(row)


@router.put("/spaces/{sid}")
def update_space(
    sid: int,
    body: SpaceIn,
    current: User = Depends(require_perm("knowledge:space:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(Space, sid)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "空间不存在")
    row.name = body.name or row.name
    row.description = body.description
    row.status = body.status or row.status
    row.dept_id = body.dept_id if body.dept_id is not None else row.dept_id
    audit(db, user_id=current.id, module="knowledge", action="space_update", biz_type="kb_space", biz_id=sid)
    db.commit()
    return svc.out_space(row)


@router.delete("/spaces/{sid}")
def delete_space(
    sid: int,
    current: User = Depends(require_perm("knowledge:space:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(Space, sid)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "空间不存在")
    svc.delete_space(db, row)
    recycle.soft_delete(db, Space, row, user=current, module="knowledge", resource="Space")
    audit(db, user_id=current.id, module="knowledge", action="space_delete", biz_type="kb_space", biz_id=sid)
    db.commit()
    return None


# ---------------- 文件夹 ----------------


@router.get("/folders")
def list_folders(
    space_id: int | None = Query(None, alias="spaceId"),
    parent_id: int | None = Query(None, alias="parentId"),
    current: User = Depends(require_perm("knowledge:document:list")),
    db: Session = Depends(get_db),
):
    rows = svc.folder_children(db, space_id, parent_id)
    return {"items": [svc.out_folder(r) for r in rows]}


@router.get("/folders/tree")
def folder_tree(
    space_id: int = Query(..., alias="spaceId"),
    current: User = Depends(require_perm("knowledge:document:list")),
    db: Session = Depends(get_db),
):
    return {"items": svc.folder_tree(db, space_id)}


@router.post("/folders")
def create_folder(
    body: FolderIn,
    current: User = Depends(require_perm("knowledge:document:create")),
    db: Session = Depends(get_db),
):
    row = svc.create_folder(db, body, current)
    audit(db, user_id=current.id, module="knowledge", action="folder_create", biz_type="kb_folder", biz_id=row.id)
    db.commit()
    return svc.out_folder(row)


@router.put("/folders/{fid}")
def update_folder(
    fid: int,
    body: FolderIn,
    current: User = Depends(require_perm("knowledge:document:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(Folder, fid)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文件夹不存在")
    row.name = body.name or row.name
    row.description = body.description
    row.status = body.status or row.status
    row.category_id = body.category_id if body.category_id is not None else row.category_id
    audit(db, user_id=current.id, module="knowledge", action="folder_update", biz_type="kb_folder", biz_id=fid)
    db.commit()
    return svc.out_folder(row)


@router.delete("/folders/{fid}")
def delete_folder(
    fid: int,
    current: User = Depends(require_perm("knowledge:document:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(Folder, fid)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文件夹不存在")
    svc.delete_folder(db, row)
    recycle.soft_delete(db, Folder, row, user=current, module="knowledge", resource="Folder")
    audit(db, user_id=current.id, module="knowledge", action="folder_delete", biz_type="kb_folder", biz_id=fid)
    db.commit()
    return None


# ---------------- 文档 ----------------


def _visible_where(db: Session, user: User):
    scope = svc.visible_document_ids(db, user)
    ors = [Document.space_id.in_(scope["spaceIds"]), Document.owner_id == scope["ownerId"]]
    if scope["docIds"]:
        ors.append(Document.id.in_(scope["docIds"]))
    if scope["folderIds"]:
        ors.append(Document.folder_id.in_(scope["folderIds"]))
    return or_(*ors), scope


@router.get("/documents")
def list_documents(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    q: str = Query("", description="关键词"),
    category_id: int | None = Query(None, alias="categoryId"),
    space_id: int | None = Query(None, alias="spaceId"),
    folder_id: int | None = Query(None, alias="folderId"),
    doc_type: str = Query("", alias="docType"),
    current: User = Depends(require_perm("knowledge:document:list")),
    db: Session = Depends(get_db),
):
    """文档列表（按当前用户可见范围过滤）。"""
    where, _ = _visible_where(db, current)
    stmt = select(Document).where(Document.deleted == 0, where)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Document.title.like(like), Document.tags.like(like), Document.code.like(like)))
    if category_id:
        ids = svc.category_descendants(db, category_id)
        stmt = stmt.where(Document.category_id.in_(ids))
    if space_id:
        stmt = stmt.where(Document.space_id == space_id)
    if folder_id:
        stmt = stmt.where(Document.folder_id == folder_id)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(Document.update_time.desc(), Document.id.desc()).offset((page - 1) * size).limit(size)
    rows = db.scalars(stmt).all()
    return {
        "items": [svc.out_document(r, svc.perm_of_document(db, current, r)) for r in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/documents/{did}")
def get_document(
    did: int,
    current: User = Depends(require_perm("knowledge:document:list")),
    db: Session = Depends(get_db),
):
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    perm = svc.perm_of_document(db, current, row)
    if perm < svc.PERM_READ:
        raise BizException(R.KNOWLEDGE_PERMISSION_DENIED)
    return svc.out_document(row, perm)


@router.post("/documents")
def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    space_id: int = Form(...),
    folder_id: int | None = Form(None),
    category_id: int | None = Form(None),
    doc_type: str = Form("document"),
    tags: str = Form(""),
    summary: str = Form(""),
    status: str = Form("published"),
    current: User = Depends(require_perm("knowledge:document:create")),
    db: Session = Depends(get_db),
):
    """单个文档上传。"""
    name = title.strip() or (file.filename or "文档")
    file_row = svc.store_file(db, file.filename or "file", file.file.read(), current.id)
    doc = svc.create_document(
        db,
        title=name,
        space_id=space_id,
        user=current,
        file_row=file_row,
        folder_id=folder_id,
        category_id=category_id,
        doc_type=doc_type,
        tags=tags,
        summary=summary,
        status=status,
    )
    audit(db, user_id=current.id, module="knowledge", action="document_upload", biz_type="kb_document", biz_id=doc.id)
    db.commit()
    return svc.out_document(doc, svc.PERM_MANAGE)


@router.post("/documents/batch")
def upload_documents_batch(
    files: list[UploadFile] = File(...),
    space_id: int = Form(...),
    folder_id: int | None = Form(None),
    category_id: int | None = Form(None),
    doc_type: str = Form("document"),
    status: str = Form("published"),
    current: User = Depends(require_perm("knowledge:document:create")),
    db: Session = Depends(get_db),
):
    """批量上传（单文件失败不影响其余文件，逐个返回结果）。"""
    items: list[dict] = []
    for f in files:
        try:
            file_row = svc.store_file(db, f.filename or "file", f.file.read(), current.id)
            doc = svc.create_document(
                db,
                title=(f.filename or "文档").rsplit(".", 1)[0],
                space_id=space_id,
                user=current,
                file_row=file_row,
                folder_id=folder_id,
                category_id=category_id,
                doc_type=doc_type,
                status=status,
            )
            items.append({"name": f.filename, "ok": True, "documentId": doc.id, "title": doc.title})
        except BizException as exc:
            items.append({"name": f.filename, "ok": False, "message": exc.message})
    audit(db, user_id=current.id, module="knowledge", action="document_batch_upload", detail={"count": len(items)})
    db.commit()
    return {"items": items, "total": len(items), "success": sum(1 for i in items if i["ok"])}


@router.put("/documents/{did}")
def update_document(
    did: int,
    body: DocumentIn,
    current: User = Depends(require_perm("knowledge:document:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, row, svc.PERM_EDIT)
    row.title = body.title or row.title
    row.folder_id = body.folder_id if body.folder_id is not None else row.folder_id
    row.category_id = body.category_id if body.category_id is not None else row.category_id
    row.doc_type = body.doc_type if body.doc_type in svc.DOC_TYPES else row.doc_type
    row.tags = body.tags if body.tags is not None else row.tags
    row.summary = body.summary if body.summary is not None else row.summary
    row.status = body.status or row.status
    row.expired_at = body.expired_at if body.expired_at is not None else row.expired_at
    row.update_time = datetime.now()
    audit(db, user_id=current.id, module="knowledge", action="document_update", biz_type="kb_document", biz_id=did)
    db.commit()
    return svc.out_document(row, svc.perm_of_document(db, current, row))


@router.delete("/documents/{did}")
def delete_document(
    did: int,
    current: User = Depends(require_perm("knowledge:document:delete")),
    db: Session = Depends(get_db),
):
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, row, svc.PERM_MANAGE)
    recycle.soft_delete(db, Document, row, user=current, module="knowledge", resource="Document")
    audit(db, user_id=current.id, module="knowledge", action="document_delete", biz_type="kb_document", biz_id=did)
    db.commit()
    return None


@router.get("/documents/{did}/versions")
def list_versions(
    did: int,
    current: User = Depends(require_perm("knowledge:document:list")),
    db: Session = Depends(get_db),
):
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, row, svc.PERM_READ)
    return {"items": [svc.out_version(v) for v in svc.versions_of(db, did)]}


@router.post("/documents/{did}/versions")
def add_version(
    did: int,
    file: UploadFile = File(...),
    comment: str = Form(""),
    current: User = Depends(require_perm("knowledge:document:edit")),
    db: Session = Depends(get_db),
):
    """上传新版本。"""
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, row, svc.PERM_EDIT)
    file_row = svc.store_file(db, file.filename or "file", file.file.read(), current.id)
    ver = svc.add_version(db, row, file_row, user=current, comment=comment)
    audit(
        db,
        user_id=current.id,
        module="knowledge",
        action="document_version",
        biz_type="kb_document",
        biz_id=did,
        detail={"version": ver.version_no},
    )
    db.commit()
    return svc.out_version(ver)


@router.post("/documents/{did}/rollback/{vid}")
def rollback(
    did: int,
    vid: int,
    current: User = Depends(require_perm("knowledge:document:edit")),
    db: Session = Depends(get_db),
):
    """回滚到历史版本（生成新版本，历史保留）。"""
    doc = db.get(Document, did)
    if not doc or doc.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, doc, svc.PERM_EDIT)
    ver = db.get(Version, vid)
    if not ver or ver.deleted or ver.document_id != did:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "版本不存在")
    new_ver = svc.rollback_version(db, doc, ver, current)
    audit(
        db,
        user_id=current.id,
        module="knowledge",
        action="document_rollback",
        biz_type="kb_document",
        biz_id=did,
        detail={"from": ver.version_no, "to": new_ver.version_no},
    )
    db.commit()
    return svc.out_version(new_ver)


@router.get("/documents/{did}/preview")
def preview_document(
    did: int,
    current: User = Depends(require_perm("knowledge:document:list")),
    db: Session = Depends(get_db),
):
    """在线浏览（服务端抽取文本 / 图片直出）。"""
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, row, svc.PERM_READ)
    return svc.document_preview(db, row)


def _serve_file(doc: Document, db: Session, as_attachment: bool) -> Response:
    file_row = db.get(KbFile, doc.file_id) if doc.file_id else None
    if not file_row:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文件不存在")
    path = svc.file_abs_path(file_row)
    if not path.exists():
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文件已不存在")
    data = path.read_bytes()
    headers = {}
    if as_attachment:
        from urllib.parse import quote

        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(file_row.file_name)}"
    return Response(content=data, media_type=file_row.content_type or "application/octet-stream", headers=headers)


@router.get("/documents/{did}/raw")
def raw_document(
    did: int,
    current: User = Depends(require_perm("knowledge:preview")),
    db: Session = Depends(get_db),
):
    """在线预览原文件（图片 / pdf 浏览器直开）。"""
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, row, svc.PERM_READ)
    return _serve_file(row, db, as_attachment=False)


@router.get("/documents/{did}/download")
def download_document(
    did: int,
    current: User = Depends(require_perm("knowledge:download")),
    db: Session = Depends(get_db),
):
    """下载原文件。"""
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, row, svc.PERM_READ)
    audit(db, user_id=current.id, module="knowledge", action="document_download", biz_type="kb_document", biz_id=did)
    db.commit()
    return _serve_file(row, db, as_attachment=True)


# ---------------- 授权 ----------------


@router.get("/documents/{did}/permissions")
def list_permissions(
    did: int,
    current: User = Depends(require_perm("knowledge:document:share")),
    db: Session = Depends(get_db),
):
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, row, svc.PERM_MANAGE)
    rows = db.scalars(
        select(Permission).where(
            Permission.deleted == 0,
            Permission.resource_type == "document",
            Permission.resource_id == did,
        )
    ).all()
    return {"items": [svc.out_permission(r) for r in rows]}


@router.put("/documents/{did}/permissions")
def set_permissions(
    did: int,
    body: list[PermissionIn],
    current: User = Depends(require_perm("knowledge:document:share")),
    db: Session = Depends(get_db),
):
    """整体覆盖文档授权（内部 / 外部，只读 / 可编辑 / 可管理）。"""
    row = db.get(Document, did)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    svc.assert_perm(db, current, row, svc.PERM_MANAGE)
    for item in body:
        if item.perm not in svc.PERM_VALUES:
            raise BizException(R.GENERIC_PARAM, "perm 只支持 read / edit / manage")
        if item.subject_type not in ("user", "role", "dept"):
            raise BizException(R.GENERIC_PARAM, "subjectType 只支持 user / role / dept")
    old = db.scalars(
        select(Permission).where(
            Permission.deleted == 0,
            Permission.resource_type == "document",
            Permission.resource_id == did,
        )
    ).all()
    for o in old:
        o.deleted = 1
    for item in body:
        db.add(
            Permission(
                resource_type="document",
                resource_id=did,
                subject_type=item.subject_type,
                subject_id=item.subject_id,
                subject_name=item.subject_name,
                perm=item.perm,
                is_external=item.is_external,
                expire_at=item.expire_at,
                create_by=current.id,
            )
        )
    db.flush()
    audit(db, user_id=current.id, module="knowledge", action="document_permission", biz_type="kb_document", biz_id=did)
    db.commit()
    rows = db.scalars(
        select(Permission).where(
            Permission.deleted == 0,
            Permission.resource_type == "document",
            Permission.resource_id == did,
        )
    ).all()
    return {"items": [svc.out_permission(r) for r in rows]}


@router.delete("/permissions/{pid}")
def delete_permission(
    pid: int,
    current: User = Depends(require_perm("knowledge:document:share")),
    db: Session = Depends(get_db),
):
    row = db.get(Permission, pid)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "授权记录不存在")
    recycle.soft_delete(db, Permission, row, user=current, module="knowledge", resource="Permission")
    audit(db, user_id=current.id, module="knowledge", action="permission_delete", biz_type="kb_permission", biz_id=pid)
    db.commit()
    return None


# ---------------- 分享链接 ----------------


@router.get("/links")
def list_links(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("knowledge:link:list")),
    db: Session = Depends(get_db),
):
    from app.common.filters import apply_list_filters

    stmt, total = apply_list_filters(
        select(ShareLink),
        ShareLink,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["title", "remark"],
        filter_cols={"status": "status", "resource_type": "resource_type", "perm": "perm"},
        sort_cols={"id", "expire_at", "create_time"},
        default_sort=("create_time", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {
        "items": [
            {
                "id": r.id,
                "token": r.token,
                "title": r.title,
                "resourceType": r.resource_type,
                "resourceId": r.resource_id,
                "perm": r.perm,
                "requirePhone": bool(r.require_phone),
                "expireAt": r.expire_at.strftime("%Y-%m-%d %H:%M:%S") if r.expire_at else "",
                "maxUpload": r.max_upload,
                "uploadCount": r.upload_count,
                "downloadCount": r.download_count,
                "status": svc.link_status(db, r),
                "creatorName": r.creator_name,
                "remark": r.remark,
                "createTime": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("/links")
def create_link(
    body: ShareLinkIn,
    current: User = Depends(require_perm("knowledge:link:create")),
    db: Session = Depends(get_db),
):
    """生成外部分享链接（可只读 / 可上传 / 可编辑）。"""
    if body.resource_type == "document":
        doc = db.get(Document, body.resource_id)
        if not doc or doc.deleted:
            raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
        svc.assert_perm(db, current, doc, svc.PERM_MANAGE)
    else:
        folder = db.get(Folder, body.resource_id)
        if not folder or folder.deleted:
            raise BizException(R.KNOWLEDGE_NOT_FOUND, "文件夹不存在")
    row = svc.create_link(db, body, current)
    audit(db, user_id=current.id, module="knowledge", action="link_create", biz_type="kb_share_link", biz_id=row.id)
    db.commit()
    return {
        "id": row.id,
        "token": row.token,
        "title": row.title,
        "perm": row.perm,
        "requirePhone": bool(row.require_phone),
        "expireAt": row.expire_at.strftime("%Y-%m-%d %H:%M:%S") if row.expire_at else "",
        "status": "active",
        "url": f"/knowledge/share/{row.token}",
    }


@router.delete("/links/{lid}")
def close_link(
    lid: int,
    current: User = Depends(require_perm("knowledge:link:delete")),
    db: Session = Depends(get_db),
):
    row = db.get(ShareLink, lid)
    if not row or row.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "分享链接不存在")
    row.status = "closed"
    recycle.soft_delete(db, ShareLink, row, user=current, module="knowledge", resource="ShareLink")
    audit(db, user_id=current.id, module="knowledge", action="link_close", biz_type="kb_share_link", biz_id=lid)
    db.commit()
    return None


# ---------------- 设置 ----------------


@router.get("/settings")
def get_settings(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传格式 / 大小上限（系统管理区可改）。"""
    return {
        "allowedExt": svc.allowed_ext(db),
        "maxMb": svc.max_mb(db),
        "previewMaxChars": svc.preview_max_chars(db),
        "defaultAllowedExt": svc.DEFAULT_ALLOWED_EXT,
    }


@router.put("/settings")
def update_settings(
    body: KnowledgeSettingIn,
    current: User = Depends(require_perm("knowledge:setting:edit")),
    db: Session = Depends(get_db),
):
    from app.modules.settings.service import set_value

    exts = [e.strip().lower().lstrip(".") for e in body.allowed_ext if e.strip()]
    # 空列表 = 清空配置 → 回落系统默认格式（allowed_ext 对空值返回默认）
    set_value(db, svc.CFG_ALLOWED_EXT, ",".join(exts), current.id, "知识库允许上传的格式")
    set_value(db, svc.CFG_MAX_MB, str(body.max_mb), current.id, "知识库上传大小上限（MB）")
    set_value(db, svc.CFG_PREVIEW_CHARS, str(body.preview_max_chars), current.id, "知识库在线预览抽文本上限")
    audit(
        db,
        user_id=current.id,
        module="knowledge",
        action="knowledge_setting_update",
        detail={"ext": exts, "maxMb": body.max_mb},
    )
    db.commit()
    return {
        "allowedExt": svc.allowed_ext(db),
        "maxMb": svc.max_mb(db),
        "previewMaxChars": svc.preview_max_chars(db),
        "defaultAllowedExt": svc.DEFAULT_ALLOWED_EXT,
    }


# ---------------- 外部分享（无需登录） ----------------


def _load_link(db: Session, token: str) -> ShareLink:
    row = db.scalar(select(ShareLink).where(ShareLink.token == token, ShareLink.deleted == 0))
    if row is None:
        raise BizException(R.KNOWLEDGE_LINK_EXPIRED, "链接无效")
    return row


@router.get("/public/links/{token}")
def public_link_info(token: str, db: Session = Depends(get_db)):
    """分享链接信息（不含正文）。

    关闭后的链接仍能查到（状态 closed），便于访问者看到「链接已关闭」而不是通用报错。
    """
    link = db.scalar(select(ShareLink).where(ShareLink.token == token))
    if link is None:
        raise BizException(R.KNOWLEDGE_LINK_EXPIRED, "链接无效")
    if link.deleted or link.status == "closed":
        status = "closed"
    else:
        status = svc.link_status(db, link)
    return {
        "title": link.title,
        "perm": link.perm,
        "requirePhone": bool(link.require_phone),
        "status": status,
        "remark": link.remark,
        "expireAt": link.expire_at.strftime("%Y-%m-%d %H:%M:%S") if link.expire_at else "",
    }


@router.post("/public/links/{token}/code")
def public_link_send_code(
    token: str,
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    """发送短信验证码。"""
    link = _load_link(db, token)
    phone = str(body.get("phone", "") or "")
    out = svc.link_send_code(db, link, phone)
    svc.link_log(db, link, "code", phone, ip=client_ip(request))
    db.commit()
    return out


@router.post("/public/links/{token}/verify")
def public_link_verify(
    token: str,
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
):
    """校验验证码 → 返回访问令牌。"""
    link = _load_link(db, token)
    phone = str(body.get("phone", "") or "")
    code = str(body.get("code", "") or "")
    access = svc.link_verify(db, link, phone, code)
    svc.link_log(db, link, "verify", phone, ip=client_ip(request))
    db.commit()
    return {"token": access, "perm": link.perm, "title": link.title}


@router.get("/public/links/{token}/documents")
def public_link_documents(
    token: str,
    request: Request,
    access: str = Query("", description="访问令牌"),
    db: Session = Depends(get_db),
):
    """分享链接下的文档清单。"""
    link = _load_link(db, token)
    svc.link_check_token(db, link, access)
    items = svc.link_content(db, link)
    svc.link_log(db, link, "view", ip=client_ip(request))
    db.commit()
    return {"items": items, "perm": link.perm, "title": link.title}


@router.get("/public/links/{token}/raw/{did}")
def public_link_raw(
    token: str,
    did: int,
    request: Request,
    access: str = Query("", description="访问令牌"),
    db: Session = Depends(get_db),
):
    """下载分享链接下的文件。"""
    link = _load_link(db, token)
    svc.link_check_token(db, link, access)
    doc = db.get(Document, did)
    if not doc or doc.deleted:
        raise BizException(R.KNOWLEDGE_NOT_FOUND, "文档不存在")
    if link.resource_type == "document" and doc.id != link.resource_id:
        raise BizException(R.KNOWLEDGE_PERMISSION_DENIED)
    if link.resource_type == "folder" and doc.folder_id != link.resource_id:
        raise BizException(R.KNOWLEDGE_PERMISSION_DENIED)
    link.download_count = (link.download_count or 0) + 1
    svc.link_log(db, link, "download", ip=client_ip(request))
    db.commit()
    return _serve_file(doc, db, as_attachment=True)


@router.post("/public/links/{token}/upload")
def public_link_upload(
    token: str,
    request: Request,
    access: str = Query("", description="访问令牌"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """外部人员上传文件到分享文件夹。"""
    link = _load_link(db, token)
    svc.link_check_token(db, link, access)
    if link.perm not in ("upload", "edit"):
        raise BizException(R.KNOWLEDGE_PERMISSION_DENIED, "该链接不允许上传")
    if link.max_upload and (link.upload_count or 0) >= link.max_upload:
        raise BizException(R.KNOWLEDGE_INVALID_STATE, "上传次数已达上限")
    if link.resource_type != "folder":
        raise BizException(R.KNOWLEDGE_INVALID_STATE, "该链接不支持上传")
    file_row = svc.store_file(db, file.filename or "file", file.file.read(), None)
    doc = svc.create_document(
        db,
        title=(file.filename or "上传文件").rsplit(".", 1)[0],
        space_id=db.get(Folder, link.resource_id).space_id,
        user=None,
        file_row=file_row,
        folder_id=link.resource_id,
        status="published",
        version_comment="外部上传",
    )
    link.upload_count = (link.upload_count or 0) + 1
    svc.link_log(db, link, "upload", file_name=file.filename or "", ip=client_ip(request))
    db.commit()
    return {"id": doc.id, "title": doc.title}

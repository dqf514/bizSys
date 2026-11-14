"""AI 中心端点：/admin/ai/* 用量监控与设置（admin:ai:*），/ai/capabilities 登录可用的能力探测。"""

from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.aicenter import schemas as S
from app.modules.aicenter import service as svc
from app.modules.aicenter.models import KnowledgeEntry
from app.modules.auth.models import User
from app.services.excel import export_xlsx, now_filename

router = APIRouter(prefix="/admin/ai", tags=["admin-ai"], route_class=EnvelopeRoute)
cap_router = APIRouter(prefix="/ai", tags=["ai"], route_class=EnvelopeRoute)


@router.get("/usage")
def list_usage(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    _: User = Depends(require_perm("admin:ai:usage")),
    db: Session = Depends(get_db),
):
    return svc.list_usage(db, PageParams(page=page, size=size), request.query_params)


@router.get("/usage/export")
def export_usage(
    request: Request,
    current: User = Depends(require_perm("admin:ai:usage:export")),
    db: Session = Depends(get_db),
):
    rows = svc.usage_export_rows(db, request.query_params)
    payload = export_xlsx(rows, svc.EXPORT_COLUMNS, "ai_usage")
    record(db, user_id=current.id, module="admin", action="ai_usage_export", detail={"count": len(rows)})
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('ai_usage')}"},
    )


@router.get("/stats")
def ai_stats(
    days: int = Query(30, ge=1, le=90),
    _: User = Depends(require_perm("admin:ai:usage")),
    db: Session = Depends(get_db),
):
    return svc.stats(db, days)


@router.get("/settings")
def get_center_settings(
    _: User = Depends(require_perm("admin:ai:settings")),
    db: Session = Depends(get_db),
):
    return svc.center_settings_out(db)


@router.put("/settings")
def put_center_settings(
    body: S.AiCenterSettingsIn,
    current: User = Depends(require_perm("admin:ai:settings")),
    db: Session = Depends(get_db),
):
    data = svc.update_center_settings(db, body, current.id)
    record(db, user_id=current.id, module="admin", action="ai_settings_update", detail=body.model_dump())
    db.commit()
    return data


@router.get("/prompts")
def list_prompts(
    _: User = Depends(require_perm("admin:ai:settings")),
):
    """提示词注册表只读列表（版本与模板预览，集中维护在 services/prompts.py，不提供在线编辑）。"""
    return svc.list_prompts()


@cap_router.get("/capabilities")
def ai_capabilities(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """登录即可：前端按此显隐 AI 入口（未配置/功能停用时给明确提示而不是静默失败）。"""
    return svc.capabilities(db)


@cap_router.post("/nl-query")
def nl_query(
    body: S.NlQueryIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """自然语言问数：登录可用；AI 只产白名单意图，后端按模板执行并按域校验列表权限。"""
    from app.modules.aicenter import nl_query as nlq

    data = nlq.ask(
        db, current, body.question.strip(),
        body.context.model_dump() if body.context else None,
    )
    record(db, user_id=current.id, module="ai", action="ai_nl_query",
           detail={"question": body.question[:200], "domain": data["domain"]})
    db.commit()
    return data


# ---------------- AI 全局助手 / 每日摘要 / 知识库问答（登录可用） ----------------


@cap_router.post("/assistant")
def ai_assistant(
    body: S.AssistantIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """全局助手：意图路由（问数/导航/指引）。只读接口，不执行任何业务写操作。"""
    from app.modules.aicenter import assistant

    data = assistant.chat(db, current, body.message, body.menus)
    record(db, user_id=current.id, module="ai", action="ai_assistant",
           detail={"message": body.message[:200], "type": data["type"]})
    db.commit()
    return data


@cap_router.get("/daily-digest")
def daily_digest(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """今日待办摘要：聚合审批/任务/临期 → AI 一段话（不可用时回退模板摘要）。"""
    from app.modules.aicenter import digest

    return digest.daily_digest(db, current)


@cap_router.post("/daily-digest/push")
def daily_digest_push(
    body: S.DigestPushIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """摘要推送给自己：企微就绪且已绑定 → 企微；否则站内通知（留痕 sys_notify + 审计）。"""
    from app.modules.aicenter import digest

    data = digest.push_digest(db, current, body.summary.strip(), [h.strip() for h in body.highlights if h.strip()])
    record(db, user_id=current.id, module="ai", action="ai_digest_push", detail={"channel": data["channel"]})
    db.commit()
    return data


@cap_router.post("/knowledge/ask")
def knowledge_ask(
    body: S.KnowledgeAskIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """知识库问答：检索命中条目 → AI 回答并标注来源；无 AI 时降级为原文展示。"""
    from app.modules.aicenter import knowledge

    return knowledge.ask(db, current, body.question)


@cap_router.get("/knowledge/search")
def knowledge_search(
    q: str = Query("", max_length=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """知识库关键词搜索（降级/纯检索入口）。"""
    from app.modules.aicenter import knowledge

    return knowledge.search(db, q.strip())


# ---------------- 知识库管理（admin:ai:knowledge） ----------------


@router.get("/knowledge")
def knowledge_list(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    _: User = Depends(require_perm("admin:ai:knowledge")),
    db: Session = Depends(get_db),
):
    from app.modules.aicenter import knowledge

    q = (request.query_params.get("q") or "").strip()
    category = (request.query_params.get("category") or "").strip()
    return knowledge.list_entries(db, PageParams(page=page, size=size), q, category)


@router.post("/knowledge", status_code=201)
def knowledge_create(
    body: S.KnowledgeEntryIn,
    current: User = Depends(require_perm("admin:ai:knowledge")),
    db: Session = Depends(get_db),
):
    from app.modules.aicenter import knowledge

    e = knowledge.create_entry(db, body, current)
    record(db, user_id=current.id, module="admin", action="ai_knowledge_create",
           biz_type="ai_knowledge", biz_id=e.id, detail={"title": e.title})
    db.commit()
    return {"id": e.id}


@router.put("/knowledge/{kid}")
def knowledge_update(
    kid: int,
    body: S.KnowledgeEntryIn,
    current: User = Depends(require_perm("admin:ai:knowledge")),
    db: Session = Depends(get_db),
):
    from app.modules.aicenter import knowledge

    e = db.get(KnowledgeEntry, kid)
    if not e or e.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    knowledge.update_entry(db, e, body, current)
    record(db, user_id=current.id, module="admin", action="ai_knowledge_update",
           biz_type="ai_knowledge", biz_id=e.id, detail={"title": e.title})
    db.commit()
    return {"id": e.id}


@router.delete("/knowledge/{kid}", status_code=204)
def knowledge_delete(
    kid: int,
    current: User = Depends(require_perm("admin:ai:knowledge")),
    db: Session = Depends(get_db),
):
    e = db.get(KnowledgeEntry, kid)
    if not e or e.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    e.deleted = 1
    record(db, user_id=current.id, module="admin", action="ai_knowledge_delete",
           biz_type="ai_knowledge", biz_id=e.id, detail={"title": e.title})
    db.commit()


@router.post("/knowledge/{kid}/attachment")
def knowledge_attachment_upload(
    kid: int,
    file: UploadFile,
    current: User = Depends(require_perm("admin:ai:knowledge")),
    db: Session = Depends(get_db),
):
    from app.modules.aicenter import knowledge

    e = db.get(KnowledgeEntry, kid)
    if not e or e.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    knowledge.save_attachment(db, e, file.filename or "", file.file.read())
    record(db, user_id=current.id, module="admin", action="ai_knowledge_attachment",
           biz_type="ai_knowledge", biz_id=e.id, detail={"file": file.filename})
    db.commit()
    return {"id": e.id, "attachmentName": e.attachment_name}


@router.get("/knowledge/{kid}/attachment")
def knowledge_attachment_download(
    kid: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """附件下载：登录即可（问答页可查阅条目附件）。"""
    from urllib.parse import quote

    from app.modules.aicenter import knowledge

    e = db.get(KnowledgeEntry, kid)
    if not e or e.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    dest = knowledge.attachment_file(e)
    return Response(
        dest.read_bytes(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(e.attachment_name or 'file')}"},
    )

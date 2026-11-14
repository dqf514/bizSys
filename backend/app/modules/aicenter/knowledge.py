"""AI 知识库：条目 CRUD / 关键词检索 / AI 问答（无 AI 时降级为关键词搜索展示原文）。"""

import json
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.core import response as R
from app.core.config import settings
from app.core.exceptions import BizException
from app.modules.aicenter.models import KnowledgeEntry
from app.modules.auth.models import User
from app.services import ai as ai_svc
from app.services import prompts

TOP_K = 3


def _entry_out(e: KnowledgeEntry, excerpt: str = "") -> dict:
    return {
        "id": e.id,
        "title": e.title,
        "category": e.category,
        "content": e.content,
        "excerpt": excerpt,
        "attachmentName": e.attachment_name or "",
        "hasAttachment": bool(e.attachment_path),
        "createTime": str(e.create_time)[:19] if e.create_time else "",
        "updateTime": str(e.update_time)[:19] if e.update_time else "",
    }


# ---------------- 检索 ----------------


def _keywords(question: str) -> list[str]:
    """检索关键词：按标点/空白分词；长词（>4 字）展开为 2-gram，兼容无空格中文问句。"""
    import re

    toks = [w for w in re.split(r"[\s？?，,。.!！；;：:、]+", question.strip()) if len(w) >= 2]
    kws: list[str] = []
    for w in toks:
        kws.append(w)
        if len(w) > 4:
            kws += [w[i : i + 2] for i in range(len(w) - 1)]
    if not kws and question.strip():
        q = question.strip()
        kws = [q[i : i + 2] for i in range(len(q) - 1)] or [q[:32]]
    return kws[:30]


def search_entries(db: Session, question: str, limit: int = TOP_K) -> list[KnowledgeEntry]:
    """关键词检索：按问题分词在标题/分类/正文中匹配，按命中数排序。"""
    keywords = _keywords(question)
    if not keywords:
        return []
    rows = list(
        db.scalars(select(KnowledgeEntry).where(KnowledgeEntry.deleted == 0).order_by(KnowledgeEntry.id)).all()
    )
    scored: list[tuple[int, KnowledgeEntry]] = []
    for e in rows:
        hay = f"{e.title}\n{e.category}\n{e.content}"
        score = sum(hay.count(kw) * (3 if kw in e.title else 1) for kw in keywords)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    return [e for _, e in scored[:limit]]


def _excerpt(e: KnowledgeEntry, keywords: list[str] | None = None, width: int = 120) -> str:
    text = (e.content or "").strip()
    if not text:
        return ""
    return text[:width] + ("…" if len(text) > width else "")


def search(db: Session, question: str) -> dict:
    """降级搜索（也是问答的检索层）：命中条目 + 摘要。"""
    entries = search_entries(db, question, limit=5)
    return {"entries": [_entry_out(e, _excerpt(e)) for e in entries]}


# ---------------- 问答 ----------------


def ask(db: Session, user: User, question: str) -> dict:
    """检索相关条目 → AI 基于条目回答并标注来源；AI 不可用/功能关闭时降级为原文展示。"""
    question = question.strip()
    if not question:
        raise BizException(R.GENERIC_PARAM, "请输入问题")
    entries = search_entries(db, question)
    sources = [{"id": e.id, "title": e.title, "category": e.category} for e in entries]

    if not ai_svc.feature_enabled(db, "knowledge"):
        return {
            "answer": "",
            "sources": sources,
            "entries": [_entry_out(e, _excerpt(e)) for e in entries],
            "degraded": True,
        }

    ctx = "\n\n".join(
        f"[条目 {e.id}] {e.title}（{e.category or '未分类'}）\n{e.content[:1500]}" for e in entries
    ) or "（无命中条目）"
    messages = [
        {"role": "system", "content": prompts.get("knowledge")["system"]},
        {"role": "user", "content": f"知识库条目：\n{ctx}\n\n问题：{question}"},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="knowledge", messages=messages, user=user,
            biz_type="knowledge", prompt_version=prompts.feature_version("knowledge"),
            json_mode=True, max_tokens=800,
        )
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        answer = str(parsed.get("answer") or "").strip()
        used = {int(i) for i in (parsed.get("usedIds") or []) if str(i).isdigit() or isinstance(i, int)}
    except (ai_svc.AiUnavailable, ValueError, TypeError):
        return {
            "answer": "",
            "sources": sources,
            "entries": [_entry_out(e, _excerpt(e)) for e in entries],
            "degraded": True,
        }
    valid_ids = {e.id for e in entries}
    sources = [s for s in sources if s["id"] in (used & valid_ids)] or sources
    return {"answer": answer[:2000], "sources": sources, "entries": [], "degraded": False}


# ---------------- 管理端 CRUD ----------------


def list_entries(db: Session, page: PageParams, q: str, category: str) -> dict:
    conds = [KnowledgeEntry.deleted == 0]
    if q:
        like = f"%{q}%"
        conds.append(
            KnowledgeEntry.title.like(like)
            | KnowledgeEntry.category.like(like)
            | KnowledgeEntry.content.like(like)
        )
    if category:
        conds.append(KnowledgeEntry.category == category)
    total = db.scalar(select(func.count(KnowledgeEntry.id)).where(*conds)) or 0
    rows = db.scalars(
        select(KnowledgeEntry).where(*conds)
        .order_by(KnowledgeEntry.id.desc())
        .offset((page.page - 1) * page.size)
        .limit(page.size)
    ).all()
    return {"items": [_entry_out(e) for e in rows], "total": total, "page": page.page, "size": page.size}


def create_entry(db: Session, body, user: User) -> KnowledgeEntry:
    e = KnowledgeEntry(
        title=body.title.strip(),
        category=body.category.strip(),
        content=body.content.strip(),
        create_by=user.id,
    )
    db.add(e)
    db.flush()
    return e


def update_entry(db: Session, e: KnowledgeEntry, body, user: User) -> KnowledgeEntry:
    e.title = body.title.strip()
    e.category = body.category.strip()
    e.content = body.content.strip()
    e.update_by = user.id
    db.flush()
    return e


def save_attachment(db: Session, e: KnowledgeEntry, filename: str, data: bytes) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.upload_ext_set:
        raise BizException(R.GENERIC_PARAM, f"不支持的文件类型：{ext or '无扩展名'}")
    if not data:
        raise BizException(R.GENERIC_PARAM, "文件为空")
    if len(data) > settings.upload_max_mb * 1024 * 1024:
        raise BizException(R.GENERIC_PARAM, f"文件超过大小上限 {settings.upload_max_mb}MB")
    # 旧附件清理
    if e.attachment_path:
        old = Path(settings.upload_dir) / e.attachment_path
        old.unlink(missing_ok=True)
    rel = Path("knowledge") / f"{uuid.uuid4().hex}"
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    e.attachment_path = str(rel)
    e.attachment_name = filename or "file"
    db.flush()


def attachment_file(e: KnowledgeEntry) -> Path:
    if not e.attachment_path:
        raise BizException(R.GENERIC_NOT_FOUND, "该条目无附件")
    dest = Path(settings.upload_dir) / e.attachment_path
    if not dest.exists():
        raise BizException(R.GENERIC_NOT_FOUND, "附件文件已丢失")
    return dest

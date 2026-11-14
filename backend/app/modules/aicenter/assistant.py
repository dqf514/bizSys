"""AI 全局助手：意图路由（问数/导航/指引）。只读——不执行任何业务写操作。

- query：复用 nl_query 白名单问数（自身再做一次权限校验）；
- navigate：候选菜单取自服务端权限菜单树与前端传入标题的交集，AI 选中的路径
  必须在候选集内才返回（防越权/幻觉跳转），前端确认后才跳转；
- guide：基于知识库检索条目回答（复用 knowledge.ask 的检索与标注来源）。
AI 未配置时降级：菜单关键词命中→导航建议，否则知识库关键词搜索。
"""

import json

from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.admin import service as admin_svc
from app.modules.aicenter import knowledge as kb
from app.modules.auth.models import User
from app.services import ai as ai_svc

ASSISTANT_PROMPT_VERSION = "v1"
ASSISTANT_SYSTEM = (
    "你是企业系统的全局助手。把用户消息分类为三种意图之一，输出严格 JSON：\n"
    '1) 查数 query（询问业务数据/统计/数量/金额）：{"type":"query","question":"改写后的完整问题"}\n'
    '2) 导航 navigate（想打开某个页面/功能）：{"type":"navigate","path":"候选菜单中最匹配的一项的 path"}\n'
    '3) 指引 guide（询问怎么操作/流程/规则）：{"type":"guide","question":"改写后的完整问题"}\n'
    "导航只能从给定的候选菜单中选择 path，不要编造路径。只输出 JSON。"
)

# 深链静态路由（不占菜单但可导航）
STATIC_PATHS = ("/approval", "/profile", "/ai/knowledge", "/workbench")


def _flatten_menus(tree: list[dict]) -> list[dict]:
    out: list[dict] = []

    def walk(nodes):
        for n in nodes:
            if n.get("menuType") == "menu" and n.get("path"):
                out.append({"title": n.get("name") or "", "titleKey": n.get("titleKey") or "", "path": n["path"]})
            if n.get("children"):
                walk(n["children"])

    walk(tree)
    return out


def _candidates(db: Session, user: User, client_menus: list[dict]) -> list[dict]:
    """服务端权限菜单 ∩ 前端传入的本地化标题；path 以服务端为准。"""
    server = _flatten_menus(admin_svc.menu_tree_for_user(db, user))
    titles = {}
    for m in client_menus[:100]:
        p, t = str(m.get("path") or "")[:255], str(m.get("title") or "")[:64]
        if p and t:
            titles.setdefault(p, t)
    out = []
    for s in server:
        out.append({"path": s["path"], "title": titles.get(s["path"]) or s["title"] or s["path"]})
    known = {s["path"] for s in server}
    for p, t in titles.items():
        if p not in known and p in STATIC_PATHS:
            out.append({"path": p, "title": t})
    return out[:80]


def _navigate_reply(path: str, title: str) -> dict:
    return {"type": "navigate", "text": "", "path": path, "menuName": title, "data": None, "sources": []}


def _guide_reply(db: Session, user: User, question: str) -> dict:
    ans = kb.ask(db, user, question)
    return {
        "type": "guide",
        "text": ans["answer"] or "",
        "path": "",
        "menuName": "",
        "data": None,
        "sources": ans["sources"],
        "entries": ans.get("entries") or [],
        "degraded": ans["degraded"],
    }


def _query_reply(db: Session, user: User, question: str) -> dict:
    from app.modules.aicenter import nl_query as nlq

    data = nlq.ask(db, user, question)
    return {
        "type": "query",
        "text": data["text"],
        "path": data.get("link") or "",
        "menuName": "",
        "data": data,
        "sources": [],
    }


def _fallback_route(db: Session, user: User, message: str, cands: list[dict]) -> dict:
    """无 AI 时的降级路由：菜单标题关键词命中 → 导航；否则知识库搜索。"""
    for c in cands:
        if c["title"] and (c["title"] in message or message in c["title"]):
            return _navigate_reply(c["path"], c["title"])
    return _guide_reply(db, user, message)


def chat(db: Session, user: User, message: str, client_menus: list[dict]) -> dict:
    message = message.strip()
    if not message:
        raise BizException(R.GENERIC_PARAM, "请输入内容")
    cands = _candidates(db, user, client_menus)

    if not ai_svc.feature_enabled(db, "assistant"):
        return _fallback_route(db, user, message, cands)

    menu_lines = "\n".join(f"- {c['title']}：{c['path']}" for c in cands) or "（无）"
    messages = [
        {"role": "system", "content": ASSISTANT_SYSTEM},
        {"role": "user", "content": f"候选菜单：\n{menu_lines}\n\n用户消息：{message}"},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="assistant", messages=messages, user=user,
            biz_type="assistant", prompt_version=ASSISTANT_PROMPT_VERSION,
            json_mode=True, max_tokens=500,
        )
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
    except ai_svc.AiUnavailable:
        return _fallback_route(db, user, message, cands)
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请换个说法试试") from exc

    itype = str(parsed.get("type") or "")
    if itype == "query":
        return _query_reply(db, user, str(parsed.get("question") or message))
    if itype == "navigate":
        path = str(parsed.get("path") or "")
        hit = next((c for c in cands if c["path"] == path), None)
        if hit:
            return _navigate_reply(hit["path"], hit["title"])
        # 幻觉路径：不落导航，降级为指引
        return _guide_reply(db, user, message)
    if itype == "guide":
        return _guide_reply(db, user, str(parsed.get("question") or message))
    raise BizException(R.AI_PARSE_FAILED, "AI 意图无法识别，请换个说法试试")

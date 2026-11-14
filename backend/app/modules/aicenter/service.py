"""AI 中心业务：用量统计（SQL 聚合）/ 明细分页导出 / 功能开关与配额设置。"""

import json
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.filters import apply_list_filters
from app.common.pagination import PageParams, page_result
from app.modules.aicenter import schemas as S
from app.modules.aicenter.models import AiUsageLog
from app.modules.settings.service import get_value, set_value
from app.services import ai as ai_svc
from app.services import masking as masking_svc
from app.services import prompts

STATUS_CN = {"success": "成功", "error": "失败", "fallback": "回退"}


def _row_out(r: AiUsageLog) -> dict:
    return {
        "id": r.id,
        "userName": r.user_name,
        "feature": r.feature,
        "model": r.model,
        "promptTokens": r.prompt_tokens,
        "completionTokens": r.completion_tokens,
        "totalTokens": (r.prompt_tokens or 0) + (r.completion_tokens or 0),
        "cost": float(r.cost) if r.cost is not None else None,
        "masking": r.masking,
        "durationMs": r.duration_ms,
        "status": r.status,
        "error": r.error,
        "bizType": r.biz_type,
        "bizId": r.biz_id,
        "createTime": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
    }


def list_usage(db: Session, pp: PageParams, query_params) -> dict:
    stmt, total = apply_list_filters(
        select(AiUsageLog),
        AiUsageLog,
        query_params,
        db,
        pp,
        search_cols=["user_name", "error"],
        filter_cols={"feature", "status"},
        range_cols={"create_time"},
        sort_cols={"id", "create_time", "feature", "status", "user_name"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return page_result([_row_out(r) for r in rows], total, pp.page, pp.size)


def usage_export_rows(db: Session, query_params) -> list[dict]:
    rows: list[dict] = []
    total = None
    page = 1
    while total is None or len(rows) < total:
        data = list_usage(db, PageParams(page=page, size=200), query_params)
        total = data["total"]
        rows.extend(data["items"])
        if not data["items"] or page > 500:  # 防呆上限 10 万行
            break
        page += 1
    return rows


EXPORT_COLUMNS = [
    {"key": "createTime", "label": "时间", "width": 20},
    {"key": "userName", "label": "用户", "width": 14},
    {"key": "feature", "label": "功能", "width": 16},
    {"key": "model", "label": "模型", "width": 18},
    {"key": "promptTokens", "label": "Prompt Tokens", "width": 14},
    {"key": "completionTokens", "label": "Completion Tokens", "width": 16},
    {"key": "durationMs", "label": "耗时(ms)", "width": 10},
    {"key": "cost", "label": "估算成本", "width": 12, "formatter": lambda v, _r: "-" if v is None else f"{v:.6f}"},
    {"key": "masking", "label": "脱敏级别", "width": 10},
    {"key": "status", "label": "状态", "width": 10, "formatter": lambda v, _r: STATUS_CN.get(v, v)},
    {"key": "error", "label": "错误/回退原因", "width": 30},
]


def stats(db: Session, days: int = 30) -> dict:
    """统计卡 + 趋势 + 按功能/用户/模型聚合，全部 SQL 聚合不拉全量。"""
    days = max(1, min(days, 90))
    base = [AiUsageLog.deleted == 0]

    total_calls = db.scalar(select(func.count(AiUsageLog.id)).where(*base)) or 0
    by_status = dict(
        db.execute(select(AiUsageLog.status, func.count()).where(*base).group_by(AiUsageLog.status)).all()
    )
    total_tokens = db.scalar(
        select(func.coalesce(func.sum(AiUsageLog.prompt_tokens + AiUsageLog.completion_tokens), 0)).where(
            *base, AiUsageLog.status == ai_svc.USAGE_SUCCESS
        )
    ) or 0
    active_users = db.scalar(
        select(func.count(func.distinct(AiUsageLog.user_id))).where(*base, AiUsageLog.user_id.isnot(None))
    ) or 0
    avg_ms = db.scalar(
        select(func.coalesce(func.avg(AiUsageLog.duration_ms), 0)).where(
            *base, AiUsageLog.status == ai_svc.USAGE_SUCCESS
        )
    ) or 0
    total_cost = db.scalar(
        select(func.coalesce(func.sum(AiUsageLog.cost), 0)).where(
            *base, AiUsageLog.status == ai_svc.USAGE_SUCCESS, AiUsageLog.cost.isnot(None)
        )
    ) or 0

    since = date.today() - timedelta(days=days - 1)
    trend_rows = db.execute(
        select(
            func.date(AiUsageLog.create_time),
            func.count(),
            func.coalesce(func.sum(AiUsageLog.prompt_tokens + AiUsageLog.completion_tokens), 0),
        )
        .where(*base, func.date(AiUsageLog.create_time) >= since)
        .group_by(func.date(AiUsageLog.create_time))
        .order_by(func.date(AiUsageLog.create_time))
    ).all()
    trend_map = {str(d): (c, int(tk)) for d, c, tk in trend_rows}
    trend = [
        {"date": str(since + timedelta(days=i)), "calls": trend_map.get(str(since + timedelta(days=i)), (0, 0))[0],
         "tokens": trend_map.get(str(since + timedelta(days=i)), (0, 0))[1]}
        for i in range(days)
    ]

    by_feature = [
        {"feature": f, "calls": c, "tokens": int(tk)}
        for f, c, tk in db.execute(
            select(
                AiUsageLog.feature,
                func.count(),
                func.coalesce(func.sum(AiUsageLog.prompt_tokens + AiUsageLog.completion_tokens), 0),
            )
            .where(*base)
            .group_by(AiUsageLog.feature)
            .order_by(func.count().desc())
        ).all()
    ]
    by_user = [
        {"userName": u or "-", "calls": c, "tokens": int(tk)}
        for u, c, tk in db.execute(
            select(
                AiUsageLog.user_name,
                func.count(),
                func.coalesce(func.sum(AiUsageLog.prompt_tokens + AiUsageLog.completion_tokens), 0),
            )
            .where(*base)
            .group_by(AiUsageLog.user_name)
            .order_by(func.count().desc())
            .limit(10)
        ).all()
    ]
    by_model = [
        {"model": m or "-", "calls": c, "tokens": int(tk), "cost": float(cost)}
        for m, c, tk, cost in db.execute(
            select(
                AiUsageLog.model,
                func.count(),
                func.coalesce(func.sum(AiUsageLog.prompt_tokens + AiUsageLog.completion_tokens), 0),
                func.coalesce(func.sum(AiUsageLog.cost), 0),
            )
            .where(*base, AiUsageLog.model != "")
            .group_by(AiUsageLog.model)
            .order_by(func.count().desc())
        ).all()
    ]

    success = int(by_status.get(ai_svc.USAGE_SUCCESS, 0))
    done = success + int(by_status.get(ai_svc.USAGE_ERROR, 0))
    return {
        "days": days,
        "cards": {
            "totalCalls": int(total_calls),
            "successCalls": success,
            "errorCalls": int(by_status.get(ai_svc.USAGE_ERROR, 0)),
            "fallbackCalls": int(by_status.get(ai_svc.USAGE_FALLBACK, 0)),
            "totalTokens": int(total_tokens),
            "totalCost": float(total_cost),
            "successRate": round(success / done * 100, 1) if done else 0.0,
            "activeUsers": int(active_users),
            "avgDurationMs": int(avg_ms),
        },
        "trend": trend,
        "byFeature": by_feature,
        "byUser": by_user,
        "byModel": by_model,
    }


# ---------------- 功能开关 / 配额 / 脱敏 / 单价设置 ----------------


def _model_prices_out(db: Session) -> list[dict]:
    raw = get_value(db, ai_svc.KEY_MODEL_PRICES)
    if not raw:
        return []
    try:
        prices = json.loads(raw)
    except ValueError:
        return []
    return [
        {"model": m, "input": float(v["input"]), "output": float(v["output"])}
        for m, v in prices.items()
        if isinstance(v, dict) and "input" in v and "output" in v
    ]


def center_settings_out(db: Session) -> dict:
    def qi(key: str) -> int:
        try:
            return max(0, int(get_value(db, key) or 0))
        except ValueError:
            return 0

    return {
        "enabled": ai_svc.ai_ready(db),
        "features": {f: get_value(db, ai_svc.KEY_FEATURE_PREFIX + f) != "0" for f in ai_svc.FEATURES},
        "quota": {
            "userDailyCalls": qi(ai_svc.KEY_QUOTA_USER_CALLS),
            "userDailyTokens": qi(ai_svc.KEY_QUOTA_USER_TOKENS),
            "globalDailyTokens": qi(ai_svc.KEY_QUOTA_GLOBAL_TOKENS),
        },
        "masking": masking_svc.configured_level(db),
        "modelPrices": _model_prices_out(db),
    }


def update_center_settings(db: Session, body: S.AiCenterSettingsIn, user_id: int) -> dict:
    if body.features is not None:
        for f in ai_svc.FEATURES:
            if f in body.features:
                set_value(
                    db, ai_svc.KEY_FEATURE_PREFIX + f, "1" if body.features[f] else "0", user_id, f"AI 功能开关 {f}"
                )
    if body.quota is not None:
        q = body.quota
        set_value(db, ai_svc.KEY_QUOTA_USER_CALLS, str(q.userDailyCalls), user_id, "AI 每用户每日调用次数配额")
        set_value(db, ai_svc.KEY_QUOTA_USER_TOKENS, str(q.userDailyTokens), user_id, "AI 每用户每日 token 配额")
        set_value(db, ai_svc.KEY_QUOTA_GLOBAL_TOKENS, str(q.globalDailyTokens), user_id, "AI 全局每日 token 预算")
    if body.masking is not None:
        set_value(db, masking_svc.KEY_MASKING_LEVEL, body.masking, user_id, "AI 出网脱敏级别")
    if body.modelPrices is not None:
        # 同模型重复行以后者为准；空列表清空配置
        prices = {p.model.strip(): {"input": p.input, "output": p.output} for p in body.modelPrices if p.model.strip()}
        set_value(
            db, ai_svc.KEY_MODEL_PRICES, json.dumps(prices, ensure_ascii=False), user_id, "AI 模型单价（每千 token）"
        )
    return center_settings_out(db)


def list_prompts() -> list[dict]:
    """提示词注册表只读列表。"""
    return prompts.list_prompts()


def capabilities(db: Session) -> dict:
    """登录用户可见的 AI 能力探测（前端决定入口显隐/提示）。"""
    ready = ai_svc.ai_ready(db)
    cfg = ai_svc.ai_config(db)
    return {
        "enabled": ready,
        "visionModel": cfg["vision_model"] or cfg["model"] if ready else "",
        "features": {f: (ready and get_value(db, ai_svc.KEY_FEATURE_PREFIX + f) != "0") for f in ai_svc.FEATURES},
    }

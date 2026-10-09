"""列表检索参数解析（白名单驱动，全模块复用）。

支持：?page=1&size=20&sort=updated_at:desc&status=xx&q=关键词
      &filters[customer_id]=1&range[end_date]=2026-01-01|2026-12-31
用法：
    stmt, total = apply_list_filters(
        select(Model), Model, params,
        search_cols=["name", "customer_no"],       # q 模糊匹配列
        filter_cols={"status", "customer_id"},     # 等值过滤白名单
        range_cols={"end_date"},                   # 区间过滤白名单
        default_sort=("updated_at", "desc"),
        search_cols_mode="or",
    )
"""

from datetime import datetime

from sqlalchemy import Select, func, or_
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.core import response as R
from app.core.exceptions import BizException


def _parse_sort(raw: str | None, allowed: set[str], default: tuple[str, str]):
    if not raw:
        return default
    col, _, direction = raw.partition(":")
    col = col.strip()
    if col not in allowed:
        return default
    return col, (direction.lower() == "asc") and "asc" or "desc"


def apply_list_filters(
    stmt: Select,
    model,
    query_params,
    db: Session,
    page: PageParams,
    search_cols: list[str] | None = None,
    filter_cols: set[str] | None = None,
    range_cols: set[str] | None = None,
    sort_cols: set[str] | None = None,
    default_sort: tuple[str, str] = ("update_time", "desc"),
    include_deleted: bool = False,
    extra_where: list | None = None,
) -> tuple[Select, int]:
    """返回 (带分页的 stmt, total)。query_params 为 starlette QueryParams。"""
    filter_cols = filter_cols or set()
    range_cols = range_cols or set()
    sort_cols = sort_cols or {"update_time", "create_time", "id"}
    search_cols = search_cols or []

    conditions: list = []
    if not include_deleted and hasattr(model, "deleted"):
        conditions.append(model.deleted == 0)

    q = (query_params.get("q") or "").strip()
    if q and search_cols:
        likes = [getattr(model, c).like(f"%{q}%") for c in search_cols if hasattr(model, c)]
        if likes:
            conditions.append(or_(*likes))

    # status 单独放行（状态页签）
    status = query_params.get("status")
    if status and hasattr(model, "status"):
        if status != "all":
            conditions.append(model.status == status)

    for key in filter_cols:
        raw = query_params.get(f"filters[{key}]")
        if raw not in (None, "") and hasattr(model, key):
            if "," in raw:
                conditions.append(getattr(model, key).in_(raw.split(",")))
            else:
                conditions.append(getattr(model, key) == raw)

    for key in range_cols:
        raw = query_params.get(f"range[{key}]")
        if raw and hasattr(model, key):
            start, _, end = raw.partition("|")
            col = getattr(model, key)
            if start:
                conditions.append(col >= _parse_date(start))
            if end:
                conditions.append(col <= _parse_date(end))

    if extra_where:
        conditions.extend(extra_where)

    if conditions:
        stmt = stmt.where(*conditions)

    from sqlalchemy import select as sa_select

    count_sub = stmt.order_by(None).subquery()
    total = db.scalar(sa_select(func.count()).select_from(count_sub)) or 0

    col_name, direction = _parse_sort(query_params.get("sort"), sort_cols, default_sort)
    col = getattr(model, col_name)
    stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc())
    stmt = stmt.offset((page.page - 1) * page.size).limit(page.size)
    return stmt, total


def _parse_date(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise BizException(R.GENERIC_PARAM, f"非法日期格式：{s}")


__all__ = ["apply_list_filters", "_parse_date"]

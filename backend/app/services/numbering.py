"""统一编号服务：规则可配（前缀+结构化日期位+流水），分类映射 + 兜底规则，DB 行锁防重（并发安全）。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.admin.models import NumberRule, NumberSeq

_CYCLE_FORMAT = {"daily": "%Y%m%d", "monthly": "%Y%m", "yearly": "%Y"}


def _period_key(rule: NumberRule, now: datetime) -> str:
    fmt = _CYCLE_FORMAT.get(rule.reset_cycle)
    return now.strftime(fmt) if fmt else "-"


def _date_part(rule: NumberRule, now: datetime) -> str:
    """结构化年/月/日位数优先；全 0 时回退兼容旧的 strftime date_format。"""
    parts = []
    if rule.year_digits:
        parts.append(now.strftime("%Y" if rule.year_digits == 4 else "%y"))
    if rule.month_digits:
        parts.append(now.strftime("%m"))
    if rule.day_digits:
        parts.append(now.strftime("%d"))
    if parts:
        return "".join(parts)
    if rule.date_format:
        return now.strftime(rule.date_format)
    return ""


def format_no(rule: NumberRule, period: str, seq: int) -> str:
    now = datetime.now()
    parts = [p for p in (rule.prefix, _date_part(rule, now), str(seq).rjust(rule.seq_len, "0")) if p]
    return (rule.separator or "").join(parts)


def resolve_rule(db: Session, biz_type: str, category: str | None = None) -> NumberRule | None:
    """精确匹配 biz_type+category_key；未命中回退 biz_type 兜底规则（category_key 为空）。"""
    stmt = select(NumberRule).where(
        NumberRule.biz_type == biz_type, NumberRule.enabled == 1, NumberRule.deleted == 0
    )
    if category:
        rule = db.scalar(stmt.where(NumberRule.category_key == category))
        if rule:
            return rule
    return db.scalar(stmt.where(NumberRule.category_key == ""))


def next_no(db: Session, biz_type: str, category: str | None = None) -> str:
    rule = resolve_rule(db, biz_type, category)
    if not rule:
        raise BizException(R.ADMIN_NUMBER_CONFLICT, f"编号规则不存在：{biz_type}")

    now = datetime.now()
    period = _period_key(rule, now)

    row = db.scalar(
        select(NumberSeq).where(NumberSeq.rule_id == rule.id, NumberSeq.period_key == period).with_for_update()
    )
    if row is None:
        try:
            with db.begin_nested():  # savepoint：并发首建撞唯一键只回滚本次插入
                row = NumberSeq(rule_id=rule.id, period_key=period, value=0)
                db.add(row)
                db.flush()
        except IntegrityError:
            # 另一事务已先行创建，重读并加行锁
            row = db.scalar(
                select(NumberSeq).where(NumberSeq.rule_id == rule.id, NumberSeq.period_key == period).with_for_update()
            )
    # seq_start：新周期/重置后首个号不低于起始值
    row.value = max(row.value + 1, rule.seq_start or 1)
    db.flush()
    return format_no(rule, period, row.value)


def preview_no(rule: NumberRule, seq: int | None = None) -> str:
    """管理页预览（不占号），默认取规则起始值。"""
    now = datetime.now()
    period = _period_key(rule, now)
    return format_no(rule, period, seq if seq is not None else (rule.seq_start or 1))


def reset_seq(db: Session, rule: NumberRule, value: int = 0) -> str:
    """把当前周期的序列计数器重置为 value（下个号 = max(value+1, seq_start)）。返回周期键。"""
    period = _period_key(rule, datetime.now())
    row = db.scalar(
        select(NumberSeq).where(NumberSeq.rule_id == rule.id, NumberSeq.period_key == period).with_for_update()
    )
    if row is None:
        row = NumberSeq(rule_id=rule.id, period_key=period, value=0)
        db.add(row)
        db.flush()
    row.value = value
    db.flush()
    return period

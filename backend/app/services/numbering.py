"""统一编号服务：规则可配（前缀+日期+序列），DB 行锁防重（并发安全）。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.admin.models import NumberRule, NumberSeq


def _period_key(rule: NumberRule, now: datetime) -> str:
    if rule.reset_cycle == "daily":
        return now.strftime("%Y%m%d")
    if rule.reset_cycle == "monthly":
        return now.strftime("%Y%m")
    return "-"


def format_no(rule: NumberRule, period: str, seq: int) -> str:
    now = datetime.now()
    date_part = now.strftime(rule.date_format) if rule.date_format else ""
    return f"{rule.prefix}{date_part}{str(seq).rjust(rule.seq_len, '0')}"


def next_no(db: Session, biz_type: str) -> str:
    rule = db.scalar(
        select(NumberRule).where(NumberRule.biz_type == biz_type, NumberRule.enabled == 1, NumberRule.deleted == 0)
    )
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
    row.value += 1
    db.flush()
    return format_no(rule, period, row.value)


def preview_no(rule: NumberRule, seq: int = 1) -> str:
    """管理页预览（不占号）。"""
    now = datetime.now()
    period = _period_key(rule, now)
    return format_no(rule, period, seq)

"""编号服务：格式 / 唯一 / 预览不占号。"""

from app.services.numbering import next_no, preview_no


def test_next_no_format_and_unique(db):
    a = next_no(db, "customer")
    b = next_no(db, "customer")
    assert a.startswith("CC") and b.startswith("CC")
    assert a != b
    db.rollback()


def test_contract_no_has_date(db):
    from datetime import datetime

    no = next_no(db, "contract")
    assert no.startswith("HT" + datetime.now().strftime("%Y%m%d"))
    db.rollback()


def test_preview_does_not_consume(db):
    from sqlalchemy import select

    from app.modules.admin.models import NumberSeq, NumberRule

    rule = db.scalar(select(NumberRule).where(NumberRule.biz_type == "customer"))
    before = db.scalar(select(NumberSeq).where(NumberSeq.rule_id == rule.id))
    before_val = before.value if before else 0
    preview_no(rule, 99)
    after = db.scalar(select(NumberSeq).where(NumberSeq.rule_id == rule.id))
    assert (after.value if after else 0) == before_val
    db.rollback()

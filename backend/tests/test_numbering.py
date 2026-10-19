"""编号服务：格式 / 唯一 / 预览不占号 / 分类映射与兜底 / 起始值 / 日期位数 / 重置序列 / 并发。"""

import threading
import uuid
from datetime import datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.admin.models import NumberRule, NumberSeq
from app.services.numbering import format_no, next_no, preview_no, reset_seq


def test_next_no_format_and_unique(db):
    a = next_no(db, "customer")
    b = next_no(db, "customer")
    assert a.startswith("CC") and b.startswith("CC")
    assert a != b
    db.rollback()


def test_contract_no_has_date(db):
    no = next_no(db, "contract")
    assert no.startswith("HT" + datetime.now().strftime("%Y%m%d"))
    db.rollback()


def test_preview_does_not_consume(db):
    rule = db.scalar(select(NumberRule).where(NumberRule.biz_type == "customer"))
    before = db.scalar(select(NumberSeq).where(NumberSeq.rule_id == rule.id))
    before_val = before.value if before else 0
    preview_no(rule, 99)
    after = db.scalar(select(NumberSeq).where(NumberSeq.rule_id == rule.id))
    assert (after.value if after else 0) == before_val
    db.rollback()


def test_category_hit_and_fallback(db):
    """contract+testing 命中 JC 分类规则；contract+sales 无分类规则回退 HT 兜底。"""
    today = datetime.now().strftime("%Y%m%d")
    no_jc = next_no(db, "contract", category="testing")
    assert no_jc.startswith("JC" + today)
    no_ht = next_no(db, "contract", category="sales")
    assert no_ht.startswith("HT" + today)
    no_none = next_no(db, "contract")
    assert no_none.startswith("HT" + today)
    db.rollback()


def test_seq_start_and_separator(db):
    rule = NumberRule(
        biz_type="ut_start",
        category_key="",
        prefix="QS",
        year_digits=2,
        month_digits=2,
        day_digits=0,
        seq_len=3,
        seq_start=100,
        separator="-",
        reset_cycle="none",
        enabled=1,
    )
    db.add(rule)
    db.flush()
    no = next_no(db, "ut_start")
    assert no == f"QS-{datetime.now().strftime('%y%m')}-100"
    no2 = next_no(db, "ut_start")
    assert no2.endswith("-101")
    db.rollback()


def test_date_digits_combinations():
    rule = NumberRule(prefix="T", year_digits=4, month_digits=0, day_digits=2, seq_len=2, seq_start=1, separator="")
    now = datetime.now()
    assert format_no(rule, "-", 5) == f"T{now.strftime('%Y')}{now.strftime('%d')}05"
    rule2 = NumberRule(prefix="", year_digits=0, month_digits=0, day_digits=0, seq_len=4, seq_start=1, separator="-")
    assert format_no(rule2, "-", 7) == "0007"  # 空前缀不参与拼接
    # 兼容旧 strftime 格式串
    rule3 = NumberRule(
        prefix="L", date_format="%Y%m", year_digits=0, month_digits=0, day_digits=0, seq_len=2, seq_start=1
    )
    assert format_no(rule3, "-", 1) == f"L{now.strftime('%Y%m')}01"


def test_reset_seq(db):
    rule = NumberRule(biz_type="ut_reset", category_key="", prefix="RS", seq_len=3, seq_start=1, enabled=1)
    db.add(rule)
    db.flush()
    first = next_no(db, "ut_reset")
    assert first.endswith("001")
    period = reset_seq(db, rule, 0)
    assert period == "-"
    again = next_no(db, "ut_reset")
    assert again.endswith("001")
    reset_seq(db, rule, 50)
    jumped = next_no(db, "ut_reset")
    assert jumped.endswith("051")
    db.rollback()


def test_reset_seq_respects_seq_start(db):
    rule = NumberRule(biz_type="ut_reset2", category_key="", prefix="RB", seq_len=3, seq_start=10, enabled=1)
    db.add(rule)
    db.flush()
    assert next_no(db, "ut_reset2").endswith("010")
    reset_seq(db, rule, 0)
    # 归 0 后下个号仍从 seq_start 开始
    assert next_no(db, "ut_reset2").endswith("010")
    db.rollback()


def test_next_no_concurrent_unique():
    """多线程并发取号不重复（DB 行锁）。"""
    db = SessionLocal()
    biz = f"utc{uuid.uuid4().hex[:10]}"  # uuid 保证跨运行幂等（本用例 commit 不回滚）
    try:
        rule = NumberRule(biz_type=biz, category_key="", prefix="CC", seq_len=6, seq_start=1, enabled=1)
        db.add(rule)
        db.commit()
    finally:
        db.close()

    numbers: list[str] = []
    lock = threading.Lock()

    def worker():
        s = SessionLocal()
        try:
            for _ in range(10):
                n = next_no(s, biz)
                s.commit()
                with lock:
                    numbers.append(n)
        finally:
            s.close()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(numbers) == 50
    assert len(set(numbers)) == 50


def test_preview_and_reset_api(client, admin_headers):
    """preview 不落库不占号；reset 端点重置当前周期并写审计。"""
    r = client.post(
        "/api/v1/admin/number-rules/preview",
        headers=admin_headers,
        json={
            "bizType": "customer",
            "prefix": "PV",
            "yearDigits": 4,
            "monthDigits": 2,
            "dayDigits": 2,
            "seqLen": 3,
            "seqStart": 5,
            "separator": "-",
            "resetCycle": "none",
        },
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["preview"] == f"PV-{datetime.now().strftime('%Y%m%d')}-005"

    # reset 端点 + 审计：用独立规则，避免影响 customer 等共享序列
    uniq = f"utrst{uuid.uuid4().hex[:8]}"
    rc = client.post(
        "/api/v1/admin/number-rules",
        headers=admin_headers,
        json={"bizType": uniq, "prefix": "RS", "seqLen": 3},
    ).json()
    assert rc["code"] == 0, rc
    rid = rc["data"]["id"]
    r2 = client.post(f"/api/v1/admin/number-rules/{rid}/reset", headers=admin_headers, json={"value": 50}).json()
    assert r2["code"] == 0, r2
    assert r2["data"]["value"] == 50
    logs = client.get(
        "/api/v1/admin/audit-logs", headers=admin_headers, params={"module": "admin", "size": 10}
    ).json()
    assert any(x["action"] == "number_rule_reset" for x in logs["data"]["items"])


def test_category_rule_create_conflict_api(client, admin_headers):
    """同 biz_type+category_key 重复创建报冲突；不同 category 可共存。"""
    base = {"bizType": "contract", "categoryKey": "testing", "prefix": "XX"}
    r = client.post("/api/v1/admin/number-rules", headers=admin_headers, json=base).json()
    assert r["code"] != 0  # 种子已有 contract+testing
    uniq = f"ut{uuid.uuid4().hex[:10]}"
    r2 = client.post(
        "/api/v1/admin/number-rules", headers=admin_headers, json={**base, "categoryKey": uniq}
    ).json()
    assert r2["code"] == 0, r2
    assert r2["data"]["categoryKey"] == uniq

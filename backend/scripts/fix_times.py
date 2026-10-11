"""演示数据时间微调：把生成脚本落库的 00:00:00 / 深夜凌晨时间规整到工作时间段。

- fin_payment.create_time 以 paid_at 为日期 + 随机上班时间
- 审批实例 / 意见 / 待办：按时间线重排，落在 08:00-19:59，保证先后顺序
- 报告 create/update/seal 同样规整
- 通知 / 审计 / 登录日志随机到具体时分秒（避免全部同一时刻）

用法：docker exec -w /app -e PYTHONPATH=/app bizsys-api python /tmp/fix_times.py
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

R = random.Random(4242)


def biz(t: datetime) -> datetime:
    """把时刻挪进 08:00-19:59。"""
    if t.hour < 8:
        return t.replace(hour=8, minute=R.randint(0, 59), second=R.randint(0, 59))
    if t.hour > 19:
        return t.replace(hour=19, minute=R.randint(0, 55), second=R.randint(0, 59))
    return t.replace(minute=R.randint(0, 59), second=R.randint(0, 59))


def normalize(seq: list[datetime]) -> list[datetime]:
    """保持先后顺序，同时全部落在工作时间。"""
    out: list[datetime] = []
    prev: datetime | None = None
    for t in seq:
        t = biz(t)
        if prev is not None and t <= prev:
            t = prev + timedelta(minutes=R.randint(20, 200))
            if t.hour > 19:
                nxt = (prev + timedelta(days=1)).date()
                t = datetime(nxt.year, nxt.month, nxt.day, R.randint(9, 17),
                             R.randint(0, 59), R.randint(0, 59))
            if t <= prev:
                t = prev + timedelta(minutes=30)
        out.append(t)
        prev = t
    return out


def main() -> None:
    from sqlalchemy import text

    from app.core.db import engine

    with engine.begin() as conn:
        # 1) 到账：paid_at 日期 + 上班时间
        conn.execute(text("""
            UPDATE fin_payment
            SET create_time = paid_at + INTERVAL FLOOR(9 + RAND()*9) HOUR
                            + INTERVAL FLOOR(RAND()*60) MINUTE + INTERVAL FLOOR(RAND()*60) SECOND,
                update_time = create_time
            WHERE paid_at IS NOT NULL
        """))
        conn.execute(text("""
            UPDATE fin_payment
            SET create_time = DATE(create_time) + INTERVAL FLOOR(9 + RAND()*9) HOUR
                            + INTERVAL FLOOR(RAND()*60) MINUTE,
                update_time = create_time
            WHERE paid_at IS NULL
        """))

        # 2) 审批链
        insts = conn.execute(text(
            "SELECT id, create_time, finished_at FROM approval_instance WHERE deleted=0 ORDER BY id"
        )).all()
        for iid, ctime, fat in insts:
            recs = conn.execute(text(
                "SELECT id, at FROM approval_record WHERE instance_id=:i ORDER BY at, id"
            ), {"i": iid}).all()
            seq = [ctime] + [r[1] for r in recs] + ([fat] if fat else [])
            norm = normalize(seq)
            new_c = norm[0]
            new_recs = norm[1:1 + len(recs)]
            new_f = norm[-1] if fat else None
            conn.execute(text(
                "UPDATE approval_instance SET create_time=:c, update_time=:u, finished_at=:f WHERE id=:i"
            ), {"c": new_c, "u": new_f or new_c, "f": new_f, "i": iid})
            for (rid, _old), t in zip(recs, new_recs):
                conn.execute(text("UPDATE approval_record SET at=:t, create_time=:t WHERE id=:r"),
                             {"t": t, "r": rid})
            tasks = conn.execute(text(
                "SELECT id, status, seq FROM approval_task WHERE instance_id=:i ORDER BY seq, id"
            ), {"i": iid}).all()
            for n, (tid, st, _seq) in enumerate(tasks):
                create_t = new_c + timedelta(minutes=15 * (n + 1))
                if new_recs:
                    acted = new_recs[min(n, len(new_recs) - 1)] if st != "pending" else None
                else:
                    acted = None
                conn.execute(text(
                    "UPDATE approval_task SET create_time=:c, acted_at=COALESCE(:a, acted_at) WHERE id=:i"
                ), {"c": create_t, "a": acted, "i": tid})

        # 3) 报告
        rows = conn.execute(text(
            "SELECT id, create_time, update_time, seal_time FROM rpt_report WHERE deleted=0"
        )).all()
        for rid, c, u, s in rows:
            seq = normalize([c, u] + ([s] if s else []))
            conn.execute(text(
                "UPDATE rpt_report SET create_time=:c, update_time=:u, "
                "seal_time=CASE WHEN seal_time IS NULL THEN NULL ELSE :s END WHERE id=:i"
            ), {"c": seq[0], "u": seq[1], "s": (seq[2] if s else None), "i": rid})

        # 4) 通知 / 审计 / 登录日志：随机日期 + 随机工作时间
        for tbl in ("sys_notify", "sys_audit_log", "sys_login_log"):
            conn.execute(text(f"""
                UPDATE {tbl}
                SET create_time = DATE(NOW()) - INTERVAL FLOOR(1 + RAND()*60) DAY
                                + INTERVAL FLOOR(8 + RAND()*11) HOUR
                                + INTERVAL FLOOR(RAND()*60) MINUTE
                                + INTERVAL FLOOR(RAND()*60) SECOND
                WHERE create_time > DATE_SUB(NOW(), INTERVAL 1 DAY)
            """))
    print("fix_times DONE")


if __name__ == "__main__":
    main()

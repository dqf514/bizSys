"""补充修复：混合乱码（同一字符串内部分中文正常、部分仍为双编码乱码）。

首轮 fix_mojibake.py 只处理"整串无 CJK"的值；此类混合值被跳过。
策略：找 [0x80,0xFF] 及 cp1252 扩展区字符的最长连续段（UTF-8 中文被错读为 latin1/cp1252 后必落在这些区间），
逐段还原字节再 decode utf-8；解出 CJK 才替换，否则原样保留。

用法: python scripts/fix_mojibake_mixed.py [--apply] [--backup <path>]
"""

import argparse
import json
import re

from sqlalchemy import text

from app.core.db import engine

# cp1252 对 0x80-0x9F 的扩展映射（与首轮脚本一致）
CP1252_EXTRA = {
    0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84, 0x2026: 0x85,
    0x2020: 0x86, 0x2021: 0x87, 0x02C6: 0x88, 0x2030: 0x89, 0x0160: 0x8A,
    0x2039: 0x8B, 0x0152: 0x8C, 0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92,
    0x201C: 0x93, 0x201D: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
    0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B, 0x0153: 0x9C,
    0x017E: 0x9E, 0x0178: 0x9F,
}

CJK_RE = re.compile(r"[一-鿿]")
EXTRA_CHARS = frozenset(CP1252_EXTRA)


def _is_suspect(c: str) -> bool:
    o = ord(c)
    return 0x80 <= o <= 0xFF or o in EXTRA_CHARS


def _fix_run(run: str) -> str:
    try:
        raw = bytes(CP1252_EXTRA.get(ord(c), ord(c)) if ord(c) < 0x100 or ord(c) in CP1252_EXTRA else 0x3F
                    for c in run)
        decoded = raw.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return run
    return decoded if CJK_RE.search(decoded) else run


def fix_value(v: str) -> str:
    out: list[str] = []
    i, n = 0, len(v)
    changed = False
    while i < n:
        if _is_suspect(v[i]):
            j = i
            while j < n and _is_suspect(v[j]):
                j += 1
            run = v[i:j]
            fixed = _fix_run(run)
            changed = changed or fixed != run
            out.append(fixed)
            i = j
        else:
            out.append(v[i])
            i += 1
    return "".join(out) if changed else v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", default="")
    args = ap.parse_args()

    with engine.begin() as conn:
        cols = conn.execute(text("""
            SELECT c.table_name, c.column_name FROM information_schema.columns c
            JOIN information_schema.columns idc
              ON idc.table_schema = c.table_schema AND idc.table_name = c.table_name AND idc.column_name = 'id'
            WHERE c.table_schema = DATABASE()
              AND c.data_type IN ('char','varchar','text','mediumtext','longtext','json')
        """)).all()

        fixed = 0
        backup = open(args.backup, "w", encoding="utf-8") if args.backup else None
        try:
            for tbl, col in cols:
                rows = conn.execute(text(f"SELECT id, `{col}` FROM `{tbl}` WHERE `{col}` IS NOT NULL")).all()
                for rid, val in rows:
                    if not isinstance(val, str) or not any(_is_suspect(c) for c in val):
                        continue
                    new = fix_value(val)
                    if new == val:
                        continue
                    fixed += 1
                    if backup:
                        backup.write(json.dumps(
                            {"table": tbl, "column": col, "id": rid, "old": val, "new": new},
                            ensure_ascii=False) + "\n")
                    if args.apply:
                        conn.execute(text(f"UPDATE `{tbl}` SET `{col}` = :v WHERE id = :i"), {"v": new, "i": rid})
            print(f"scanned {len(cols)} columns")
        finally:
            if backup:
                backup.close()
        print(f"{'APPLIED' if args.apply else 'DRY-RUN'} fixed={fixed}")


if __name__ == "__main__":
    main()

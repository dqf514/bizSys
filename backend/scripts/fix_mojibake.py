"""一次性修复：种子/历史数据 latin1/cp1252 双编码乱码还原为 UTF-8 中文。

背景：历史某次种子/演示数据写入时连接未指定 charset=utf8mb4，UTF-8 字节被按 latin1
落库，读回后表现为 "ä¸šå¡ç»Ÿ" 类 mojibake（同一字符串内可能混有 C1 控制符与
cp1252 扩展字符，如 š/Ÿ/ˆ，故需逐字符混合编码还原）。

判定（只转确实乱码的行）：原值不含 CJK，且还原后出现 CJK。
幂等：已修复为中文的行不再命中，可反复执行。

用法：
  uv run python scripts/fix_mojibake.py                         # dry-run：只扫描报告，不写库
  uv run python scripts/fix_mojibake.py --apply                 # 实际修复（单事务提交）
  uv run python scripts/fix_mojibake.py --apply --backup <path> # 修复前导出 old/new 到 JSONL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import bindparam, create_engine, text

# 允许从仓库 backend/ 目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402

TEXT_TYPES = ("char", "varchar", "text", "tinytext", "mediumtext", "longtext", "json")


def _has_cjk(s: str) -> bool:
    return any("一" <= c <= "鿿" for c in s)


def _to_bytes(s: str) -> bytes | None:
    """逐字符还原原始字节：U+0000-U+00FF 按 latin1，其余按 cp1252（š/Ÿ/ˆ 等扩展位）。"""
    out = bytearray()
    for ch in s:
        o = ord(ch)
        if o < 0x100:
            out.append(o)
        else:
            try:
                out.extend(ch.encode("cp1252"))
            except UnicodeEncodeError:
                return None
    return bytes(out)


def fix_value(s: str) -> str | None:
    """返回还原后的值；非乱码返回 None。"""
    if not s or _has_cjk(s):
        return None
    b = _to_bytes(s)
    if b is None:
        return None
    try:
        fixed = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if fixed == s or not _has_cjk(fixed):
        return None
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写库（默认 dry-run）")
    ap.add_argument("--backup", default="", help="修复前把 old/new 导出到该 JSONL 文件")
    args = ap.parse_args()

    engine = create_engine(settings.db_url)
    changes: list[dict] = []
    with engine.connect() as c:
        db = c.execute(text("SELECT DATABASE()")).scalar()
        cols = c.execute(
            text(
                "SELECT c.TABLE_NAME, c.COLUMN_NAME FROM information_schema.COLUMNS c "
                "JOIN information_schema.COLUMNS p ON p.TABLE_SCHEMA = c.TABLE_SCHEMA "
                "  AND p.TABLE_NAME = c.TABLE_NAME AND p.COLUMN_NAME = 'id' "
                "WHERE c.TABLE_SCHEMA = :db AND c.DATA_TYPE IN :types "
                "ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION"
            ).bindparams(bindparam("types", expanding=True)),
            {"db": db, "types": TEXT_TYPES},
        ).fetchall()
        print(f"database={db}，扫描文本列 {len(cols)} 个")
        for table, column in cols:
            rows = c.execute(text(f"SELECT id, `{column}` FROM `{table}`")).fetchall()
            for rid, val in rows:
                if not isinstance(val, str):
                    continue
                fixed = fix_value(val)
                if fixed is not None:
                    changes.append(
                        {"table": table, "column": column, "id": rid, "old": val, "new": fixed}
                    )

    by_table: dict[str, int] = {}
    for ch in changes:
        by_table[ch["table"]] = by_table.get(ch["table"], 0) + 1
    for t, n in sorted(by_table.items()):
        print(f"  {t}: {n} 列值待修复")
    print(f"合计 {len(changes)} 个列值（{sum(1 for _ in {c['table'] for c in changes})} 张表）")

    if not changes:
        return 0
    if not args.apply:
        print("dry-run 模式，未写库。加 --apply 执行修复。")
        return 0

    if args.backup:
        path = Path(args.backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for ch in changes:
                f.write(json.dumps(ch, ensure_ascii=False) + "\n")
        print(f"已备份 {len(changes)} 条到 {path}")

    with engine.begin() as c:
        for ch in changes:
            c.execute(
                text(f"UPDATE `{ch['table']}` SET `{ch['column']}` = :v WHERE id = :id"),
                {"v": ch["new"], "id": ch["id"]},
            )
    print(f"已修复 {len(changes)} 个列值。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

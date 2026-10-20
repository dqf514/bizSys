"""数据库备份执行：mysqldump 优先，不可用降级内置逐表导出；SQLite 直接复制库文件。

备份文件：{dir}/bizsys_YYYYMMDD_HHMMSS.sql.gz + 同名 .meta.json（kind/tool/大小/时间）。
恢复：gunzip 后 mysql < file.sql（内置导出含 DROP/CREATE TABLE，可整库恢复）。
"""

import gzip
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine.url import make_url

from app.core.config import settings

logger = logging.getLogger("bizsys.backup")

META_SUFFIX = ".meta.json"


def mysqldump_path() -> str | None:
    return shutil.which("mysqldump")


def backup_dir(configured: str = "") -> Path:
    d = Path(configured) if configured else Path("./backups")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _esc(v: object) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return "0x" + bytes(v).hex()
    if isinstance(v, datetime):
        v = v.strftime("%Y-%m-%d %H:%M:%S")
    s = str(v)
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r") + "'"


def _builtin_mysql_dump(url, dest: Path) -> None:
    """纯 Python 逐表导出（DDL + INSERT），不依赖 mysqldump。"""
    import pymysql

    conn = pymysql.connect(
        host=url.host or "127.0.0.1",
        port=url.port or 3306,
        user=url.username or "",
        password=url.password or "",
        database=url.database,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur, gzip.open(dest, "wt", encoding="utf-8") as gz:
            gz.write(f"-- bizSys builtin backup {datetime.now():%Y-%m-%d %H:%M:%S}\nSET FOREIGN_KEY_CHECKS=0;\n")
            cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
            tables = [r[0] for r in cur.fetchall()]
            for table in tables:
                cur.execute(f"SHOW CREATE TABLE `{table}`")
                create_sql = cur.fetchone()[1]
                gz.write(f"\nDROP TABLE IF EXISTS `{table}`;\n{create_sql};\n")
                cur.execute(f"SELECT * FROM `{table}`")
                rows = cur.fetchall()
                if not rows:
                    continue
                cols = ",".join(f"`{d[0]}`" for d in cur.description)
                batch: list[str] = []
                for row in rows:
                    batch.append("(" + ",".join(_esc(v) for v in row) + ")")
                    if len(batch) >= 500:
                        gz.write(f"INSERT INTO `{table}` ({cols}) VALUES\n" + ",\n".join(batch) + ";\n")
                        batch.clear()
                if batch:
                    gz.write(f"INSERT INTO `{table}` ({cols}) VALUES\n" + ",\n".join(batch) + ";\n")
            gz.write("SET FOREIGN_KEY_CHECKS=1;\n")
    finally:
        conn.close()


def _mysqldump(url, dest: Path, dump_bin: str) -> None:
    env = {**os.environ, "MYSQL_PWD": url.password or ""}  # 避免密码出现在进程列表
    cmd = [
        dump_bin,
        f"--host={url.host or '127.0.0.1'}",
        f"--port={url.port or 3306}",
        f"--user={url.username or ''}",
        "--single-transaction",
        "--default-character-set=utf8mb4",
        url.database,
    ]
    with gzip.open(dest, "wb") as gz:
        proc = subprocess.run(cmd, stdout=gz, stderr=subprocess.PIPE, env=env, timeout=600)
    if proc.returncode != 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"mysqldump 失败：{proc.stderr.decode(errors='replace')[:300]}")


def run_backup(kind: str = "manual", configured_dir: str = "") -> dict:
    """执行一次备份并应用保留策略；返回备份信息 dict。"""
    url = make_url(settings.db_url)
    out_dir = backup_dir(configured_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"bizsys_{stamp}.sql.gz"
    # 同秒并发兜底
    n = 1
    while dest.exists():
        dest = out_dir / f"bizsys_{stamp}_{n}.sql.gz"
        n += 1

    if url.drivername.startswith("sqlite"):
        db_file = Path(url.database or "")
        if not db_file.exists():
            raise RuntimeError(f"SQLite 库文件不存在：{db_file}")
        with open(db_file, "rb") as src, gzip.open(dest, "wb") as gz:
            shutil.copyfileobj(src, gz)
        tool = "sqlite-copy"
    else:
        dump_bin = mysqldump_path()
        if dump_bin:
            _mysqldump(url, dest, dump_bin)
            tool = "mysqldump"
        else:
            logger.warning("mysqldump 不可用，使用内置逐表导出")
            _builtin_mysql_dump(url, dest)
            tool = "builtin"

    info = {
        "name": dest.name,
        "size": dest.stat().st_size,
        "kind": kind,
        "tool": tool,
        "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out_dir / f"{dest.name}{META_SUFFIX}").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return info


def list_backups(configured_dir: str = "") -> list[dict]:
    out_dir = backup_dir(configured_dir)
    items = []
    for f in sorted(out_dir.glob("bizsys_*.sql.gz"), key=lambda x: x.name, reverse=True):
        meta_file = f.with_name(f.name + META_SUFFIX)
        meta = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        items.append(
            {
                "name": f.name,
                "size": f.stat().st_size,
                "kind": meta.get("kind", "manual"),
                "tool": meta.get("tool", ""),
                "createdAt": meta.get("createdAt")
                or datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items


def resolve_backup(name: str, configured_dir: str = "") -> Path:
    """按文件名解析备份路径（防目录穿越）。"""
    if not name or "/" in name or "\\" in name or not name.endswith(".sql.gz"):
        raise FileNotFoundError(name)
    dest = backup_dir(configured_dir) / name
    if not dest.exists():
        raise FileNotFoundError(name)
    return dest


def delete_backup(name: str, configured_dir: str = "") -> None:
    dest = resolve_backup(name, configured_dir)
    dest.unlink()
    dest.with_name(dest.name + META_SUFFIX).unlink(missing_ok=True)


def apply_retention(retention: int, configured_dir: str = "") -> int:
    """按保留份数清理最旧备份，返回删除数。"""
    if retention <= 0:
        return 0
    items = list_backups(configured_dir)  # 新的在前
    removed = 0
    for it in items[retention:]:
        try:
            delete_backup(it["name"], configured_dir)
            removed += 1
        except OSError:
            logger.warning("备份清理失败：%s", it["name"])
    return removed

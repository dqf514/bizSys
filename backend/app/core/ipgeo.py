"""IP 属地解析（离线 ip2region v4 库）。

审计日志 / 登录日志展示客户端 IP 的属地（省 / 市）。

- **数据源**：`app/core/data/ip2region_v4.xdb`（v4 格式，IPv4），随仓库入库；
  检索实现为 vendored 的纯 Python 绑定（`app/core/ip2region/`）——
  **不引入 pip 依赖、不访问外网**（属地解析属于展示增强，不允许拖慢主链路或依赖外网）。
- **属地在读取时计算**：审计表是**只追加**的（`sys_audit_log` 有 BEFORE UPDATE/DELETE 触发器），
  落库存属地需要回填历史行 → 不可行；改为查询时算一次（内存向量索引 + 二分查找，微秒级），
  好处是**历史记录立即就有属地**，且不用为审计表加列 / 加迁移。
"""

import ipaddress
import threading
from functools import lru_cache
from pathlib import Path

from app.core.ip2region import util
from app.core.ip2region.searcher import Searcher, new_with_buffer

# 离线库文件（随仓库入库）
XDB_PATH = Path(__file__).resolve().parent / "data" / "ip2region_v4.xdb"

# 属地文案（后端直接给中文文案，前端原样展示）
REGION_LOCALHOST = "本机"
REGION_PRIVATE = "内网"

_searcher: Searcher | None = None
_searcher_failed = False
_lock = threading.Lock()


def _get_searcher() -> Searcher | None:
    """惰性加载离线库（整文件进内存，检索无 IO、天然线程安全）。

    库文件缺失 / 损坏时不抛错 —— 属地只是展示增强，缺了不影响主流程。
    """
    global _searcher, _searcher_failed
    if _searcher is not None or _searcher_failed:
        return _searcher
    with _lock:
        if _searcher is not None or _searcher_failed:
            return _searcher
        try:
            content = XDB_PATH.read_bytes()
            with open(XDB_PATH, "rb") as fh:
                header = util.load_header(fh)
            version = util.version_from_header(header)
            if version is None:
                _searcher_failed = True
                return None
            _searcher = new_with_buffer(version, content)
        except Exception:  # 缺库 / 坏库都不能拖垮主链路
            _searcher_failed = True
            return None
        return _searcher


@lru_cache(maxsize=4096)
def _lookup(ip: str) -> str:
    """查离线库，返回原始串 `国家|省|市|运营商|国家码`（查不到返回空串）。"""
    searcher = _get_searcher()
    if searcher is None:
        return ""
    try:
        return searcher.search(ip)
    except Exception:  # 非法 IP / 库异常都按「查不到」处理
        return ""


def _format(raw: str) -> str:
    """原始串 → 属地文案。

    - 中国：`省 市`（去重，如「香港」）
    - 其他：`国家 市`
    - 占位符 `0` 与空段一律丢弃
    """
    if not raw:
        return ""
    parts = [p.strip() for p in raw.split("|")]
    parts = [p for p in parts if p and p != "0"]
    if not parts:
        return ""
    country = parts[0]
    region = parts[1] if len(parts) > 1 else ""
    city = parts[2] if len(parts) > 2 else ""
    if country == "中国":
        vals = [region, city]
    else:
        vals = [country, city]
    out: list[str] = []
    for v in vals:
        if v and v not in out:
            out.append(v)
    return " ".join(out)


def resolve_region(ip: str | None) -> str:
    """IP → 属地文案。

    - 空 / 非法 IP → `""`
    - 回环（127.0.0.1 / ::1）→ `本机`
    - 内网 / 保留地址 → `内网`
    - 公网 → 离线库属地（如 `安徽省 宣城市`）
    """
    if not ip:
        return ""
    ip = ip.strip()
    if not ip:
        return ""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if addr.is_loopback:
        return REGION_LOCALHOST
    if (
        addr.is_private
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    ):
        return REGION_PRIVATE
    return _format(_lookup(ip))

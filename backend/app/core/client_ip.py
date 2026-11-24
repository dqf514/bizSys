"""真实客户端 IP 解析（反向代理链）。

背景：审计日志要记"终端 IP"（ALCOA 可归因）。但应用跑在**容器 nginx 之后**，
nginx 前面还可能有一层对外网关（`deploy/DEPLOY.md`：portal.hmvic.cn → 18080），
`request.client.host` 拿到的是 **TCP 对端地址**（nginx / 网关容器的内网 IP），
不是访问者的公网 IP。

nginx 侧已按标准透传 `X-Forwarded-For`（追加语义 `$proxy_add_x_forwarded_for`）
与 `X-Real-IP`，所以这里在**应用侧**把真实 IP 还原出来 —— 改应用而不是改 nginx。

两种取法（都是业界标准做法）：

- **跳数模式**（Django `USE_X_FORWARDED_FOR` 同款）：`X-Forwarded-For` 从右往左数
  `trusted_proxy_hops` 跳。每个受控代理都会在链尾追加它看到的对端地址，
  所以链尾第 N 条就是真实客户端。链比预期短时（直连、无网关）取最左一条。
- **网段模式**（Spring Tomcat `RemoteIpValve` 同款）：从右往左跳过落在
  `trusted_proxy_cidrs` 里的地址（显式配置的网关网段），取第一条非代理地址。
  配了网段就以网段为准（跳数忽略），适合"不同访问路径跳数不同"的场景。

安全前提：代理必须用**追加语义**设置 `X-Forwarded-For`（nginx：
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`）；若代理原样透传
客户端自带的 `X-Forwarded-For`，链首可被伪造。
"""

import ipaddress
from functools import lru_cache

from starlette.requests import Request

from app.core.config import settings


@lru_cache(maxsize=16)
def _parse_cidrs(raw: str) -> tuple:
    """解析逗号分隔的 IP / CIDR 列表（非法项忽略）。"""
    nets = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return tuple(nets)


def _addr(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    raw = raw.split("%", 1)[0]  # IPv6 zone id（fe80::1%eth0）
    try:
        return ipaddress.ip_address(raw)
    except ValueError:
        return None


def _is_trusted_proxy(raw: str, cidrs) -> bool:
    addr = _addr(raw)
    if addr is None:
        return False
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return any(addr.version == net.version and addr in net for net in cidrs)


def _xff_entries(request: Request) -> list[str]:
    raw = request.headers.get("x-forwarded-for") or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def client_ip(request: Request) -> str:
    """返回真实客户端 IP；无法判定时退回 TCP 对端地址。"""
    peer = request.client.host if request.client else ""
    if not settings.trust_proxy_headers:
        return peer

    entries = _xff_entries(request)
    if not entries:
        # 没有任何代理链信息：X-Real-IP（nginx 设为 $remote_addr）→ TCP 对端
        return (request.headers.get("x-real-ip") or "").strip() or peer

    cidrs = _parse_cidrs(settings.trusted_proxy_cidrs)
    if cidrs:
        # 网段模式：从右往左跳过受信任代理（显式配置的网关网段）
        for entry in reversed(entries):
            if entry != peer and not _is_trusted_proxy(entry, cidrs):
                return entry
        return entries[0]

    hops = settings.trusted_proxy_hops
    if hops <= 0:
        # 0 = 不信任任何代理头，只认 TCP 对端
        return peer
    # 跳数模式：链尾第 N 条即真实客户端；链短于跳数时取最左一条
    return entries[max(0, len(entries) - hops)]

"""真实客户端 IP 解析（反向代理链）。

背景：审计日志要记访问者的公网 IP，而不是 nginx / 网关容器的内网 IP。

覆盖：
- 跳数模式：两跳（网关 + 容器 nginx）、单跳、链短于跳数时的钳位；
- 网段模式：显式受信任代理网段（优先级高于跳数）；
- 回落链：无 XFF → X-Real-IP → TCP 对端；
- 端到端：登录失败写入的 `sys_login_log.ip` / `sys_audit_log.ip` 是真实客户端 IP。
"""

import uuid

from conftest import captcha_fields
from starlette.requests import Request

from app.core import client_ip as cip
from app.core.config import settings

GATEWAY = "172.16.0.5"
CLIENT = "203.0.113.7"


def _request(headers: dict[str, str] | None = None, peer: str = "testclient") -> Request:
    raw = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": raw,
            "client": (peer, 1234),
        }
    )


def test_hops_two_gateway_chain(monkeypatch):
    """网关 + 容器 nginx 两跳：取链头（最左）= 真实客户端。"""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    req = _request({"X-Forwarded-For": f"{CLIENT}, {GATEWAY}"})
    assert cip.client_ip(req) == CLIENT


def test_hops_one_takes_chain_tail(monkeypatch):
    """单跳（只有容器 nginx）：取链尾 = nginx 看到的对端。"""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    req = _request({"X-Forwarded-For": f"{CLIENT}, {GATEWAY}"})
    assert cip.client_ip(req) == GATEWAY


def test_hops_shorter_chain_clamps_to_leftmost(monkeypatch):
    """直连容器 nginx（只有一条记录）：跳数超量时取最左一条，仍是真实客户端。"""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    req = _request({"X-Forwarded-For": CLIENT})
    assert cip.client_ip(req) == CLIENT


def test_cidr_mode_skips_trusted_proxy(monkeypatch):
    """网段模式：显式配置的网关网段被跳过，取其左侧的客户端地址。"""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "172.16.0.0/12")
    req = _request({"X-Forwarded-For": f"{CLIENT}, {GATEWAY}"})
    assert cip.client_ip(req) == CLIENT


def test_cidr_mode_all_private_falls_back_to_leftmost(monkeypatch):
    """局域网客户端（私网地址）且链上全是受信任网段：取最左一条。"""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "172.16.0.0/12,192.168.0.0/16")
    req = _request({"X-Forwarded-For": "192.168.1.50"})
    assert cip.client_ip(req) == "192.168.1.50"


def test_fallback_to_real_ip_then_peer(monkeypatch):
    """没有 XFF：退回 X-Real-IP，再退回 TCP 对端。"""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    req = _request({"X-Real-IP": GATEWAY}, peer="172.18.0.4")
    assert cip.client_ip(req) == GATEWAY
    req = _request({}, peer="172.18.0.4")
    assert cip.client_ip(req) == "172.18.0.4"


def test_proxy_headers_disabled(monkeypatch):
    """总开关关掉：一律用 TCP 对端，不采信任何代理头。"""
    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    req = _request({"X-Forwarded-For": f"{CLIENT}, {GATEWAY}"}, peer="172.18.0.4")
    assert cip.client_ip(req) == "172.18.0.4"


def test_hops_zero_disables_proxy_headers(monkeypatch):
    """跳数配 0 = 不信任代理头。"""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    req = _request({"X-Forwarded-For": f"{CLIENT}, {GATEWAY}"}, peer="172.18.0.4")
    assert cip.client_ip(req) == "172.18.0.4"


def test_login_audit_records_real_client_ip(client, db, monkeypatch):
    """端到端：登录失败写入的登录日志 / 审计日志记录真实客户端 IP。"""
    from sqlalchemy import select

    from app.modules.admin.models import AuditLog, LoginLog

    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")

    username = f"ip_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/auth/login",
        headers={"X-Forwarded-For": f"{CLIENT}, {GATEWAY}"},
        json={"username": username, "password": "Wrong@123456", **captcha_fields(client)},
    )
    assert resp.status_code in (200, 401)

    rows = db.scalars(select(LoginLog).where(LoginLog.username == username)).all()
    assert rows, "登录失败应写登录日志"
    assert rows[-1].ip == CLIENT

    audits = db.scalars(select(AuditLog).where(AuditLog.action == "login_failed").order_by(AuditLog.id.desc())).all()
    assert audits, "登录失败应写审计日志"
    assert audits[0].ip == CLIENT


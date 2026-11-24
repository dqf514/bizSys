"""审计 / 登录日志的 IP 属地（离线 ip2region 库）+ 外部门户入口不在内网导航。"""

from app.core import ipgeo


def _flatten(nodes) -> list[dict]:
    out: list[dict] = []
    for n in nodes or []:
        out.append(n)
        out.extend(_flatten(n.get("children") or []))
    return out


# ---------------- 属地解析 ----------------


def test_loopback_is_localhost():
    assert ipgeo.resolve_region("127.0.0.1") == "本机"
    assert ipgeo.resolve_region("::1") == "本机"


def test_private_ranges_are_internal():
    for ip in ("10.0.0.5", "172.16.0.1", "192.168.1.10", "169.254.10.1"):
        assert ipgeo.resolve_region(ip) == "内网"


def test_invalid_ip_returns_empty():
    assert ipgeo.resolve_region("") == ""
    assert ipgeo.resolve_region(None) == ""
    assert ipgeo.resolve_region("not-an-ip") == ""
    assert ipgeo.resolve_region("999.1.1.1") == ""


def test_public_ip_resolves_offline_database():
    """公网 IP 走离线 xdb：安徽电信段应解析到「安徽 宣城」。"""
    region = ipgeo.resolve_region("36.7.0.1")
    assert "安徽" in region
    assert "宣城" in region
    # 属地不依赖外网，纯本地库解析
    assert ipgeo.resolve_region("114.114.114.114") != ""


# ---------------- 接口出参 ----------------


def test_audit_list_includes_ip_region(client, admin_headers):
    r = client.get("/api/v1/admin/audit-logs", headers=admin_headers)
    assert r.json()["code"] == 0
    data = r.json()["data"]
    assert "items" in data and "total" in data
    for item in data["items"]:
        assert "ipRegion" in item
        assert "ip" in item


def test_audit_evidence_includes_ip_region(client, admin_headers):
    r = client.get("/api/v1/admin/audit-logs", headers=admin_headers)
    items = r.json()["data"]["items"]
    assert items
    row_id = items[0]["id"]
    r2 = client.get(f"/api/v1/admin/audit-logs/{row_id}/evidence", headers=admin_headers)
    assert r2.json()["code"] == 0
    assert "ipRegion" in r2.json()["data"]


def test_login_logs_endpoint(client, admin_headers):
    """登录日志列表：含 IP 与属地（此前该表没有任何查询端点）。"""
    r = client.get("/api/v1/admin/login-logs", headers=admin_headers)
    assert r.json()["code"] == 0
    data = r.json()["data"]
    assert "items" in data and "total" in data
    for item in data["items"]:
        assert "ip" in item
        assert "ipRegion" in item


def test_login_logs_filter_by_success(client, admin_headers):
    r = client.get("/api/v1/admin/login-logs?filters[success]=1", headers=admin_headers)
    assert r.json()["code"] == 0
    for item in r.json()["data"]["items"]:
        assert item["success"] == 1


# ---------------- 外部门户入口不在内网导航 ----------------


def test_portal_entries_not_in_internal_menu(client, admin_headers):
    """外部门户是独立认证的第二套外壳 —— 内网导航不再展示「客户自助 / 在线委托」入口。"""
    r = client.get("/api/v1/auth/me", headers=admin_headers)
    assert r.json()["code"] == 0
    names = {n["name"] for n in _flatten(r.json()["data"].get("menus") or [])}
    assert "PortalHome" not in names
    assert "PortalOrders" not in names

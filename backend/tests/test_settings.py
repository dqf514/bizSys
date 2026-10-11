"""系统设置：读写 / Logo 上传校验 / Favicon 上传清除 / branding 免登录 / 企微未配置错误码。"""

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
ICO_BYTES = b"\x00\x00\x01\x00" + b"\x00" * 60


def test_settings_read_write_and_secret_mask(client, admin_headers):
    r = client.get("/api/v1/admin/settings", headers=admin_headers)
    assert r.json()["code"] == 0

    r = client.put(
        "/api/v1/admin/settings",
        headers=admin_headers,
        json={
            "siteName": "bizSys 测试站",
            "wecom": {"enabled": False, "corpId": "ww1234567890", "agentId": "1000002", "secret": "s3cret"},
        },
    )
    data = r.json()
    assert data["code"] == 0, data
    assert data["data"]["siteName"] == "bizSys 测试站"
    assert data["data"]["wecom"]["corpId"] == "ww1234567890"

    r = client.get("/api/v1/admin/settings", headers=admin_headers)
    d = r.json()["data"]
    assert d["siteName"] == "bizSys 测试站"
    assert d["wecom"]["secretSet"] is True
    # secret 明文永不返回
    assert "s3cret" not in r.text
    assert "secret" not in d["wecom"] or d["wecom"].get("secret") in (None, "")


def test_settings_perm_required(client, manager_headers):
    r = client.get("/api/v1/admin/settings", headers=manager_headers)
    assert r.json()["code"] == 20002
    r = client.get("/api/v1/admin/settings")
    assert r.status_code == 401


def test_branding_public_and_reflects_settings(client, admin_headers):
    r = client.get("/api/v1/public/branding")  # 免登录
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["siteName"] == "bizSys 测试站"
    assert d["wecomEnabled"] is False
    assert "logoUrl" in d


def test_logo_upload_validation(client, admin_headers):
    # 不支持的扩展名
    r = client.post(
        "/api/v1/admin/settings/logo",
        headers=admin_headers,
        files={"file": ("logo.txt", b"hello", "text/plain")},
    )
    assert r.json()["code"] == 10001

    # 超过 2MB
    r = client.post(
        "/api/v1/admin/settings/logo",
        headers=admin_headers,
        files={"file": ("logo.png", b"\x89PNG" + b"\x00" * (2 * 1024 * 1024), "image/png")},
    )
    assert r.json()["code"] == 10001

    # 正常上传
    r = client.post(
        "/api/v1/admin/settings/logo",
        headers=admin_headers,
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    data = r.json()
    assert data["code"] == 0, data
    assert data["data"]["logoUrl"] == "/api/v1/public/logo"

    # branding 反映 logoUrl
    d = client.get("/api/v1/public/branding").json()["data"]
    assert d["logoUrl"] == "/api/v1/public/logo"

    # 免登录可拿 logo 文件流
    r = client.get("/api/v1/public/logo")
    assert r.status_code == 200
    assert r.content == PNG_BYTES
    assert r.headers["content-type"] == "image/png"


def test_favicon_upload_and_clear(client, admin_headers):
    # 不支持的扩展名
    r = client.post(
        "/api/v1/admin/settings/favicon",
        headers=admin_headers,
        files={"file": ("favicon.svg", b"<svg/>", "image/svg+xml")},
    )
    assert r.json()["code"] == 10001

    # 正常上传 .ico
    r = client.post(
        "/api/v1/admin/settings/favicon",
        headers=admin_headers,
        files={"file": ("favicon.ico", ICO_BYTES, "image/x-icon")},
    )
    data = r.json()
    assert data["code"] == 0, data
    assert data["data"]["faviconUrl"] == "/api/v1/public/favicon"

    # settings / branding 均反映 faviconUrl
    d = client.get("/api/v1/admin/settings", headers=admin_headers).json()["data"]
    assert d["faviconUrl"] == "/api/v1/public/favicon"
    d = client.get("/api/v1/public/branding").json()["data"]
    assert d["faviconUrl"] == "/api/v1/public/favicon"

    # 免登录可拿 favicon 文件流
    r = client.get("/api/v1/public/favicon")
    assert r.status_code == 200
    assert r.content == ICO_BYTES
    assert r.headers["content-type"] == "image/x-icon"

    # 清除后恢复默认（faviconUrl 为空，文件流 404）
    r = client.delete("/api/v1/admin/settings/favicon", headers=admin_headers)
    assert r.json()["code"] == 0
    d = client.get("/api/v1/public/branding").json()["data"]
    assert d["faviconUrl"] == ""
    assert client.get("/api/v1/public/favicon").json()["code"] == 10002


def test_wecom_not_configured_errors(client, admin_headers):
    # 确保处于未启用状态
    client.put("/api/v1/admin/settings", headers=admin_headers, json={"wecom": {"enabled": False}})

    r = client.get("/api/v1/auth/wecom/qr-url", params={"redirect_uri": "http://localhost:5173/login"})
    assert r.json()["code"] == 90001

    r = client.post("/api/v1/auth/wecom/callback", json={"code": "x", "state": "y"})
    assert r.json()["code"] == 20006  # state 无效先拦截


def test_wecom_qr_url_when_enabled(client, admin_headers):
    client.put(
        "/api/v1/admin/settings",
        headers=admin_headers,
        json={"wecom": {"enabled": True, "corpId": "ww1234567890", "agentId": "1000002", "secret": "s3cret"}},
    )
    r = client.get("/api/v1/auth/wecom/qr-url", params={"redirect_uri": "http://localhost:5173/login"})
    d = r.json()
    assert d["code"] == 0, d
    assert d["data"]["url"].startswith("https://open.work.weixin.qq.com/wwopen/sso/qrConnect?")
    assert "appid=ww1234567890" in d["data"]["url"]
    assert "agentid=1000002" in d["data"]["url"]
    assert "state=" in d["data"]["url"]

    # branding 反映 wecomEnabled
    assert client.get("/api/v1/public/branding").json()["data"]["wecomEnabled"] is True

    # 还原：不影响其他用例/联调默认状态
    client.put("/api/v1/admin/settings", headers=admin_headers, json={"wecom": {"enabled": False}})

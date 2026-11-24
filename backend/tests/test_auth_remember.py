"""登录「记住登录状态」：会话口径（长期 / 会话级）、刷新继承、改密吊销其余会话。"""

from datetime import UTC, datetime

from conftest import captcha_fields

from app.core.redis import get_redis
from app.core.security import decode_token


def _login(client, username: str, password: str, remember: bool) -> dict:
    r = client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": password,
            "remember": remember,
            **captcha_fields(client),
        },
    )
    data = r.json()
    assert data["code"] == 0, data
    return data["data"]


def test_login_remember_true_is_long_session(client):
    """勾选「记住登录状态」→ refresh token 30 天（claim rem=True）。"""
    data = _login(client, "admin", "Admin@123456", True)
    assert data["remember"] is True
    payload = decode_token(data["refresh_token"], "refresh")
    assert payload["rem"] is True
    # 到期时间约 30 天（留 1 小时余量）
    remain = payload["exp"] - datetime.now(UTC).timestamp()
    assert 29 * 86400 < remain <= 30 * 86400
    # Redis 里的吊销索引同步登记
    r = get_redis()
    assert r.sismember(f"refresh:user:{payload['sub']}", payload["jti"])
    assert r.ttl(f"refresh:{payload['jti']}") > 29 * 86400


def test_login_remember_false_is_session_scope(client):
    """不勾选 → refresh token 12 小时（claim rem=False）。"""
    data = _login(client, "admin", "Admin@123456", False)
    assert data["remember"] is False
    payload = decode_token(data["refresh_token"], "refresh")
    assert payload["rem"] is False
    remain = payload["exp"] - datetime.now(UTC).timestamp()
    assert 11 * 3600 < remain <= 12 * 3600


def test_refresh_inherits_remember_flag(client):
    """刷新轮换时必须继承会话口径 —— 否则「不记住」会被悄悄延长成 30 天。"""
    data = _login(client, "admin", "Admin@123456", False)
    old = data["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old}).json()
    assert r2["code"] == 0
    assert r2["data"]["remember"] is False
    new_payload = decode_token(r2["data"]["refresh_token"], "refresh")
    assert new_payload["rem"] is False
    remain = new_payload["exp"] - datetime.now(UTC).timestamp()
    assert 11 * 3600 < remain <= 12 * 3600
    # 旧 token 已轮换失效
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": old}).json()
    assert r3["code"] != 0


def test_refresh_returns_new_token_for_persistence(client):
    """轮换后必须返回新的 refresh token —— 前端要存回，否则 15 分钟后被踢回登录页。"""
    data = _login(client, "admin", "Admin@123456", True)
    old = data["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old}).json()
    assert r2["code"] == 0
    new_token = r2["data"]["refresh_token"]
    assert new_token and new_token != old
    # 新 token 可继续刷新（会话能一直续下去）
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": new_token}).json()
    assert r3["code"] == 0
    assert r3["data"]["refresh_token"] != new_token


def test_change_password_revokes_other_sessions(client):
    """改密 → 吊销本用户其余会话；带上的当前会话保留。"""
    first = _login(client, "admin", "Admin@123456", True)
    second = _login(client, "admin", "Admin@123456", True)
    keep = first["refresh_token"]
    other = second["refresh_token"]

    r = client.post(
        "/api/v1/auth/password",
        json={
            "old_password": "Admin@123456",
            "new_password": "Admin@1234567",
            "refresh_token": keep,
        },
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )
    assert r.json()["code"] == 0

    # 其余会话失效
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": other}).json()
    assert r2["code"] != 0
    # 当前会话保留
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": keep}).json()
    assert r3["code"] == 0

    # 改回原密码，避免影响后续用例
    client.post(
        "/api/v1/auth/password",
        json={
            "old_password": "Admin@1234567",
            "new_password": "Admin@123456",
            "refresh_token": keep,
        },
        headers={"Authorization": f"Bearer {r3['data']['access_token']}"},
    )

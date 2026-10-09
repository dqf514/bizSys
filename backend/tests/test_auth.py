"""鉴权：登录信封 / me / refresh / 未登录 401。"""

import uuid


def test_login_envelope_and_me(client, admin_headers):
    r = client.get("/api/v1/auth/me", headers=admin_headers)
    data = r.json()
    assert data["code"] == 0
    assert "super" in data["data"]["roles"]
    assert data["data"]["menus"]


def test_login_wrong_password(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad-password"})
    data = r.json()
    assert data["code"] == 20001
    assert r.status_code == 401


def test_unauthorized_without_token(client):
    r = client.get("/api/v1/auth/me")
    data = r.json()
    assert data["code"] == 20001
    assert r.status_code == 401


def test_refresh_flow(client, admin_headers):
    # 重新登录拿 refresh_token
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123456"}).json()
    refresh = r["data"]["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).json()
    assert r2["code"] == 0
    assert r2["data"]["access_token"]
    # 吊销后再用应失败
    client.post("/api/v1/auth/logout", json={"refresh_token": refresh}, headers=admin_headers)
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).json()
    assert r3["code"] != 0


def test_locked_after_five_failures(client):
    # 5 次失败锁定（独立随机用户，避免影响其他用例）
    username = f"lock_{uuid.uuid4().hex[:8]}"
    from app.core.db import SessionLocal
    from app.core.security import hash_password
    from app.modules.auth.models import User

    db = SessionLocal()
    db.add(User(username=username, password_hash=hash_password("Right@123456"), name="锁定测试", status="enabled"))
    db.commit()
    db.close()

    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": username, "password": "wrong"})
    r = client.post("/api/v1/auth/login", json={"username": username, "password": "Right@123456"})
    data = r.json()
    assert data["code"] == 20003

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


def _make_user(username: str, password: str = "Test@123456", status: str = "enabled") -> None:
    from app.core.db import SessionLocal
    from app.core.security import hash_password
    from app.modules.auth.models import User

    db = SessionLocal()
    db.add(User(username=username, password_hash=hash_password(password), name="测试用户", status=status))
    db.commit()
    db.close()


def _login(client, username: str, password: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    data = r.json()
    assert data["code"] == 0, data
    return {"Authorization": f"Bearer {data['data']['access_token']}"}


def test_refresh_rotation(client):
    # 刷新后旧 refresh_token 立即失效（旋转）
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123456"}).json()
    old_refresh = r["data"]["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh}).json()
    assert r2["code"] == 0
    new_refresh = r2["data"]["refresh_token"]
    assert new_refresh and new_refresh != old_refresh

    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh}).json()
    assert r3["code"] == 20001

    r4 = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh}).json()
    assert r4["code"] == 0


def test_change_password_endpoint(client):
    username = f"pwd_{uuid.uuid4().hex[:8]}"
    _make_user(username, "Old@123456")
    headers = _login(client, username, "Old@123456")

    # 原密码错误 → 20004
    r = client.post(
        "/api/v1/auth/password", headers=headers, json={"old_password": "wrong", "new_password": "New@123456"}
    ).json()
    assert r["code"] == 20004

    # 新密码太短 → 10001
    r = client.post(
        "/api/v1/auth/password", headers=headers, json={"old_password": "Old@123456", "new_password": "short"}
    ).json()
    assert r["code"] == 10001

    # 正常修改后可用新密码登录
    r = client.post(
        "/api/v1/auth/password", headers=headers, json={"old_password": "Old@123456", "new_password": "New@123456"}
    ).json()
    assert r["code"] == 0
    _login(client, username, "New@123456")


def test_login_log_written(client):
    username = f"log_{uuid.uuid4().hex[:8]}"
    _make_user(username, "Right@123456")
    client.post("/api/v1/auth/login", json={"username": username, "password": "wrong"})
    client.post("/api/v1/auth/login", json={"username": username, "password": "Right@123456"})

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.admin.models import LoginLog

    db = SessionLocal()
    rows = db.scalars(select(LoginLog).where(LoginLog.username == username).order_by(LoginLog.id)).all()
    db.close()
    assert [r.success for r in rows] == [0, 1]
    assert rows[0].reason


def test_disabled_or_deleted_role_grants_nothing(db):
    # 停用/删除角色后 perm_codes / role_codes 不再放行（与菜单树过滤一致）
    from app.core.security import hash_password
    from app.modules.admin.models import Menu, Role, RoleMenu, UserRole
    from app.modules.auth.models import User

    suf = uuid.uuid4().hex[:8]
    perm = f"test:perm:{suf}"
    menu = Menu(name=f"m_{suf}", permission=perm, menu_type="button")
    role = Role(code=f"role_{suf}", name="测试角色")
    db.add_all([menu, role])
    db.flush()
    db.add(RoleMenu(role_id=role.id, menu_id=menu.id))
    user = User(username=f"roleu_{suf}", password_hash=hash_password("x"), name="t")
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.flush()
    db.expire(user)
    assert perm in user.perm_codes
    assert f"role_{suf}" in user.role_codes

    role.status = "disabled"
    db.flush()
    db.expire(user)
    assert user.perm_codes == []
    assert user.role_codes == []

    role.status = "enabled"
    role.deleted = 1
    db.flush()
    db.expire(user)
    assert user.perm_codes == []
    assert user.role_codes == []

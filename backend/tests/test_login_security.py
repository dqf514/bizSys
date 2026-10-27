"""登录安全升级：图形验证码必填/一次性/作废 + MFA 开关/发送/校验 + 消息通道设置。"""

import json
import uuid

from conftest import captcha_fields, post_login


def _make_user(username: str, password: str = "Test@123456", mobile: str = "", email: str = "") -> None:
    from app.core.db import SessionLocal
    from app.core.security import hash_password
    from app.modules.auth.models import User

    db = SessionLocal()
    db.add(
        User(
            username=username,
            password_hash=hash_password(password),
            name="安全测试",
            status="enabled",
            mobile=mobile,
            email=email,
        )
    )
    db.commit()
    db.close()


def _login(client, username: str, password: str) -> dict:
    r = post_login(client, username, password)
    data = r.json()
    assert data["code"] == 0, data
    return {"Authorization": f"Bearer {data['data']['access_token']}"}


def _step_up_token(client, headers: dict, password: str) -> str:
    r = client.post("/api/v1/auth/step-up", headers=headers, json={"password": password}).json()
    assert r["code"] == 0, r
    return r["data"]["stepUpToken"]


# ---------------- 图形验证码 ----------------


def test_login_requires_captcha(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123456"})
    assert r.json()["code"] == 10001  # 缺 captchaId/captchaText → 参数校验失败


def test_login_wrong_captcha(client):
    r = client.get("/api/v1/auth/captcha").json()
    assert r["code"] == 0
    cid = r["data"]["captchaId"]
    assert r["data"]["svg"].startswith("<svg")
    r2 = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456", "captchaId": cid, "captchaText": "ZZZZ"},
    )
    assert r2.json()["code"] == 20009
    assert r2.status_code == 400


def test_captcha_one_time(client):
    # 正确验证码 + 错误密码：验证码被消费；同一张图第二次直接 20009
    fields = captcha_fields(client)
    r1 = client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad", **fields})
    assert r1.json()["code"] == 20001
    r2 = client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad", **fields})
    assert r2.json()["code"] == 20009


def test_captcha_invalidated_after_three_failures(client):
    from app.core.redis import get_redis

    cid = client.get("/api/v1/auth/captcha").json()["data"]["captchaId"]
    answer = get_redis().get(f"captcha:{cid}")
    for _ in range(3):
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "x", "captchaId": cid, "captchaText": "ZZZZ"},
        )
        assert r.json()["code"] == 20009
    # 连续错 3 次后即使答案正确也已作废
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "x", "captchaId": cid, "captchaText": answer},
    )
    assert r.json()["code"] == 20009


def test_captcha_failure_does_not_lock_account(client):
    # 验证码错误不计入密码失败锁定计数
    username = f"cap_{uuid.uuid4().hex[:8]}"
    _make_user(username)
    for _ in range(5):
        fields = captcha_fields(client)
        bad = {"captchaId": fields["captchaId"], "captchaText": "ZZZZ"}
        client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "Test@123456", **bad},
        )
    r = post_login(client, username, "Test@123456")
    assert r.json()["code"] == 0


# ---------------- MFA 二步验证 ----------------


def test_mfa_toggle_requires_step_up(client):
    username = f"mfa_{uuid.uuid4().hex[:8]}"
    _make_user(username, mobile="13800001234")
    headers = _login(client, username, "Test@123456")
    r = client.post("/api/v1/auth/mfa/toggle", headers=headers, json={"enabled": True})
    assert r.status_code == 403
    assert r.json()["code"] == 20007


def test_mfa_toggle_requires_bound_channel(client):
    username = f"mfa_{uuid.uuid4().hex[:8]}"
    _make_user(username)  # 无手机/邮箱
    headers = _login(client, username, "Test@123456")
    token = _step_up_token(client, headers, "Test@123456")
    r = client.post("/api/v1/auth/mfa/toggle", headers={**headers, "X-Step-Up-Token": token}, json={"enabled": True})
    assert r.json()["code"] == 20014


def _enable_mfa(client, username: str, password: str) -> dict:
    headers = _login(client, username, password)
    token = _step_up_token(client, headers, password)
    r = client.post("/api/v1/auth/mfa/toggle", headers={**headers, "X-Step-Up-Token": token}, json={"enabled": True})
    assert r.json()["code"] == 0, r
    assert r.json()["data"]["mfaEnabled"] is True
    return headers


def test_mfa_full_flow(client):
    username = f"mfa_{uuid.uuid4().hex[:8]}"
    _make_user(username, mobile="13800005678", email="mfa_test@example.com")
    _enable_mfa(client, username, "Test@123456")

    # 登录：密码通过但不发 token，转入二步验证
    r = post_login(client, username, "Test@123456").json()
    assert r["code"] == 0
    data = r["data"]
    assert data["mfaRequired"] is True
    assert "access_token" not in data
    channels = {c["channel"]: c["target"] for c in data["channels"]}
    assert channels["sms"] == "138****5678"
    assert channels["email"] == "m***@example.com"
    mfa_token = data["mfaToken"]

    # 发送验证码（dev 环境回显 debugCode）
    r = client.post("/api/v1/auth/mfa/send", json={"mfaToken": mfa_token, "channel": "sms"}).json()
    assert r["code"] == 0
    sms_code = r["data"]["debugCode"]
    assert sms_code

    # 60 秒内重复发送被拒
    r = client.post("/api/v1/auth/mfa/send", json={"mfaToken": mfa_token, "channel": "sms"})
    assert r.json()["code"] == 20013
    assert r.status_code == 429

    # 错误验证码 → 20011；换个通道重新发送（覆盖旧码）后正确验证码放行
    wrong = "000000" if sms_code != "000000" else "111111"
    r = client.post("/api/v1/auth/mfa/verify", json={"mfaToken": mfa_token, "code": wrong})
    assert r.json()["code"] == 20011
    r2 = client.post("/api/v1/auth/mfa/send", json={"mfaToken": mfa_token, "channel": "email"}).json()
    assert r2["code"] == 0
    code = r2["data"]["debugCode"]
    r3 = client.post("/api/v1/auth/mfa/verify", json={"mfaToken": mfa_token, "code": code})
    assert r3.json()["code"] == 0
    assert r3.json()["data"]["access_token"]
    assert r3.json()["data"]["user"]["mfaEnabled"] is True

    # mfaToken 一次性：验证成功后全部失效
    r4 = client.post("/api/v1/auth/mfa/verify", json={"mfaToken": mfa_token, "code": code})
    assert r4.json()["code"] == 20010


def test_mfa_code_five_failures_invalidate(client):
    username = f"mfa_{uuid.uuid4().hex[:8]}"
    _make_user(username, mobile="13800009999")
    _enable_mfa(client, username, "Test@123456")
    data = post_login(client, username, "Test@123456").json()["data"]
    mfa_token = data["mfaToken"]
    r = client.post("/api/v1/auth/mfa/send", json={"mfaToken": mfa_token, "channel": "sms"}).json()
    assert r["code"] == 0
    wrong = "000000" if r["data"]["debugCode"] != "000000" else "111111"
    for _ in range(5):
        client.post("/api/v1/auth/mfa/verify", json={"mfaToken": mfa_token, "code": wrong})
    # 5 次错误后本次登录作废
    r = client.post("/api/v1/auth/mfa/verify", json={"mfaToken": mfa_token, "code": r["data"]["debugCode"]})
    assert r.json()["code"] == 20010


def test_mfa_disabled_user_unaffected(client):
    username = f"mfa_{uuid.uuid4().hex[:8]}"
    _make_user(username, mobile="13800001111")
    r = post_login(client, username, "Test@123456").json()
    assert r["code"] == 0
    assert "access_token" in r["data"]
    assert r["data"]["user"]["mfaEnabled"] is False


def test_mfa_toggle_off_restores_password_only_login(client):
    username = f"mfa_{uuid.uuid4().hex[:8]}"
    _make_user(username, mobile="13800002222")
    headers = _enable_mfa(client, username, "Test@123456")
    token = _step_up_token(client, headers, "Test@123456")
    r = client.post("/api/v1/auth/mfa/toggle", headers={**headers, "X-Step-Up-Token": token}, json={"enabled": False})
    assert r.json()["code"] == 0
    assert r.json()["data"]["mfaEnabled"] is False
    r = post_login(client, username, "Test@123456").json()
    assert r["code"] == 0
    assert "access_token" in r["data"]


def test_profile_contains_mfa_enabled(client):
    username = f"mfa_{uuid.uuid4().hex[:8]}"
    _make_user(username)
    headers = _login(client, username, "Test@123456")
    r = client.get("/api/v1/auth/profile", headers=headers).json()
    assert r["data"]["mfaEnabled"] is False


# ---------------- 消息通道设置 ----------------


def _cleanup_messaging_config() -> None:
    from sqlalchemy import delete

    from app.core.db import SessionLocal
    from app.modules.settings.models import SysConfig

    db = SessionLocal()
    db.execute(delete(SysConfig).where(SysConfig.key.like("msg.%")))
    db.commit()
    db.close()


def test_messaging_settings_roundtrip_no_plaintext(client, admin_headers):
    _cleanup_messaging_config()
    payload = {
        "messaging": {
            "email": {
                "host": "smtp.example.com",
                "port": 465,
                "security": "ssl",
                "username": "bot@example.com",
                "password": "super-secret-pw",
                "sender": "bizSys <bot@example.com>",
            },
            "sms": {
                "provider": "aliyun",
                "aliyun": {
                    "accessKeyId": "AKIDTEST",
                    "accessKeySecret": "ak-secret-plain",
                    "signName": "bizSys",
                    "templateCode": "SMS_123456",
                },
            },
        }
    }
    r = client.put("/api/v1/admin/settings", headers=admin_headers, json=payload).json()
    assert r["code"] == 0, r
    r = client.get("/api/v1/admin/settings", headers=admin_headers).json()
    msg = r["data"]["messaging"]
    assert msg["email"]["host"] == "smtp.example.com"
    assert msg["email"]["passwordSet"] is True
    assert msg["sms"]["provider"] == "aliyun"
    assert msg["sms"]["aliyun"]["accessKeySecretSet"] is True
    # 整个响应不得出现任何密文明文
    raw = json.dumps(r, ensure_ascii=False)
    assert "super-secret-pw" not in raw
    assert "ak-secret-plain" not in raw
    assert "password" not in msg["email"]

    # 密文落库（不是明文）
    from app.core.db import SessionLocal
    from app.modules.settings.service import get_value

    db = SessionLocal()
    stored = get_value(db, "msg.email.password")
    db.close()
    assert stored.startswith("enc:")

    # 调试通道：邮件已配置会真实发送（这里把 host 清掉验证 debug 兜底）
    _cleanup_messaging_config()
    r = client.post(
        "/api/v1/admin/settings/messaging/test",
        headers=admin_headers,
        json={"channel": "email", "target": "qa@example.com"},
    ).json()
    assert r["code"] == 0
    assert r["data"]["mode"] == "debug"
    assert r["data"]["debugCode"]


def test_messaging_test_endpoint_requires_admin(client, manager_headers):
    r = client.post(
        "/api/v1/admin/settings/messaging/test",
        headers=manager_headers,
        json={"channel": "sms", "target": "13800000000"},
    )
    assert r.status_code == 403

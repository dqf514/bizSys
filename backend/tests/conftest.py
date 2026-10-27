"""pytest 基建：独立测试库 bizsys_test（建表 + 复用幂等种子），必须先设 DB_URL 再导入 app。"""

import os
import pathlib
import re

# 优先级：环境变量 DB_URL（CI）> 本地 .env > 默认（本机 3307 开发库）
_ENV = pathlib.Path(__file__).resolve().parent.parent / ".env"
_URL = "mysql+pymysql://root:bizsys123@127.0.0.1:3307/bizsys?charset=utf8mb4"
if _ENV.exists():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        if _line.startswith("DB_URL="):
            _URL = _line.split("=", 1)[1].strip()
if os.environ.get("DB_URL"):
    _URL = os.environ["DB_URL"]

TEST_URL = re.sub(r"(//[^/]+/)[^?/]+", r"\1bizsys_test", _URL, count=1)
os.environ["DB_URL"] = TEST_URL

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

# 确保测试库存在（连 server 级）
_server_url = re.sub(r"/[^?/]+(\?.*)?$", r"\1", TEST_URL)
_admin_engine = create_engine(_server_url, isolation_level="AUTOCOMMIT")
with _admin_engine.connect() as _conn:
    _conn.execute(text("CREATE DATABASE IF NOT EXISTS bizsys_test CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"))
_admin_engine.dispose()

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402  导入即注册全部模块表

Base.metadata.create_all(bind=engine)

from app.seeds import init_data as seed  # noqa: E402

_seed_session = SessionLocal()
try:
    seed.main()
finally:
    _seed_session.close()


@pytest.fixture(scope="session")
def client():
    from starlette.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="session")
def admin_headers(client):
    return _login(client, "admin", "Admin@123456")


def captcha_fields(client) -> dict:
    """获取图形验证码并直接从 Redis 读答案（测试与 dev 共用 Redis 实例）。"""
    from app.core.redis import get_redis

    r = client.get("/api/v1/auth/captcha").json()
    cid = r["data"]["captchaId"]
    return {"captchaId": cid, "captchaText": get_redis().get(f"captcha:{cid}")}


def post_login(client, username: str, password: str):
    """带图形验证码的登录请求，返回原始响应（不断言）。"""
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, **captcha_fields(client)},
    )


def _login(client, username: str, password: str) -> dict:
    r = post_login(client, username, password)
    data = r.json()
    assert data["code"] == 0, data
    return {"Authorization": f"Bearer {data['data']['access_token']}"}


@pytest.fixture(scope="session")
def manager_headers(client):
    return _login(client, "manager1", "Test@123456")


@pytest.fixture(scope="session")
def leader_headers(client):
    return _login(client, "leader1", "Test@123456")


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()

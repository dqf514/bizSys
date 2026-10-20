"""数据维护：备份设置读写 / 手动备份生成文件 / 列表下载删除 / retention 清理 / 权限与入参拦截。

破坏性 purge 用例在 test_zz_purge.py（字母序最后，避免删用户影响其他用例的会话夹具）。
"""

import json
import uuid
from pathlib import Path

UUID = uuid.uuid4().hex[:8]
TMP_DIR = ""  # 每个用例写入独立临时目录


def _set_tmp_dir(client, headers, d: Path) -> None:
    r = client.put(
        "/api/v1/admin/maintenance/settings",
        headers=headers,
        json={"backup": {"dir": str(d)}},
    ).json()
    assert r["code"] == 0, r


def test_settings_read_write(client, admin_headers, tmp_path):
    r = client.get("/api/v1/admin/maintenance/settings", headers=admin_headers).json()
    assert r["code"] == 0
    data = r["data"]
    assert data["backup"]["retention"] >= 1
    assert data["backup"]["dbBackend"] == "mysql"
    assert "mysqldumpAvailable" in data["backup"]
    assert data["showDemoAccounts"] is False

    r = client.put(
        "/api/v1/admin/maintenance/settings",
        headers=admin_headers,
        json={"backup": {"enabled": True, "time": "03:30", "retention": 5}, "showDemoAccounts": True},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["backup"]["enabled"] is True
    assert r["data"]["backup"]["time"] == "03:30"
    assert r["data"]["backup"]["retention"] == 5
    assert r["data"]["showDemoAccounts"] is True

    # 公开 branding 带出开关（登录页未登录态可读）
    r = client.get("/api/v1/public/branding").json()
    assert r["data"]["showDemoAccounts"] is True

    # 非法时间格式拒绝；还原开关
    r = client.put(
        "/api/v1/admin/maintenance/settings",
        headers=admin_headers,
        json={"backup": {"time": "25:99"}},
    ).json()
    assert r["code"] != 0
    client.put(
        "/api/v1/admin/maintenance/settings",
        headers=admin_headers,
        json={"backup": {"enabled": False, "time": "02:00", "retention": 7}, "showDemoAccounts": False},
    )


def test_backup_run_list_download_delete(client, admin_headers, tmp_path):
    _set_tmp_dir(client, admin_headers, tmp_path)
    # 手动备份生成文件（bizsys_test 为 MySQL，mysqldump 不在则内置导出）
    r = client.post("/api/v1/admin/maintenance/backup/run", headers=admin_headers).json()
    assert r["code"] == 0, r
    name = r["data"]["name"]
    assert name.endswith(".sql.gz") and r["data"]["size"] > 0
    assert (tmp_path / name).exists()
    meta = json.loads((tmp_path / f"{name}.meta.json").read_text(encoding="utf-8"))
    assert meta["kind"] == "manual"

    # 列表
    r = client.get("/api/v1/admin/maintenance/backups", headers=admin_headers).json()
    assert any(b["name"] == name for b in r["data"])

    # 下载（gzip 头）
    resp = client.get(f"/api/v1/admin/maintenance/backups/{name}/download", headers=admin_headers)
    assert resp.status_code == 200 and resp.content[:2] == b"\x1f\x8b"

    # 目录穿越拦截（不匹配路由或非 0 业务码均可）
    resp = client.get("/api/v1/admin/maintenance/backups/..%2F..%2Fevil.sql.gz/download", headers=admin_headers)
    assert resp.status_code != 200

    # 删除
    r = client.delete(f"/api/v1/admin/maintenance/backups/{name}", headers=admin_headers).json()
    assert r["code"] == 0
    assert not (tmp_path / name).exists()
    r = client.delete(f"/api/v1/admin/maintenance/backups/{name}", headers=admin_headers).json()
    assert r["code"] != 0


def test_backup_retention(client, admin_headers, tmp_path):
    _set_tmp_dir(client, admin_headers, tmp_path)
    r = client.put(
        "/api/v1/admin/maintenance/settings",
        headers=admin_headers,
        json={"backup": {"retention": 1, "dir": str(tmp_path)}},
    ).json()
    assert r["code"] == 0
    for _ in range(2):
        r = client.post("/api/v1/admin/maintenance/backup/run", headers=admin_headers).json()
        assert r["code"] == 0, r
    r = client.get("/api/v1/admin/maintenance/backups", headers=admin_headers).json()
    assert len(r["data"]) == 1  # 只保留最新一份
    # 还原 retention
    client.put(
        "/api/v1/admin/maintenance/settings",
        headers=admin_headers,
        json={"backup": {"retention": 7, "dir": ""}},
    )


def test_maintenance_perm_guard(client, manager_headers):
    """biz_user 无 admin:backup:view / admin:maintenance:purge → 403。"""
    r = client.get("/api/v1/admin/maintenance/settings", headers=manager_headers).json()
    assert r["code"] == 20002
    r = client.post(
        "/api/v1/admin/maintenance/purge",
        headers=manager_headers,
        json={"password": "Test@123456", "confirm": "CLEAR"},
    ).json()
    assert r["code"] == 20002


def test_purge_rejects_bad_password_and_confirm(client, admin_headers):
    r = client.post(
        "/api/v1/admin/maintenance/purge",
        headers=admin_headers,
        json={"password": "wrong-password", "confirm": "CLEAR"},
    ).json()
    assert r["code"] == 20004
    r = client.post(
        "/api/v1/admin/maintenance/purge",
        headers=admin_headers,
        json={"password": "Admin@123456", "confirm": "YES"},
    ).json()
    assert r["code"] == 10001

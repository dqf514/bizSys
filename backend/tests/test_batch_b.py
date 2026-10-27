"""批次B：个人档案（profile/step-up/头像/紧急联系人/银行卡）+ 管理员组织字段。"""

import io
import uuid

from conftest import post_login

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # 正确魔数的最小假 PNG
UUID = uuid.uuid4().hex[:8]


def _login(client, username: str, password: str) -> dict:
    r = post_login(client, username, password)
    data = r.json()
    assert data["code"] == 0, data
    return {"Authorization": f"Bearer {data['data']['access_token']}"}


def _create_user(client, admin_headers, **extra) -> dict:
    suf = uuid.uuid4().hex[:8]
    payload = {"username": f"pb_{suf}", "password": "Test@123456", "name": f"批次B_{suf}",
               "status": "enabled", "role_ids": []}
    payload.update(extra)
    r = client.post("/api/v1/admin/users", headers=admin_headers, json=payload).json()
    assert r["code"] == 0, r
    return _login(client, f"pb_{suf}", "Test@123456")


def _step_up_headers(client, headers, password="Test@123456") -> dict:
    r = client.post("/api/v1/auth/step-up", headers=headers, json={"password": password}).json()
    assert r["code"] == 0, r
    return {**headers, "X-Step-Up-Token": r["data"]["stepUpToken"]}


# ---------------- 档案读取 ----------------


def test_profile_get(client, admin_headers):
    h = _create_user(client, admin_headers)
    r = client.get("/api/v1/auth/profile", headers=h).json()
    assert r["code"] == 0, r
    d = r["data"]
    for k in ("username", "name", "mobile", "email", "employeeNo", "hireDate",
              "jobLevel", "avatarUrl", "deptName", "leaderName"):
        assert k in d, k
    assert d["leaderName"] == ""  # 无部门链 → 空（前端显示 "-"）


def test_profile_direct_leader(client, admin_headers, db):
    """直接领导：部门负责人链（本部门无负责人向上找父部门）。"""
    from app.modules.admin.models import Dept, UserDept
    from app.modules.auth.models import User

    suf = uuid.uuid4().hex[:8]
    parent = Dept(name=f"pb_父部门_{suf}", code=f"pb_p_{suf}")
    child = Dept(name=f"pb_子部门_{suf}", code=f"pb_c_{suf}", parent_id=None)
    db.add(parent)
    db.flush()
    child.parent_id = parent.id
    db.add(child)
    db.flush()
    boss_h = _create_user(client, admin_headers)
    emp_h = _create_user(client, admin_headers)
    # 找到刚建的 boss / emp 用户
    me = client.get("/api/v1/auth/me", headers=boss_h).json()["data"]
    boss_id = me["id"]
    emp_id = client.get("/api/v1/auth/me", headers=emp_h).json()["data"]["id"]
    db.add(UserDept(user_id=boss_id, dept_id=parent.id, is_primary=0, is_leader=1))
    db.add(UserDept(user_id=emp_id, dept_id=child.id, is_primary=1, is_leader=0))
    db.commit()
    # 员工主部门冗余同步（真实链路里由 admin 编辑用户时写入）
    emp = db.get(User, emp_id)
    emp.dept_id = child.id
    db.commit()

    d = client.get("/api/v1/auth/profile", headers=emp_h).json()["data"]
    assert d["leaderName"] == me["name"], d


# ---------------- step-up + 联系方式变更 ----------------


def test_contact_change_requires_step_up(client, admin_headers):
    h = _create_user(client, admin_headers)
    # 变更电话无 step-up → 403/20007
    r = client.patch("/api/v1/auth/profile", headers=h, json={"mobile": "13800000000"})
    assert r.status_code == 403 and r.json()["code"] == 20007
    # 未变更字段不需要 step-up
    r = client.patch("/api/v1/auth/profile", headers=h, json={"mobile": ""})
    assert r.json()["code"] == 0
    # 错误密码 step-up → 20004
    r = client.post("/api/v1/auth/step-up", headers=h, json={"password": "wrong-pass"})
    assert r.json()["code"] == 20004
    # 正确密码 → token；带 token 变更成功
    h2 = _step_up_headers(client, h)
    r = client.patch("/api/v1/auth/profile", headers=h2,
                     json={"mobile": "13800000000", "email": f"pb_{UUID}@example.com"})
    assert r.json()["code"] == 0, r.json()
    assert r.json()["data"]["mobile"] == "13800000000"
    # 伪造 token → 403
    r = client.patch("/api/v1/auth/profile",
                     headers={**h, "X-Step-Up-Token": "bad-token"},
                     json={"mobile": "13900000000"})
    assert r.status_code == 403 and r.json()["code"] == 20007


def test_email_format_and_unique(client, admin_headers):
    _create_user(client, admin_headers, email=f"pb_dup_{UUID}@example.com")
    h2 = _create_user(client, admin_headers)
    s2 = _step_up_headers(client, h2)
    # 格式错误 → 10001
    r = client.patch("/api/v1/auth/profile", headers=s2, json={"email": "not-an-email"})
    assert r.json()["code"] == 10001
    # 撞别人的邮箱 → 20008
    r = client.patch("/api/v1/auth/profile", headers=s2, json={"email": f"pb_dup_{UUID}@example.com"})
    assert r.json()["code"] == 20008
    # 电话格式错误 → 10001
    r = client.patch("/api/v1/auth/profile", headers=s2, json={"mobile": "abc!!"})
    assert r.json()["code"] == 10001


def test_profile_org_fields_readonly_for_self(client, admin_headers):
    """组织字段只能管理员改：self PATCH 携带 employeeNo 被忽略。"""
    h = _create_user(client, admin_headers)
    h2 = _step_up_headers(client, h)
    r = client.patch("/api/v1/auth/profile", headers=h2,
                     json={"mobile": "", "email": "", "employeeNo": "HACK01", "jobLevel": "P9"})
    assert r.json()["code"] == 0
    d = client.get("/api/v1/auth/profile", headers=h).json()["data"]
    assert d["employeeNo"] == "" and d["jobLevel"] == ""


# ---------------- 头像 ----------------


def test_avatar_upload_and_serve(client, admin_headers):
    h = _create_user(client, admin_headers)
    r = client.post("/api/v1/auth/profile/avatar", headers=h,
                    files={"file": ("a.png", io.BytesIO(PNG_BYTES), "image/png")})
    assert r.json()["code"] == 0, r.json()
    url = r.json()["data"]["avatarUrl"]
    assert url.startswith("/api/v1/auth/avatar/")
    # 公开可读（无 token）
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    # /auth/me 带 avatar_url
    me = client.get("/api/v1/auth/me", headers=h).json()["data"]
    assert me.get("avatar_url") or me.get("avatarUrl")


def test_avatar_reject_bad_type_and_magic(client, admin_headers):
    h = _create_user(client, admin_headers)
    # 扩展名不允许
    r = client.post("/api/v1/auth/profile/avatar", headers=h,
                    files={"file": ("a.gif", io.BytesIO(b"GIF89a" + b"\x00" * 32), "image/gif")})
    assert r.json()["code"] == 10001
    # 扩展名 png 但魔数不对
    r = client.post("/api/v1/auth/profile/avatar", headers=h,
                    files={"file": ("a.png", io.BytesIO(b"not a png at all........."), "image/png")})
    assert r.json()["code"] == 10001


# ---------------- 紧急联系人 ----------------


def test_contacts_crud_and_isolation(client, admin_headers):
    h1 = _create_user(client, admin_headers)
    h2 = _create_user(client, admin_headers)
    r = client.post("/api/v1/auth/profile/contacts", headers=h1,
                    json={"name": "张三", "relation": "配偶", "phone": "13800000000", "remark": "备注"})
    assert r.status_code == 201, r.json()
    cid = r.json()["data"]["id"]
    rows = client.get("/api/v1/auth/profile/contacts", headers=h1).json()["data"]
    assert len(rows) == 1 and rows[0]["name"] == "张三"
    r = client.put(f"/api/v1/auth/profile/contacts/{cid}", headers=h1,
                   json={"name": "张三", "relation": "家人", "phone": "13900000000"})
    assert r.json()["code"] == 0 and r.json()["data"]["relation"] == "家人"
    # 他人操作 → 404（不暴露存在性）
    assert client.put(f"/api/v1/auth/profile/contacts/{cid}", headers=h2,
                      json={"name": "x"}).json()["code"] == 10002
    assert client.delete(f"/api/v1/auth/profile/contacts/{cid}", headers=h2).json()["code"] == 10002
    assert client.get("/api/v1/auth/profile/contacts", headers=h2).json()["data"] == []
    client.delete(f"/api/v1/auth/profile/contacts/{cid}", headers=h1)
    assert client.get("/api/v1/auth/profile/contacts", headers=h1).json()["data"] == []


# ---------------- 银行卡 ----------------

CARD_NO = "6222021001118888"


def test_bank_accounts_masking_and_step_up(client, admin_headers):
    h = _create_user(client, admin_headers, name="批次B银行卡")
    # 新增无 step-up → 403/20007
    r = client.post("/api/v1/auth/profile/bank-accounts", headers=h,
                    json={"bankName": "工商银行", "cardNo": CARD_NO, "holderName": "批次B银行卡"})
    assert r.status_code == 403 and r.json()["code"] == 20007
    s = _step_up_headers(client, h)
    r = client.post("/api/v1/auth/profile/bank-accounts", headers=s,
                    json={"bankName": "工商银行", "cardNo": CARD_NO, "holderName": "批次B银行卡"})
    assert r.status_code == 201, r.json()
    bid = r.json()["data"]["id"]
    # 列表脱敏
    rows = client.get("/api/v1/auth/profile/bank-accounts", headers=h).json()["data"]
    assert len(rows) == 1 and "8888" in rows[0]["cardNo"] and CARD_NO not in rows[0]["cardNo"]
    # 完整查看需 step-up
    assert client.get(f"/api/v1/auth/profile/bank-accounts/{bid}/reveal", headers=h).json()["code"] == 20007
    full = client.get(f"/api/v1/auth/profile/bank-accounts/{bid}/reveal", headers=s).json()["data"]
    assert full["cardNo"] == CARD_NO
    # 卡号非数字 → 422/10001
    r = client.post("/api/v1/auth/profile/bank-accounts", headers=s,
                    json={"bankName": "工商银行", "cardNo": "abcd1234", "holderName": "x"})
    assert r.status_code == 422 and r.json()["code"] == 10001
    # 删除需 step-up
    assert client.delete(f"/api/v1/auth/profile/bank-accounts/{bid}", headers=h).json()["code"] == 20007
    assert client.delete(f"/api/v1/auth/profile/bank-accounts/{bid}", headers=s).json()["code"] == 0
    assert client.get("/api/v1/auth/profile/bank-accounts", headers=h).json()["data"] == []


def test_bank_audit_no_full_card(client, admin_headers, db):
    """敏感变更审计不落完整卡号明文。"""
    from app.modules.admin.models import AuditLog

    h = _create_user(client, admin_headers, name="批次B审计")
    s = _step_up_headers(client, h)
    card = "6222021001119999"
    r = client.post("/api/v1/auth/profile/bank-accounts", headers=s,
                    json={"bankName": "招商银行", "cardNo": card, "holderName": "批次B审计"})
    assert r.status_code == 201
    row = db.query(AuditLog).filter(
        AuditLog.module == "auth", AuditLog.action == "bank_create", AuditLog.deleted == 0
    ).order_by(AuditLog.id.desc()).first()
    assert row is not None
    assert card not in (row.detail or "")
    assert "9999" in (row.detail or "")


# ---------------- 管理员组织字段 ----------------


def test_admin_user_org_fields(client, admin_headers):
    suf = uuid.uuid4().hex[:8]
    r = client.post("/api/v1/admin/users", headers=admin_headers, json={
        "username": f"pb_org_{suf}", "password": "Test@123456", "name": f"批次B组织_{suf}",
        "employeeNo": f"E{suf[:6]}", "hireDate": "2024-03-01", "jobLevel": "P5",
    }).json()
    assert r["code"] == 0, r
    uid = r["data"]["id"]
    assert r["data"]["employeeNo"] == f"E{suf[:6]}" and r["data"]["hireDate"] == "2024-03-01"
    # 管理员可改（表单全量提交，与 mobile/email 同一约定）
    r = client.put(f"/api/v1/admin/users/{uid}", headers=admin_headers, json={
        "username": f"pb_org_{suf}", "name": f"批次B组织_{suf}",
        "employeeNo": f"E{suf[:6]}", "hireDate": "2024-03-01", "jobLevel": "P6",
    }).json()
    assert r["code"] == 0 and r["data"]["jobLevel"] == "P6"
    # 本人档案可见（只读）
    h = _login(client, f"pb_org_{suf}", "Test@123456")
    d = client.get("/api/v1/auth/profile", headers=h).json()["data"]
    assert d["employeeNo"] == f"E{suf[:6]}" and d["jobLevel"] == "P6" and d["hireDate"] == "2024-03-01"

"""一键清空测试数据（破坏性，字母序最后执行）：清空集/保留集断言 + 会话失效 + 清空后重种子。"""

import uuid

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modules.admin.models import Dept, DictType, Menu, Role
from app.modules.approval.models import ApprovalDefinition
from app.modules.auth.models import User
from app.modules.contract.models import Contract
from app.modules.crm.models import Customer

UUID = uuid.uuid4().hex[:8]


def _count(model) -> int:
    db = SessionLocal()
    try:
        return db.scalar(select(func.count()).select_from(model)) or 0
    finally:
        db.close()


def test_purge_clears_test_data(client, admin_headers, tmp_path):
    # 备份目录指向临时目录，避免污染 dev backups
    r = client.put(
        "/api/v1/admin/maintenance/settings",
        headers=admin_headers,
        json={"backup": {"dir": str(tmp_path)}},
    ).json()
    assert r["code"] == 0

    # 造业务数据
    r = client.post(
        "/api/v1/crm/customers",
        headers=admin_headers,
        json={"name": f"清空测试客户_{UUID}", "level": "A"},
    ).json()
    assert r["code"] == 0, r
    cust_id = r["data"]["id"]
    r = client.post(
        "/api/v1/contract/contracts",
        headers=admin_headers,
        json={"name": f"清空测试合同_{UUID}", "customer_id": cust_id, "amount": 1},
    ).json()
    assert r["code"] == 0, r

    assert _count(Customer) > 0 and _count(Contract) > 0
    menus_before = _count(Menu)
    dicts_before = _count(DictType)
    flows_before = _count(ApprovalDefinition)
    roles_before = _count(Role)

    # 执行清空
    r = client.post(
        "/api/v1/admin/maintenance/purge",
        headers=admin_headers,
        json={"password": "Admin@123456", "confirm": "CLEAR"},
    ).json()
    assert r["code"] == 0, r
    counts = r["data"]["counts"]
    assert counts.get("sys_user", 0) >= 1  # 删掉了非 admin 用户
    assert r["data"]["backup"]["name"].endswith(".sql.gz")  # 清空前自动备份

    db = SessionLocal()
    try:
        # 保留集
        assert _count(Menu) == menus_before
        assert _count(DictType) == dicts_before
        assert _count(ApprovalDefinition) == flows_before
        assert _count(Role) == roles_before
        assert _count(Dept) > 0
        usernames = list(db.scalars(select(User.username)))
        assert usernames == ["admin"]
        # 清空集
        assert _count(Customer) == 0 and _count(Contract) == 0
        from app.modules.admin.models import AuditLog

        actions = list(db.scalars(select(AuditLog.action)))
        assert actions == ["maintenance_purge"]  # 审计清空后只剩本次清空记录
    finally:
        db.close()

    # manager1 已被删除：登录失败；admin 正常
    r = client.post("/api/v1/auth/login", json={"username": "manager1", "password": "Test@123456"}).json()
    assert r["code"] != 0
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123456"}).json()
    assert r["code"] == 0

    # 收尾：重跑种子补回演示账号（保持测试库可重复运行）
    from app.seeds import init_data

    init_data.main()
    db = SessionLocal()
    try:
        # purge 删除用户后种子以新 id 重建，需把种子流程 USER 节点的 approver_value 重指到新 id
        name_to_username = {"部门负责人": "manager1", "分管领导": "leader1", "系统管理员": "admin"}
        from app.modules.approval.models import ApprovalNode

        for uname, username in name_to_username.items():
            uid = db.scalar(select(User.id).where(User.username == username, User.deleted == 0))
            if uid:
                for n in db.scalars(
                    select(ApprovalNode).where(
                        ApprovalNode.approver_type == "USER", ApprovalNode.approver_name == uname
                    )
                ):
                    n.approver_value = str(uid)
        db.commit()
        assert db.scalar(select(User).where(User.username == "manager1", User.deleted == 0))
    finally:
        db.close()
    client.put(
        "/api/v1/admin/maintenance/settings",
        headers={"Authorization": f"Bearer {r['data']['access_token']}"},
        json={"backup": {"dir": ""}},
    )

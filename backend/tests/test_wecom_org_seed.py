"""E1：企业微信**全模拟**组织 / 人员 / 标签种子。

覆盖：
- 11 个部门（WC01…WC11）+ 父子层级 + 负责人（dept.manager_id ↔ 任职表 is_leader）；
- 23 个标签角色（wc_tag_01…）**只作审批人来源、不挂菜单**；
- 40 个模拟账号（mock001…mock040），密码统一；
- 任职（多部门 + 主部门）与标签关系正确；
- **隐私红线**：无真实姓名 / 手机 / 邮箱 / 证件号残留。
"""

from sqlalchemy import select

from app.modules.admin.models import Dept, Role, UserDept, UserRole
from app.modules.auth.models import User
from app.modules.hr.models import HrEmployee, HrPosition
from app.seeds import wecom_org


def _mock_users(db) -> list[User]:
    return list(
        db.scalars(select(User).where(User.username.like("mock%"), User.deleted == 0).order_by(User.username)).all()
    )


def test_departments_seeded(db):
    """11 个企微部门落地，父子关系按文档树。"""
    rows = list(db.scalars(select(Dept).where(Dept.code.like("WC%"), Dept.deleted == 0)).all())
    assert len(rows) == 11
    by_name = {d.name: d for d in rows}
    root = by_name["合肥汽车检测认证技术中心"]
    assert root.parent_id is None
    assert by_name["业务运营部"].parent_id == root.id
    assert by_name["土建"].parent_id == by_name["项目建设部"].id
    assert {d.code for d in rows} == {f"WC{i:02d}" for i in range(1, 12)}
    db.rollback()


def test_tag_roles_have_no_menus(db):
    """标签 → 角色：23 个角色，名称对齐企微标签，且**不挂任何菜单**（只作审批人来源）。"""
    roles = list(db.scalars(select(Role).where(Role.code.like("wc_tag_%"), Role.deleted == 0)).all())
    assert len(roles) == 23
    assert {r.code for r in roles} == {wecom_org.tag_role_code(t["name"]) for t in wecom_org.tag_data()}
    assert all(len(r.menus) == 0 for r in roles)
    assert all("企业微信标签" in r.remark for r in roles)
    db.rollback()


def test_mock_users_seeded(db):
    """40 个模拟账号：用户名 mockNNN、姓名 模拟员工NN、密码统一。"""
    users = _mock_users(db)
    assert len(users) == 40
    for u in users:
        assert u.name.startswith("模拟员工"), u.name
        assert u.employee_no.startswith("MOCK")
    assert {u.username for u in users} == {f"mock{i:03d}" for i in range(1, 41)}
    db.rollback()


def test_memberships_and_tags(db):
    """任职（主部门唯一）与标签角色挂接正确。"""
    u6 = db.scalar(select(User).where(User.username == "mock006", User.deleted == 0))
    rows = list(
        db.scalars(select(UserDept).where(UserDept.user_id == u6.id, UserDept.deleted == 0).order_by(UserDept.id)).all()
    )
    assert len(rows) == 2
    assert sum(r.is_primary for r in rows) == 1
    primary = next(r for r in rows if r.is_primary == 1)
    dept = db.get(Dept, primary.dept_id)
    assert dept.name == "业务运营部"
    assert u6.dept_id == dept.id

    # 标签 → 角色 → 用户
    role = db.scalar(
        select(Role).where(Role.code == wecom_org.tag_role_code("董事长"), Role.deleted == 0)
    )
    assert role is not None and role.name == "董事长"
    u1 = db.scalar(select(User).where(User.username == "mock001", User.deleted == 0))
    link = db.scalar(
        select(UserRole).where(UserRole.user_id == u1.id, UserRole.role_id == role.id, UserRole.deleted == 0)
    )
    assert link is not None
    db.rollback()


def test_dept_manager_matches_leader(db):
    """部门负责人：dept.manager_id 与任职表 is_leader 一致（审批引擎 DEPT_LEADER 读任职表）。"""
    dept = db.scalar(select(Dept).where(Dept.code == "WC03", Dept.deleted == 0))
    assert dept.name == "业务运营部"
    assert dept.manager_id
    leader = db.get(User, dept.manager_id)
    assert leader.name == "模拟员工06"
    row = db.scalar(
        select(UserDept).where(
            UserDept.user_id == leader.id, UserDept.dept_id == dept.id, UserDept.deleted == 0
        )
    )
    assert row is not None and row.is_leader == 1
    db.rollback()


def test_resigned_user_disabled(db):
    """已离职成员：账号禁用、档案 employ_status=resigned。"""
    u = db.scalar(select(User).where(User.username == "mock039", User.deleted == 0))
    assert u.status == "disabled"
    emp = db.scalar(select(HrEmployee).where(HrEmployee.employee_no == "MOCK039", HrEmployee.deleted == 0))
    assert emp is not None and emp.employ_status == "resigned"
    db.rollback()


def test_employee_archive_and_positions(db):
    """员工档案与岗位按脱敏数据生成。"""
    emps = list(
        db.scalars(select(HrEmployee).where(HrEmployee.employee_no.like("MOCK%"), HrEmployee.deleted == 0)).all()
    )
    assert len(emps) == 40
    assert all(e.name.startswith("模拟员工") for e in emps)
    positions = list(
        db.scalars(select(HrPosition).where(HrPosition.code.like("WCP%"), HrPosition.deleted == 0)).all()
    )
    assert positions
    assert {p.name for p in positions} >= {"董事长", "总经理", "财务负责人", "项目总指挥"}
    assert all(p.code.startswith("WCP") for p in positions)
    db.rollback()


def test_no_real_pii_leaked(db):
    """隐私红线：模拟人员的手机 / 邮箱 / 证件号 / 企微 ID 一律为空。"""
    users = _mock_users(db)
    assert all(not u.mobile for u in users)
    assert all(not u.email for u in users)
    assert all(not u.wecom_userid for u in users)
    emps = list(
        db.scalars(select(HrEmployee).where(HrEmployee.employee_no.like("MOCK%"), HrEmployee.deleted == 0)).all()
    )
    assert all(not e.id_no for e in emps)
    assert all(not e.mobile for e in emps)
    assert all(not e.email for e in emps)
    db.rollback()


def test_import_org_is_idempotent(db):
    """重复执行导入不产生重复行（种子幂等）。"""
    before_depts = len(db.scalars(select(Dept).where(Dept.code.like("WC%"), Dept.deleted == 0)).all())
    before_users = len(_mock_users(db))
    summary = wecom_org.import_org(db)
    assert summary["depts"] == 11
    assert summary["tag_roles"] == 23
    assert summary["users"] == 40
    assert len(db.scalars(select(Dept).where(Dept.code.like("WC%"), Dept.deleted == 0)).all()) == before_depts
    assert len(_mock_users(db)) == before_users
    db.rollback()

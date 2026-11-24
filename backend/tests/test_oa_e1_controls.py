"""E1：OA 表单新控件（明细表 / 公式 / 手机号 / 位置 / 假勤原子 / 人事原子）
+ 模板可见范围（scope）+ 节点字段权限掩码。

覆盖：
- 公式字段由服务端重算（前端提交的值不作数）；
- 明细表：子列必填 / 数字列类型 / 未定义列 → 62003；
- 手机号正则、假勤/人事原子类型约束；
- 可见范围：目录裁剪 + 直调接口拦截（403）；
- 实例详情按当前待办节点的字段权限掩码（hidden 不出参、viewonly 只读）。
"""

import json
import uuid

from sqlalchemy import select

from app.core.exceptions import BizException
from app.modules.approval import service as approval_svc
from app.modules.approval.schemas import DefinitionIn, NodeIn
from app.modules.auth.models import User
from app.modules.oa import service as oa_svc
from app.modules.oa.models import OaForm


def _users(db):
    admin = db.scalar(select(User).where(User.username == "admin"))
    m1 = db.scalar(select(User).where(User.username == "manager1"))
    l1 = db.scalar(select(User).where(User.username == "leader1"))
    return admin, m1, l1


def _form(db, fields, *, scope=None, definition_id=None, key=None):
    form = OaForm(
        key=key or ("ut_e1_" + uuid.uuid4().hex[:8]),
        name="E1 测试表单",
        form_version=1,
        status="published",
        category="other",
        schema_json=json.dumps({"fields": fields}, ensure_ascii=False),
        scope_json=oa_svc._scope_json(scope),
        flow_definition_id=definition_id,
    )
    db.add(form)
    db.flush()
    return form


def _apply(db, form, user, data):
    return oa_svc.apply(db, form.id, user, data)


# ---------------- 公式 ----------------


def test_formula_recomputed_by_server(db):
    """公式字段：提交时服务端重算，前端塞的错值被覆盖。"""
    _admin, m1, _l1 = _users(db)
    form = _form(
        db,
        [
            {"key": "qty", "label": "数量", "type": "number"},
            {"key": "price", "label": "单价", "type": "money"},
            {"key": "total", "label": "合计", "type": "formula", "formula": "Money-qty * Money-price"},
        ],
    )
    inst = _apply(db, form, m1, {"qty": 3, "price": 5, "total": 999})
    assert inst.status == "approved"
    detail = oa_svc.instance_detail(db, inst, m1)
    assert detail["formData"]["total"] == 15
    db.rollback()


def test_formula_reference_missing_field_rejected(db):
    """公式引用不存在的控件 → 发布前校验失败（62002）。"""
    form = _form(
        db,
        [
            {"key": "a", "label": "甲", "type": "number"},
            {"key": "b", "label": "乙", "type": "formula", "formula": "Money-a + Money-ghost"},
        ],
    )
    try:
        oa_svc.validate_fields(oa_svc.fields_of(form))
        raise AssertionError("expected BizException")
    except BizException as e:
        assert e.code == 62002
    db.rollback()


# ---------------- 明细表 ----------------


def test_table_rows_validated(db):
    """明细表：必填子列缺失 / 数字列非数字 / 未定义列 → 62003；合法行通过。"""
    _admin, m1, _l1 = _users(db)
    form = _form(
        db,
        [
            {
                "key": "items",
                "label": "明细",
                "type": "table",
                "columns": [
                    {"key": "name", "label": "名称", "type": "text", "required": True},
                    {"key": "price", "label": "单价", "type": "money"},
                ],
            }
        ],
    )
    # 合法
    inst = _apply(db, form, m1, {"items": [{"name": "钢管", "price": 12.5}]})
    detail = oa_svc.instance_detail(db, inst, m1)
    assert detail["formData"]["items"][0]["name"] == "钢管"
    # 必填子列缺失
    try:
        _apply(db, form, m1, {"items": [{"price": 1}]})
        raise AssertionError("expected BizException")
    except BizException as e:
        assert e.code == 62003
    # 数字列传文本
    try:
        _apply(db, form, m1, {"items": [{"name": "x", "price": "abc"}]})
        raise AssertionError("expected BizException")
    except BizException as e:
        assert e.code == 62003
    # 未定义列
    try:
        _apply(db, form, m1, {"items": [{"name": "x", "ghost": 1}]})
        raise AssertionError("expected BizException")
    except BizException as e:
        assert e.code == 62003
    db.rollback()


def test_table_without_columns_rejected_on_publish(db):
    """明细表未配子列 → 发布前校验失败（62002）。"""
    form = _form(db, [{"key": "items", "label": "明细", "type": "table"}])
    try:
        oa_svc.validate_fields(oa_svc.fields_of(form))
        raise AssertionError("expected BizException")
    except BizException as e:
        assert e.code == 62002
    db.rollback()


# ---------------- 手机号 / 位置 / 原子控件 ----------------


def test_phone_validation(db):
    """手机号控件：格式非法 → 62003；合法通过。"""
    _admin, m1, _l1 = _users(db)
    form = _form(db, [{"key": "mobile", "label": "手机号", "type": "phone"}])
    assert _apply(db, form, m1, {"mobile": "13800138000"}).id
    try:
        _apply(db, form, m1, {"mobile": "12345"})
        raise AssertionError("expected BizException")
    except BizException as e:
        assert e.code == 62003
    db.rollback()


def test_attendance_atomic_type_constrained(db):
    """假勤原子控件：配置了 refType 就只能取该原子类型。"""
    _admin, m1, _l1 = _users(db)
    form = _form(db, [{"key": "leave", "label": "请假", "type": "attendance", "refType": "vacation"}])
    assert _apply(db, form, m1, {"leave": {"kind": "vacation", "detail": "3 天"}}).id
    try:
        _apply(db, form, m1, {"leave": {"kind": "attendance", "detail": "x"}})
        raise AssertionError("expected BizException")
    except BizException as e:
        assert e.code == 62003
    # 原子类型完全缺失
    try:
        _apply(db, form, m1, {"leave": {"detail": "x"}})
        raise AssertionError("expected BizException")
    except BizException as e:
        assert e.code == 62003
    db.rollback()


def test_location_control_accepts_text(db):
    """位置控件：文本值通过。"""
    _admin, m1, _l1 = _users(db)
    form = _form(db, [{"key": "spot", "label": "地点", "type": "location"}])
    assert _apply(db, form, m1, {"spot": "合肥高新区"}).id
    db.rollback()


# ---------------- 可见范围 ----------------


def test_scope_filters_catalog(db):
    """可见范围：命中的账号可见，未命中的在目录里看不到。"""
    _admin, m1, l1 = _users(db)
    mine = _form(db, [{"key": "reason", "label": "事由", "type": "text"}], scope={"users": [m1.username]})
    assert any(f["id"] == mine.id for g in oa_svc.catalog(db, m1) for f in g["forms"])
    assert all(f["id"] != mine.id for g in oa_svc.catalog(db, l1) for f in g["forms"])
    db.rollback()


def test_scope_blocks_apply(db):
    """可见范围外直接调发起接口 → 403。"""
    _admin, _m1, l1 = _users(db)
    form = _form(db, [{"key": "reason", "label": "事由", "type": "text"}], scope={"depts": ["不存在的部门"]})
    assert all(f["id"] != form.id for g in oa_svc.catalog(db, l1) for f in g["forms"])
    try:
        _apply(db, form, l1, {"reason": "x"})
        raise AssertionError("expected BizException")
    except BizException as e:
        assert e.http_status == 403
    db.rollback()


def test_empty_scope_visible_to_all(db):
    """未配置可见范围 = 全员可见。"""
    _admin, m1, l1 = _users(db)
    form = _form(db, [{"key": "reason", "label": "事由", "type": "text"}], scope=None)
    assert any(f["id"] == form.id for g in oa_svc.catalog(db, m1) for f in g["forms"])
    assert any(f["id"] == form.id for g in oa_svc.catalog(db, l1) for f in g["forms"])
    db.rollback()


# ---------------- 节点字段权限掩码 ----------------


def test_instance_detail_applies_field_permission_mask(db):
    """当前待办节点的字段权限：hidden 字段不出现在 schema/数据里，viewonly 只读。"""
    admin, m1, _l1 = _users(db)
    code = "e1_oa_" + uuid.uuid4().hex[:8]
    definition = approval_svc.create_definition(
        db,
        DefinitionIn(
            code=code,
            name="E1 OA 字段权限",
            biz_type="oa",
            nodes=[
                NodeIn(
                    seq=1,
                    node_name="部门审批",
                    node_type="approval",
                    approver_type="USER",
                    approver_value=str(m1.id),
                    approver_name=m1.name or m1.username,
                    field_permissions={"secret": "hidden", "reason": "viewonly"},
                )
            ],
        ),
    )
    form = _form(
        db,
        [
            {"key": "reason", "label": "事由", "type": "text"},
            {"key": "secret", "label": "机密", "type": "text"},
        ],
        definition_id=definition["id"],
    )
    inst = _apply(db, form, m1, {"reason": "出差报销", "secret": "机密内容"})
    detail = oa_svc.instance_detail(db, inst, m1)
    assert "secret" not in detail["formData"]
    assert all(f.get("key") != "secret" for f in detail["schema"]["fields"])
    reason = next(f for f in detail["schema"]["fields"] if f.get("key") == "reason")
    assert reason.get("readOnly") is True
    assert detail["fieldPermissions"]["secret"] == "hidden"
    db.rollback()

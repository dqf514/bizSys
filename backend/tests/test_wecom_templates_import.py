"""E1：企业微信 39 个在用审批模板的移植落地校验。

覆盖：
- 39 表单 + 39 流程定义落地（随种子幂等导入）；
- 每个 definition 的节点 seq **连续**（1..N），无空洞；
- 条件节点必有分支或默认跳转（末位「流程结束」终止节点除外）；
- 分支 targetSeq / defaultSeq 指向**真实存在**的 seq；
- 表单元数据通过 `validate_fields`（含明细表 / 公式 / 明细列聚合校验）；
- 节点字段权限与流程通用选项落库，取值合法；
- 条件组 / 数值区间（between）求值口径正确；
- 流程包 JSON（批量导入导出用）生成且结构完整；
- 隐私红线：模板与流程里不残留真实人员数据。
"""

import json

from sqlalchemy import select

from app.modules.approval.condition import eval_condition
from app.modules.approval.models import ApprovalDefinition, ApprovalNode
from app.modules.oa.models import OaForm
from app.modules.oa.service import fields_of, validate_fields
from app.seeds import wecom_templates

# 企微标签 → 角色的唯一通道：只作审批人来源
ROLE_PREFIX = "wc_tag_"


def _forms(db) -> list[OaForm]:
    return list(
        db.scalars(select(OaForm).where(OaForm.key.like("wc_%"), OaForm.deleted == 0).order_by(OaForm.key)).all()
    )


def _definitions(db) -> list[ApprovalDefinition]:
    return list(
        db.scalars(
            select(ApprovalDefinition)
            .where(ApprovalDefinition.code.like("wc_%_approve"), ApprovalDefinition.deleted == 0)
            .order_by(ApprovalDefinition.code)
        ).all()
    )


def _nodes(db, definition_id: int) -> list[ApprovalNode]:
    return list(
        db.scalars(
            select(ApprovalNode)
            .where(ApprovalNode.definition_id == definition_id, ApprovalNode.deleted == 0)
            .order_by(ApprovalNode.seq)
        ).all()
    )


def test_all_templates_landed(db):
    """39 表单 + 39 流程定义。"""
    forms = _forms(db)
    defs = _definitions(db)
    assert len(forms) == 39
    assert len(defs) == 39
    assert {f.key for f in forms} == {f"wc_{s}" for s in wecom_templates.TEMPLATE_SLUGS}
    assert {d.code for d in defs} == {f"wc_{s}_approve" for s in wecom_templates.TEMPLATE_SLUGS}
    # 全部 published、biz_type=oa
    assert all(f.status == "published" for f in forms)
    assert all(d.biz_type == "oa" for d in defs)
    db.rollback()


def test_forms_schema_valid(db):
    """每个表单的字段定义通过发布前校验（含明细表列、公式聚合引用）。"""
    for form in _forms(db):
        flds = fields_of(form)
        assert flds, form.key
        validate_fields(flds)  # 非法会抛 BizException
    db.rollback()


def test_node_seq_is_contiguous(db):
    """节点 seq 连续 1..N（引擎按 seq 顺序推进）。"""
    for d in _definitions(db):
        nodes = _nodes(db, d.id)
        assert nodes, d.code
        assert [n.seq for n in nodes] == list(range(1, len(nodes) + 1)), d.code
    db.rollback()


def test_condition_nodes_routable(db):
    """条件节点：要么有分支、要么有默认跳转；末位「流程结束」可无分支。

    引擎的 `route_from` 语义：条件节点先按分支路由，否则走 default_seq，
    再否则取「下一个更大 seq」。两者都没有就会误落到分支目标 —— 因此
    **非末位**条件节点必须显式可路由。
    """
    for d in _definitions(db):
        nodes = _nodes(db, d.id)
        max_seq = max(n.seq for n in nodes)
        for n in nodes:
            if n.node_type != "condition":
                continue
            branches = json.loads(n.branches or "[]")
            if branches or n.default_seq is not None:
                continue
            # 无分支无默认 → 只能是流程终止节点（必须是最后一个）
            assert n.seq == max_seq, f"{d.code} 条件节点「{n.node_name}」既无分支也无默认跳转"
    db.rollback()


def test_branch_targets_exist(db):
    """分支 targetSeq 与 defaultSeq 都指向真实存在的节点。"""
    for d in _definitions(db):
        seqs = {n.seq for n in _nodes(db, d.id)}
        for n in _nodes(db, d.id):
            for b in json.loads(n.branches or "[]"):
                tgt = b.get("targetSeq")
                assert tgt is not None, f"{d.code} 节点「{n.node_name}」分支缺 targetSeq"
                assert tgt in seqs, f"{d.code} 分支目标 seq {tgt} 不存在"
            if n.default_seq is not None:
                assert n.default_seq in seqs, f"{d.code} 默认跳转 seq {n.default_seq} 不存在"
    db.rollback()


def test_field_permissions_landed(db):
    """节点字段权限落库，取值 ⊆ editable/viewonly/hidden。"""
    total = 0
    for d in _definitions(db):
        for n in _nodes(db, d.id):
            perms = json.loads(n.field_permissions or "{}")
            assert isinstance(perms, dict)
            for key, mode in perms.items():
                assert mode in ("editable", "viewonly", "hidden"), (d.code, key, mode)
            total += len(perms)
    assert total > 0, "节点字段权限未落库"
    db.rollback()


def test_general_options_landed(db):
    """流程通用选项落库（企微 general_option）。"""
    seen: set[str] = set()
    for d in _definitions(db):
        opts = json.loads(d.options or "{}")
        assert isinstance(opts, dict)
        seen.update(opts.keys())
    assert seen & {
        "commentRequired",
        "commentSignRequired",
        "allowAddSign",
        "allowWithdrawAfterApproved",
        "allowModifyFlow",
        "allowModifyCc",
        "executorCommentRequired",
        "executorCanModify",
        "allowProxySubmit",
        "detailTablePermission",
    }, "流程通用选项未落库"
    db.rollback()


def test_tag_roles_used_as_approvers(db):
    """企微标签 → 角色（wc_tag_*）作为审批人来源被引用。"""
    used = set()
    for d in _definitions(db):
        for n in _nodes(db, d.id):
            if n.approver_type == "ROLE" and (n.approver_value or "").startswith(ROLE_PREFIX):
                used.add(n.approver_value)
    assert used, "没有任何节点引用企微标签角色"
    db.rollback()


def test_variables_schema_declares_exposed_fields(db):
    """暴露为流程变量的字段必须出现在 variables_schema 中（引擎按 schema 校验）。"""
    for d in _definitions(db):
        schema = json.loads(d.variables_schema or "{}")
        assert isinstance(schema, dict)
        for n in _nodes(db, d.id):
            if n.approver_type in ("FORM_USER", "FORM_ROLE", "FORM_DEPT_LEADER"):
                assert (n.approver_value or "") in schema, f"{d.code} 变量「{n.approver_value}」未声明"
    db.rollback()


def test_between_and_condition_group_eval():
    """数值区间（between）与条件组（and/or）求值口径。"""
    assert eval_condition({"field": "amount", "op": "between", "value": [1000, 10000]}, {"amount": 5000})
    assert not eval_condition({"field": "amount", "op": "between", "value": [1000, 10000]}, {"amount": 20000})
    assert eval_condition(
        {"logic": "and", "rules": [
            {"field": "amount", "op": "gte", "value": 100},
            {"field": "dept", "op": "eq", "value": "财务部"},
        ]},
        {"amount": 200, "dept": "财务部"},
    )
    assert not eval_condition(
        {"logic": "and", "rules": [
            {"field": "amount", "op": "gte", "value": 100},
            {"field": "dept", "op": "eq", "value": "财务部"},
        ]},
        {"amount": 200, "dept": "技术部"},
    )
    assert eval_condition(
        {"logic": "or", "rules": [
            {"field": "a", "op": "empty"},
            {"field": "b", "op": "not_empty"},
        ]},
        {"a": "", "b": 1},
    )


def test_imported_condition_evaluates(db):
    """取一条真实导入的条件分支表达式求值（验证字段名与公式变量可用）。"""
    found = 0
    for d in _definitions(db):
        for n in _nodes(db, d.id):
            for b in json.loads(n.branches or "[]"):
                expr = b.get("expr")
                if not isinstance(expr, dict) or not expr.get("field"):
                    continue
                field = expr["field"]
                if field.startswith("org."):
                    continue
                # 变量名必须在 variables_schema 里
                schema = json.loads(d.variables_schema or "{}")
                assert field in schema, f"{d.code} 条件字段 {field} 未声明为流程变量"
                found += 1
    assert found > 0, "没有任何可求值的导入条件"
    db.rollback()


def test_scope_json_shape(db):
    """模板可见范围 scope_json 结构合法（depts/roles/users 三个数组）。"""
    for form in _forms(db):
        if not form.scope_json:
            continue
        scope = json.loads(form.scope_json)
        assert set(scope) <= {"depts", "roles", "users"}
        for v in scope.values():
            assert isinstance(v, list)
            assert all(isinstance(x, str) for x in v)
    db.rollback()


def test_flow_packages_generated():
    """流程包 JSON（bizsys.flowpackage/v1）已生成且 39 条结构完整。"""
    path = wecom_templates.DATA_DIR / "wecom_flow_packages.json"
    assert path.exists(), "流程包 JSON 未生成"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "bizsys.flowpackage/v1"
    packages = payload["packages"]
    assert len(packages) == 39
    for pkg in packages:
        assert pkg["code"].startswith("wc_") and pkg["code"].endswith("_approve")
        assert pkg["form"]["key"].startswith("wc_")
        assert pkg["flow"]["nodes"], pkg["code"]
        assert pkg["flow"]["options"] is not None
    # 幂等：节点 seq 连续
    for pkg in packages:
        seqs = [n["seq"] for n in pkg["flow"]["nodes"]]
        assert seqs == list(range(1, len(seqs) + 1)), pkg["code"]


def test_no_real_personnel_in_packages():
    """隐私红线：流程包内不出现手机号 / 邮箱 / 证件号等真实个人信息。"""
    path = wecom_templates.DATA_DIR / "wecom_flow_packages.json"
    text = path.read_text(encoding="utf-8")
    import re

    assert not re.search(r"1[3-9]\d{9}", text), "流程包内出现疑似手机号"
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), "流程包内出现疑似邮箱"
    assert not re.search(r"\d{17}[\dXx]", text), "流程包内出现疑似证件号"


def test_import_is_idempotent(db):
    """重复导入不产生重复表单 / 流程定义。"""
    before_forms = len(_forms(db))
    before_defs = len(_definitions(db))
    summary = wecom_templates.import_templates(db, write_packages=False)
    assert summary["errors"] == []
    assert summary["forms"] == 39
    assert summary["definitions"] == 39
    assert len(_forms(db)) == before_forms
    assert len(_definitions(db)) == before_defs
    db.rollback()

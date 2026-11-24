"""审批流程包（FlowPackage）—— **流程与表单的 JSON 化载体**（E1）。

用户诉求「所有审批流程可以 json 化，为后期批量导入导出创造便利」的落地：
一套 schema + 一组纯函数，把「OA 表单 + 审批定义」打包成可导出的 JSON，
再从 JSON 幂等地导回数据库（upsert）。

schema 版本：``bizsys.flowpackage/v1``

```jsonc
{
  "schema": "bizsys.flowpackage/v1",
  "exportedAt": "2026-11-24T10:00:00",
  "packages": [
    {
      "code": "wc_purchase_apply_approve",   // 流程定义 code
      "name": "采购申请",
      "bizType": "oa",
      "enabled": true,
      "remark": "企业微信模板移植",
      "source": "wecom",                     // 来源标记（wecom / bizsys）
      "form": {                              // 绑定的 OA 表单（可空）
        "key": "wc_purchase_apply", "name": "采购申请", "category": "wc_biz",
        "icon": "", "sort": 3, "description": "...",
        "scope": {"depts": [], "roles": [], "users": []},
        "fields": [ { "key": "...", "label": "...", "type": "...", ... } ]
      },
      "flow": {
        "variablesSchema": {},               // 流程变量声明
        "options": {},                       // 流程通用选项
        "nodes": [ { "seq": 1, "nodeName": "...", "nodeType": "approval", ... } ],
        "edges": [ { "source": 1, "target": 2, "expr": null, "priority": 1 } ]
      }
    }
  ]
}
```

**幂等**：导入按 ``code`` upsert 流程定义（无进行中实例则原地更新，有则另存新版本），
按 ``form.key`` upsert 表单；重复导入不产生重复行。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.approval.graph import build_process_graph, dumps_graph, parse_branches, parse_json
from app.modules.approval.models import ApprovalDefinition, ApprovalNode
from app.modules.approval.schemas import DefinitionIn
from app.modules.oa.models import OaForm

SCHEMA = "bizsys.flowpackage/v1"

#: 流程包允许的节点类型（与引擎一致）
NODE_TYPES = ("approval", "condition", "cc", "executor")


# --------------------------------------------------------------------------- 导出


def _node_payload(node: ApprovalNode) -> dict:
    return {
        "seq": node.seq,
        "nodeName": node.node_name or "",
        "nodeType": node.node_type or "approval",
        "signMode": node.sign_mode or "or",
        "approverType": node.approver_type or "USER",
        "approverValue": node.approver_value or "",
        "approverName": node.approver_name or "",
        "chainLevels": node.chain_levels,
        "branches": parse_branches(node),
        "defaultSeq": node.default_seq,
        "fieldPermissions": parse_json(node.field_permissions, {}) or {},
    }


def _form_payload(form: OaForm | None) -> dict | None:
    if form is None:
        return None
    schema = parse_json(form.schema_json, {}) or {}
    return {
        "key": form.key,
        "name": form.name,
        "category": form.category or "",
        "icon": form.icon or "",
        "sort": form.sort or 0,
        "description": form.description or "",
        "scope": parse_json(form.scope_json, {}) or {},
        "fields": schema.get("fields") or [],
    }


def form_payload(form: OaForm | None) -> dict | None:
    """OA 表单 → 流程包中的 form 段（公开别名，供 OA 路由复用）。"""
    return _form_payload(form)


def build_package(db: Session, definition: ApprovalDefinition, form: OaForm | None = None) -> dict:
    """单个流程定义 → 流程包字典。"""
    nodes = [n for n in definition.nodes if n.deleted == 0]
    ordered = sorted(nodes, key=lambda n: n.seq)
    edges: list[dict] = []
    for n in ordered:
        if n.node_type != "condition":
            continue
        for b in parse_branches(n):
            edges.append(
                {
                    "source": n.seq,
                    "target": b.get("targetSeq") or b.get("target_seq"),
                    "expr": b.get("expr"),
                    "priority": 1,
                }
            )
        if n.default_seq:
            edges.append({"source": n.seq, "target": n.default_seq, "expr": None, "priority": 99})
    return {
        "code": definition.code,
        "name": definition.name,
        "bizType": definition.biz_type,
        "enabled": bool(definition.enabled),
        "remark": definition.remark or "",
        "flowVersion": definition.flow_version,
        "source": "bizsys",
        "form": _form_payload(form),
        "flow": {
            "variablesSchema": parse_json(definition.variables_schema, {}) or {},
            "options": parse_json(definition.options, {}) or {},
            "nodes": [_node_payload(n) for n in ordered],
            "edges": edges,
        },
    }


def _form_of(db: Session, definition: ApprovalDefinition) -> OaForm | None:
    """流程定义绑定的 OA 表单（绑定关系记在 `oa_form.flow_definition_id` 上）。"""
    return db.scalar(
        select(OaForm).where(OaForm.flow_definition_id == definition.id, OaForm.deleted == 0).limit(1)
    )


def export_package(db: Session, code: str) -> dict:
    """导出单个流程包（按流程定义 code）。"""
    d = db.scalar(
        select(ApprovalDefinition).where(ApprovalDefinition.code == code, ApprovalDefinition.deleted == 0).limit(1)
    )
    if not d:
        raise BizException(R.GENERIC_NOT_FOUND, f"流程定义不存在：{code}")
    return {
        "schema": SCHEMA,
        "exportedAt": datetime.now().isoformat(timespec="seconds"),
        "packages": [build_package(db, d, _form_of(db, d))],
    }


def export_all(db: Session, biz_type: str = "") -> dict:
    """导出全部流程包（可按 bizType 过滤）。"""
    stmt = select(ApprovalDefinition).where(ApprovalDefinition.deleted == 0)
    if biz_type:
        stmt = stmt.where(ApprovalDefinition.biz_type == biz_type)
    rows = db.scalars(stmt.order_by(ApprovalDefinition.biz_type, ApprovalDefinition.code)).all()
    packages = []
    for d in rows:
        # 同 code 多版本只导出最新启用版本
        packages.append(build_package(db, d, _form_of(db, d)))
    return {
        "schema": SCHEMA,
        "exportedAt": datetime.now().isoformat(timespec="seconds"),
        "packages": packages,
    }


# --------------------------------------------------------------------------- 导入


def _validate_payload(payload: Any) -> list[dict]:
    if not isinstance(payload, dict):
        raise BizException(R.GENERIC_PARAM, "流程包必须是 JSON 对象")
    schema = payload.get("schema")
    if schema != SCHEMA:
        raise BizException(R.GENERIC_PARAM, f"流程包 schema 不受支持：{schema}（期望 {SCHEMA}）")
    packages = payload.get("packages")
    if not isinstance(packages, list) or not packages:
        raise BizException(R.GENERIC_PARAM, "流程包缺少 packages 列表")
    for pkg in packages:
        if not isinstance(pkg, dict) or not pkg.get("code"):
            raise BizException(R.GENERIC_PARAM, "流程包条目缺少 code")
    return packages


def _definition_body(pkg: dict) -> DefinitionIn:
    """流程包 → DefinitionIn（走引擎的入参校验，非法包直接报错）。"""
    flow = pkg.get("flow") or {}
    nodes = []
    for n in flow.get("nodes") or []:
        nodes.append(
            {
                "seq": int(n.get("seq") or 1),
                "nodeName": n.get("nodeName") or "",
                "nodeType": n.get("nodeType") or "approval",
                "signMode": n.get("signMode") or "or",
                "approverType": n.get("approverType") or "USER",
                "approverValue": str(n.get("approverValue") or ""),
                "approverName": n.get("approverName") or "",
                "chainLevels": n.get("chainLevels"),
                "branches": n.get("branches") or None,
                "defaultSeq": n.get("defaultSeq"),
                "fieldPermissions": n.get("fieldPermissions") or None,
            }
        )
    return DefinitionIn(
        code=pkg["code"],
        name=pkg.get("name") or pkg["code"],
        biz_type=pkg.get("bizType") or "oa",
        enabled=1 if pkg.get("enabled", True) else 0,
        remark=(pkg.get("remark") or "")[:255],
        variables_schema=flow.get("variablesSchema") or None,
        options=flow.get("options") or None,
        nodes=nodes,
    )


def import_packages(db: Session, payload: Any, dry_run: bool = False) -> dict:
    """导入流程包（upsert 表单 + 流程定义）。

    ``dry_run=True`` 只做校验与统计，不落库。
    """
    from app.modules.approval import service as approval_svc  # noqa: PLC0415 避免循环导入

    packages = _validate_payload(payload)
    created = updated = 0
    form_created = form_updated = 0
    errors: list[str] = []
    for pkg in packages:
        try:
            body = _definition_body(pkg)
            approval_svc._validate_nodes(body)  # noqa: SLF001 - 复用引擎校验
        except BizException as exc:
            errors.append(f"{pkg.get('code')}：{exc.message}")
            continue
        if dry_run:
            continue
        d = db.scalar(
            select(ApprovalDefinition)
            .where(ApprovalDefinition.code == body.code, ApprovalDefinition.deleted == 0)
            .limit(1)
        )
        if d is None:
            approval_svc.create_definition(db, body)
            created += 1
        else:
            approval_svc.update_definition(db, d.id, body)
            updated += 1
        d = db.scalar(
            select(ApprovalDefinition)
            .where(ApprovalDefinition.code == body.code, ApprovalDefinition.deleted == 0)
            .limit(1)
        )
        if d and pkg.get("form"):
            c, u = _upsert_form(db, pkg["form"], d.id)
            form_created += c
            form_updated += u
    db.flush()
    return {
        "schema": SCHEMA,
        "total": len(packages),
        "created": created,
        "updated": updated,
        "formCreated": form_created,
        "formUpdated": form_updated,
        "errors": errors,
        "dryRun": dry_run,
    }


def _upsert_form(db: Session, form: dict, flow_definition_id: int) -> tuple[int, int]:
    """表单 upsert：返回 (新建数, 更新数)。"""
    key = (form.get("key") or "").strip()
    if not key:
        return (0, 0)
    row = db.scalar(select(OaForm).where(OaForm.key == key, OaForm.form_version == 1, OaForm.deleted == 0).limit(1))
    scope = form.get("scope") or {}
    scope_json = None
    if isinstance(scope, dict) and any(scope.get(k) for k in ("depts", "roles", "users")):
        scope_json = json.dumps(
            {k: [str(x) for x in (scope.get(k) or [])] for k in ("depts", "roles", "users")},
            ensure_ascii=False,
        )
    payload = {
        "name": form.get("name") or key,
        "category": form.get("category") or "",
        "icon": form.get("icon") or "",
        "sort": form.get("sort") or 0,
        "description": form.get("description") or "",
        "schema_json": json.dumps({"fields": form.get("fields") or []}, ensure_ascii=False),
        "scope_json": scope_json,
        "flow_definition_id": flow_definition_id,
    }
    if row is None:
        row = OaForm(key=key, name=payload["name"], form_version=1, status="published")
        db.add(row)
        db.flush()
        for k, v in payload.items():
            setattr(row, k, v)
        row.published_at = row.published_at or datetime.now()
        return (1, 0)
    for k, v in payload.items():
        setattr(row, k, v)
    return (0, 1)


def packages_of_definition(db: Session, definition_id: int) -> dict | None:
    """按流程定义 id 取流程包（供 OA 表单导出端点复用）。"""
    d = db.get(ApprovalDefinition, definition_id)
    if not d or d.deleted:
        return None
    return build_package(db, d, _form_of(db, d))


def graph_of(nodes: list[ApprovalNode]) -> str:
    """由节点行生成 LogicFlow 图 JSON（未提交自定义图时用）。"""
    return dumps_graph(build_process_graph(nodes))

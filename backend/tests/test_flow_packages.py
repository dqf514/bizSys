"""E1：审批流程包（FlowPackage）JSON 化导入导出。

覆盖：
- 导出全部 / 导出单个（JSON 文件，schema `bizsys.flowpackage/v1`）；
- 导入（幂等 upsert 表单 + 流程定义），非法包被拒绝；
- OA 表单流程包导出；
- 权限点 `admin:flow:export` / `admin:flow:import` 生效。
"""

import json

from sqlalchemy import select

from app.modules.approval.models import ApprovalDefinition
from app.modules.oa.models import OaForm

SCHEMA = "bizsys.flowpackage/v1"


def _wc_payload() -> dict:
    from app.seeds import wecom_templates

    path = wecom_templates.DATA_DIR / "wecom_flow_packages.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_export_all_packages(client, admin_headers):
    """导出全部流程包：JSON 文件、schema 正确、含企微模板。"""
    r = client.get("/api/v1/approval/packages/export-all", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers.get("content-disposition", "")
    payload = r.json()
    assert payload["schema"] == SCHEMA
    codes = {p["code"] for p in payload["packages"]}
    assert any(c.startswith("wc_") for c in codes)
    for pkg in payload["packages"]:
        assert pkg["code"]
        assert "form" in pkg
        assert "flow" in pkg
        assert "nodes" in pkg["flow"]


def test_export_one_package(client, admin_headers):
    """导出单个流程包（按 code）。"""
    r = client.get("/api/v1/approval/definitions/wc_payment_apply_approve/package", headers=admin_headers)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["schema"] == SCHEMA
    assert len(payload["packages"]) == 1
    pkg = payload["packages"][0]
    assert pkg["code"] == "wc_payment_apply_approve"
    assert pkg["form"]["key"] == "wc_payment_apply"
    assert pkg["flow"]["nodes"]
    seqs = [n["seq"] for n in pkg["flow"]["nodes"]]
    assert seqs == list(range(1, len(seqs) + 1))


def test_export_unknown_package_404(client, admin_headers):
    """导出不存在的流程包 → 业务错误码。"""
    r = client.get("/api/v1/approval/definitions/not_exist_code/package", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] != 0


def test_import_packages_is_idempotent(client, admin_headers, db):
    """导入流程包：幂等，重复导入不产生重复流程定义。"""
    payload = _wc_payload()
    before = len(db.scalars(select(ApprovalDefinition).where(ApprovalDefinition.deleted == 0)).all())

    r = client.post(
        "/api/v1/approval/packages/import",
        headers=admin_headers,
        json=payload,
        params={"dry_run": "false"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0, body
    result = body["data"]
    assert result["total"] == 39
    assert result["errors"] == []
    assert result["created"] == 0, "流程定义已存在，不应重复创建"
    assert result["updated"] == 39

    after = len(db.scalars(select(ApprovalDefinition).where(ApprovalDefinition.deleted == 0)).all())
    assert after == before


def test_import_dry_run_does_not_write(client, admin_headers, db):
    """试导入只校验不落库。"""
    payload = _wc_payload()
    before = len(db.scalars(select(ApprovalDefinition).where(ApprovalDefinition.deleted == 0)).all())
    r = client.post(
        "/api/v1/approval/packages/import",
        headers=admin_headers,
        json=payload,
        params={"dry_run": "true"},
    )
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["dryRun"] is True
    assert result["created"] == 0 and result["updated"] == 0
    after = len(db.scalars(select(ApprovalDefinition).where(ApprovalDefinition.deleted == 0)).all())
    assert after == before


def test_import_rejects_bad_schema(client, admin_headers):
    """schema 不匹配的包被拒绝。"""
    r = client.post(
        "/api/v1/approval/packages/import",
        headers=admin_headers,
        json={"schema": "something/v9", "packages": [{"code": "x"}]},
    )
    assert r.status_code == 200
    assert r.json()["code"] != 0


def test_import_rejects_broken_package(client, admin_headers):
    """包内流程定义非法（节点 seq 断裂/条件不可路由）→ 记入 errors 而不是整体崩。"""
    bad = {
        "schema": SCHEMA,
        "packages": [
            {
                "code": "wc_broken_test_approve",
                "name": "坏包",
                "bizType": "oa",
                "flow": {
                    "nodes": [
                        {"seq": 1, "nodeName": "条件", "nodeType": "condition", "branches": None},
                    ]
                },
            }
        ],
    }
    r = client.post("/api/v1/approval/packages/import", headers=admin_headers, json=bad)
    assert r.status_code == 200
    result = r.json()["data"]
    assert result["errors"], "非法包应记入 errors"
    assert result["created"] == 0


def test_oa_form_package_export(client, admin_headers, db):
    """OA 表单流程包导出（未绑定流程时只导出表单部分）。"""
    form = db.scalar(select(OaForm).where(OaForm.key == "wc_payment_apply", OaForm.deleted == 0))
    assert form is not None
    r = client.get(f"/api/v1/oa/admin/forms/{form.id}/package", headers=admin_headers)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["schema"] == SCHEMA
    pkg = payload["packages"][0]
    assert pkg["form"]["key"] == "wc_payment_apply"
    assert pkg["form"]["fields"]


def test_export_requires_permission(client, manager_headers):
    """无 `admin:flow:export` 权限 → 拒绝。"""
    r = client.get("/api/v1/approval/packages/export-all", headers=manager_headers)
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        assert r.json()["code"] != 0

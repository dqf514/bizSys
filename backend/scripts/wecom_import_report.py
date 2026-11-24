"""企业微信审批移植导入报告。

对已落库的 39 个企微审批模板做一次**体检**：模板/字段/节点/分支统计、流程结构
自检（seq 连续性、条件节点默认跳转、分支目标可达、字段权限完整性），
并输出**待人工复核**项（op 语义推定、区间按标题重建、非同名标签映射等）。

用法（在 `backend/` 目录执行）::

    uv run python scripts/wecom_import_report.py            # 只体检当前库
    uv run python scripts/wecom_import_report.py --import    # 先幂等导入再体检
    uv run python scripts/wecom_import_report.py --import --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.exceptions import BizException  # noqa: E402
from app.modules.approval.models import ApprovalDefinition, ApprovalNode  # noqa: E402
from app.modules.oa.models import OaForm  # noqa: E402
from app.modules.oa.service import fields_of, validate_fields  # noqa: E402
from app.seeds import wecom_templates  # noqa: E402


def _collect(db) -> list[dict]:
    """逐模板体检：表单字段 + 流程节点 + 结构自检。"""
    rows: list[dict] = []
    for slug in wecom_templates.TEMPLATE_SLUGS:
        form = db.scalar(
            select(OaForm)
            .where(OaForm.key == f"wc_{slug}", OaForm.form_version == 1, OaForm.deleted == 0)
            .limit(1)
        )
        code = f"wc_{slug}_approve"
        d = db.scalar(
            select(ApprovalDefinition)
            .where(ApprovalDefinition.code == code, ApprovalDefinition.deleted == 0)
            .order_by(ApprovalDefinition.flow_version.desc(), ApprovalDefinition.id.desc())
            .limit(1)
        )
        row: dict = {
            "slug": slug,
            "code": code,
            "formKey": f"wc_{slug}",
            "name": (form.name if form else "") or "",
            "category": (form.category if form else "") or "",
            "flowName": (d.name if d else "") or "",
            "found": bool(form and d),
            "fields": 0,
            "tables": 0,
            "formulas": 0,
            "nodes": 0,
            "conditions": 0,
            "branches": 0,
            "exposed": 0,
            "fieldPerms": 0,
            "options": 0,
            "scope": 0,
            "problems": [],
        }
        if not form:
            row["problems"].append("表单缺失")
        if not d:
            row["problems"].append("流程定义缺失")
        if form:
            flds = fields_of(form)
            row["fields"] = len(flds)
            row["tables"] = sum(1 for f in flds if f.type == "table")
            row["formulas"] = sum(1 for f in flds if f.type == "formula")
            row["exposed"] = sum(1 for f in flds if f.expose_variable)
            scope = json.loads(form.scope_json or "{}")
            if not isinstance(scope, dict):
                scope = {}
            row["scope"] = sum(len(v) for v in scope.values() if isinstance(v, list))
            try:
                validate_fields(flds)
            except BizException as exc:
                for e in str(exc.message).split("；"):
                    row["problems"].append(f"表单元数据校验：{e}")
        if d:
            nodes = db.scalars(
                select(ApprovalNode)
                .where(ApprovalNode.definition_id == d.id, ApprovalNode.deleted == 0)
                .order_by(ApprovalNode.seq)
            ).all()
            row["nodes"] = len(nodes)
            seqs = [n.seq for n in nodes]
            if seqs and seqs != list(range(1, len(seqs) + 1)):
                row["problems"].append(f"节点 seq 不连续：{seqs[:12]}")
            known = set(seqs)
            for n in nodes:
                row["fieldPerms"] += len(json.loads(n.field_permissions or "{}"))
                branches = json.loads(n.branches or "[]")
                row["branches"] += len(branches)
                if n.node_type == "condition":
                    row["conditions"] += 1
                    if not branches and n.default_seq is None and seqs and n.seq != max(seqs):
                        row["problems"].append(f"条件节点「{n.node_name}」既无分支也无默认跳转")
                    for b in branches:
                        tgt = b.get("targetSeq")
                        if tgt is not None and tgt not in known:
                            row["problems"].append(f"分支目标 seq {tgt} 不存在")
                if n.default_seq is not None and n.default_seq not in known:
                    row["problems"].append(f"默认跳转 seq {n.default_seq} 不存在")
            opts = json.loads(d.options or "{}")
            row["options"] = len(opts)
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="企业微信审批移植导入报告")
    ap.add_argument("--import", dest="do_import", action="store_true", help="先幂等导入再体检")
    ap.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        import_report: dict = {}
        if args.do_import:
            import_report = wecom_templates.import_templates(db, write_packages=True)
            db.commit()
        rows = _collect(db)
    finally:
        db.close()

    problems = [r for r in rows if r["problems"]]
    review = import_report.get("review", [])
    errors = import_report.get("errors", [])

    if args.as_json:
        print(
            json.dumps(
                {
                    "import": import_report,
                    "templates": rows,
                    "problemTemplates": len(problems),
                    "reviewItems": len(review),
                    "errors": errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if (errors or problems) else 0

    print("=" * 72)
    print("企业微信审批移植 · 导入报告")
    print("=" * 72)
    if args.do_import:
        print(
            "导入：模板 {templates} / 表单 {forms} / 流程定义 {definitions} / 节点 {nodes} / "
            "分支 {branches} / 条件 {conditions} / 流程包 {packages}".format(
                **{
                    k: import_report.get(k, 0)
                    for k in (
                        "templates",
                        "forms",
                        "definitions",
                        "nodes",
                        "branches",
                        "conditions",
                        "packages",
                    )
                }
            )
        )
        if errors:
            print(f"导入错误 {len(errors)} 条：")
            for e in errors:
                print(f"  ✗ {e}")
        print()

    totals = Counter()
    for r in rows:
        for k in ("fields", "tables", "formulas", "nodes", "conditions", "branches", "exposed", "fieldPerms"):
            totals[k] += r[k]
    print(
        "落库合计：模板 {n} · 字段 {fields}（明细表 {tables} / 公式 {formulas}）· "
        "流程节点 {nodes} · 条件节点 {conditions} · 分支 {branches} · "
        "暴露变量字段 {exposed} · 节点字段权限 {fieldPerms}".format(n=len(rows), **totals)
    )
    print()

    print("-" * 72)
    print("逐模板明细")
    print("-" * 72)
    print(f"{'模板':<26}{'分类':<8}{'字段':>5}{'节点':>5}{'条件':>5}{'分支':>5}  状态")
    for r in rows:
        status = "OK" if not r["problems"] else "；".join(r["problems"])
        print(
            f"{r['name'][:24]:<26}{r['category'][:6]:<8}"
            f"{r['fields']:>5}{r['nodes']:>5}{r['conditions']:>5}{r['branches']:>5}  {status}"
        )

    print()
    print("-" * 72)
    print(f"待人工复核（{len(review)} 项）")
    print("-" * 72)
    if review:
        for item in review:
            print(f"  · {item}")
    else:
        print("  （无）")

    print()
    if problems or errors:
        print(f"结论：{len(problems)} 个模板存在结构问题，{len(errors)} 条导入错误 —— 需修复后重跑。")
        return 1
    print("结论：39 个模板结构自检全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

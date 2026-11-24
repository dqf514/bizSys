"""把《企业微信审批与组织数据技术文档.html》解析成结构化 JSON。

产出三份数据（供种子导入与对照用）：
- wecom_org.json    组织架构（部门树 + 负责人）
- wecom_tags.json   标签体系（角色映射依据）
- wecom_people.json 人员（**仅岗位/姓名/部门**，手机与邮箱不在本文件保留）
- wecom_templates.json 审批模板（表单字段 + 流程节点 + 连线条件 + 通用选项）

用法（仓库根目录执行）：
    python backend/scripts/parse_wecom_doc.py \
        --doc "企业微信审批与组织数据技术文档.html" \
        --out backend/app/seeds/data
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

DOC_NAME = "企业微信审批与组织数据技术文档.html"


def _strip_tags(fragment: str) -> str:
    """去标签并还原实体；<br> 与块级标签视作换行。"""
    frag = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    frag = re.sub(r"<(p|div|tr|li|h[1-6])\b[^>]*>", "\n", frag, flags=re.I)
    frag = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", frag, flags=re.I)
    frag = re.sub(r"<[^>]+>", "", frag)
    frag = html.unescape(frag)
    lines = [ln.strip() for ln in frag.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _tables(section: str) -> list[list[list[str]]]:
    """抽出 section 内所有表格，返回 [[行][列][文本], ...]。"""
    result: list[list[list[str]]] = []
    for tm in re.finditer(r"<table\b[^>]*>([\s\S]*?)</table>", section, flags=re.I):
        body = tm.group(1)
        rows: list[list[str]] = []
        for rm in re.finditer(r"<tr\b[^>]*>([\s\S]*?)</tr>", body, flags=re.I):
            cells = [_strip_tags(c.group(1)) for c in re.finditer(r"<t[hd]\b[^>]*>([\s\S]*?)</t[hd]>", rm.group(1), re.I)]
            rows.append(cells)
        if rows:
            result.append(rows)
    return result


def _kv_table(rows: list[list[str]]) -> dict[str, str]:
    """把「th/td 成对」的表格转成字典（重复键保留最后一个）。"""
    out: dict[str, str] = {}
    for row in rows:
        for i in range(0, len(row) - 1, 2):
            key = row[i].strip()
            if key:
                out[key] = row[i + 1].strip()
    return out


def parse_org(doc: str) -> dict:
    """③ 组织架构（部门树）+ ⑤ 人员信息（人员表在独立的 people section）。"""
    depts: list[dict] = []
    people: list[dict] = []
    for sid, handler in (("org", "dept"), ("people", "person")):
        sec = re.search(rf'<section id="{sid}"[\s\S]*?</section>', doc)
        if not sec:
            continue
        for rows in _tables(sec.group(0)):
            head = rows[0]
            if handler == "dept" and head and head[0].startswith("部门名称"):
                for row in rows[1:]:
                    if len(row) < 7:
                        continue
                    name_path = [ln for ln in row[0].split("\n") if ln]
                    depts.append(
                        {
                            "name": name_path[0] if name_path else "",
                            "path": " / ".join(name_path),
                            "wecom_id": row[1].strip(),
                            "parent_name": (row[2].split("\n")[0] if row[2] else ""),
                            "level": _int(row[3]),
                            "direct_count": _int(row[4]),
                            "recursive_count": _int(row[5]),
                            "leader": ("" if row[6].strip() == "未设置" else row[6].strip()),
                        }
                    )
            elif handler == "person" and head and head[0] == "#":
                for row in rows[1:]:
                    if len(row) < 11:
                        continue
                    dept_paths = [ln for ln in row[4].split("\n") if ln]
                    people.append(
                        {
                            "seq": _int(row[0]),
                            "name": row[1].strip(),
                            "gender": row[2].strip(),
                            "title": row[3].strip(),
                            "dept_paths": dept_paths,
                            "account": row[7].strip(),
                            "wecom_vid": row[8].strip(),
                            "tags": [t for t in row[9].split("、") if t and t != "—"],
                            "status": row[10].strip(),
                        }
                    )
    return {"depts": depts, "people": people}


def parse_tags(doc: str) -> list[dict]:
    """④ 标签体系。"""
    sec = re.search(r'<section id="tags"[\s\S]*?</section>', doc)
    if not sec:
        return []
    tags: list[dict] = []
    for rows in _tables(sec.group(0)):
        if not rows[0] or rows[0][0] != "标签名称":
            continue
        for row in rows[1:]:
            if len(row) < 4:
                continue
            tags.append(
                {
                    "name": row[0].strip(),
                    "wecom_tagid": row[1].strip(),
                    "member_count": _int(row[2]),
                }
            )
    return tags


def anonymize(org: dict, tags: list[dict]) -> dict:
    """把真实人员数据替换成**全模拟**人员（防隐私泄露）。

    保留：部门树、职务（岗位信息）、标签→成员归属关系、模板的表单/流程/条件全量结构。
    替换：姓名 → 「模拟员工NN」，登录账号 → mockNNN，vid → 平台无关的占位；
    手机号 / 企业邮箱 **完全不落盘**（原文档里存在，解析阶段直接丢弃）。
    部门负责人按「姓名 → 模拟姓名」映射回写。
    """
    people = org["people"]
    name_map: dict[str, str] = {}
    acct_map: dict[str, str] = {}
    out_people: list[dict] = []
    for p in sorted(people, key=lambda x: x["seq"]):
        sid = p["seq"]
        mock_name = f"模拟员工{sid:02d}"
        mock_acct = f"mock{sid:03d}"
        name_map[p["name"]] = mock_name
        acct_map[p["name"]] = mock_acct
        out_people.append(
            {
                "seq": sid,
                "name": mock_name,
                "gender": p["gender"],
                "title": p["title"],
                "dept_paths": p["dept_paths"],
                "account": mock_acct,
                "tags": p["tags"],
                "status": p["status"],
            }
        )

    out_depts = []
    for d in org["depts"]:
        item = dict(d)
        item["leader"] = name_map.get(d["leader"], "")
        out_depts.append(item)

    tag_members: dict[str, list[str]] = {}
    for p in out_people:
        for t in p["tags"]:
            tag_members.setdefault(t, []).append(p["name"])
    out_tags = []
    for t in tags:
        members = tag_members.get(t["name"], [])
        out_tags.append(
            {
                "name": t["name"],
                "wecom_tagid": t["wecom_tagid"],
                "member_count": len(members) or t["member_count"],
                "members": members,
            }
        )

    return {"depts": out_depts, "people": out_people, "tags": out_tags, "name_map": name_map, "acct_map": acct_map}


#: 模板里引用人员的常见写法：{"vid":"<姓名>"} / {"tagid":"<标签id>"}
_VID_RE = re.compile(r'\{"vid":"([^"]+)"\}')


def scrub_templates(templates: list[dict], name_map: dict[str, str], acct_map: dict[str, str]) -> list[dict]:
    """把**模板里引用到的真实姓名**替换为模拟标识（防隐私泄露）。

    模板的连线条件与节点审批人规则里会直接出现成员姓名（如「抄送：张辉」、
    「部门：[{"vid":"杨忆南"}]」）。这里统一脱敏：vid 槽位换成模拟账号（mockNNN，
    导入器据此解析 sys_user），其余正文里的姓名换成「模拟员工NN」。
    """
    # 长名优先，避免「王芳」被「王芳琳」之类的短名先替换掉
    ordered = sorted(name_map, key=len, reverse=True)

    def _scrub_text(text: str) -> str:
        def _vid(m: re.Match) -> str:
            raw = m.group(1)
            acct = acct_map.get(raw)
            return '{"vid":"%s"}' % acct if acct else m.group(0)

        text = _VID_RE.sub(_vid, text)
        for real in ordered:
            if real in text:
                text = text.replace(real, name_map[real])
        return text

    def _walk(node):
        if isinstance(node, str):
            return _scrub_text(node)
        if isinstance(node, list):
            return [_walk(x) for x in node]
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        return node

    return [_walk(t) for t in templates]


def parse_template(section: str, section_id: str = "") -> dict:
    """解析单个审批模板 section。"""
    name = _first(re.search(r"<h2[^>]*>([\s\S]*?)</h2>", section))
    crumb = _first(re.search(r'<div class="crumb">([\s\S]*?)</div>', section))
    chips = [_strip_tags(c) for c in re.findall(r'<span class="chip">([\s\S]*?)</span>', section)]
    meta = {
        "name": name,
        "group": crumb.split("/")[0].strip() if crumb else "",
        "wecom_numeric_id": section_id.replace("t-", ""),
    }
    for ch in chips:
        if ch.startswith("模板数字ID："):
            meta["wecom_numeric_id"] = ch.replace("模板数字ID：", "").strip()
        elif ch.startswith("可见："):
            meta["visible_scope"] = ch.replace("可见：", "").strip()

    tables = _tables(section)
    basic = _kv_table(tables[0]) if tables else {}
    meta["wecom_template_key"] = basic.get("template_id", "")
    meta["visible_scope"] = basic.get("可见范围", meta.get("visible_scope", ""))
    meta["print_mode"] = basic.get("打印模式", "")
    meta["event_type"] = basic.get("事件类型", "")

    fields: list[dict] = []
    nodes: list[dict] = []
    lines: list[dict] = []
    general: dict[str, str] = {}

    for idx, rows in enumerate(tables):
        head = rows[0]
        if head and head[0] == "序号":
            for row in rows[1:]:
                if len(row) < 6:
                    continue
                fields.append(
                    {
                        "seq": _int(row[0]),
                        "label": row[1].split("\n")[0].strip(),
                        "hint": "\n".join(row[1].split("\n")[1:]).strip(),
                        "control": row[2].split("\n")[-1].strip(),
                        "control_label": row[2].split("\n")[0].strip(),
                        "required": row[3].strip() == "必填",
                        "config": row[4].strip(),
                        "wecom_control_id": row[5].strip(),
                    }
                )
        elif head and head[0] == "节点ID":
            for row in rows[1:]:
                if len(row) < 5:
                    continue
                nodes.append(
                    {
                        "wecom_node_id": row[0].strip(),
                        "type": row[1].strip(),
                        "name": row[2].split("\n")[0].strip(),
                        "approver_rule": row[3].strip(),
                        "field_permissions": _parse_field_permissions(row[4]),
                    }
                )
        elif head and head[0] == "起点":
            for row in rows[1:]:
                if len(row) < 5:
                    continue
                lines.append(
                    {
                        "from": row[0].split("\n")[0].strip(),
                        "from_name": "\n".join(row[0].split("\n")[1:]).strip(),
                        "to": row[1].split("\n")[0].strip(),
                        "to_name": "\n".join(row[1].split("\n")[1:]).strip(),
                        "priority": _int(row[2]),
                        "condition_title": row[3].strip(),
                        "condition": row[4].strip(),
                    }
                )
        elif head and head[0] == "编码":
            continue

    gm = re.search(r"3\.3 流程通用选项[\s\S]*?<div class=\"chips\">([\s\S]*?)</div>", section)
    if gm:
        for chip in re.findall(r'<span class="chip">([\s\S]*?)</span>', gm.group(1)):
            text = _strip_tags(chip)
            if "=" in text:
                k, v = text.split("=", 1)
                general[k.strip()] = v.strip()

    return {
        "meta": meta,
        "fields": fields,
        "nodes": nodes,
        "lines": lines,
        "general_options": general,
    }


def _parse_field_permissions(raw: str) -> dict[str, str]:
    """字段权限串「字段名：仅可见」→ {字段名: 权限}。"""
    out: dict[str, str] = {}
    for ln in raw.split("\n"):
        ln = ln.strip()
        if not ln or ln == "—":
            continue
        if "：" in ln:
            k, v = ln.split("：", 1)
            out[k.strip()] = v.strip()
    return out


def parse_templates(doc: str) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(r'<section class="tpl-section" id="(t-[^"]+)">([\s\S]*?)</section>', doc):
        out.append(parse_template(m.group(2), m.group(1)))
    return out


def _first(m: re.Match | None) -> str:
    return _strip_tags(m.group(1)) if m else ""


def _int(raw: str) -> int:
    try:
        return int(re.sub(r"[^\d-]", "", raw))
    except (TypeError, ValueError):
        return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DOC_NAME)
    ap.add_argument("--out", default="backend/app/seeds/data")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    doc_path = Path(args.doc)
    if not doc_path.is_absolute():
        doc_path = root / doc_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = doc_path.read_text(encoding="utf-8")
    org = parse_org(doc)
    tags = parse_tags(doc)
    templates = parse_templates(doc)
    anon = anonymize(org, tags)
    templates = scrub_templates(templates, anon["name_map"], anon["acct_map"])

    (out_dir / "wecom_org.json").write_text(
        json.dumps(anon["depts"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "wecom_tags.json").write_text(json.dumps(anon["tags"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "wecom_people.json").write_text(
        json.dumps(anon["people"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "wecom_templates.json").write_text(
        json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"depts={len(org['depts'])} people={len(org['people'])} tags={len(tags)} templates={len(templates)}")
    print(f"fields={sum(len(t['fields']) for t in templates)} "
          f"nodes={sum(len(t['nodes']) for t in templates)} lines={sum(len(t['lines']) for t in templates)}")


if __name__ == "__main__":
    main()

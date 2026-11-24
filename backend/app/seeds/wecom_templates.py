"""企业微信 39 个在用审批模板 → bizSys OA 表单 + 审批定义（E1 幂等种子）。

数据源：`app/seeds/data/wecom_templates.json`（由 `scripts/parse_wecom_doc.py`
从《企业微信审批与组织数据技术文档.html》解析并**脱敏**而来）。

每个企微模板落成两行：

| 企微 | bizSys | 键 |
| --- | --- | --- |
| 审批模板（表单） | `oa_form` | `key = wc_<slug>`，`status=published`，`scope_json` 可见范围 |
| 审批模板（流程） | `approval_definition` + `approval_node` | `code = wc_<slug>_approve`，`biz_type="oa"` |

**隐私红线**：本模块只消费脱敏后的 JSON（姓名 `模拟员工NN`、账号 `mockNNN`），
不写入任何真实姓名 / 手机 / 邮箱 / 证件号 / 企微 ID。

移植要点：

1. **控件映射**（22 类企微控件 → bizSys 字段类型）；明细表子列类型按列名推断，
   子列的原始控件 id 从「节点字段权限的孤儿键」回收；公式表达式翻译为
   `SUM(表key.列key)` 聚合（服务端重算）。
2. **图结构线性化**：企微是 DAG（多入口汇合），审批引擎是「线性 seq + 条件节点前跳」。
   本模块用 *DFS 前序 + 跳转节点* 把 DAG 翻译成线性节点序列（见 `_Linearizer`）。
3. **条件规则翻译**：企微 op 编码（op1..op6）→ 引擎比较符；阈值缺失的两处按标题重建
   区间并标记 `reconstructed` / `needs_review`（见 `OP_MAP`、`_interval_from_title`）。
4. **审批人映射**：标签 → `sys_role(wc_tag_*)`；部门/上级 → 组织类型；自选 → 表单变量。
5. **流程通用选项**（意见必填 / 允许加签 / 办理人可修改 …）写入 `approval_definition.options`。
6. **节点字段权限**（「仅可见」→ viewonly）写入 `approval_node.field_permissions`。
7. **可见范围**（部门 / 标签 / 人员名单）写入 `oa_form.scope_json`。
8. 导入完成后落一份 `app/seeds/data/wecom_flow_packages.json`（流程包 JSON，批量导入导出用）。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.approval.models import ApprovalDefinition
from app.modules.approval.schemas import DefinitionIn
from app.modules.oa.models import OaForm

DATA_DIR = Path(__file__).parent / "data"

# --------------------------------------------------------------------------- 常量

#: 39 个模板的 slug（与 `wecom_templates.json` 顺序严格一致）
TEMPLATE_SLUGS = [
    "change_approval", "acceptance_apply", "purchase_apply", "travel_apply_dept",
    "cmd_present", "general_apply", "business_entertain", "invoice_apply",
    "bank_deposit", "travel_overstandard", "travel_expense", "bill_expense",
    "payment_apply", "contract_sign", "advance_loan", "cmd_payment",
    "meeting_review", "document_approval", "seal_carve", "seal_use",
    "doc_flow", "business_card", "leave", "outing",
    "overtime", "punch_correction", "punch_approval", "staff_demand",
    "staff_monthly_review", "housing_subsidy", "hr_onboard", "hr_regular",
    "hr_transfer", "hr_resign", "recruit_demand", "staff_regular",
    "travel_apply", "advanced_feature", "robot_apply",
]

#: 企微分组 → bizSys 表单分类（字典 oa_category 的 value）
CATEGORY_BY_GROUP = {
    "业务管理": "wc_biz",
    "财务": "wc_fin",
    "行政": "wc_admin",
    "假勤": "wc_att",
    "人事": "wc_hr",
    "其他": "wc_other",
}

#: 分类图标（Element Plus 图标名，须在 `frontend/src/icons.ts` 登记）
CATEGORY_ICON = {
    "wc_biz": "Tickets",
    "wc_fin": "Money",
    "wc_admin": "Stamp",
    "wc_att": "Calendar",
    "wc_hr": "User",
    "wc_other": "Document",
}

#: 企微控件 → bizSys 字段类型
CONTROL_TYPE = {
    "Text": "text",
    "Textarea": "textarea",
    "Number": "number",
    "Money": "money",
    "Date": "date",
    "DateRange": "daterange",
    "File": "file",
    "Tips": "text_block",
    "Selector": "select",
    "RelatedApproval": "resource",
    "Table": "table",
    "Formula": "formula",
    "PhoneNumber": "phone",
    "Location": "location",
    "Attendance": "attendance",
    "Vacation": "attendance",
    "PunchCorrection": "attendance",
    "Onboarding": "hr_ref",
    "Regularization": "hr_ref",
    "Transfer": "hr_ref",
    "Resignation": "hr_ref",
    "Contact": "user",
}

#: 假勤原子类型
ATTENDANCE_REF = {"Attendance": "attendance", "Vacation": "vacation", "PunchCorrection": "punch"}
#: 人事原子类型
HR_REF = {"Onboarding": "onboard", "Regularization": "regular", "Transfer": "transfer", "Resignation": "resign"}

#: 企微数值比较符编码 → 引擎比较符（推定，见 docs/api-contract.md E1 章节）
OP_MAP = {"op1": "eq", "op2": "gt", "op3": "lt", "op4": "gte", "op5": "lte", "op6": "between"}

#: 源文档中 tagid 被截断（`67554019270`）→ 补全为「分管领导-技术」（**待界面复核**）
TAG_ID_OVERRIDE = {"67554019270": "6755401927078052"}

#: 审批节点名 → 企微标签（审批人来源；标签 → `sys_role(wc_tag_*)`）
NODE_TAG = {
    "业务运营组员": ["组员-业务运营"],
    "业务运营部分管领导": ["分管领导-业务运营部"],
    "主办会计": ["主办会计"],
    "主办会计财务部长": ["主办会计", "财务部长"],
    "分管领导-综合管理部": ["分管领导-综合管理部"],
    "参会人（总经理外）": ["总经办会议参会人（总经理外）"],
    "总经理": ["总经理"],
    "总经理意见与签字": ["总经理"],
    "组长-ALL": ["组长-ALL"],
    "组长-土建": ["组长-工程"],
    "组长-土建组": ["组长-工程"],
    "组长-工艺设备": ["组长-工艺设备"],
    "组长-采购商务部": ["组长-采购商务"],
    "组长-项目规划部": ["组长-规划"],
    "综合管理部意见与签字": ["分管领导-综合管理部"],
    "综合管理部负责人": ["分管领导-综合管理部"],
    "董事长": ["董事长"],
    "财务分管领导": ["分管领导-财务"],
    "财务负责人": ["分管领导-财务"],
    "财务部组员": ["组员-财务部"],
    "财务部长": ["财务部长"],
    "项目建设总指挥": ["总指挥-项目建设"],
    "项目建设部门分管领导": ["分管领导-项目建设"],
}

#: 办理节点名 → 办理人来源
EXECUTOR_SOURCE = {
    "人事专员办理": ("tag", ["人事专员"]),
    "出纳": ("tag", ["财务出纳"]),
    "财务部经办人": ("tag", ["组员-财务部"]),
    "综合管理部负责人": ("tag", ["分管领导-综合管理部"]),
    "综合管理部负责人办理": ("tag", ["分管领导-综合管理部"]),
    "办理人": ("dept_leader", []),
    "管理员": ("role", ["super"]),
}

#: 抄送节点名 → 抄送人来源（按节点名判定的固定抄送人）
CC_NODE_SOURCE = {
    "抄送人事部": ("tag", ["人事专员"]),
    "抄送人（905项目请抄送给副总指挥）": ("tag", ["副总指挥-项目建设部"]),
}

#: 流程通用选项：企微选项名 → 引擎选项键
GENERAL_OPTION_MAP = {
    "审批人可修改流程": "allowModifyFlow",
    "审批人可修改抄送": "allowModifyCc",
    "通过后申请人可撤销": "allowWithdrawAfterApproved",
    "审批意见需签名": "commentSignRequired",
    "允许加签": "allowAddSign",
    "审批意见必填": "commentRequired",
    "办理人意见必填": "executorCommentRequired",
    "办理人可修改": "executorCanModify",
    "允许他人代提交": "allowProxySubmit",
    "明细表权限控制": "detailTablePermission",
}

#: 明细列类型推断关键词（先匹配先生效）
COLUMN_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("select", ("类型", "类别", "状态", "方式", "结算方式")),
    ("money", ("金额", "价格", "单价", "总价", "费用", "预算", "薪", "款", "合计", "总额", "标准", "税")),
    ("number", ("数量", "个数", "人数", "天数")),
    ("date", ("日期", "时间")),
    ("textarea", ("说明", "备注", "描述")),
    ("file", ("附件", "文件")),
    ("phone", ("电话", "手机")),
)

#: 明细列类型 → 可接受的原始控件 id 前缀（按优先级）
COLUMN_ACCEPT = {
    "select": ("Selector", "Text", "Textarea"),
    "money": ("Money", "Formula", "Number"),
    "number": ("Number", "Money"),
    "date": ("Date",),
    "textarea": ("Textarea", "Text"),
    "phone": ("PhoneNumber", "Text"),
    "file": ("File", "Text"),
    "text": ("Text", "Textarea", "Selector", "PhoneNumber", "File", "Number", "Money", "Date"),
}

#: 明细列最终落库类型（bizSys 明细列仅支持 text/textarea/number/money/date/select，
#: 而 select 必须配选项 —— 企微明细列无选项数据源，一律降级为 text）
COLUMN_STORE_TYPE = {
    "select": "text",
    "money": "money",
    "number": "number",
    "date": "date",
    "textarea": "textarea",
    "phone": "text",
    "file": "text",
    "text": "text",
}

#: 推断类型 → 原始控件类型的「精确匹配」名（列控件 id 前缀）
COLUMN_CANON = {
    "select": "Selector",
    "money": "Money",
    "number": "Number",
    "date": "Date",
    "textarea": "Textarea",
    "file": "File",
    "phone": "PhoneNumber",
    "text": "Text",
}

_TIPS_PREFIX_RE = re.compile(r"kContentType\w+\s*")
_INTERVAL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(w?)\s*[-~—]\s*(\d+(?:\.\d+)?)\s*(w?)", re.I)
#: 公式表达式词法：控件 id（`Money-1762…`）/ 运算符 / 数字 —— 控件 id 自带连字符，不能按 `-` 切
_FORMULA_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9_]+|[+\-*/]|\d+(?:\.\d+)?")


# --------------------------------------------------------------------------- 小工具


def _load(name: str) -> Any:
    path = DATA_DIR / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def templates_data() -> list[dict]:
    return _load("wecom_templates.json")


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def _raw_type(ctrl_id: str) -> str:
    """原始控件 id 前缀 → 控件名（`item-150…` 这类无前缀的返回空串）。"""
    raw = (ctrl_id or "").split("-", 1)[0]
    return raw if raw in CONTROL_TYPE else ""


def _tips_text(config: str) -> str:
    """Tips 控件正文：去掉 `kContentTypePlainText` 之类前缀与尾部语言标记。"""
    text = _TIPS_PREFIX_RE.sub("", config or "")
    text = re.sub(r"\s+(zh_CN|en_US|en)\s*$", "", text.strip())
    text = re.sub(r"\s{2,}", " ", text)
    return text[:255]


def _selector_options(config: str) -> tuple[str, list[str]]:
    """`单选：A / B` → ("select", [A, B])；`多选：A / B` → ("checkbox", [...])。"""
    raw = (config or "").strip()
    kind, opts = "select", []
    if "：" in raw:
        head, _, tail = raw.partition("：")
        kind = head.strip()
        opts = [o.strip() for o in tail.split("/") if o.strip()]
    if kind.startswith("多选"):
        return "checkbox", opts
    return "select", opts


def _table_columns(config: str) -> list[str]:
    """`明细字段：A、B、C` → [A, B, C]。"""
    raw = (config or "").strip()
    if "：" in raw:
        raw = raw.split("：", 1)[1]
    return [c.strip() for c in raw.replace("、", ",").split(",") if c.strip()]


def _contact_mode(config: str) -> tuple[str, bool]:
    """Contact 控件 → (mode, multiple)。"""
    raw = (config or "").replace(" ", "")
    multiple = '"type":"multi"' in raw
    if '"mode":"department"' in raw:
        return "dept", multiple
    return "user", multiple


def _interval_from_title(title: str) -> list[float] | None:
    """从条件标题重建区间：`1000-10000` / `10w-100w`（w = 万）。"""
    m = _INTERVAL_RE.search(title or "")
    if not m:
        return None
    lo = float(m.group(1)) * (10000 if m.group(2).lower() == "w" else 1)
    hi = float(m.group(3)) * (10000 if m.group(4).lower() == "w" else 1)
    return [lo, hi]


def _parse_condition(text: str) -> dict | None:
    """企微条件文本 → {control, kind, value, title}；无条件返回 None。

    文本形如::

        变更是否涉及设备
        字段：Selector-1777467980749
        单选：是
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines or "无条件" in lines[0]:
        return None
    out: dict[str, Any] = {"control": "", "kind": "", "value": "", "title": lines[0]}
    for ln in lines[1:]:
        if ln.startswith("字段："):
            out["control"] = ln.split("：", 1)[1].strip()
        elif ln.startswith("单选："):
            out["kind"] = "select"
            out["value"] = ln.split("：", 1)[1].strip()
        elif ln.startswith("多选："):
            out["kind"] = "multi"
            out["value"] = ln.split("：", 1)[1].strip()
        elif ln.startswith("数值："):
            out["kind"] = "number"
            out["value"] = ln.split("：", 1)[1].strip()
        elif ln.startswith("部门："):
            out["kind"] = "dept"
            out["value"] = ln.split("：", 1)[1].strip()
    if not out["control"] or not out["kind"]:
        return None
    return out


def _numeric_rule(raw: str, title: str) -> tuple[dict | None, str]:
    """`数值：op4 / 1000000` → (规则片段, 备注)。阈值缺失时按标题重建。"""
    op_raw, _, threshold = (raw or "").partition("/")
    op_raw = op_raw.strip()
    threshold = threshold.strip()
    op = OP_MAP.get(op_raw)
    if not op:
        return None, f"未知比较符 {op_raw}"
    if threshold in ("", "undefined"):
        if op == "between":
            interval = _interval_from_title(title)
            if not interval:
                return None, "区间阈值缺失且标题无法重建"
            return {"op": "between", "value": interval}, "区间按标题重建（待界面复核）"
        return {"op": "gt", "value": 0}, "阈值缺失，按 >0 处理（待界面复核）"
    try:
        value = float(threshold)
    except ValueError:
        return None, f"阈值无法解析：{threshold}"
    if op == "between":
        return None, "区间需要上下限"
    return {"op": op, "value": value}, ""


# --------------------------------------------------------------------------- 上下文


class _Context:
    """导入上下文：模拟人员 id、标签成员、标签 → 角色 code。"""

    def __init__(self, db: Session) -> None:
        from app.modules.admin.models import Dept, Role  # noqa: PLC0415 避免循环导入
        from app.modules.auth.models import User  # noqa: PLC0415

        self.db = db
        self.user_by_acct: dict[str, Any] = {}
        self.user_by_name: dict[str, Any] = {}
        for u in db.scalars(select(User).where(User.username.like("mock%"), User.deleted == 0)).all():
            self.user_by_acct[u.username] = u
            self.user_by_name[u.name or ""] = u
        self.role_codes = {r.code for r in db.scalars(select(Role).where(Role.deleted == 0)).all()}
        self.dept_names = {d.name for d in db.scalars(select(Dept).where(Dept.deleted == 0)).all()}

        tags = _load("wecom_tags.json")
        self.tag_members: dict[str, list[str]] = {
            t.get("name", ""): list(t.get("members") or []) for t in tags
        }
        self.tag_id_to_name: dict[str, str] = {
            str(t.get("wecom_tagid")): t.get("name", "") for t in tags if t.get("wecom_tagid")
        }

    def user_id(self, account_or_name: str) -> int | None:
        key = (account_or_name or "").strip()
        if not key:
            return None
        u = self.user_by_acct.get(key) or self.user_by_name.get(key)
        return u.id if u else None

    def tag_role_codes(self, tag_names: list[str]) -> list[str]:
        out = []
        for name in tag_names:
            code = f"wc_tag_{name}"
            if code in self.role_codes:
                out.append(code)
        return out

    def tag_user_ids(self, tag_name: str) -> list[int]:
        ids = []
        for member in self.tag_members.get(tag_name, []):
            uid = self.user_id(member)
            if uid:
                ids.append(uid)
        return ids


# --------------------------------------------------------------------------- 图线性化


class _Item:
    """线性序列中的一项：企微节点（kind=node）或跳转节点（kind=jump）。"""

    __slots__ = ("kind", "wecom_id")

    def __init__(self, kind: str, wecom_id: str) -> None:
        self.kind = kind
        self.wecom_id = wecom_id


class _Linearizer:
    """把企微 DAG 翻译成「线性 seq + 条件节点前跳」。

    规则：

    - 非路由节点只有唯一后继 → 直接顺排；
    - 路由节点 R 的每条出边成为一条分支：无条件的那条 → `default_seq`，
      其余 → `branches`（按 priority 顺序）；分支链末尾补一个 **跳转节点**
      （恒真条件）指回汇合点；
    - 汇合点 M = 各后继可达集（含自身）交集里拓扑序最靠前者；
    - 企微「流程结束」落成末位终止节点（条件节点、无分支、无默认），
      引擎走到即结束；
    - 跳转/分支目标一律 **向后**（线性序更大），杜绝回跳死循环。
    """

    def __init__(self, tpl: dict) -> None:
        self.tpl = tpl
        self.nodes = {n["wecom_node_id"]: n for n in tpl["nodes"]}
        self.out: dict[str, list[dict]] = {}
        self.indeg: dict[str, int] = {nid: 0 for nid in self.nodes}
        for line in tpl["lines"]:
            self.out.setdefault(line["from"], []).append(line)
            self.indeg[line["to"]] = self.indeg.get(line["to"], 0) + 1
        for lst in self.out.values():
            lst.sort(key=lambda x: (int(x.get("priority") or 0), str(x.get("to"))))
        self.order = self._topo_order()
        self.pos = {nid: i for i, nid in enumerate(self.order)}
        self.items: list[_Item] = []
        self.emitted: set[str] = set()
        self.node_index: dict[str, int] = {}
        self.branches: list[dict] = []
        self.jumps: dict[int, str] = {}
        self.jump_targets: dict[int, int] = {}
        self.warnings: list[str] = []

    # -- 拓扑序 --
    def _topo_order(self) -> list[str]:
        base = {nid: i for i, nid in enumerate(self.nodes)}
        indeg = dict(self.indeg)
        ready = sorted([n for n in self.nodes if indeg.get(n, 0) == 0], key=lambda n: base[n])
        order: list[str] = []
        while ready:
            nid = ready.pop(0)
            order.append(nid)
            for line in self.out.get(nid, []):
                tgt = line["to"]
                indeg[tgt] -= 1
                if indeg[tgt] == 0:
                    ready.append(tgt)
                    ready.sort(key=lambda n: base[n])
        for nid in self.nodes:  # 环路兜底
            if nid not in order:
                order.append(nid)
        return order

    # -- 可达集 --
    def _reachable(self, nid: str) -> set[str]:
        seen: set[str] = set()
        stack = [nid]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for line in self.out.get(cur, []):
                stack.append(line["to"])
        return seen

    def merge_of(self, router: str) -> str:
        """路由节点的汇合点 = 各后继可达集（含自身）交集里拓扑序最靠前者。"""
        succs = [line["to"] for line in self.out.get(router, [])]
        if not succs:
            return router
        common: set[str] | None = None
        for s in succs:
            reach = self._reachable(s) | {s}
            common = reach if common is None else (common & reach)
        if not common:
            self.warnings.append(f"路由节点 {router} 的分支无公共汇合点，按最后一条分支处理")
            return succs[-1]
        return min(common, key=lambda n: self.pos.get(n, 10**6))

    # -- 发射 --
    def _push(self, nid: str) -> int | None:
        if nid in self.emitted:
            return None
        self.emitted.add(nid)
        idx = len(self.items)
        self.items.append(_Item("node", nid))
        self.node_index.setdefault(nid, idx)
        return idx

    def _emit_from(self, cur: str | None, stop: str | None) -> int | None:
        """从 cur 发射（含 cur）直到遇到 stop（不含）。返回 cur 的项下标。"""
        if cur is None or cur == stop:
            return None
        idx = self._push(cur)
        if idx is None:
            return None
        node = self.nodes.get(cur, {})
        if node.get("type") == "条件分支":
            self._emit_router(cur, idx, stop)
            return idx
        succs = self.out.get(cur, [])
        if succs:
            self._emit_from(succs[0]["to"], stop)
        return idx

    def _emit_router(self, router: str, router_idx: int, stop: str | None) -> None:
        """路由节点：落自身 → 逐条分支（分支链末尾补跳转）→ 汇合点及其后续。

        ``router`` 已由调用方 `_emit_from` 压入线性序列，这里不再重复压栈。

        跳转目标**延迟解析**：嵌套路由（外层路由的分支链里含内层路由）时，
        汇合点要到外层路由收尾时才发射，这里只记下「跳向哪个企微节点」，
        线性化结束后统一换算成项下标。
        """
        merge = self.merge_of(router)
        records: list[dict] = []
        jump_idxs: list[int] = []
        for line in self.out.get(router, []):
            target = line["to"]
            chain_idx = None if target == merge else self._emit_from(target, merge)
            records.append(
                {"router": router_idx, "line": line, "chain": chain_idx, "merge": merge}
            )
            if chain_idx is None:
                continue
            jump_idxs.append(len(self.items))
            self.items.append(_Item("jump", merge))
        # 汇合点本身（尚未发射时）在此发射
        self._emit_from(merge, stop)
        self.branches.extend(records)
        for ji in jump_idxs:
            self.jumps[ji] = merge

    # -- 入口 --
    def linearize(self) -> list[_Item]:
        start = "START" if "START" in self.nodes else None
        if start:
            for line in self.out.get(start, []):
                self._emit_from(line["to"], None)
        else:
            for nid in self.order:
                if not self.indeg.get(nid):
                    self._emit_from(nid, None)
        orphans = [nid for nid in self.order if nid not in self.emitted and nid != "START"]
        if orphans:
            self.warnings.append(f"存在不可达节点 {len(orphans)} 个（已跳过）：{orphans[:5]}")
        self._resolve_targets()
        return self.items

    def _resolve_targets(self) -> None:
        """把「跳转/分支 → 企微节点」的延迟引用换算成线性项下标。"""
        self.jump_targets: dict[int, int] = {}
        for ji, merge_id in self.jumps.items():
            mi = self.node_index.get(merge_id)
            if mi is None:
                self.warnings.append(f"跳转目标节点 {merge_id} 未发射，跳转已丢弃")
                continue
            self.jump_targets[ji] = mi
        for rec in self.branches:
            if rec.get("chain") is not None:
                rec["target"] = rec["chain"]
            else:
                rec["target"] = self.node_index.get(rec["merge"])


# --------------------------------------------------------------------------- 表单字段构建


def _infer_column_type(label: str) -> str:
    """明细列类型推断（按关键词）。"""
    for ctype, keywords in COLUMN_TYPE_RULES:
        if any(k in label for k in keywords):
            return ctype
    return "text"


def _collect_pool(tpl: dict) -> list[str]:
    """回收「节点字段权限里的孤儿键」= 明细列的原始控件 id（字段与标签之外的键）。"""
    fids = {f.get("wecom_control_id", "") for f in tpl["fields"]}
    flabels = {f.get("label", "") for f in tpl["fields"]}
    pool: list[str] = []
    for node in tpl["nodes"]:
        for key in node.get("field_permissions") or {}:
            if key not in fids and key not in flabels and key not in pool:
                pool.append(key)
    return sorted(pool)


def _assign_table_columns(
    tables: list[dict],
    pool: list[str],
    hard: dict[tuple[str, int], str],
) -> tuple[dict[str, list[str]], list[str]]:
    """把池子里的明细列控件 id 分配到各表的列上。

    - **硬约束** ``hard[(表名, 列下标)] = 控件 id``：来自条件标题（如「发票明细-总价税合计总金额」）。
    - 其余按「原始控件类型 → 列名推断类型」就近匹配，剩余按位置兜底。

    返回 ``({表名: [控件 id...]}, 未分配的池子元素)``。
    """
    remaining = list(pool)
    mapping: dict[str, list[str]] = {}
    notes: list[str] = []

    for tbl in tables:
        cols = _table_columns(tbl.get("config", ""))
        label = tbl.get("label", "")
        fam = _digits(tbl.get("wecom_control_id", ""))[:7]
        group = [i for i in remaining if _digits(i).startswith(fam)]
        if len(group) == len(cols) and cols:
            candidates = group
        else:
            candidates = list(remaining)
            if cols and len(candidates) != len(cols):
                notes.append(f"表「{label}」列控件 id 数量不符（候选 {len(candidates)} / 列 {len(cols)}）")
        chosen: list[str] = [""] * len(cols)
        want_types = [_infer_column_type(c) for c in cols]

        # 1. 硬约束（来自条件标题的「表名-列名」）
        for idx in range(len(cols)):
            cid = hard.get((label, idx))
            if cid and cid in candidates:
                chosen[idx] = cid

        # 2. 精确类型分组：按列名推断的类型优先取同名控件（如「金额」← Money-*）
        used = {c for c in chosen if c}
        for want in dict.fromkeys(want_types):
            canon = COLUMN_CANON.get(want, "")
            ids_r = [c for c in candidates if _raw_type(c) == canon and c not in used]
            if not ids_r:
                continue
            for idx in [i for i, w in enumerate(want_types) if w == want and not chosen[i]]:
                chosen[idx] = ids_r.pop(0)
                used.add(chosen[idx])
                if not ids_r:
                    break

        # 3. 类型可接受兜底（如「超标金额」← Formula-*）
        for idx in range(len(cols)):
            if chosen[idx]:
                continue
            for cid in candidates:
                if cid in used:
                    continue
                raw = _raw_type(cid)
                if raw and raw in COLUMN_ACCEPT.get(want_types[idx], ()):
                    chosen[idx] = cid
                    used.add(cid)
                    break

        # 4. 位置兜底
        spare = [c for c in candidates if c not in used]
        for idx in range(len(cols)):
            if not chosen[idx] and spare:
                chosen[idx] = spare.pop(0)
                used.add(chosen[idx])

        mapping[label] = chosen
        for cid in chosen:
            if cid in remaining:
                remaining.remove(cid)

    return mapping, remaining


def _build_fields(
    tpl: dict,
    key_by_template: dict[str, str],
    conditions: list[dict],
) -> tuple[list[dict], dict, list[str]]:
    """企微模板 → 表单字段列表 + 控件 id 索引。

    返回 ``(fields, index, notes)``，index 含：

    - ``by_ctrl``：控件 id → 字段 key
    - ``by_col``：明细列控件 id → (表字段 key, 列 key)
    - ``label_key``：字段名 → 字段 key
    """
    fields: list[dict] = []
    index: dict[str, Any] = {"by_ctrl": {}, "by_col": {}, "label_key": {}}
    notes: list[str] = []

    # --- 1. 明细列控件 id 的硬约束（条件标题里的「表名-列名」）---
    tables = [f for f in tpl["fields"] if f.get("control") == "Table"]
    hard: dict[tuple[str, int], str] = {}
    for cond in conditions:
        ctrl = cond["control"]
        title = cond.get("title", "")
        for tbl in tables:
            tlabel = tbl.get("label", "")
            if not tlabel or not title.startswith(tlabel):
                continue
            suffix = title[len(tlabel):].lstrip("-－:： ")
            cols = _table_columns(tbl.get("config", ""))
            for idx, col in enumerate(cols):
                if col and (col in suffix or suffix in col):
                    hard.setdefault((tlabel, idx), ctrl)
                    break

    pool = _collect_pool(tpl)
    col_map, leftover = _assign_table_columns(tables, pool, hard)
    if leftover:
        notes.append(f"有 {len(leftover)} 个字段权限键未能对应到明细列（已忽略）")

    # --- 2. 逐字段转换 ---
    for idx, f in enumerate(tpl["fields"], start=1):
        control = f.get("control", "")
        ftype = CONTROL_TYPE.get(control, "text")
        key = f"f{idx}"
        label = (f.get("label") or control or key)[:64]
        cfg = f.get("config", "")
        payload: dict[str, Any] = {
            "key": key,
            "label": label,
            "type": ftype,
            "required": bool(f.get("required")),
        }
        hint = (f.get("hint") or "").strip()
        if hint:
            payload["placeholder"] = hint[:255]

        if control == "Selector":
            _, opts = _selector_options(cfg)
            if opts:
                payload["options"] = opts
        elif control == "Tips":
            payload["description"] = _tips_text(cfg)
        elif control == "Contact":
            mode, multiple = _contact_mode(cfg)
            if mode == "dept":
                payload["type"] = "resource"
                payload["resource"] = "dept"
            else:
                payload["multiple"] = multiple
        elif control == "RelatedApproval":
            payload["resource"] = "oa_instance"
            related = []
            for tid in re.findall(r'"template_id"\s*:\s*\[\s*"([^"]+)"', cfg):
                fkey = key_by_template.get(tid)
                if fkey:
                    related.append(fkey)
            payload["relatedFormKeys"] = related
        elif control == "Table":
            cols = _table_columns(cfg)
            payload["columns"] = [
                {
                    "key": f"c{i}",
                    "label": col[:64],
                    "type": COLUMN_STORE_TYPE[_infer_column_type(col)],
                    "required": False,
                }
                for i, col in enumerate(cols, start=1)
            ]
        elif control == "Formula":
            payload["formula"] = ""  # 表达式在列 id 分配完成后回填
        elif control in ATTENDANCE_REF:
            payload["refType"] = ATTENDANCE_REF[control]
        elif control in HR_REF:
            payload["refType"] = HR_REF[control]

        fields.append(payload)
        ctrl_id = f.get("wecom_control_id", "")
        if ctrl_id:
            index["by_ctrl"][ctrl_id] = key
        index["label_key"][label] = key

    # --- 3. 明细列控件 id → (表字段 key, 列 key) ---
    for fld, src in zip(fields, tpl["fields"], strict=False):
        if fld["type"] != "table":
            continue
        tkey = fld["key"]
        ctrl_ids = col_map.get(src.get("label", ""), [])
        for cidx, col in enumerate(fld.get("columns", []), start=1):
            if cidx <= len(ctrl_ids) and ctrl_ids[cidx - 1]:
                index["by_col"][ctrl_ids[cidx - 1]] = (tkey, col["key"])

    # --- 4. 公式表达式回填（控件 id → SUM(表key.列key)）---
    for fld, src in zip(fields, tpl["fields"], strict=False):
        if fld["type"] != "formula":
            continue
        expr = (src.get("config") or "").strip()
        if not expr:
            fld["type"] = "text"
            notes.append(f"公式字段「{fld['label']}」无表达式，已降级为文本")
            continue
        parts = _FORMULA_TOKEN_RE.findall(expr)
        out_parts: list[str] = []
        ok = True
        for token in parts:
            if token in ("+", "-", "*", "/"):
                out_parts.append(token)
                continue
            ref = index["by_col"].get(token)
            if ref:
                out_parts.append(f"SUM({ref[0]}.{ref[1]})")
                continue
            ctrl_key = index["by_ctrl"].get(token)
            if ctrl_key is None:
                # 源文档里的控件 id 可能被截断（如 `Money-176293514815`），按前缀唯一匹配
                hits = [k for k in index["by_col"] if k.startswith(token)]
                if len(hits) == 1:
                    tkey, ckey = index["by_col"][hits[0]]
                    out_parts.append(f"SUM({tkey}.{ckey})")
                    continue
                hits = [k for k in index["by_ctrl"] if k.startswith(token)]
                ctrl_key = index["by_ctrl"][hits[0]] if len(hits) == 1 else None
            if ctrl_key is not None:
                out_parts.append(ctrl_key)
            else:
                ok = False
                out_parts.append(token)
        if not ok:
            fld["type"] = "text"
            fld.pop("formula", None)
            notes.append(f"公式字段「{fld['label']}」的表达式未能翻译（{expr[:40]}）")
            continue
        fld["formula"] = " ".join(out_parts)[:255]

    return fields, index, notes


# --------------------------------------------------------------------------- 审批人映射


def _approver_of(
    node: dict,
    ctx: _Context,
    sel_field: str | None,
    notes: list[str],
) -> dict:
    """企微审批节点 → 引擎审批人配置。

    返回 {approver_type, approver_value, approver_name, chain_levels, sign_mode}。
    """
    name = node.get("name", "")
    rule = node.get("approver_rule", "") or ""
    head = rule.split("｜")[0].strip()

    # 1. 标签成员
    if head == "标签成员":
        tags = NODE_TAG.get(name, [])
        codes = ctx.tag_role_codes(tags)
        if not codes:
            notes.append(f"节点「{name}」未匹配到标签角色")
        return {
            "approver_type": "ROLE",
            "approver_value": ",".join(codes)[:64],
            "approver_name": ("标签：" + "、".join(tags))[:128] if tags else name[:128],
            "chain_levels": None,
            "sign_mode": "and" if name == "会签审批人" else "or",
        }

    # 2. 申请人自选（表单变量）
    if head == "申请人自选":
        return {
            "approver_type": "FORM_USER",
            "approver_value": (sel_field or "")[:64],
            "approver_name": f"{name}（申请人自选）"[:128],
            "chain_levels": None,
            "sign_mode": "and" if name == "会签审批人" else "or",
        }

    # 3. 指定成员
    if head == "指定成员":
        raw = ""
        for part in rule.split("｜"):
            if part.strip().startswith("成员："):
                raw = part.strip()[len("成员："):]
                break
        ids = [ctx.user_id(m.strip()) for m in raw.split("、")]
        ids = [i for i in ids if i]
        if not ids:
            notes.append(f"节点「{name}」指定成员未匹配到模拟人员")
        return {
            "approver_type": "USER",
            "approver_value": ",".join(str(i) for i in ids)[:64],
            "approver_name": f"{name}（指定成员）"[:128],
            "chain_levels": None,
            "sign_mode": "or",
        }

    # 4. 考核人（表单字段指定）
    if head == "APV_MEMBER_CONTROL":
        return {
            "approver_type": "FORM_USER",
            "approver_value": (sel_field or "")[:64],
            "approver_name": f"{name}（表单指定）"[:128],
            "chain_levels": None,
            "sign_mode": "or",
        }

    # 5. 管理员指定审批人集合
    if head == "APV_APPROVER_COLLECTION":
        return {
            "approver_type": "SUPERVISOR_CHAIN",
            "approver_value": "",
            "approver_name": f"{name}（管理员指定，默认取上级）"[:128],
            "chain_levels": 1,
            "sign_mode": "and",
        }

    # 6. 上级审批 / 指定上级（按节点名细分）
    if head in ("APV_MEMBER_LEADER", "上级审批"):
        if name in ("直接部门负责人", "上级审批", "上级审批人"):
            atype, levels = "DEPT_LEADER", None
        elif name in ("直接部门分管领导", "分管领导意见"):
            atype, levels = "PARENT_DEPT_LEADER", None
        else:  # 指定上级
            atype, levels = "SUPERVISOR_CHAIN", 1
        return {
            "approver_type": atype,
            "approver_value": "",
            "approver_name": name[:128],
            "chain_levels": levels,
            "sign_mode": "or",
        }

    notes.append(f"节点「{name}」审批人规则未识别：{head}")
    return {
        "approver_type": "USER",
        "approver_value": "",
        "approver_name": name[:128],
        "chain_levels": None,
        "sign_mode": "or",
    }


def _cc_receivers(node: dict, ctx: _Context, sel_field: str | None) -> list[dict]:
    """抄送节点 → 若干抄送人配置（一条规则可能含「固定成员 + 申请人自选」）。"""
    rule = node.get("approver_rule", "") or ""
    name = node.get("name", "")
    out: list[dict] = []

    # 1. 节点名指定的固定抄送人
    src = CC_NODE_SOURCE.get(name)
    if src:
        kind, values = src
        if kind == "tag":
            codes = ctx.tag_role_codes(values)
            out.append(
                {
                    "approver_type": "ROLE",
                    "approver_value": ",".join(codes)[:64],
                    "approver_name": ("抄送：" + "、".join(values))[:128],
                }
            )

    # 2. 规则里的「抄送：成员、成员」
    fixed = re.search(r"抄送：([^｜]+)", rule)
    if fixed:
        ids = []
        for member in fixed.group(1).split("、"):
            uid = ctx.user_id(member.strip())
            if uid:
                ids.append(uid)
        if ids:
            out.append(
                {
                    "approver_type": "USER",
                    "approver_value": ",".join(str(i) for i in ids)[:64],
                    "approver_name": ("抄送：" + fixed.group(1).strip())[:128],
                }
            )

    # 3. 申请人自选抄送人
    if sel_field:
        out.append(
            {
                "approver_type": "FORM_USER",
                "approver_value": sel_field[:64],
                "approver_name": "抄送人（申请人自选）"[:128],
            }
        )
    return out


# --------------------------------------------------------------------------- 可见范围


def _scope_of(tpl: dict, ctx: _Context) -> dict:
    """企微可见范围 → {depts, roles, users}。空 = 全员可见。"""
    raw = (tpl["meta"].get("visible_scope") or "").strip()
    if not raw:
        return {}
    scope: dict[str, list[str]] = {"depts": [], "roles": [], "users": []}
    tag_names = set(ctx.tag_members.keys())
    for part in re.split(r"[、,]", raw):
        token = part.strip()
        if not token:
            continue
        if token in ctx.dept_names:
            scope["depts"].append(token)
        elif token in tag_names:
            scope["roles"].append(f"wc_tag_{token}")
        elif re.fullmatch(r"mock\d{3}", token):
            scope["users"].append(token)
        elif token.startswith("模拟员工"):
            num = token.replace("模拟员工", "").strip()
            if num.isdigit():
                scope["users"].append(f"mock{int(num):03d}")
        else:
            continue
    if not any(scope.values()):
        return {}
    return scope


# --------------------------------------------------------------------------- 导入主流程


def import_templates(db: Session, write_packages: bool = True) -> dict:
    """幂等导入 39 个企微审批模板（表单 + 流程定义）。

    返回导入报告（统计 + 待人工复核项）。
    """
    from app.modules.approval import packages as pkg_mod  # noqa: PLC0415

    tpls = templates_data()
    ctx = _Context(db)
    key_by_template = {
        t["meta"].get("wecom_template_key", ""): f"wc_{slug}"
        for t, slug in zip(tpls, TEMPLATE_SLUGS, strict=False)
    }

    report: dict[str, Any] = {
        "templates": len(tpls),
        "forms": 0,
        "definitions": 0,
        "nodes": 0,
        "branches": 0,
        "conditions": 0,
        "review": [],
        "errors": [],
    }

    for idx, tpl in enumerate(tpls):
        slug = TEMPLATE_SLUGS[idx] if idx < len(TEMPLATE_SLUGS) else f"tpl{idx}"
        form_key = f"wc_{slug}"
        flow_code = f"wc_{slug}_approve"
        meta = tpl["meta"]
        try:
            stats = _import_one(
                db, ctx, tpl, slug, form_key, flow_code, key_by_template, report
            )
            report["forms"] += 1
            report["definitions"] += 1
            for k in ("nodes", "branches", "conditions"):
                report[k] += stats[k]
        except Exception as exc:  # noqa: BLE001 - 单个模板失败不影响其余
            report["errors"].append(f"{meta.get('name', slug)}：{exc}")
            db.rollback()

    db.flush()

    # 流程包 JSON（批量导入导出用）
    if write_packages:
        packages = []
        for slug in TEMPLATE_SLUGS:
            code = f"wc_{slug}_approve"
            d = db.scalar(
                select(ApprovalDefinition)
                .where(ApprovalDefinition.code == code, ApprovalDefinition.deleted == 0)
                .order_by(ApprovalDefinition.flow_version.desc(), ApprovalDefinition.id.desc())
                .limit(1)
            )
            if not d:
                continue
            form = db.scalar(
                select(OaForm)
                .where(OaForm.key == f"wc_{slug}", OaForm.form_version == 1, OaForm.deleted == 0)
                .limit(1)
            )
            pkg = pkg_mod.build_package(db, d, form)
            pkg["source"] = "wecom"
            packages.append(pkg)
        payload = {
            "schema": pkg_mod.SCHEMA,
            "exportedAt": datetime.now().isoformat(timespec="seconds"),
            "packages": packages,
        }
        (DATA_DIR / "wecom_flow_packages.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report["packages"] = len(packages)

    return report


def _import_one(
    db: Session,
    ctx: _Context,
    tpl: dict,
    slug: str,
    form_key: str,
    flow_code: str,
    key_by_template: dict[str, str],
    report: dict[str, Any],
) -> dict:
    """导入单个模板（表单 + 流程定义），返回统计。"""
    meta = tpl["meta"]
    notes: list[str] = []

    # ---------- 1. 条件解析 ----------
    conditions: list[dict] = []
    for line in tpl["lines"]:
        parsed = _parse_condition(line.get("condition", ""))
        if parsed:
            parsed["from"] = line["from"]
            parsed["to"] = line["to"]
            # 连线上的「条件标题」承载了区间信息（如 `1000-10000`），阈值缺失时按它重建
            parsed["line_title"] = line.get("condition_title", "")
            conditions.append(parsed)

    # ---------- 2. 表单字段 ----------
    fields, index, field_notes = _build_fields(tpl, key_by_template, conditions)
    notes.extend(field_notes)
    key_by_label = index["label_key"]

    # ---------- 3. 自选审批人 / 抄送人字段（FORM_USER 变量源）----------
    sel_fields: dict[str, str] = {}
    cc_fields: dict[str, str] = {}
    sel_seq = cc_seq = 0
    for node in tpl["nodes"]:
        rule = node.get("approver_rule", "") or ""
        head = rule.split("｜")[0].strip()
        if node.get("type") == "审批节点" and head in ("申请人自选", "APV_MEMBER_CONTROL"):
            if head == "APV_MEMBER_CONTROL":
                # 绑定到表单里已有的「考核人」字段
                bound = next(
                    (f["key"] for f in fields if f["type"] == "user" and "考核" in f["label"]),
                    "",
                )
                if bound:
                    sel_fields[node["wecom_node_id"]] = bound
                    # 该字段要作为流程变量暴露给引擎（FORM_USER 解析用）
                    for f in fields:
                        if f["key"] == bound:
                            f["exposeVariable"] = True
                    continue
            sel_seq += 1
            fkey = f"sel{sel_seq}"
            fields.append(
                {
                    "key": fkey,
                    "label": f"{node.get('name', '审批人')}（自选）"[:64],
                    "type": "user",
                    "required": head == "申请人自选",
                    "multiple": True,
                    "exposeVariable": True,
                }
            )
            sel_fields[node["wecom_node_id"]] = fkey
        elif node.get("type") == "抄送节点":
            has_self = "申请人可自选抄送人" in rule
            no_fixed = not re.search(r"抄送：", rule) and node.get("name", "") not in CC_NODE_SOURCE
            if has_self or no_fixed:
                cc_seq += 1
                fkey = f"cc{cc_seq}"
                fields.append(
                    {
                        "key": fkey,
                        "label": f"{node.get('name', '抄送人')}（自选）"[:64],
                        "type": "user",
                        "required": False,
                        "multiple": True,
                        "exposeVariable": True,
                    }
                )
                cc_fields[node["wecom_node_id"]] = fkey

    # ---------- 4. 条件表达式 ----------
    cond_exprs: dict[tuple[str, str], dict | None] = {}
    exposed: set[str] = set()
    synthetic_fields: list[dict] = []
    field_types = {f["key"]: f["type"] for f in fields}
    for cond in conditions:
        ctrl = cond["control"]
        kind = ""
        if ctrl == "item-applyer":
            var_name, kind = "org.applicantId", "applicant"
        elif ctrl in index["by_ctrl"]:
            fkey = index["by_ctrl"][ctrl]
            if field_types.get(fkey) == "daterange":
                # 企微对「时长」按小时做数值比较（如 op2/72 = 大于 3 天），
                # 而 daterange 不可直接作为流程变量 —— 合成 HOURS() 公式字段暴露给引擎。
                var_name = f"hours_{fkey}"
                kind = "hours"
                if var_name not in {f["key"] for f in synthetic_fields}:
                    flabel = next((f["label"] for f in fields if f["key"] == fkey), "时长")
                    synthetic_fields.append(
                        {
                            "key": var_name,
                            "label": f"{flabel}（小时）"[:64],
                            "type": "formula",
                            "formula": f"HOURS({fkey})",
                            "exposeVariable": True,
                        }
                    )
            else:
                var_name, kind = fkey, "field"
        elif ctrl in index["by_col"]:
            tkey, ckey = index["by_col"][ctrl]
            var_name = f"sum_{tkey}_{ckey}"
            kind = "sum"
            if var_name not in {f["key"] for f in synthetic_fields}:
                col_label = ""
                for fld in fields:
                    if fld["key"] == tkey:
                        for col in fld.get("columns", []):
                            if col["key"] == ckey:
                                col_label = col["label"]
                synthetic_fields.append(
                    {
                        "key": var_name,
                        "label": f"{col_label or '合计'}（合计）"[:64],
                        "type": "formula",
                        "formula": f"SUM({tkey}.{ckey})",
                        "exposeVariable": True,
                    }
                )
        else:
            report["review"].append(f"{meta.get('name')}：条件引用未知控件 {ctrl}")
            cond_exprs[(cond["from"], cond["to"])] = None
            continue

        expr: dict[str, Any] | None = None
        if cond["kind"] == "select":
            expr = {"field": var_name, "op": "eq", "value": cond["value"]}
        elif cond["kind"] == "multi":
            expr = {"field": var_name, "op": "contains", "value": cond["value"]}
        elif cond["kind"] == "number":
            rule_expr, note = _numeric_rule(
                cond["value"], cond.get("line_title") or cond.get("title", "")
            )
            if rule_expr is None:
                report["review"].append(
                    f"{meta.get('name')}：条件「{cond.get('title')}」解析失败（{note}）"
                )
            else:
                expr = {"field": var_name, **rule_expr}
                if note:
                    report["review"].append(f"{meta.get('name')}：条件「{cond.get('title')}」{note}")
        elif cond["kind"] == "dept":
            ids: list[int] = []
            raw = cond["value"]
            for tagid in re.findall(r'"tagid"\s*:\s*"([^"]+)"', raw):
                tagid = TAG_ID_OVERRIDE.get(tagid, tagid)
                tag = ctx.tag_id_to_name.get(tagid)
                if not tag:
                    report["review"].append(f"{meta.get('name')}：条件引用未知标签 {tagid}")
                    continue
                ids.extend(ctx.tag_user_ids(tag))
            for vid in re.findall(r'"vid"\s*:\s*"([^"]+)"', raw):
                uid = ctx.user_id(vid)
                if uid:
                    ids.append(uid)
            if not ids:
                report["review"].append(f"{meta.get('name')}：条件「{cond.get('title')}」人员范围为空")
            expr = {"field": var_name, "op": "in", "value": sorted(set(ids))}

        if expr and kind in ("field", "sum", "hours"):
            exposed.add(var_name)
        cond_exprs[(cond["from"], cond["to"])] = expr

    fields.extend(synthetic_fields)

    # 暴露变量的字段：条件引用到的字段 + 公式字段
    for fld in fields:
        if fld["key"] in exposed:
            fld["exposeVariable"] = True
        elif fld["type"] == "formula" and fld.get("formula"):
            fld["exposeVariable"] = True

    # ---------- 5. 线性化 ----------
    lin = _Linearizer(tpl)
    items = lin.linearize()
    notes.extend(lin.warnings)

    # ---------- 6. 引擎节点 ----------
    variables: dict[str, Any] = {}
    for fld in fields:
        if fld.get("exposeVariable"):
            variables[fld["key"]] = {"type": fld["type"], "label": fld["label"]}
    variables.setdefault("org", {"type": "object", "label": "申请人组织"})
    variables.setdefault("form", {"type": "object", "label": "表单信息"})

    stats = {"nodes": 0, "branches": 0, "conditions": 0}
    expanded: list[list[dict]] = []  # 每个项对应的引擎节点（抄送拆分时为 2 个）
    for item in items:
        if item.kind == "jump":
            expanded.append(
                [
                    {
                        "node_name": "跳转",
                        "node_type": "condition",
                        "sign_mode": "or",
                        "approver_type": "USER",
                        "approver_value": "",
                        "approver_name": "",
                        "branches": [{"expr": {"default": True}, "target_seq": 0}],
                        "default_seq": None,
                        "field_permissions": None,
                    }
                ]
            )
            continue
        node = lin.nodes[item.wecom_id]
        ntype = node.get("type", "")
        base = {
            "node_name": (node.get("name") or "")[:64],
            "node_type": "approval",
            "sign_mode": "or",
            "approver_type": "USER",
            "approver_value": "",
            "approver_name": "",
            "chain_levels": None,
            "branches": None,
            "default_seq": None,
            "field_permissions": None,
        }
        if ntype == "条件分支":
            base.update({"node_name": (node.get("name") or "条件分支")[:64], "node_type": "condition"})
        elif ntype == "流程结束":
            base.update({"node_name": "流程结束", "node_type": "condition"})
        elif ntype == "抄送节点":
            receivers = _cc_receivers(node, ctx, cc_fields.get(item.wecom_id))
            base.update({"node_type": "cc"})
            if not receivers:
                receivers = [
                    {
                        "approver_type": "FORM_USER",
                        "approver_value": cc_fields.get(item.wecom_id, ""),
                        "approver_name": "抄送人（申请人自选）",
                    }
                ]
            if len(receivers) == 1:
                r = receivers[0]
                base.update(
                    {
                        "approver_type": r["approver_type"],
                        "approver_value": r["approver_value"],
                        "approver_name": r["approver_name"][:128],
                    }
                )
                expanded.append([base])
            else:
                # 「固定成员 + 申请人自选」→ 拆成两个抄送节点
                expanded.append(
                    [
                        {
                            **base,
                            "approver_type": r["approver_type"],
                            "approver_value": r["approver_value"],
                            "approver_name": r["approver_name"][:128],
                        }
                        for r in receivers
                    ]
                )
            continue
        elif ntype == "办理节点":
            src = EXECUTOR_SOURCE.get(node.get("name", ""))
            base.update({"node_type": "executor"})
            if not src:
                notes.append(f"办理节点「{node.get('name')}」未映射办理人")
            else:
                kind, values = src
                if kind == "tag":
                    codes = ctx.tag_role_codes(values)
                    base.update(
                        {
                            "approver_type": "ROLE",
                            "approver_value": ",".join(codes)[:64],
                            "approver_name": ("办理：" + "、".join(values))[:128],
                        }
                    )
                    if not codes:
                        notes.append(f"办理节点「{node.get('name')}」标签角色缺失")
                elif kind == "role":
                    base.update(
                        {
                            "approver_type": "ROLE",
                            "approver_value": ",".join(values)[:64],
                            "approver_name": node.get("name", "")[:128],
                        }
                    )
                else:
                    base.update(
                        {
                            "approver_type": "DEPT_LEADER",
                            "approver_name": node.get("name", "办理人")[:128],
                        }
                    )
        else:  # 审批节点
            appr = _approver_of(node, ctx, sel_fields.get(item.wecom_id), notes)
            base.update(
                {
                    "node_type": "approval",
                    "approver_type": appr["approver_type"],
                    "approver_value": appr["approver_value"],
                    "approver_name": appr["approver_name"],
                    "chain_levels": appr["chain_levels"],
                    "sign_mode": appr["sign_mode"],
                }
            )

        # 节点字段权限（「仅可见」→ viewonly）
        perms: dict[str, str] = {}
        for label, perm in (node.get("field_permissions") or {}).items():
            fkey = key_by_label.get(label)
            if not fkey:
                continue
            perms[fkey] = "viewonly" if "可见" in perm else "editable"
        if perms:
            base["field_permissions"] = perms

        expanded.append([base])

    # ---------- 7. 序号分配 + 目标回填 ----------
    item_seq: list[int] = []
    nodes_out: list[dict] = []
    for group in expanded:
        item_seq.append(len(nodes_out) + 1)
        for nd in group:
            nodes_out.append({**nd, "seq": len(nodes_out) + 1})

    for rec in lin.branches:
        router_seq = item_seq[rec["router"]]
        target_seq = item_seq[rec["target"]] if rec["target"] is not None else None
        if target_seq is None or target_seq <= router_seq:
            report["review"].append(
                f"{meta.get('name')}：分支目标非法（{rec['line'].get('condition_title')}）已丢弃"
            )
            continue
        expr = cond_exprs.get((rec["line"]["from"], rec["line"]["to"]))
        is_default = "无条件" in (rec["line"].get("condition") or "")
        node = nodes_out[router_seq - 1]
        if is_default:
            node["default_seq"] = target_seq
            continue
        if expr is None:
            report["review"].append(
                f"{meta.get('name')}：分支「{rec['line'].get('condition_title')}」条件未解析，已落为不命中"
            )
            expr = {"field": "__never__", "op": "eq", "value": "__never__"}
        branches = node.get("branches") or []
        branches.append({"expr": expr, "target_seq": target_seq})
        node["branches"] = branches

    for jump_idx, target_idx in lin.jump_targets.items():
        seq = item_seq[jump_idx]
        target_seq = item_seq[target_idx]
        if target_seq <= seq:
            report["review"].append(f"{meta.get('name')}：跳转目标非法已丢弃")
            continue
        nodes_out[seq - 1]["branches"] = [{"expr": {"default": True}, "target_seq": target_seq}]

    stats["nodes"] = len(nodes_out)
    stats["branches"] = sum(len(n["branches"] or []) for n in nodes_out)
    stats["conditions"] = sum(1 for n in nodes_out if n["node_type"] == "condition")

    # ---------- 8. 落库 ----------
    body = DefinitionIn(
        code=flow_code,
        name=(meta.get("name") or flow_code)[:64],
        biz_type="oa",
        enabled=1,
        remark=f"企业微信模板移植（模板ID {meta.get('wecom_numeric_id', '')}）"[:255],
        variables_schema=variables,
        options=_general_options(tpl),
        nodes=nodes_out,
    )
    definition = _upsert_definition(db, flow_code, body)

    scope = _scope_of(tpl, ctx)
    _upsert_form(db, form_key, meta, fields, scope, definition.id)

    for n in notes:
        report["review"].append(f"{meta.get('name')}：{n}")
    return stats


def _general_options(tpl: dict) -> dict:
    """企微通用选项 → 引擎通用选项。"""
    out: dict[str, Any] = {}
    for name, value in (tpl.get("general_options") or {}).items():
        key = GENERAL_OPTION_MAP.get(name)
        if not key:
            continue
        out[key] = str(value).strip() == "开"
    return out


def _upsert_definition(db: Session, code: str, body: DefinitionIn) -> ApprovalDefinition:
    """流程定义 upsert（幂等）。"""
    from app.modules.approval import service as approval_svc  # noqa: PLC0415

    d = db.scalar(
        select(ApprovalDefinition)
        .where(ApprovalDefinition.code == code, ApprovalDefinition.deleted == 0)
        .order_by(ApprovalDefinition.flow_version.desc(), ApprovalDefinition.id.desc())
        .limit(1)
    )
    if d is None:
        approval_svc.create_definition(db, body)
    else:
        approval_svc.update_definition(db, d.id, body)
    d = db.scalar(
        select(ApprovalDefinition)
        .where(ApprovalDefinition.code == code, ApprovalDefinition.deleted == 0)
        .order_by(ApprovalDefinition.flow_version.desc(), ApprovalDefinition.id.desc())
        .limit(1)
    )
    if d is None:  # pragma: no cover - 理论上不会发生
        raise RuntimeError(f"流程定义写入失败：{code}")
    return d


def _upsert_form(
    db: Session,
    key: str,
    meta: dict,
    fields: list[dict],
    scope: dict,
    flow_definition_id: int | None,
) -> OaForm:
    """OA 表单 upsert（幂等）。"""
    schema_json = json.dumps({"fields": fields}, ensure_ascii=False)
    scope_json = None
    if scope and any(scope.get(k) for k in ("depts", "roles", "users")):
        scope_json = json.dumps(
            {k: [str(x) for x in (scope.get(k) or [])] for k in ("depts", "roles", "users")},
            ensure_ascii=False,
        )
    group = meta.get("group", "")
    category = CATEGORY_BY_GROUP.get(group, "wc_other")
    row = db.scalar(
        select(OaForm)
        .where(OaForm.key == key, OaForm.form_version == 1, OaForm.deleted == 0)
        .limit(1)
    )
    if row is None:
        row = OaForm(key=key, name=meta.get("name", key), form_version=1, status="published")
        db.add(row)
        db.flush()
    row.name = meta.get("name", row.name)
    row.category = category
    row.icon = CATEGORY_ICON.get(category, "")
    row.sort = 100
    row.description = (
        f"企业微信模板「{meta.get('name', '')}」移植（模板ID {meta.get('wecom_numeric_id', '')}）"
    )[:512]
    row.schema_json = schema_json
    row.scope_json = scope_json
    row.flow_definition_id = flow_definition_id
    row.status = "published"
    row.published_at = row.published_at or datetime.now()
    db.flush()
    return row

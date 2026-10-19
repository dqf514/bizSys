"""幂等种子：超管/角色/菜单树/字典/编号规则/部门。

用法：uv run python -m app.seeds.init_data
"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.modules.admin.models import (
    Dept,
    DictItem,
    DictType,
    Menu,
    NumberRule,
    Role,
    RoleMenu,
    UserRole,
)
from app.modules.approval.graph import build_process_graph, dumps_graph
from app.modules.approval.models import ApprovalDefinition, ApprovalNode
from app.modules.auth.models import User

# (title_key, name, path, component_key, icon, permission, children)
# children 中 permission 为空串表示纯目录
MENU_TREE = [
    ("menu.workbench", "Workbench", "/workbench", "workbench/Dashboard", "Odometer", "workbench:view", []),
    # 客户/合同/任务与参考系统一致：各自是一级模块，不收拢进"基础信息"目录
    (
        "menu.contract",
        "Contracts",
        "/contract/contracts",
        "contract/ContractList",
        "Document",
        "contract:list",
        [
            (None, "contract-create", "", "", "", "contract:create", []),
            (None, "contract-edit", "", "", "", "contract:edit", []),
            (None, "contract-submit", "", "", "", "contract:submit", []),
            (None, "contract-delete", "", "", "", "contract:delete", []),
            (None, "contract-export", "", "", "", "contract:list:export", []),
        ],
    ),
    (
        "menu.task",
        "Tasks",
        "/task/tasks",
        "task/TaskList",
        "List",
        "task:list",
        [
            (None, "task-create", "", "", "", "task:create", []),
            (None, "task-edit", "", "", "", "task:edit", []),
            (None, "task-assign", "", "", "", "task:assign", []),
            (None, "task-submit", "", "", "", "task:submit", []),
            (None, "task-export", "", "", "", "task:list:export", []),
        ],
    ),
    (
        "menu.customer",
        "Customers",
        "/crm/customers",
        "crm/CustomerList",
        "User",
        "crm:customer:list",
        [
            (None, "customer-create", "", "", "", "crm:customer:create", []),
            (None, "customer-edit", "", "", "", "crm:customer:edit", []),
            (None, "customer-delete", "", "", "", "crm:customer:delete", []),
            (None, "customer-export", "", "", "", "crm:customer:list:export", []),
            (None, "customer-import", "", "", "", "crm:customer:import", []),
        ],
    ),
    (
        "menu.finance",
        "Finance",
        "",
        "",
        "Money",
        "",
        [
            (
                "menu.financeInvoice",
                "FinanceInvoices",
                "/finance/invoices",
                "finance/InvoiceList",
                "Postcard",
                "finance:invoice:list",
                [
                    (None, "invoice-export", "", "", "", "finance:invoice:export", []),
                ],
            ),
            (
                "menu.financeSettlement",
                "FinanceSettlements",
                "/finance/settlements",
                "finance/SettlementList",
                "Tickets",
                "finance:settlement:list",
                [
                    (None, "settlement-create", "", "", "", "finance:settlement:create", []),
                    (None, "settlement-export", "", "", "", "finance:settlement:export", []),
                    (None, "invoice-apply", "", "", "", "finance:invoice:apply", []),
                    (None, "invoice-edit", "", "", "", "finance:invoice:edit", []),
                ],
            ),
            (
                "menu.financePayment",
                "FinancePayments",
                "/finance/payments",
                "finance/PaymentList",
                "Wallet",
                "finance:payment:list",
                [
                    (None, "payment-create", "", "", "", "finance:payment:create", []),
                    (None, "payment-export", "", "", "", "finance:payment:export", []),
                ],
            ),
        ],
    ),
    (
        "menu.report",
        "Reports",
        "/report/reports",
        "report/ReportList",
        "Document",
        "report:list",
        [
            (None, "report-create", "", "", "", "report:create", []),
            (None, "report-submit", "", "", "", "report:submit", []),
            (None, "report-seal", "", "", "", "report:seal", []),
            (None, "report-export", "", "", "", "report:export", []),
        ],
    ),
    ("menu.approval", "ApprovalCenter", "/approval", "approval/TodoList", "Stamp", "approval:view", []),
    (
        "menu.oaSystem",
        "OaSystem",
        "",
        "",
        "Suitcase",
        "",
        [
            ("menu.oaApply", "OaApply", "/oa/apply", "oa/ApplyForm", "Promotion", "oa:apply", []),
            ("menu.oaMy", "OaMy", "/oa/my", "oa/MyInstances", "Document", "oa:my", []),
            ("menu.oaRelated", "OaRelated", "/oa/related", "oa/Related", "Bell", "oa:related", []),
            ("menu.oaStats", "OaStats", "/oa/stats", "oa/StatsBoard", "DataAnalysis", "oa:stats:view", []),
        ],
    ),
    (
        "menu.system",
        "System",
        "",
        "",
        "Setting",
        "",
        [
            (
                "menu.sysOrg",
                "SysOrg",
                "",
                "",
                "User",
                "",
                [
                    (
                        "menu.users",
                        "Users",
                        "/admin/users",
                        "admin/UserList",
                        "UserFilled",
                        "admin:user:list",
                        [
                            (None, "user-create", "", "", "", "admin:user:create", []),
                            (None, "user-edit", "", "", "", "admin:user:edit", []),
                            (None, "user-delete", "", "", "", "admin:user:delete", []),
                            (None, "user-export", "", "", "", "admin:user:list:export", []),
                        ],
                    ),
                    (
                        "menu.roles",
                        "Roles",
                        "/admin/roles",
                        "admin/RoleList",
                        "Key",
                        "admin:role:list",
                        [
                            (None, "role-create", "", "", "", "admin:role:create", []),
                            (None, "role-edit", "", "", "", "admin:role:edit", []),
                            (None, "role-delete", "", "", "", "admin:role:delete", []),
                        ],
                    ),
                    (
                        "menu.depts",
                        "Depts",
                        "/admin/depts",
                        "admin/DeptList",
                        "OfficeBuilding",
                        "admin:dept:list",
                        [
                            (None, "dept-edit", "", "", "", "admin:dept:edit", []),
                        ],
                    ),
                ],
            ),
            (
                "menu.sysData",
                "SysData",
                "",
                "",
                "Coin",
                "",
                [
                    (
                        "menu.flow",
                        "FlowDefs",
                        "/admin/flowdefs",
                        "admin/FlowDefList",
                        "Connection",
                        "admin:flow:list",
                        [
                            (None, "flow-edit", "", "", "", "admin:flow:edit", []),
                        ],
                    ),
                    (
                        "menu.dict",
                        "Dicts",
                        "/admin/dict",
                        "admin/DictList",
                        "Notebook",
                        "admin:dict:list",
                        [
                            (None, "dict-edit", "", "", "", "admin:dict:edit", []),
                        ],
                    ),
                    (
                        "menu.numbering",
                        "NumberRules",
                        "/admin/numbering",
                        "admin/NumberRuleList",
                        "Postcard",
                        "admin:numbering:list",
                        [
                            (None, "numbering-edit", "", "", "", "admin:numbering:edit", []),
                        ],
                    ),
                ],
            ),
            (
                "menu.oaAdmin",
                "OaAdmin",
                "",
                "",
                "Stamp",
                "",
                [
                    (
                        "menu.oaFormDesign",
                        "OaFormDesign",
                        "/admin/oa/forms",
                        "oa/AdminForms",
                        "EditPen",
                        "oa:admin:design",
                        [],
                    ),
                    (
                        "menu.oaFlowStats",
                        "OaFlowStats",
                        "/admin/oa/stats",
                        "oa/AdminStats",
                        "DataLine",
                        "oa:admin:stats",
                        [],
                    ),
                    (
                        "menu.oaFlowHandle",
                        "OaFlowHandle",
                        "/admin/oa/instances",
                        "oa/AdminInstances",
                        "Warning",
                        "oa:admin:handle",
                        [],
                    ),
                ],
            ),
            (
                "menu.sysOps",
                "SysOps",
                "",
                "",
                "Tools",
                "",
                [
                    (
                        "menu.menus",
                        "Menus",
                        "/admin/menus",
                        "admin/MenuList",
                        "Menu",
                        "admin:menu:list",
                        [
                            (None, "menu-create", "", "", "", "admin:menu:create", []),
                            (None, "menu-edit", "", "", "", "admin:menu:edit", []),
                            (None, "menu-delete", "", "", "", "admin:menu:delete", []),
                        ],
                    ),
                    ("menu.audit", "AuditLogs", "/admin/audit", "admin/AuditLogList", "Memo", "admin:audit:list", []),
                    (
                        "menu.settings",
                        "Settings",
                        "/admin/settings",
                        "admin/SystemSettings",
                        "Tools",
                        "admin:setting:list",
                        [
                            (None, "setting-edit", "", "", "", "admin:setting:edit", []),
                        ],
                    ),
                ],
            ),
        ],
    ),
]


def _menu_type(children, comp: str, perm: str, path: str) -> str:
    if perm and not comp and not path:
        return "button"
    if children and not comp:
        return "dir"
    return "menu"


DICTS: dict[str, tuple[str, list[tuple[str, str, str]]]] = {
    # code: (name, [(label, label_en, value)...])
    "customer_type": (
        "客户类型",
        [
            ("企业单位", "Enterprise", "enterprise"),
            ("科研院所", "Research", "research"),
            ("政府机构", "Government", "government"),
            ("其他", "Other", "other"),
        ],
    ),
    "customer_grade": (
        "客户等级",
        [("A级", "Grade A", "A"), ("B级", "Grade B", "B"), ("C级", "Grade C", "C"), ("D级", "Grade D", "D")],
    ),
    "contract_type": (
        "合同类型",
        [
            ("检测校准合同", "Testing & Calibration", "testing"),
            ("销售合同", "Sales", "sales"),
            ("技术服务合同", "Technical Service", "service"),
            ("框架合同", "Framework", "framework"),
        ],
    ),
    "task_type": (
        "任务类型",
        [
            ("工程咨询", "Engineering Consulting", "consulting"),
            ("模型加工中心", "Model Processing Center", "model"),
            ("风洞实验", "Wind Tunnel Test", "windtunnel"),
        ],
    ),
    "biz_block": (
        "业务板块",
        [
            ("工程咨询部", "Consulting Dept", "consulting_dept"),
            ("模型加工中心", "Model Center", "model_center"),
            ("风洞试验部", "Wind Tunnel Dept", "windtunnel_dept"),
        ],
    ),
    "pay_cycle": (
        "结算周期",
        [("月结", "Monthly", "monthly"), ("季结", "Quarterly", "quarterly"), ("一次性", "One-time", "once")],
    ),
    "delivery_way": (
        "交付方式",
        [("报告", "Report", "report"), ("现场交付", "On-site", "onsite"), ("电子交付", "Electronic", "electronic")],
    ),
    "pay_type": (
        "到账方式",
        [
            ("网银", "Bank Transfer", "bank_transfer"),
            ("汇票", "Draft", "draft"),
            ("现金", "Cash", "cash"),
            ("POS", "POS", "pos"),
        ],
    ),
    "oa_category": (
        "OA 表单分类",
        [
            ("请假", "Leave", "leave"),
            ("报销", "Expense", "expense"),
            ("行政", "Administration", "admin"),
            ("其他", "Other", "other"),
        ],
    ),
}

NUMBER_RULES = [
    # 字段序：biz_type, category_key, prefix, year/month/day_digits, seq_len, seq_start, separator, reset_cycle, example
    ("customer", "", "CC", 0, 0, 0, 5, 1, "", "none", "CC00001"),
    ("contract", "", "HT", 4, 2, 2, 4, 1, "", "daily", "HT202610090001"),
    # 分类映射示例：检测校准类合同单独编号
    ("contract", "testing", "JC", 4, 2, 2, 4, 1, "", "daily", "JC202610090001"),
    ("task", "", "RW", 4, 2, 2, 4, 1, "", "daily", "RW202610090001"),
    ("report", "", "BG", 4, 2, 2, 4, 1, "", "daily", "BG202610090001"),
    ("settlement", "", "HK", 4, 2, 2, 4, 1, "", "daily", "HK202610090001"),
    ("payment", "", "DZ", 4, 2, 2, 4, 1, "", "daily", "DZ202610090001"),
    ("oa", "", "OA", 4, 2, 2, 4, 1, "", "daily", "OA202610090001"),
]

DEPTS = [
    ("工程咨询部", "D01"),
    ("模型加工中心", "D02"),
    ("风洞试验部", "D03"),
    ("综合管理部", "D04"),
]


def _seed_menus(db: Session) -> dict[str, int]:
    """菜单树幂等种子：只负责补齐缺失菜单、同步代码耦合字段；结构/排序由菜单管理维护。

    - 缺失的种子菜单：按 MENU_TREE 的 parent_id/sort 插入。
    - 已存在的种子菜单：仅同步 title_key/path/component_key/icon/permission/menu_type，
      不回写 parent_id/sort（管理员在菜单管理里的结构调整与排序得以保留）。
    - 树外的菜单（界面自定义新增）：保留，不做逻辑删除。
    """
    existing = {m.name: m for m in db.scalars(select(Menu).where(Menu.deleted == 0)).all()}
    perm_to_id: dict[str, int] = {}

    def walk(nodes, parent_id: int | None):
        for idx, (title_key, name, path, comp, icon, perm, children) in enumerate(nodes):
            m = existing.get(name)
            if m is None:
                m = Menu(
                    parent_id=parent_id,
                    name=name,
                    title_key=title_key or "",
                    path=path,
                    component_key=comp,
                    icon=icon,
                    permission=perm or "",
                    menu_type=_menu_type(children, comp, perm, path),
                    sort=idx,
                )
                db.add(m)
                db.flush()
                existing[name] = m
            else:
                # 仅同步代码耦合字段；parent_id/sort 由菜单管理维护
                m.title_key = title_key or ""
                m.path = path
                m.component_key = comp
                m.icon = icon
                m.permission = perm or ""
                m.menu_type = _menu_type(children, comp, perm, path)
            if perm:
                perm_to_id[perm] = m.id
            walk(children, m.id)

    walk(MENU_TREE, None)
    return perm_to_id


def _seed_roles(db: Session, perm_to_id: dict[str, int]) -> Role:
    super_role = db.scalar(select(Role).where(Role.code == "super", Role.deleted == 0))
    if not super_role:
        super_role = Role(code="super", name="超级管理员", data_scope="all")
        db.add(super_role)
        db.flush()
    # 超管挂全部菜单
    db.query(RoleMenu).filter(RoleMenu.role_id == super_role.id).delete()
    for mid in perm_to_id.values():
        db.add(RoleMenu(role_id=super_role.id, menu_id=mid))

    biz_role = db.scalar(select(Role).where(Role.code == "biz_user", Role.deleted == 0))
    if not biz_role:
        biz_role = Role(code="biz_user", name="业务人员", data_scope="dept")
        db.add(biz_role)
        db.flush()
    # 每次全量重挂（菜单树是渐进演进的，避免早期创建后漏挂新权限）
    db.query(RoleMenu).filter(RoleMenu.role_id == biz_role.id).delete()
    biz_perms = [
        "workbench:view",
        "crm:customer:list",
        "crm:customer:create",
        "crm:customer:edit",
        "crm:customer:delete",
        "crm:customer:list:export",
        "crm:customer:import",
        "contract:list",
        "contract:create",
        "contract:edit",
        "contract:submit",
        "contract:delete",
        "contract:list:export",
        "task:list",
        "task:create",
        "task:edit",
        "task:assign",
        "task:submit",
        "task:list:export",
        "finance:settlement:list",
        "finance:settlement:create",
        "finance:settlement:export",
        "finance:invoice:apply",
        "finance:invoice:edit",
        "finance:invoice:list",
        "finance:invoice:export",
        "finance:payment:list",
        "finance:payment:create",
        "finance:payment:export",
        "report:list",
        "report:create",
        "report:submit",
        "report:seal",
        "report:export",
        "approval:view",
        "oa:apply",
        "oa:my",
        "oa:related",
    ]
    for p in biz_perms:
        if p in perm_to_id:
            db.add(RoleMenu(role_id=biz_role.id, menu_id=perm_to_id[p]))
    return super_role


def _seed_admin(db: Session, super_role: Role) -> None:
    admin = db.scalar(select(User).where(User.username == "admin", User.deleted == 0))
    if not admin:
        admin = User(
            username="admin",
            password_hash=hash_password("Admin@123456"),
            name="系统管理员",
            dept_name="综合管理部",
            status="enabled",
        )
        db.add(admin)
        db.flush()
    if not db.scalar(select(UserRole).where(UserRole.user_id == admin.id, UserRole.deleted == 0)):
        db.add(UserRole(user_id=admin.id, role_id=super_role.id))

    # 演示审批人（两级审批种子：挂业务角色——有菜单/权限但不超管，审批动作靠待办指派）
    biz_role = db.scalar(select(Role).where(Role.code == "biz_user", Role.deleted == 0)) or super_role
    for username, name in (("manager1", "部门负责人"), ("leader1", "分管领导")):
        u = db.scalar(select(User).where(User.username == username, User.deleted == 0))
        if not u:
            u = User(
                username=username,
                password_hash=hash_password("Test@123456"),
                name=name,
                status="enabled",
            )
            db.add(u)
            db.flush()
        if not db.scalar(select(UserRole).where(UserRole.user_id == u.id, UserRole.deleted == 0)):
            db.add(UserRole(user_id=u.id, role_id=biz_role.id))


def _seed_dicts(db: Session) -> None:
    for code, (name, items) in DICTS.items():
        t = db.scalar(select(DictType).where(DictType.code == code, DictType.deleted == 0))
        if not t:
            t = DictType(code=code, name=name)
            db.add(t)
            db.flush()
        for label, label_en, value in items:
            exists = db.scalar(
                select(DictItem).where(DictItem.dict_type_code == code, DictItem.value == value, DictItem.deleted == 0)
            )
            if not exists:
                db.add(DictItem(dict_type_code=code, label=label, label_en=label_en, value=value, sort=0))


def _seed_number_rules(db: Session) -> None:
    for (
        biz_type,
        category_key,
        prefix,
        year_digits,
        month_digits,
        day_digits,
        seq_len,
        seq_start,
        separator,
        reset_cycle,
        example,
    ) in NUMBER_RULES:
        exists = db.scalar(
            select(NumberRule).where(
                NumberRule.biz_type == biz_type, NumberRule.category_key == category_key, NumberRule.deleted == 0
            )
        )
        if not exists:
            db.add(
                NumberRule(
                    biz_type=biz_type,
                    category_key=category_key,
                    prefix=prefix,
                    year_digits=year_digits,
                    month_digits=month_digits,
                    day_digits=day_digits,
                    seq_len=seq_len,
                    seq_start=seq_start,
                    separator=separator,
                    reset_cycle=reset_cycle,
                    example=example,
                )
            )


def _seed_flows(db: Session) -> None:
    """合同两级审批：部门负责人(manager1) → 分管领导(leader1)；开票申请一级审批：manager1。"""
    _seed_flow(
        db,
        code="contract_approve",
        name="合同审批",
        biz_type="contract",
        remark="默认两级顺序审批",
        nodes=((1, "部门负责人审批", "manager1"), (2, "分管领导审批", "leader1")),
    )
    _seed_flow(
        db,
        code="invoice_apply",
        name="开票申请审批",
        biz_type="invoice",
        remark="开票申请默认一级审批",
        nodes=((1, "部门负责人审批", "manager1"),),
    )
    _seed_flow(
        db,
        code="report_sign",
        name="报告签批",
        biz_type="report",
        remark="报告签批默认一级审批",
        nodes=((1, "部门负责人审批", "manager1"),),
    )
    # OA 示例流程：请假/报销/用章各一条两级审批
    for code, name in (
        ("oa_leave_approve", "OA 请假审批"),
        ("oa_expense_approve", "OA 报销审批"),
        ("oa_seal_approve", "OA 用章审批"),
    ):
        _seed_flow(
            db,
            code=code,
            name=name,
            biz_type="oa",
            remark="OA 默认两级顺序审批",
            nodes=((1, "部门负责人审批", "manager1"), (2, "分管领导审批", "leader1")),
        )


def _seed_flow(db: Session, *, code: str, name: str, biz_type: str, remark: str, nodes) -> None:
    if db.scalar(select(ApprovalDefinition).where(ApprovalDefinition.code == code, ApprovalDefinition.deleted == 0)):
        return
    d = ApprovalDefinition(code=code, name=name, biz_type=biz_type, remark=remark)
    db.add(d)
    db.flush()
    for seq, node_name, username in nodes:
        u = db.scalar(select(User).where(User.username == username, User.deleted == 0))
        if not u:
            continue
        db.add(
            ApprovalNode(
                definition_id=d.id,
                seq=seq,
                node_name=node_name,
                approver_type="USER",
                approver_value=str(u.id),
                approver_name=u.name or u.username,
            )
        )
    db.flush()
    # 线性定义自动生成等价 LogicFlow 图
    d.process_graph = dumps_graph(build_process_graph([n for n in d.nodes if n.deleted == 0]))


def _seed_depts(db: Session) -> None:
    for name, code in DEPTS:
        if not db.scalar(select(Dept).where(Dept.code == code, Dept.deleted == 0)):
            db.add(Dept(name=name, code=code))


# (key, name, category, icon, sort, flow_code, description, fields)
OA_FORMS = [
    (
        "leave_application",
        "请假申请",
        "leave",
        "Calendar",
        1,
        "oa_leave_approve",
        "员工请假申请（事假/病假/年假/调休）",
        [
            {
                "key": "leave_type",
                "label": "请假类型",
                "type": "select",
                "required": True,
                "options": ["事假", "病假", "年假", "调休"],
                "expose_variable": True,
            },
            {"key": "date_range", "label": "起止日期", "type": "daterange", "required": True},
            {"key": "reason", "label": "请假事由", "type": "textarea", "required": True, "maxlength": 500},
        ],
    ),
    (
        "expense_application",
        "报销申请",
        "expense",
        "Money",
        2,
        "oa_expense_approve",
        "费用报销申请（差旅/办公/招待等）",
        [
            {"key": "amount", "label": "报销金额", "type": "money", "required": True, "expose_variable": True},
            {
                "key": "expense_type",
                "label": "费用类别",
                "type": "select",
                "required": True,
                "options": ["差旅", "办公", "招待", "其他"],
            },
            {"key": "reason", "label": "报销事由", "type": "textarea", "required": True, "maxlength": 500},
            {"key": "attachments", "label": "票据附件", "type": "file", "required": False},
        ],
    ),
    (
        "seal_application",
        "用章申请",
        "admin",
        "Stamp",
        3,
        "oa_seal_approve",
        "印章使用申请",
        [
            {
                "key": "seal_type",
                "label": "印章类型",
                "type": "select",
                "required": True,
                "options": ["公章", "合同专用章", "财务专用章", "法人章"],
                "expose_variable": True,
            },
            {"key": "purpose", "label": "用途说明", "type": "textarea", "required": True, "maxlength": 500},
            {"key": "copies", "label": "文件份数", "type": "number", "required": True},
        ],
    ),
]


def _seed_oa_forms(db: Session) -> None:
    """OA 示例表单：published，绑定对应两级审批定义。"""
    from app.modules.oa.models import OaForm  # noqa: PLC0415 避免种子与模块加载循环

    for key, name, category, icon, sort, flow_code, description, fields in OA_FORMS:
        if db.scalar(select(OaForm).where(OaForm.key == key, OaForm.form_version == 1, OaForm.deleted == 0)):
            continue
        flow_id = db.scalar(
            select(ApprovalDefinition.id).where(
                ApprovalDefinition.code == flow_code, ApprovalDefinition.deleted == 0
            )
        )
        db.add(
            OaForm(
                key=key,
                name=name,
                form_version=1,
                status="published",
                category=category,
                icon=icon,
                sort=sort,
                description=description,
                schema_json=json.dumps({"fields": fields}, ensure_ascii=False),
                flow_definition_id=flow_id,
                published_at=datetime.now(),
            )
        )


def main() -> None:
    db: Session = SessionLocal()
    try:
        perm_to_id = _seed_menus(db)
        super_role = _seed_roles(db, perm_to_id)
        _seed_admin(db, super_role)
        _seed_dicts(db)
        _seed_number_rules(db)
        _seed_depts(db)
        _seed_flows(db)
        _seed_oa_forms(db)
        db.commit()
        print(f"seed ok: menus={len(perm_to_id)} perms, dicts={len(DICTS)}, rules={len(NUMBER_RULES)}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

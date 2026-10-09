"""幂等种子：超管/角色/菜单树/字典/编号规则/部门。

用法：uv run python -m app.seeds.init_data
"""

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
from app.modules.approval.models import ApprovalDefinition, ApprovalNode
from app.modules.auth.models import User

# (title_key, name, path, component_key, icon, permission, children)
# children 中 permission 为空串表示纯目录
MENU_TREE = [
    ("menu.workbench", "Workbench", "/workbench", "workbench/Dashboard", "Odometer", "workbench:view", []),
    # 客户/合同/任务与参考系统一致：各自是一级模块，不收拢进"基础信息"目录
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
        "menu.finance",
        "Finance",
        "",
        "",
        "Money",
        "",
        [
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
    ("menu.approval", "ApprovalCenter", "/approval", "approval/TodoList", "Stamp", "approval:view", []),
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
}

NUMBER_RULES = [
    # biz_type, prefix, date_format, seq_len, reset_cycle, example
    ("customer", "CC", "", 5, "none", "CC00001"),
    ("contract", "HT", "%Y%m%d", 4, "daily", "HT202610090001"),
    ("task", "RW", "%Y%m%d", 4, "daily", "RW202610090001"),
    ("report", "BG", "%Y%m%d", 4, "daily", "BG202610090001"),
    ("settlement", "HK", "%Y%m%d", 4, "daily", "HK202610090001"),
    ("payment", "DZ", "%Y%m%d", 4, "daily", "DZ202610090001"),
]

DEPTS = [
    ("工程咨询部", "D01"),
    ("模型加工中心", "D02"),
    ("风洞试验部", "D03"),
    ("综合管理部", "D04"),
]


def _seed_menus(db: Session) -> dict[str, int]:
    """菜单树幂等同步：新增/改父级/按树顺序设 sort；树中消失的菜单逻辑删除（种子即菜单唯一权威来源）。"""
    existing = {m.name: m for m in db.scalars(select(Menu).where(Menu.deleted == 0)).all()}
    perm_to_id: dict[str, int] = {}
    seen: set[str] = set()

    def walk(nodes, parent_id: int | None):
        for idx, (title_key, name, path, comp, icon, perm, children) in enumerate(nodes):
            seen.add(name)
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
                # 结构演进时同步（如"基础信息"拆为一级模块后子菜单上移）
                m.parent_id = parent_id
                m.sort = idx
            if perm:
                perm_to_id[perm] = m.id
            walk(children, m.id)

    walk(MENU_TREE, None)
    for name, m in existing.items():
        if name not in seen:
            m.deleted = 1  # 例：BaseInfo 目录已拆分下线
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
        "finance:payment:list",
        "finance:payment:create",
        "finance:payment:export",
        "approval:view",
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
    for biz_type, prefix, date_format, seq_len, reset_cycle, example in NUMBER_RULES:
        exists = db.scalar(select(NumberRule).where(NumberRule.biz_type == biz_type, NumberRule.deleted == 0))
        if not exists:
            db.add(
                NumberRule(
                    biz_type=biz_type,
                    prefix=prefix,
                    date_format=date_format,
                    seq_len=seq_len,
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


def _seed_depts(db: Session) -> None:
    for name, code in DEPTS:
        if not db.scalar(select(Dept).where(Dept.code == code, Dept.deleted == 0)):
            db.add(Dept(name=name, code=code))


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
        db.commit()
        print(f"seed ok: menus={len(perm_to_id)} perms, dicts={len(DICTS)}, rules={len(NUMBER_RULES)}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

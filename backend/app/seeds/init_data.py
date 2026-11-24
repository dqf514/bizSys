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
from app.modules.hr.models import HrAuthorization, HrAuthorizationEvent
from app.services.numbering import next_no

# (title_key, name, path, component_key, icon, permission, children)
# children 中 permission 为空串表示纯目录
# 入口并入他页、仅作权限载体的隐藏菜单（种子里强制 visible=0）
# PartnerAccounts：并入往来单位（CRM）
HIDDEN_MENUS = {"PartnerAccounts"}

MENU_TREE = [    ("menu.workbench", "Workbench", "/workbench", "workbench/Dashboard", "Odometer", "workbench:view", []),
    # 业务中心：往来单位/合同/任务/报告/项目/财务（财务分组按业务顺序：结算→开票→到账）
    (
        "menu.bizCenter",
        "BizSystem",
        "",
        "",
        "Suitcase",
        "",
        [
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
                    # 工序流转 / 七维分配 / 全过程追溯（B5）
                    (None, "task-process-edit", "", "", "", "task:process:edit", []),
                    (None, "task-assignment-edit", "", "", "", "task:assignment:edit", []),
                    (None, "task-trace-edit", "", "", "", "task:trace:edit", []),
                    # 角色分组可见性（B5 CSV 21）：授予后仅见本组任务
                    (None, "task-group-sim", "", "", "", "task:group:sim", []),
                    (None, "task-group-model", "", "", "", "task:group:model", []),
                    (None, "task-group-test", "", "", "", "task:group:test", []),
                    (None, "task-group-outsource", "", "", "", "task:group:outsource", []),
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
                    (None, "report-seal-apply", "", "", "", "report:seal:apply", []),
                    (None, "report-export", "", "", "", "report:export", []),
                ],
            ),
            (
                "menu.project",
                "Projects",
                "/projects",
                "project/ProjectList",
                "Files",
                "project:list",
                [
                    (None, "project-create", "", "", "", "project:create", []),
                    (None, "project-submit", "", "", "", "project:submit", []),
                    (None, "project-edit", "", "", "", "project:edit", []),
                    (None, "project-delete", "", "", "", "project:delete", []),
                    (None, "project-export", "", "", "", "project:list:export", []),
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
                            (None, "settlement-confirm", "", "", "", "finance:settlement:confirm", []),
                            (None, "invoice-apply", "", "", "", "finance:invoice:apply", []),
                            (None, "invoice-edit", "", "", "", "finance:invoice:edit", []),
                        ],
                    ),
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
                        "menu.financePayment",
                        "FinancePayments",
                        "/finance/payments",
                        "finance/PaymentList",
                        "Wallet",
                        "finance:payment:list",
                        [
                            (None, "payment-create", "", "", "", "finance:payment:create", []),
                            (None, "payment-submit", "", "", "", "finance:payment:submit", []),
                            (None, "payment-export", "", "", "", "finance:payment:export", []),
                        ],
                    ),
                ],
            ),
        ],
    ),
    # 生产资源：设备资产/排程甘特/样品与物料/采购管理/产能看板
    (
        "menu.resources",
        "Resources",
        "",
        "",
        "Cpu",
        "",
        [
            (
                "menu.equipment",
                "Equipment",
                "/assets/equipment",
                "asset/EquipmentList",
                "Monitor",
                "asset:equipment:list",
                [],
            ),
            (
                "menu.schedule",
                "ProductionSchedules",
                "/production/schedule",
                "production/ScheduleBoard",
                "Calendar",
                "production:schedule:list",
                [
                    (None, "ps-create", "", "", "", "production:schedule:create", []),
                    (None, "ps-edit", "", "", "", "production:schedule:edit", []),
                    (None, "ps-delete", "", "", "", "production:schedule:delete", []),
                    (None, "ps-auto", "", "", "", "production:schedule:auto", []),
                    (None, "ps-publish", "", "", "", "production:schedule:publish", []),
                    (None, "ps-export", "", "", "", "production:schedule:list:export", []),
                ],
            ),
            (
                "menu.assetsSamples",
                "AssetsSamples",
                "",
                "",
                "Grid",
                "",
                [
                    (
                        "menu.sample",
                        "Samples",
                        "/task/samples",
                        "task/SampleList",
                        "Box",
                        "task:sample:list",
                        [
                            (None, "sample-export", "", "", "", "task:sample:list:export", []),
                        ],
                    ),
                    (
                        "menu.material",
                        "Materials",
                        "/assets/materials",
                        "asset/MaterialList",
                        "Goods",
                        "asset:material:list",
                        [
                            (None, "mt-create", "", "", "", "asset:material:create", []),
                            (None, "mt-edit", "", "", "", "asset:material:edit", []),
                            (None, "mt-delete", "", "", "", "asset:material:delete", []),
                            (None, "mt-export", "", "", "", "asset:material:export", []),
                        ],
                    ),
                    (
                        "menu.bom",
                        "Bom",
                        "/assets/boms",
                        "asset/BomList",
                        "Files",
                        "asset:bom:list",
                        [
                            (None, "bom-create", "", "", "", "asset:bom:create", []),
                            (None, "bom-edit", "", "", "", "asset:bom:edit", []),
                            (None, "bom-delete", "", "", "", "asset:bom:delete", []),
                            (None, "bom-export", "", "", "", "asset:bom:export", []),
                        ],
                    ),
                ],
            ),
            # 采购管理：申请 →(审批)→ 合同 →(会签)→ 出入库
            (
                "menu.procurement",
                "Procurement",
                "",
                "",
                "ShoppingCart",
                "",
                [
                    (
                        "menu.purchaseRequest",
                        "PurchaseRequests",
                        "/procurement/requests",
                        "procurement/PurchaseRequestList",
                        "ShoppingCart",
                        "procurement:request:list",
                        [
                            (None, "pr-create", "", "", "", "procurement:request:create", []),
                            (None, "pr-edit", "", "", "", "procurement:request:edit", []),
                            (None, "pr-submit", "", "", "", "procurement:request:submit", []),
                            (None, "pr-delete", "", "", "", "procurement:request:delete", []),
                            (None, "pr-export", "", "", "", "procurement:request:list:export", []),
                        ],
                    ),
                    (
                        "menu.purchaseContract",
                        "PurchaseContracts",
                        "/procurement/contracts",
                        "procurement/PurchaseContractList",
                        "Document",
                        "procurement:contract:list",
                        [
                            (None, "pc-create", "", "", "", "procurement:contract:create", []),
                            (None, "pc-edit", "", "", "", "procurement:contract:edit", []),
                            (None, "pc-submit", "", "", "", "procurement:contract:submit", []),
                            (None, "pc-delete", "", "", "", "procurement:contract:delete", []),
                            (None, "pc-export", "", "", "", "procurement:contract:list:export", []),
                        ],
                    ),
                    (
                        "menu.stockOrder",
                        "StockOrders",
                        "/procurement/stock",
                        "procurement/StockOrderList",
                        "Box",
                        "procurement:stock:list",
                        [
                            (None, "so-create", "", "", "", "procurement:stock:create", []),
                            (None, "so-edit", "", "", "", "procurement:stock:edit", []),
                            (None, "so-confirm", "", "", "", "procurement:stock:confirm", []),
                            (None, "so-delete", "", "", "", "procurement:stock:delete", []),
                            (None, "so-export", "", "", "", "procurement:stock:list:export", []),
                        ],
                    ),
                    (
                        "menu.tender",
                        "Tenders",
                        "/procurement/tenders",
                        "procurement/TenderList",
                        "Flag",
                        "procurement:tender:list",
                        [
                            (None, "td-create", "", "", "", "procurement:tender:create", []),
                            (None, "td-edit", "", "", "", "procurement:tender:edit", []),
                            (None, "td-delete", "", "", "", "procurement:tender:delete", []),
                            (None, "td-publish", "", "", "", "procurement:tender:publish", []),
                            (None, "td-terminate", "", "", "", "procurement:tender:terminate", []),
                            (None, "td-review", "", "", "", "procurement:tender:review", []),
                            (None, "td-evaluate", "", "", "", "procurement:tender:evaluate", []),
                            (None, "td-award", "", "", "", "procurement:tender:award", []),
                            (None, "td-export", "", "", "", "procurement:tender:list:export", []),
                        ],
                    ),
                    (
                        "menu.partnerAccount",
                        "PartnerAccounts",
                        "/procurement/partners",
                        "procurement/PartnerAccountList",
                        "User",
                        "procurement:partner:list",
                        [
                            (None, "pa-create", "", "", "", "procurement:partner:create", []),
                            (None, "pa-edit", "", "", "", "procurement:partner:edit", []),
                            (None, "pa-review", "", "", "", "procurement:partner:review", []),
                            (None, "pa-delete", "", "", "", "procurement:partner:delete", []),
                        ],
                    ),
                ],
            ),
            (
                "menu.capacity",
                "ProductionCapacity",
                "/production/capacity",
                "production/CapacityBoard",
                "PieChart",
                "production:capacity:list",
                [],
            ),
        ],
    ),
    # 库存与资产：进出库管理（仓储/库存）+ 资产财务（折旧/处置/工具）
    (
        "menu.stockAsset",
        "StockAsset",
        "",
        "",
        "Coin",
        "",
        [
            (
                "menu.stockMgmt",
                "StockManagement",
                "",
                "",
                "Box",
                "",
                [
                    (
                        "menu.purchaseOrder",
                        "PurchaseOrders",
                        "/asset/purchase-orders",
                        "asset/PurchaseOrderList",
                        "ShoppingCart",
                        "asset:purchaseOrder:list",
                        [
                            (None, "apo-create", "", "", "", "asset:purchaseOrder:create", []),
                            (None, "apo-edit", "", "", "", "asset:purchaseOrder:edit", []),
                            (None, "apo-confirm", "", "", "", "asset:purchaseOrder:confirm", []),
                            (None, "apo-close", "", "", "", "asset:purchaseOrder:close", []),
                            (None, "apo-delete", "", "", "", "asset:purchaseOrder:delete", []),
                            (None, "apo-export", "", "", "", "asset:purchaseOrder:list:export", []),
                        ],
                    ),
                    (
                        "menu.receipt",
                        "Receipts",
                        "/asset/receipts",
                        "asset/ReceiptList",
                        "CircleCheck",
                        "asset:receipt:list",
                        [
                            (None, "rc-create", "", "", "", "asset:receipt:create", []),
                            (None, "rc-edit", "", "", "", "asset:receipt:edit", []),
                            (None, "rc-accept", "", "", "", "asset:receipt:accept", []),
                            (None, "rc-submit", "", "", "", "asset:receipt:submit", []),
                            (None, "rc-delete", "", "", "", "asset:receipt:delete", []),
                            (None, "rc-export", "", "", "", "asset:receipt:list:export", []),
                        ],
                    ),
                    (
                        "menu.warehouse",
                        "Warehouses",
                        "/asset/warehouses",
                        "asset/WarehouseList",
                        "Grid",
                        "asset:warehouse:list",
                        [
                            (None, "wh-create", "", "", "", "asset:warehouse:create", []),
                            (None, "wh-edit", "", "", "", "asset:warehouse:edit", []),
                            (None, "wh-delete", "", "", "", "asset:warehouse:delete", []),
                            (None, "wh-export", "", "", "", "asset:warehouse:list:export", []),
                        ],
                    ),
                    (
                        "menu.inventoryItem",
                        "InventoryItems",
                        "/asset/items",
                        "asset/InventoryItemList",
                        "Goods",
                        "asset:item:list",
                        [
                            (None, "it-create", "", "", "", "asset:item:create", []),
                            (None, "it-edit", "", "", "", "asset:item:edit", []),
                            (None, "it-delete", "", "", "", "asset:item:delete", []),
                            (None, "it-export", "", "", "", "asset:item:list:export", []),
                        ],
                    ),
                    (
                        "menu.stockLedger",
                        "StockLedger",
                        "/asset/ledger",
                        "asset/StockLedgerList",
                        "List",
                        "asset:ledger:list",
                        [
                            (None, "lg-create", "", "", "", "asset:ledger:create", []),
                            (None, "lg-edit", "", "", "", "asset:ledger:edit", []),
                            (None, "lg-delete", "", "", "", "asset:ledger:delete", []),
                            (None, "lg-export", "", "", "", "asset:ledger:list:export", []),
                        ],
                    ),
                    (
                        "menu.stockCount",
                        "StockCounts",
                        "/asset/counts",
                        "asset/StockCountList",
                        "Tickets",
                        "asset:count:list",
                        [
                            (None, "sc-create", "", "", "", "asset:count:create", []),
                            (None, "sc-edit", "", "", "", "asset:count:edit", []),
                            (None, "sc-start", "", "", "", "asset:count:start", []),
                            (None, "sc-finish", "", "", "", "asset:count:finish", []),
                            (None, "sc-delete", "", "", "", "asset:count:delete", []),
                            (None, "sc-export", "", "", "", "asset:count:list:export", []),
                        ],
                    ),
                    (
                        "menu.prototype",
                        "Prototypes",
                        "/asset/prototypes",
                        "asset/PrototypeList",
                        "Monitor",
                        "asset:prototype:list",
                        [
                            (None, "pt-create", "", "", "", "asset:prototype:create", []),
                            (None, "pt-edit", "", "", "", "asset:prototype:edit", []),
                            (None, "pt-delete", "", "", "", "asset:prototype:delete", []),
                            (None, "pt-export", "", "", "", "asset:prototype:list:export", []),
                        ],
                    ),
                    (
                        "menu.prototypeLoan",
                        "PrototypeLoans",
                        "/asset/prototype-loans",
                        "asset/PrototypeLoanList",
                        "SwitchButton",
                        "asset:prototypeLoan:list",
                        [
                            (None, "pl-create", "", "", "", "asset:prototypeLoan:create", []),
                            (None, "pl-edit", "", "", "", "asset:prototypeLoan:edit", []),
                            (None, "pl-return", "", "", "", "asset:prototypeLoan:return", []),
                            (None, "pl-delete", "", "", "", "asset:prototypeLoan:delete", []),
                            (None, "pl-export", "", "", "", "asset:prototypeLoan:list:export", []),
                        ],
                    ),
                ],
            ),
            (
                "menu.assetFinance",
                "AssetFinance",
                "",
                "",
                "Wallet",
                "",
                [
                    (
                        "menu.fixedAsset",
                        "FixedAssets",
                        "/asset/assets",
                        "asset/FixedAssetList",
                        "Money",
                        "asset:asset:list",
                        [
                            (None, "fa-create", "", "", "", "asset:asset:create", []),
                            (None, "fa-edit", "", "", "", "asset:asset:edit", []),
                            (None, "fa-delete", "", "", "", "asset:asset:delete", []),
                            (None, "fa-depreciate", "", "", "", "asset:depreciation:create", []),
                            (None, "fa-depreciation-edit", "", "", "", "asset:depreciation:edit", []),
                            (None, "fa-depreciation-delete", "", "", "", "asset:depreciation:delete", []),
                            (None, "fa-depreciation-list", "", "", "", "asset:depreciation:list", []),
                            (None, "fa-export", "", "", "", "asset:asset:list:export", []),
                        ],
                    ),
                    (
                        "menu.disposal",
                        "Disposals",
                        "/asset/disposals",
                        "asset/DisposalList",
                        "FolderDelete",
                        "asset:disposal:list",
                        [
                            (None, "dp-create", "", "", "", "asset:disposal:create", []),
                            (None, "dp-edit", "", "", "", "asset:disposal:edit", []),
                            (None, "dp-approve", "", "", "", "asset:disposal:approve", []),
                            (None, "dp-submit", "", "", "", "asset:disposal:submit", []),
                            (None, "dp-complete", "", "", "", "asset:disposal:complete", []),
                            (None, "dp-delete", "", "", "", "asset:disposal:delete", []),
                            (None, "dp-export", "", "", "", "asset:disposal:list:export", []),
                        ],
                    ),
                    (
                        "menu.toolLoan",
                        "ToolLoans",
                        "/asset/tools",
                        "asset/ToolList",
                        "Tools",
                        "asset:tool:list",
                        [
                            (None, "tl-create", "", "", "", "asset:tool:create", []),
                            (None, "tl-edit", "", "", "", "asset:tool:edit", []),
                            (None, "tl-delete", "", "", "", "asset:tool:delete", []),
                            (None, "tl-export", "", "", "", "asset:tool:list:export", []),
                            (None, "tll-list", "", "", "", "asset:toolLoan:list", []),
                            (None, "tll-create", "", "", "", "asset:toolLoan:create", []),
                            (None, "tll-edit", "", "", "", "asset:toolLoan:edit", []),
                            (None, "tll-return", "", "", "", "asset:toolLoan:return", []),
                            (None, "tll-delete", "", "", "", "asset:toolLoan:delete", []),
                            (None, "tll-export", "", "", "", "asset:toolLoan:list:export", []),
                        ],
                    ),
                ],
            ),
        ],
    ),
    (
        "menu.salesCenter",
        "SalesSystem",
        "",
        "",
        "Sell",
        "",
        [
            (
                "menu.quotations",
                "Quotations",
                "/sales/quotations",
                "sales/QuotationList",
                "Tickets",
                "sales:quote:list",
                [
                    (None, "quote-create", "", "", "", "sales:quote:create", []),
                    (None, "quote-edit", "", "", "", "sales:quote:edit", []),
                    (None, "quote-submit", "", "", "", "sales:quote:submit", []),
                    (None, "quote-send", "", "", "", "sales:quote:send", []),
                    (None, "quote-feedback", "", "", "", "sales:quote:feedback", []),
                    (None, "quote-to-contract", "", "", "", "sales:quote:to-contract", []),
                    (None, "quote-export", "", "", "", "sales:quote:list:export", []),
                ],
            ),
            (
                "menu.quoteTemplates",
                "QuoteTemplates",
                "/sales/templates",
                "sales/QuoteTemplateList",
                "Collection",
                "sales:template:list",
                [
                    (None, "template-create", "", "", "", "sales:template:create", []),
                    (None, "template-edit", "", "", "", "sales:template:edit", []),
                    (None, "template-publish", "", "", "", "sales:template:publish", []),
                ],
            ),
            (
                "menu.revenue",
                "SalesRevenue",
                "/sales/revenue",
                "sales/RevenueBoard",
                "TrendCharts",
                "sales:revenue:view",
                [],
            ),
        ],
    ),
    # 经营与协同：客户自助/在线委托/知识库
    (
        "menu.collaboration",
        "Collaboration",
        "",
        "",
        "Connection",
        "",
        [
            # 合作方门户是独立认证的独立 shell，菜单只做入口跳转（无前端组件）
            ("menu.portalHome", "PortalHome", "/portal", "", "User", "portal:self:view", []),
            (
                # 在线委托：门户 shell 内的下单页（/portal/orders），不走内部动态路由
                "menu.portalOrders",
                "PortalOrders",
                "/portal/orders",
                "",
                "Tickets",
                "portal:order:create",
                [],
            ),
            (
                # 在线任务委托（B2）：委托单受理与派发
                "menu.entrustList",
                "EntrustList",
                "/task/entrusts",
                "task/EntrustList",
                "Tickets",
                "task:entrust:list",
                [
                    (None, "entrust-create", "", "", "", "task:entrust:create", []),
                    (None, "entrust-review", "", "", "", "task:entrust:review", []),
                    (None, "entrust-dispatch", "", "", "", "task:entrust:dispatch", []),
                    (None, "entrust-export", "", "", "", "task:entrust:export", []),
                ],
            ),
            (
                # 客户自助账号（B2）：注册审核、绑定往来单位与客户经理
                "menu.customerAccounts",
                "CustomerAccounts",
                "/crm/accounts",
                "crm/CustomerAccountList",
                "User",
                "crm:account:list",
                [
                    (None, "account-review", "", "", "", "crm:account:review", []),
                    (None, "account-edit", "", "", "", "crm:account:edit", []),
                ],
            ),
            (
                # 客户方人员备案（B2）：外来试验人员 / 跟踪支持人员登记审核
                "menu.partnerStaff",
                "PartnerStaff",
                "/crm/partner-staffs",
                "crm/PartnerStaffList",
                "Avatar",
                "crm:staff:list",
                [
                    (None, "staff-create", "", "", "", "crm:staff:create", []),
                    (None, "staff-review", "", "", "", "crm:staff:review", []),
                    (None, "staff-edit", "", "", "", "crm:staff:edit", []),
                    (None, "staff-export", "", "", "", "crm:staff:export", []),
                ],
            ),
            (
                "menu.knowledge",
                "KnowledgeBase",
                "/ai/knowledge",
                "ai/KnowledgeAsk",
                "Collection",
                "ai:knowledge:view",
                [],
            ),
        ],
    ),
    (
        "menu.hrCenter",
        "HrSystem",
        "",
        "",
        "Avatar",
        "",
        [
            (
                "menu.timesheetFill",
                "TimesheetFill",
                "/hr/timesheets",
                "hr/TimesheetFill",
                "AlarmClock",
                "hr:timesheet:list",
                [
                    (None, "timesheet-create", "", "", "", "hr:timesheet:create", []),
                    (None, "timesheet-submit", "", "", "", "hr:timesheet:submit", []),
                    (None, "timesheet-export", "", "", "", "hr:timesheet:list:export", []),
                ],
            ),
            (
                "menu.timesheetStats",
                "TimesheetStats",
                "/hr/timesheet-stats",
                "hr/TimesheetStats",
                "PieChart",
                "hr:timesheet:stats",
                [
                    (None, "timesheet-stats-export", "", "", "", "hr:timesheet:stats:export", []),
                ],
            ),
            (
                # 组织架构（B10-1 / HR L1）：场所 → 部门树 + 岗位清单 + 变更轨迹。
                # 部门的**写入口仍是** /admin/depts（sys_dept 是全站唯一部门表），
                # 本菜单只承载 `hr:org:list` 权限点与前端入口。
                "menu.hrOrg",
                "HrOrg",
                "/hr/org",
                "hr/OrgStructureList",
                "OfficeBuilding",
                "hr:org:list",
                [],
            ),
            (
                # 岗位与说明书（B10-1）：岗位职责 / 任职要求 / 关键岗位标记 / A、B 角
                "menu.hrPosition",
                "HrPosition",
                "/hr/positions",
                "hr/PositionList",
                "Position",
                "hr:position:list",
                [
                    (None, "hr-position-create", "", "", "", "hr:position:create", []),
                    (None, "hr-position-edit", "", "", "", "hr:position:edit", []),
                ],
            ),
            (
                # 人员档案（B10-1）：员工一人一档（证件号加密，出参掩码）
                "menu.staff",
                "Staff",
                "/hr/staff",
                "hr/StaffList",
                "UserFilled",
                "hr:staff:list",
                [
                    (None, "hr-staff-create", "", "", "", "hr:staff:create", []),
                    (None, "hr-staff-edit", "", "", "", "hr:staff:edit", []),
                    (None, "hr-staff-export", "", "", "", "hr:staff:export", []),
                    (None, "hr-staff-idno", "", "", "", "hr:staff:idno", []),
                ],
            ),
            (
                # 人事事务（B10-1）：入职 / 调岗 / 离职 / 返聘 + 代理人（AB 角）
                "menu.hrEmployment",
                "HrEmployment",
                "/hr/employments",
                "hr/PersonnelAffairsList",
                "Switch",
                "hr:employment:list",
                [
                    (None, "hr-employment-create", "", "", "", "hr:employment:create", []),
                    (None, "hr-employment-edit", "", "", "", "hr:employment:edit", []),
                    (None, "hr-employment-submit", "", "", "", "hr:employment:submit", []),
                    (None, "hr-employment-effect", "", "", "", "hr:employment:effect", []),
                    (None, "hr-delegate-list", "", "", "", "hr:delegate:list", []),
                    (None, "hr-delegate-edit", "", "", "", "hr:delegate:edit", []),
                ],
            ),
            (
                # 人员授权台账（B9-C3 / HR L2 授权管理）：合规 3.1「人员能力」的控制点
                "menu.authorization",
                "Authorizations",
                "/hr/authorizations",
                "hr/AuthorizationList",
                "Key",
                "hr:authorization:list",
                [
                    (None, "authorization-create", "", "", "", "hr:authorization:create", []),
                    (None, "authorization-edit", "", "", "", "hr:authorization:edit", []),
                    (None, "authorization-submit", "", "", "", "hr:authorization:submit", []),
                    (None, "authorization-approve", "", "", "", "hr:authorization:approve", []),
                    (None, "authorization-activate", "", "", "", "hr:authorization:activate", []),
                    (None, "authorization-revoke", "", "", "", "hr:authorization:revoke", []),
                    (None, "authorization-export", "", "", "", "hr:authorization:export", []),
                ],
            ),
        ],
    ),
    (
        "menu.workflowOffice",
        "OaSystem",
        "",
        "",
        "Stamp",
        "",
        [
            ("menu.oaApply", "OaApply", "/oa/apply", "oa/ApplyForm", "Promotion", "oa:apply", []),
            ("menu.oaMy", "OaMy", "/oa/my", "oa/MyInstances", "Document", "oa:my", []),
            ("menu.oaRelated", "OaRelated", "/oa/related", "oa/Related", "Bell", "oa:related", []),
            ("menu.oaStats", "OaStats", "/oa/stats", "oa/StatsBoard", "DataAnalysis", "oa:stats:view", []),
            # 作业申请（叉车/吊装/高处/动火）：权限码独立，避免与新申请的 oa:apply 撞车
            ("menu.workApply", "WorkApply", "/oa/work-apply", "oa/WorkApplyList", "Tools", "oa:workapply:list", []),
            # 流程待办：原顶层隐藏菜单，解除隐藏并迁入「流程与办公」
            ("menu.approval", "ApprovalCenter", "/approval", "approval/TodoList", "Stamp", "approval:view", []),
            ("menu.messages", "Messages", "/messages", "message/MessageCenter", "Bell", "message:center:view", []),
        ],
    ),
    # 访客与安全：访客登记/区域权限/保密协议/安全巡检
    (
        "menu.visitorSafety",
        "VisitorSafety",
        "",
        "",
        "Lock",
        "",
        [
            (
                "menu.visit",
                "Visits",
                "/visitor/visits",
                "visitor/VisitList",
                "User",
                "visitor:visit:list",
                [
                    (None, "visit-create", "", "", "", "visitor:visit:create", []),
                    (None, "visit-review", "", "", "", "visitor:visit:review", []),
                    (None, "visit-checkin", "", "", "", "visitor:visit:checkin", []),
                    (None, "visit-export", "", "", "", "visitor:visit:export", []),
                ],
            ),
            (
                "menu.zone",
                "VisitorZones",
                "/visitor/zones",
                "visitor/ZoneList",
                "OfficeBuilding",
                "visitor:zone:list",
                [
                    (None, "zone-edit", "", "", "", "visitor:zone:edit", []),
                ],
            ),
            (
                "menu.nda",
                "VisitorNda",
                "/visitor/nda",
                "visitor/NdaList",
                "Memo",
                "visitor:nda:list",
                [
                    (None, "nda-sign", "", "", "", "visitor:nda:sign", []),
                ],
            ),
            (
                # 通行凭证（门禁 / 闸机 / 梯控核验）
                "menu.visitorCredential",
                "VisitorCredentials",
                "/visitor/credentials",
                "visitor/CredentialList",
                "Key",
                "visitor:credential:list",
                [
                    (None, "credential-verify", "", "", "", "visitor:credential:verify", []),
                    (None, "credential-edit", "", "", "", "visitor:credential:edit", []),
                ],
            ),
            (
                # 黑名单（闯入 / 尾随 / 失信人员禁止入内）
                "menu.visitorBlacklist",
                "VisitorBlacklist",
                "/visitor/blacklist",
                "visitor/BlacklistList",
                "Warning",
                "visitor:blacklist:list",
                [
                    (None, "blacklist-edit", "", "", "", "visitor:blacklist:edit", []),
                ],
            ),
            (
                # 合规审计日志（只读 + 应急报表导出，保留期 ≥180 天）
                "menu.visitorAudit",
                "VisitorAuditLogs",
                "/visitor/access-logs",
                "visitor/AccessLogList",
                "Document",
                "visitor:audit:list",
                [
                    (None, "audit-export", "", "", "", "visitor:audit:export", []),
                    (None, "audit-report", "", "", "", "visitor:audit:report", []),
                ],
            ),
            (
                # 样品 / 样车交接联动
                "menu.visitorHandover",
                "VisitorHandovers",
                "/visitor/handovers",
                "visitor/HandoverList",
                "Box",
                "visitor:handover:list",
                [
                    (None, "handover-create", "", "", "", "visitor:handover:create", []),
                ],
            ),
            (
                # 预警（滞留 / 闯入 / 尾随 / 越权）
                "menu.visitorAlert",
                "VisitorAlerts",
                "/visitor/alerts",
                "visitor/AlertList",
                "AlarmClock",
                "visitor:alert:list",
                [
                    (None, "alert-handle", "", "", "", "visitor:alert:handle", []),
                ],
            ),
            (
                "menu.inspection",
                "SafetyInspections",
                "/safety/inspections",
                "safety/InspectionList",
                "FirstAidKit",
                "safety:inspection:list",
                [],
            ),
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
                            # OA 表单设计并入统一流程设计页（页签），权限点挂这里供角色分配
                            (None, "oa-design", "", "", "", "oa:admin:design", []),
                        ],
                    ),
                    (
                        # E1：流程包 JSON 化导入导出（批量迁移用）
                        "menu.flowPackages",
                        "FlowPackageList",
                        "/admin/flowpackages",
                        "admin/FlowPackageList",
                        "CopyDocument",
                        "admin:flow:export",
                        [
                            (None, "flow-package-import", "", "", "", "admin:flow:import", []),
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
                        "menu.maintenance",
                        "Maintenance",
                        "/admin/maintenance",
                        "admin/Maintenance",
                        "FirstAidKit",
                        "admin:backup:view",
                        [
                            (None, "backup-manage", "", "", "", "admin:backup:manage", []),
                            (None, "maintenance-purge", "", "", "", "admin:maintenance:purge", []),
                            # 记录时间修正：高危，仅超管（biz_perms 不含此项）
                            (None, "maintenance-retime", "", "", "", "admin:maintenance:retime", []),
                        ],
                    ),
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
                    (
                        "menu.automation",
                        "Automation",
                        "/admin/automation",
                        "admin/AutomationSettings",
                        "Switch",
                        "admin:automation:list",
                        [
                            (None, "automation-edit", "", "", "", "admin:automation:edit", []),
                        ],
                    ),
                    # 变更日志（Keep a Changelog）：数据源 = 仓库根 CHANGELOG.md
                    (
                        "menu.changelog",
                        "Changelog",
                        "/admin/changelog",
                        "admin/ChangelogList",
                        "Tickets",
                        "admin:changelog:list",
                        [],
                    ),
                ],
            ),
            (
                "menu.aiCenter",
                "AiCenter",
                "",
                "",
                "MagicStick",
                "",
                [
                    (
                        "menu.aiUsage",
                        "AiUsage",
                        "/admin/ai/usage",
                        "admin/AiUsage",
                        "DataAnalysis",
                        "admin:ai:usage",
                        [
                            (None, "ai-usage-export", "", "", "", "admin:ai:usage:export", []),
                        ],
                    ),
                    (
                        "menu.aiSettings",
                        "AiSettings",
                        "/admin/ai/settings",
                        "admin/AiSettings",
                        "Operation",
                        "admin:ai:settings",
                        [],
                    ),
                    (
                        "menu.aiKnowledge",
                        "AiKnowledge",
                        "/admin/ai/knowledge",
                        "admin/AiKnowledge",
                        "Collection",
                        "admin:ai:knowledge",
                        [],
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


DICTS: dict[str, tuple[str, list[tuple[str, ...]]]] = {
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
            ("CFD仿真", "CFD Simulation", "cfd"),
            ("委外测试", "Outsourced Testing", "outsource"),
        ],
    ),
    "entrust_type": (
        "委托类型",
        [
            ("仿真分析", "Simulation", "sim"),
            ("模型制作", "Model Making", "model"),
            ("试验测试", "Test", "test"),
            ("委外测试", "Outsourced Test", "outsource"),
        ],
    ),
    # —— B5 任务扩展字典 ——
    "task_role_group": (
        "任务角色分组",
        [
            ("仿真", "Simulation", "sim"),
            ("模型", "Model", "model"),
            ("试验", "Test", "test"),
            ("委外", "Outsourced", "outsource"),
        ],
    ),
    "task_process": (
        "任务工序",
        [
            ("需求评审", "Requirement Review", "demand_review"),
            ("方案设计", "Scheme Design", "design"),
            ("油泥制作", "Clay Model Making", "clay_model"),
            ("CNC加工", "CNC Machining", "cnc"),
            ("表面处理", "Surface Treatment", "surface"),
            ("模型装配", "Model Assembly", "assembly"),
            ("风洞试验", "Wind Tunnel Test", "wind_tunnel"),
            ("CFD仿真", "CFD Simulation", "cfd"),
            ("检测检验", "Inspection", "inspection"),
            ("报告编制", "Report Writing", "report"),
            ("委外加工", "Outsourced Machining", "outsource"),
            ("验收交付", "Acceptance & Delivery", "accept"),
        ],
    ),
    "task_dimension": (
        "七维资源维度",
        [
            ("人", "Personnel", "person"),
            ("机", "Equipment", "equipment"),
            ("料", "Material", "material"),
            ("法", "Method", "method"),
            ("环", "Environment", "env"),
            ("测", "Test Condition", "test"),
            ("安", "Safety", "safety"),
            ("样车", "Vehicle", "vehicle"),
        ],
    ),
    # 任务类型 → 默认负责人角色（extra = 角色编码）
    "task_owner_rule": (
        "任务默认负责人规则",
        [
            ("CFD仿真", "CFD Simulation", "cfd", "sim_engineer"),
            ("风洞实验", "Wind Tunnel Test", "windtunnel", "test_engineer"),
            ("模型加工中心", "Model Processing Center", "model", "model_engineer"),
            ("委外测试", "Outsourced Testing", "outsource", "outsource_specialist"),
        ],
    ),
    "partner_staff_type": (
        "外来人员类型",
        [
            ("试验人员", "Test Engineer", "tester"),
            ("支持人员", "Support Staff", "support"),
            ("见证专家", "Witness Expert", "witness"),
            ("厂商工程师", "Vendor Engineer", "vendor"),
        ],
    ),
    "visitor_type": (
        "访客类型",
        [
            ("客户", "Customer", "customer"),
            ("监管评审", "Regulator", "regulator"),
            ("供应商", "Supplier", "supplier"),
            ("快递", "Courier", "courier"),
            ("临时工", "Temp Worker", "temp"),
            ("外包维修", "Outsourced", "outsourced"),
            ("合作方", "Partner", "partner"),
            ("本单位员工", "Internal Staff", "staff"),
        ],
    ),
    "visitor_source": (
        "预约来源",
        [
            ("网页预约", "Web", "web"),
            ("微信预约", "WeChat", "wechat"),
            ("小程序预约", "Mini Program", "miniprogram"),
            ("员工邀请", "Staff Invite", "invite"),
            ("前台现场登记", "Front Desk", "onsite"),
            ("客户自助", "Customer Portal", "partner"),
        ],
    ),
    "visitor_zone_type": (
        "区域类型",
        [
            ("公共接待区", "Public Area", "public"),
            ("访客接待区", "Welcome Area", "welcome"),
            ("样车接收区", "Sample Receiving", "sample"),
            ("试验区", "Test Area", "test"),
            ("准备区", "Preparation Area", "prepare"),
            ("生产加工区", "Production Area", "production"),
            ("工具仪器间", "Tool Room", "tool"),
            ("数据机房", "Data Center", "datacenter"),
        ],
    ),
    "biz_block": (
        "业务板块",
        [
            ("工程咨询部", "Consulting Dept", "consulting_dept"),
            ("模型加工中心", "Model Center", "model_center"),
            ("风洞试验部", "Wind Tunnel Dept", "windtunnel_dept"),
            ("CFD仿真中心", "CFD Simulation Center", "cfd"),
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
            # E1：企业微信移植的 6 个模板分组
            ("业务管理", "Tickets", "wc_biz"),
            ("财务", "Money", "wc_fin"),
            ("行政（企微）", "Stamp", "wc_admin"),
            ("假勤", "Calendar", "wc_att"),
            ("人事", "User", "wc_hr"),
            ("其他（企微）", "Document", "wc_other"),
        ],
    ),
    "purchase_method": (
        "采购方式",
        [
            ("询价", "Inquiry", "inquiry"),
            ("单一来源", "Single Source", "single_source"),
            ("竞争性谈判", "Competitive Negotiation", "negotiation"),
            ("公开招标", "Public Bidding", "public_bid"),
        ],
    ),
    "supply_category": (
        "供应分类",
        [
            ("设备", "Equipment", "equipment"),
            ("耗材", "Consumable", "consumable"),
            ("服务", "Service", "service"),
            ("其他", "Other", "other"),
        ],
    ),
    "warehouse": (
        "仓库",
        [("一号仓库", "Warehouse 1", "wh1"), ("二号仓库", "Warehouse 2", "wh2")],
    ),
    "tender_method": (
        "招标方式",
        [("公开招标", "Public Tender", "public"), ("邀请招标", "Invited Tender", "invite")],
    ),
    "partner_attachment_category": (
        "往来单位附件分类",
        [
            ("营业执照", "Business License", "license"),
            ("资质证明", "Qualification", "qualification"),
            ("合同文件", "Contract File", "contract"),
            ("其他", "Other", "other"),
        ],
    ),
    "stock_category": (
        "存货类别",
        [
            ("原材料", "Raw Material", "raw"),
            ("备品备件", "Spare Part", "spare"),
            ("耗材", "Consumable", "consumable"),
            ("包装材料", "Packing Material", "packing"),
            ("其他", "Other", "other"),
        ],
    ),
    "stock_reason": (
        "出入库原因",
        [
            ("采购入库", "Purchase", "purchase"),
            ("验收入库", "Receipt", "receipt"),
            ("盘点调整", "Stock Count", "count"),
            ("领用出库", "Borrow", "borrow"),
            ("归还入库", "Return", "return"),
            ("报废出库", "Scrap", "scrap"),
            ("手工登记", "Manual", "manual"),
        ],
    ),
    "prototype_kind": (
        "样件类型",
        [
            ("样车", "Vehicle", "vehicle"),
            ("样件", "Part", "part"),
            ("样机", "Prototype", "prototype"),
            ("其他", "Other", "other"),
        ],
    ),
    "asset_category": (
        "资产类别",
        [
            ("设备", "Equipment", "equipment"),
            ("车辆", "Vehicle", "vehicle"),
            ("家具", "Furniture", "furniture"),
            ("仪器仪表", "Instrument", "instrument"),
            ("软件", "Software", "software"),
            ("其他", "Other", "other"),
        ],
    ),
    "depreciation_method": (
        "折旧方法",
        [
            ("平均年限法", "Straight Line", "straight_line"),
            ("双倍余额递减法", "Double Declining", "double_declining"),
            ("年数总和法", "Sum of Years", "sum_of_years"),
        ],
    ),
    "disposal_type": (
        "处置方式",
        [
            ("报废", "Scrap", "scrap"),
            ("出售", "Sell", "sell"),
            ("捐赠", "Donate", "donate"),
            ("调拨", "Transfer", "transfer"),
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
    ("entrust", "", "WT", 4, 2, 2, 4, 1, "", "daily", "WT202611210001"),
    ("report", "", "BG", 4, 2, 2, 4, 1, "", "daily", "BG202610090001"),
    ("settlement", "", "HK", 4, 2, 2, 4, 1, "", "daily", "HK202610090001"),
    ("payment", "", "DZ", 4, 2, 2, 4, 1, "", "daily", "DZ202610090001"),
    ("oa", "", "OA", 4, 2, 2, 4, 1, "", "daily", "OA202610090001"),
    ("purchase_request", "", "PR", 4, 2, 2, 4, 1, "", "daily", "PR202610090001"),
    ("purchase_contract", "", "CG", 4, 2, 2, 4, 1, "", "daily", "CG202610090001"),
    ("stock_in", "", "RK", 4, 2, 2, 4, 1, "", "daily", "RK202610090001"),
    ("stock_out", "", "CK", 4, 2, 2, 4, 1, "", "daily", "CK202610090001"),
    ("tender", "", "ZB", 4, 2, 2, 4, 1, "", "daily", "ZB202610090001"),
    ("quotation", "", "BJ", 4, 2, 2, 4, 1, "", "daily", "BJ202610090001"),
    # 资产与库存域单号
    ("asset_purchase_order", "", "PO", 4, 2, 2, 4, 1, "", "daily", "PO202611210001"),
    ("asset_receipt", "", "YS", 4, 2, 2, 4, 1, "", "daily", "YS202611210001"),
    ("asset_count", "", "PD", 4, 2, 2, 4, 1, "", "daily", "PD202611210001"),
    ("asset_prototype_loan", "", "LJ", 4, 2, 2, 4, 1, "", "daily", "LJ202611210001"),
    ("asset_tool_loan", "", "LY", 4, 2, 2, 4, 1, "", "daily", "LY202611210001"),
    ("asset_disposal", "", "CZ", 4, 2, 2, 4, 1, "", "daily", "CZ202611210001"),
    ("asset_bom", "", "BM", 4, 2, 2, 4, 1, "", "daily", "BM202611210001"),
    # 访客与安全域单号
    ("visit", "", "VT", 4, 2, 2, 4, 1, "", "daily", "VT202611210001"),
    ("visitor_credential", "", "VC", 4, 2, 2, 4, 1, "", "daily", "VC202611210001"),
    ("visitor_handover", "", "SH", 4, 2, 2, 4, 1, "", "daily", "SH202611210001"),
    ("visitor_nda", "", "ND", 4, 2, 2, 4, 1, "", "daily", "ND202611210001"),
    # 生产排程与项目域单号（B5）
    ("production_plan", "", "PL", 4, 2, 2, 4, 1, "", "daily", "PL202611210001"),
    ("production_schedule", "", "SC", 4, 2, 2, 4, 1, "", "daily", "SC202611210001"),
    ("project", "", "PJ", 4, 2, 2, 4, 1, "", "daily", "PJ202611210001"),
    # 人事行政域单号（B9-C3 人员授权）
    ("hr_authorization", "", "AU", 4, 2, 2, 4, 1, "", "daily", "AU202611230001"),
    # 人事事务单号（B10-1 入职/调岗/离职/返聘）
    ("hr_employment", "", "EM", 4, 2, 2, 4, 1, "", "daily", "EM202611230001"),
]

# (name, code, parent_code)：总经办为根，演示上下级多级审批
DEPTS = [
    ("总经办", "D00", None),
    ("工程咨询部", "D01", "D00"),
    ("模型加工中心", "D02", "D00"),
    ("风洞试验部", "D03", "D00"),
    ("综合管理部", "D04", "D00"),
]


def _seed_menus(db: Session) -> dict[str, int]:
    """菜单树幂等种子：只负责补齐缺失菜单、同步代码耦合字段；结构/排序由菜单管理维护。

    - 缺失的种子菜单：按 MENU_TREE 的 parent_id/sort 插入。
    - 已存在的种子菜单：仅同步 title_key/path/component_key/icon/permission/menu_type，
      不回写 parent_id/sort（管理员在菜单管理里的结构调整与排序得以保留）。
    - 树外的菜单（界面自定义新增）：保留，不做逻辑删除。
    - HIDDEN_MENUS 中的菜单强制隐藏（visible=0）：入口并入其他页面，但权限点仍由菜单承载。
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
                    visible=0 if name in HIDDEN_MENUS else 1,
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
                if name in HIDDEN_MENUS:
                    m.visible = 0
            if perm:
                if perm in perm_to_id:
                    # 权限码一菜单一归属：撞车会让后者顶掉前者，超管/角色都拿不到被顶掉的菜单
                    print(
                        f"[seed] WARN duplicate permission {perm!r} on menu {name!r}, "
                        f"{m.id} shadows {perm_to_id[perm]}"
                    )
                perm_to_id[perm] = m.id
            walk(children, m.id)

    walk(MENU_TREE, None)
    return perm_to_id


# 访客与安全域（B3）权限点集合 —— 安保员角色整域授权
VISITOR_PERMS = [
    "visitor:visit:list",
    "visitor:visit:create",
    "visitor:visit:review",
    "visitor:visit:checkin",
    "visitor:visit:export",
    "visitor:zone:list",
    "visitor:zone:edit",
    "visitor:nda:list",
    "visitor:nda:sign",
    "visitor:credential:list",
    "visitor:credential:verify",
    "visitor:credential:edit",
    "visitor:blacklist:list",
    "visitor:blacklist:edit",
    "visitor:audit:list",
    "visitor:audit:export",
    "visitor:audit:report",
    "visitor:handover:list",
    "visitor:handover:create",
    "visitor:alert:list",
    "visitor:alert:handle",
]


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
        "task:sample:list",
        "task:sample:list:export",
        # —— 任务扩展（B5）：工序流转 / 七维分配 / 全过程追溯 ——
        "task:process:edit",
        "task:assignment:edit",
        "task:trace:edit",
        "finance:settlement:list",
        "finance:settlement:create",
        "finance:settlement:export",
        "finance:settlement:confirm",
        "finance:invoice:apply",
        "finance:invoice:edit",
        "finance:invoice:list",
        "finance:invoice:export",
        "finance:payment:list",
        "finance:payment:create",
        "finance:payment:submit",
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
        "procurement:request:list",
        "procurement:request:create",
        "procurement:request:edit",
        "procurement:request:submit",
        "procurement:request:delete",
        "procurement:request:list:export",
        "procurement:contract:list",
        "procurement:contract:create",
        "procurement:contract:edit",
        "procurement:contract:submit",
        "procurement:contract:delete",
        "procurement:contract:list:export",
        "procurement:stock:list",
        "procurement:stock:create",
        "procurement:stock:edit",
        "procurement:stock:confirm",
        "procurement:stock:delete",
        "procurement:stock:list:export",
        "procurement:tender:list",
        "procurement:tender:create",
        "procurement:tender:edit",
        "procurement:tender:delete",
        "procurement:tender:publish",
        "procurement:tender:terminate",
        "procurement:tender:review",
        "procurement:tender:evaluate",
        "procurement:tender:award",
        "procurement:tender:list:export",
        "procurement:partner:list",
        "procurement:partner:create",
        "procurement:partner:edit",
        "procurement:partner:review",
        "procurement:partner:delete",
        "hr:timesheet:list",
        "hr:timesheet:create",
        "hr:timesheet:submit",
        "hr:timesheet:list:export",
        # 人员授权台账（B9-C3）：业务角色只读反查（授权管理属人事/质量职责，与检测岗分离）
        "hr:authorization:list",
        "sales:quote:list",
        "sales:quote:create",
        "sales:quote:edit",
        "sales:quote:submit",
        "sales:quote:send",
        "sales:quote:feedback",
        "sales:quote:to-contract",
        "sales:quote:list:export",
        # —— 新导航分区与骨架功能（2026-11 需求批次 B1）——
        "message:center:view",
        "ai:knowledge:view",
        "project:list",
        "project:create",
        "project:submit",
        "project:edit",
        "project:delete",
        "project:list:export",
        "asset:equipment:list",
        "asset:material:list",
        "asset:receipt:submit",
        "asset:disposal:submit",
        "report:seal:apply",
        "production:schedule:list",
        "production:schedule:create",
        "production:schedule:edit",
        "production:schedule:delete",
        "production:schedule:auto",
        "production:schedule:publish",
        "production:schedule:list:export",
        "production:capacity:list",
        "sales:revenue:view",
        "hr:staff:list",
        "oa:workapply:list",
        "portal:self:view",
        "portal:order:create",
        # —— 客户自助体系（B2）——
        "task:entrust:list",
        "task:entrust:create",
        "task:entrust:review",
        "task:entrust:dispatch",
        "task:entrust:export",
        "crm:account:list",
        "crm:account:review",
        "crm:account:edit",
        "crm:staff:list",
        "crm:staff:create",
        "crm:staff:review",
        "crm:staff:edit",
        "crm:staff:export",
        # 访客与安全域（安防/合规）不挂业务角色，见下方 security_officer 角色
    ]
    for p in biz_perms:
        if p in perm_to_id:
            db.add(RoleMenu(role_id=biz_role.id, menu_id=perm_to_id[p]))
    # 资产与库存域整域授权（按前缀批量，避免新增页面漏挂权限）
    granted = set(biz_perms)
    for perm, mid in perm_to_id.items():
        if perm.startswith("asset:") and perm not in granted:
            db.add(RoleMenu(role_id=biz_role.id, menu_id=mid))

    # 业务分组角色（B5 CSV 21）：仿真 / 模型 / 试验 / 委外
    # 授予 task:group:<组> 后，该角色用户只能看到并操作本组任务
    for code, name, group in (
        ("sim_engineer", "仿真工程师", "sim"),
        ("model_engineer", "模型工程师", "model"),
        ("test_engineer", "试验工程师", "test"),
        ("outsource_specialist", "委外专员", "outsource"),
    ):
        grp_role = db.scalar(select(Role).where(Role.code == code, Role.deleted == 0))
        if not grp_role:
            grp_role = Role(code=code, name=name, data_scope="dept")
            db.add(grp_role)
            db.flush()
        db.query(RoleMenu).filter(RoleMenu.role_id == grp_role.id).delete()
        for p in (
            "task:list",
            "task:edit",
            "task:assign",
            "task:process:edit",
            "task:assignment:edit",
            "task:trace:edit",
            f"task:group:{group}",
            "report:list",
            "workbench:view",
        ):
            if p in perm_to_id:
                db.add(RoleMenu(role_id=grp_role.id, menu_id=perm_to_id[p]))

    # 安保员（访客与安全域 B3）：安防/合规职责与业务岗分离，整域最小权限授权
    security_role = db.scalar(select(Role).where(Role.code == "security_officer", Role.deleted == 0))
    if not security_role:
        security_role = Role(code="security_officer", name="安保员", data_scope="all")
        db.add(security_role)
        db.flush()
    db.query(RoleMenu).filter(RoleMenu.role_id == security_role.id).delete()
    for p in VISITOR_PERMS:
        if p in perm_to_id:
            db.add(RoleMenu(role_id=security_role.id, menu_id=perm_to_id[p]))

    # 人事管理员（B9-C3 人员授权台账）：授权的申请/生效/撤销由人事把关，
    # 与检测岗职责分离 —— 检测员不持有授权管理权限。
    hr_role = db.scalar(select(Role).where(Role.code == "hr_manager", Role.deleted == 0))
    if not hr_role:
        hr_role = Role(code="hr_manager", name="人事管理员", data_scope="all")
        db.add(hr_role)
        db.flush()
    db.query(RoleMenu).filter(RoleMenu.role_id == hr_role.id).delete()
    for p in (
        "hr:authorization:list",
        "hr:authorization:create",
        "hr:authorization:edit",
        "hr:authorization:submit",
        "hr:authorization:approve",
        "hr:authorization:activate",
        "hr:authorization:revoke",
        "hr:authorization:export",
        "hr:timesheet:list",
        "hr:timesheet:stats",
        # —— B10-1 组织架构 / 员工主数据 / 人事事务 ——
        "hr:org:list",
        "hr:position:list",
        "hr:position:create",
        "hr:position:edit",
        "hr:staff:list",
        "hr:staff:create",
        "hr:staff:edit",
        "hr:staff:export",
        "hr:staff:idno",
        "hr:employment:list",
        "hr:employment:create",
        "hr:employment:edit",
        "hr:employment:submit",
        "hr:employment:effect",
        "hr:delegate:list",
        "hr:delegate:edit",
        # 部门树由人事维护 —— 因此给到 admin:dept 的查看/编辑权
        "admin:dept:list",
        "admin:dept:edit",
    ):
        if p in perm_to_id:
            db.add(RoleMenu(role_id=hr_role.id, menu_id=perm_to_id[p]))
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

    # B9-C3 演示账号：技术负责人 / 质量负责人（授权审批人）+ 人事管理员（授权管理）
    hr_role = db.scalar(select(Role).where(Role.code == "hr_manager", Role.deleted == 0))
    for username, name, role_code in (
        ("tech1", "技术负责人", "biz_user"),
        ("qa1", "质量负责人", "biz_user"),
        ("hr1", "人事管理员", "hr_manager"),
    ):
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
            target_role = (
                db.scalar(select(Role).where(Role.code == role_code, Role.deleted == 0))
                if role_code != "hr_manager"
                else hr_role
            )
            if target_role is not None:
                db.add(UserRole(user_id=u.id, role_id=target_role.id))

    # 演示分组角色用户（B5：仿真 / 模型 / 试验 / 委外专员）
    for username, name, role_code in (
        ("sim1", "仿真工程师", "sim_engineer"),
        ("model1", "模型工程师", "model_engineer"),
        ("test1", "试验工程师", "test_engineer"),
        ("outsource1", "委外专员", "outsource_specialist"),
    ):
        grp_role = db.scalar(select(Role).where(Role.code == role_code, Role.deleted == 0))
        if not grp_role:
            continue
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
            db.add(UserRole(user_id=u.id, role_id=grp_role.id))

    # 演示安保员（访客与安全域 B3 专用角色）
    security_role = db.scalar(select(Role).where(Role.code == "security_officer", Role.deleted == 0)) or super_role
    u = db.scalar(select(User).where(User.username == "security1", User.deleted == 0))
    if not u:
        u = User(
            username="security1",
            password_hash=hash_password("Test@123456"),
            name="安保员",
            status="enabled",
        )
        db.add(u)
        db.flush()
    if not db.scalar(select(UserRole).where(UserRole.user_id == u.id, UserRole.deleted == 0)):
        db.add(UserRole(user_id=u.id, role_id=security_role.id))


def _seed_dicts(db: Session) -> None:
    for code, (name, items) in DICTS.items():
        t = db.scalar(select(DictType).where(DictType.code == code, DictType.deleted == 0))
        if not t:
            t = DictType(code=code, name=name)
            db.add(t)
            db.flush()
        for item in items:
            # 支持 3 元组 (label, label_en, value) 与 4 元组 (label, label_en, value, extra)
            label, label_en, value = item[0], item[1], item[2]
            extra = item[3] if len(item) > 3 else ""
            exists = db.scalar(
                select(DictItem).where(DictItem.dict_type_code == code, DictItem.value == value, DictItem.deleted == 0)
            )
            if not exists:
                db.add(
                    DictItem(
                        dict_type_code=code,
                        label=label,
                        label_en=label_en,
                        value=value,
                        extra=extra,
                        sort=0,
                    )
                )


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
    # 采购申请：两级顺序；采购合同：双人同时会签(and) → 分管领导终审
    _seed_flow(
        db,
        code="purchase_request_approve",
        name="采购申请审批",
        biz_type="purchase_request",
        remark="默认两级顺序审批",
        nodes=((1, "部门负责人审批", "manager1"), (2, "分管领导审批", "leader1")),
    )
    _seed_flow(
        db,
        code="purchase_contract_approve",
        name="采购合同会签",
        biz_type="purchase_contract",
        remark="会签节点 sign_mode=and（全员通过）+ 分管领导终审",
        nodes=(
            {"seq": 1, "name": "采购会签", "users": ["manager1", "leader1"], "sign_mode": "and"},
            (2, "分管领导终审", "leader1"),
        ),
    )
    # 招标定标：分管领导单级审批
    _seed_flow(
        db,
        code="tender_award_approve",
        name="招标定标审批",
        biz_type="tender_award",
        remark="定标默认单级审批（分管领导）",
        nodes=((1, "分管领导审批", "leader1"),),
    )
    # 人员授权审批（B9-C3）：固定 USER 节点（技术负责人 → 质量负责人）。
    # 刻意不用 ROLE 节点 —— 无人持有该角色时引擎会「解析失败自动跳过」，审批形同虚设。
    _seed_flow(
        db,
        code="hr_authorization_approve",
        name="人员授权审批",
        biz_type="hr_authorization",
        remark="授权须经技术负责人 + 质量负责人两级确认后生效（不允许人工直通）",
        nodes=((1, "技术负责人审批", "tech1"), (2, "质量负责人审批", "qa1")),
    )
    # 人事事务审批（B10-1）：固定 USER 节点（人事主管 hr1 → 总经理 admin）。
    # 同样刻意不用 ROLE 节点；审批通过 ≠ 生效，副作用统一走 POST /hr/employments/{id}/effect。
    _seed_flow(
        db,
        code="hr_employment_approve",
        name="人事事务审批",
        biz_type="hr_employment",
        remark="入职/调岗/离职/返聘须经人事主管 + 总经理审批；审批通过不等于生效，副作用走生效动作",
        nodes=((1, "人事主管审核", "hr1"), (2, "总经理审批", "admin")),
    )
    # OA 示例流程：请假=组织多级（本部门负责人 → 上级部门负责人）；报销/用章=固定人两级
    _seed_flow(
        db,
        code="oa_leave_approve",
        name="OA 请假审批",
        biz_type="oa",
        remark="组织多级审批：发起人主部门负责人 → 上级部门负责人（解析失败自动跳过）",
        nodes=((1, "部门负责人审批", "DEPT_LEADER", ""), (2, "分管领导审批", "PARENT_DEPT_LEADER", "")),
    )
    for code, name in (
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
    # 销售报价：组织两级（发起人主部门负责人 → 上级部门负责人），同 OA 请假解析口径
    _seed_flow(
        db,
        code="quote_approve",
        name="报价审批",
        biz_type="sales_quotation",
        remark="组织两级审批：发起人主部门负责人 → 上级部门负责人（解析失败自动跳过）",
        nodes=((1, "部门负责人审批", "DEPT_LEADER", ""), (2, "分管领导审批", "PARENT_DEPT_LEADER", "")),
    )
    # ===== F5：流程驱动新增的单据审批 =====
    _seed_flow(
        db,
        code="project_approve",
        name="项目立项审批",
        biz_type="project",
        remark="立项两级顺序审批：通过后进入策划阶段",
        nodes=((1, "部门负责人审批", "manager1"), (2, "分管领导审批", "leader1")),
    )
    _seed_flow(
        db,
        code="timesheet_approve",
        name="工时审批",
        biz_type="timesheet",
        remark="工时经部门负责人审批后方可计入项目成本",
        nodes=((1, "部门负责人审批", "manager1"),),
    )
    _seed_flow(
        db,
        code="asset_disposal_approve",
        name="资产处置审批",
        biz_type="asset_disposal",
        remark="处置单经部门负责人 + 分管领导审批后方可核销",
        nodes=((1, "部门负责人审批", "manager1"), (2, "分管领导审批", "leader1")),
    )
    _seed_flow(
        db,
        code="asset_receipt_approve",
        name="到货验收审批",
        biz_type="asset_receipt",
        remark="验收审批通过后生成入库流水",
        nodes=((1, "部门负责人审批", "manager1"),),
    )
    _seed_flow(
        db,
        code="payment_confirm",
        name="回款复核审批",
        biz_type="payment",
        remark="复核通过后确认入账并核销结算单应收",
        nodes=((1, "部门负责人审批", "manager1"),),
    )
    _seed_flow(
        db,
        code="report_seal_approve",
        name="报告用章审批",
        biz_type="report_seal",
        remark="用章申请审批通过后由有权人执行签章",
        nodes=((1, "部门负责人审批", "manager1"), (2, "分管领导审批", "leader1")),
    )
    # ===== F6：访客预约（门户提交）→ 通用审批引擎 =====
    # 节点 1 的审批人由**表单变量** hostUserId 决定（即预约时选择的被访人），
    # 因此每个访客单的审批链不同；节点 2 按 securityLevel 条件分流：
    # 敏感区域（>=3）追加安保审批，普通区域只做安保抄送。
    _seed_flow(
        db,
        code="visitor_visit_approve",
        name="访客预约审批",
        biz_type="visitor_visit",
        remark="被访人审批（取表单变量 hostUserId）；敏感区域（securityLevel>=3）追加安保审批",
        variables_schema={
            "hostUserId": {"type": "number", "label": "被访人"},
            "hostDeptId": {"type": "number", "label": "被访部门"},
            "hostName": {"type": "string", "label": "被访人姓名"},
            "securityLevel": {"type": "number", "label": "区域安全等级"},
            "zoneIds": {"type": "string", "label": "申请区域"},
            "customerId": {"type": "number", "label": "往来单位"},
        },
        nodes=(
            {"seq": 1, "name": "被访人审批", "approver_type": "FORM_USER", "approver_value": "hostUserId"},
            {
                "seq": 2,
                "name": "安全等级分流",
                "node_type": "condition",
                "branches": [{"expr": {"field": "securityLevel", "op": "gte", "value": 3}, "targetSeq": 3}],
                "default_seq": 4,
            },
            {"seq": 3, "name": "安保审批", "approver_type": "ROLE", "approver_value": "security_officer"},
            {
                "seq": 4,
                "name": "安保知悉",
                "node_type": "cc",
                "approver_type": "ROLE",
                "approver_value": "security_officer",
            },
        ),
    )


def _declared_usernames(entry) -> list[str]:
    """从节点声明里取出「固定人（USER）」节点对应的用户名列表（非固定人节点返回空）。"""
    if isinstance(entry, dict):
        return list(entry.get("users") or [])
    if len(entry) == 3:
        return [entry[2]]
    return []


def _repair_user_nodes(db: Session, d: ApprovalDefinition, nodes) -> None:
    """修复失效的固定人（USER）审批节点。

    演示账号被删后重建 → 用户 id 变化 → 流程节点里存的旧 id 解析不到人，
    提交审批会报「节点『xx』未配置可用审批人」，整条审批链直接卡死
    （测试库的「一键清空」用例、生产的账号重建都会触发）。

    这里按种子声明的**用户名**把**已失效**的节点重新指到当前用户 id：
    - 只修失效节点 —— 管理员在「流程设置」里改过的有效节点不动；
    - 只修种子声明过的 seq —— 管理员新增的节点不动。
    """
    for entry in nodes:
        usernames = _declared_usernames(entry)
        if not usernames:
            continue
        seq = entry["seq"] if isinstance(entry, dict) else entry[0]
        node = db.scalar(
            select(ApprovalNode).where(
                ApprovalNode.definition_id == d.id,
                ApprovalNode.seq == seq,
                ApprovalNode.approver_type == "USER",
                ApprovalNode.deleted == 0,
            )
        )
        if node is None:
            continue
        ids = [v.strip() for v in (node.approver_value or "").split(",") if v.strip()]
        if len(ids) == len(usernames) and all(i.isdigit() for i in ids):
            alive = db.scalars(
                select(User.id).where(
                    User.id.in_([int(i) for i in ids]),
                    User.deleted == 0,
                    User.status == "enabled",
                )
            ).all()
            if len(alive) == len(ids):
                continue  # 节点仍然有效 —— 不动（保留管理员改动）
        # 失效 → 按用户名重新解析当前用户 id
        new_ids, new_names = [], []
        for username in usernames:
            u = db.scalar(select(User).where(User.username == username, User.deleted == 0))
            if not u:
                break
            new_ids.append(str(u.id))
            new_names.append(u.name or u.username)
        else:
            node.approver_value = ",".join(new_ids)
            node.approver_name = ",".join(new_names)


def _seed_flow(db: Session, *, code: str, name: str, biz_type: str, remark: str, nodes, variables_schema=None) -> None:
    """节点条目三种形态：
    - (seq, 节点名, 用户名)：固定人 USER 节点；
    - (seq, 节点名, approver_type, approver_value[, chain_levels])：角色/组织类型节点；
    - dict：{"seq","name","users":[用户名...],"sign_mode":"and"} 多固定人会签节点，
      或 {"seq","name","approver_type","approver_value"[,"chain_levels"][,"sign_mode"]}，
      或 {"seq","name","node_type":"condition","branches":[...],"default_seq":N} 条件分支节点。

    `variables_schema` 声明流程变量（FORM_* 审批人类型的变量名必须在其中声明）。

    定义已存在时不重建（保留管理员在「流程设置」里的改动），但会**修复失效的
    固定人节点**（见 `_repair_user_nodes`）。
    """
    existing = db.scalar(
        select(ApprovalDefinition).where(ApprovalDefinition.code == code, ApprovalDefinition.deleted == 0)
    )
    if existing:
        _repair_user_nodes(db, existing, nodes)
        return
    d = ApprovalDefinition(code=code, name=name, biz_type=biz_type, remark=remark)
    if variables_schema:
        d.variables_schema = json.dumps(variables_schema, ensure_ascii=False)
    db.add(d)
    db.flush()
    for entry in nodes:
        sign_mode = "or"
        node_type = "approval"
        branches = None
        default_seq = None
        if isinstance(entry, dict):
            seq, node_name = entry["seq"], entry["name"]
            sign_mode = entry.get("sign_mode", "or")
            node_type = entry.get("node_type", "approval")
            branches = entry.get("branches")
            default_seq = entry.get("default_seq")
            if "users" in entry:
                ids, names = [], []
                for username in entry["users"]:
                    u = db.scalar(select(User).where(User.username == username, User.deleted == 0))
                    if not u:
                        break
                    ids.append(str(u.id))
                    names.append(u.name or u.username)
                else:
                    approver_type, approver_value = "USER", ",".join(ids)
                    approver_name, chain_levels = ",".join(names), None
                    db.add(
                        ApprovalNode(
                            definition_id=d.id,
                            seq=seq,
                            node_name=node_name,
                            approver_type=approver_type,
                            approver_value=approver_value,
                            approver_name=approver_name,
                            chain_levels=chain_levels,
                            sign_mode=sign_mode,
                        )
                    )
                continue
            approver_type, approver_value = entry.get("approver_type", "USER"), entry.get("approver_value", "")
            approver_name = node_name
            chain_levels = entry.get("chain_levels")
        else:
            seq, node_name = entry[0], entry[1]
            if len(entry) == 3:
                u = db.scalar(select(User).where(User.username == entry[2], User.deleted == 0))
                if not u:
                    continue
                approver_type, approver_value, approver_name, chain_levels = (
                    "USER",
                    str(u.id),
                    u.name or u.username,
                    None,
                )
            else:
                approver_type, approver_value = entry[2], entry[3]
                approver_name = node_name
                chain_levels = entry[4] if len(entry) > 4 else None
        db.add(
            ApprovalNode(
                definition_id=d.id,
                seq=seq,
                node_name=node_name,
                node_type=node_type,
                approver_type=approver_type,
                approver_value=approver_value,
                approver_name=approver_name,
                chain_levels=chain_levels,
                sign_mode=sign_mode,
                branches=json.dumps(branches, ensure_ascii=False) if branches else None,
                default_seq=default_seq,
            )
        )
    db.flush()
    # 线性定义自动生成等价 LogicFlow 图
    d.process_graph = dumps_graph(build_process_graph([n for n in d.nodes if n.deleted == 0]))


def _seed_depts(db: Session) -> None:
    """部门树幂等种子：缺失补建，已有行同步 parent_id（上下级关系由代码维护）。"""
    by_code: dict[str, Dept] = {}
    for name, code, _parent_code in DEPTS:
        d = db.scalar(select(Dept).where(Dept.code == code, Dept.deleted == 0))
        if not d:
            d = Dept(name=name, code=code)
            db.add(d)
            db.flush()
        by_code[code] = d
    for _name, code, parent_code in DEPTS:
        by_code[code].parent_id = by_code[parent_code].id if parent_code else None
    db.flush()


def _seed_org_memberships(db: Session) -> None:
    """任职种子（幂等）：admin 主部门=综合管理部；manager1=综合管理部负责人；leader1=总经办负责人。

    配合 OA 请假演示流程（DEPT_LEADER → PARENT_DEPT_LEADER）：admin 发起请假
    → manager1（本部门负责人）→ leader1（上级总经办负责人）。
    """
    from app.modules.admin import org  # noqa: PLC0415 避免种子与模块加载循环
    from app.modules.admin.models import UserDept  # noqa: PLC0415

    def _ud(username: str, dept_code: str, is_leader: bool) -> None:
        u = db.scalar(select(User).where(User.username == username, User.deleted == 0))
        d = db.scalar(select(Dept).where(Dept.code == dept_code, Dept.deleted == 0))
        if not u or not d:
            return
        row = db.scalar(
            select(UserDept).where(
                UserDept.user_id == u.id, UserDept.dept_id == d.id, UserDept.deleted == 0
            )
        )
        if not row:
            row = UserDept(user_id=u.id, dept_id=d.id)
            db.add(row)
            db.flush()
        row.is_primary = 1
        row.is_leader = 1 if is_leader else 0
        u.dept_id = d.id
        u.dept_name = d.name
        org.sync_primary_membership(db, u)

    _ud("admin", "D04", False)
    _ud("manager1", "D04", True)
    _ud("leader1", "D00", True)


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


# (key, name, sort, layout)：预置报价模板（published），key+tpl_version=1 存在即跳过
QUOTE_TEMPLATES = [
    (
        "standard",
        "标准报价单",
        1,
        {
            "headerHtml": "<h2>报价单</h2><p>上海机动车检测认证技术研究中心有限公司</p>",
            "introHtml": "感谢贵司垂询。根据所述需求，报价明细如下：",
            "termsHtml": "<p>1. 付款方式：合同签订后 7 个工作日内支付 50% 预付款，交付验收后支付余款。</p>"
            "<p>2. 交付周期：以双方确认的项目计划为准。</p><p>3. 本报价含 6% 增值税。</p>",
            "footerHtml": "<p>联系电话：021-xxxx-xxxx　邮箱：sales@example.com</p>",
            "validDays": 30,
            "itemColumns": [
                {"key": "spec", "label": "", "visible": True},
                {"key": "unit", "label": "", "visible": True},
                {"key": "remark", "label": "", "visible": True},
            ],
        },
    ),
    (
        "simple",
        "简洁版报价单",
        2,
        {
            "headerHtml": "<h2>报价单</h2>",
            "introHtml": "根据贵司需求，报价如下：",
            "termsHtml": "<p>付款方式：一次性付款。报价含税。</p>",
            "footerHtml": "",
            "validDays": 15,
            "itemColumns": [
                {"key": "spec", "label": "", "visible": False},
                {"key": "unit", "label": "", "visible": True},
                {"key": "remark", "label": "", "visible": False},
            ],
        },
    ),
    (
        "bilingual",
        "中英文版报价单",
        3,
        {
            "headerHtml": "<h2>报价单 Quotation</h2><p>SMVIC Co., Ltd.</p>",
            "introHtml": "感谢垂询，报价明细如下。/ Thank you for your inquiry. Please find our quotation below.",
            "termsHtml": "<p>1. 付款 Payment: 50% advance, balance on delivery.</p>"
            "<p>2. 有效期 Validity: 30 days from issue date.</p>",
            "footerHtml": "<p>Tel: 021-xxxx-xxxx　Email: sales@example.com</p>",
            "validDays": 30,
            "itemColumns": [
                {"key": "spec", "label": "规格 Spec", "visible": True},
                {"key": "unit", "label": "单位 Unit", "visible": True},
                {"key": "remark", "label": "备注 Remark", "visible": True},
            ],
        },
    ),
]


def _seed_quote_templates(db: Session) -> None:
    """预置报价模板：published（幂等：同 key+tpl_version=1 存在即跳过，同 _seed_oa_forms 口径）。"""
    from app.modules.sales.models import SalesQuoteTemplate  # noqa: PLC0415 避免种子与模块加载循环

    for key, name, sort, layout in QUOTE_TEMPLATES:
        if db.scalar(
            select(SalesQuoteTemplate).where(
                SalesQuoteTemplate.key == key, SalesQuoteTemplate.tpl_version == 1, SalesQuoteTemplate.deleted == 0
            )
        ):
            continue
        db.add(
            SalesQuoteTemplate(
                key=key,
                name=name,
                tpl_version=1,
                status="published",
                sort=sort,
                layout_json=json.dumps(layout, ensure_ascii=False),
                published_at=datetime.now(),
            )        )


KNOWLEDGE_PRESETS = [
    (
        "工时填报操作指引",
        "工时",
        "路径：工作台 → 我的工时 → 填报。选择日期（默认今天），每行选择合同与任务后填写工时（0.5-24 小时）"
        "与工作内容；支持 AI 预填草稿（需人工核对后提交）。草稿可保存，提交后进入审批；"
        "被驳回的工时可修改后重新提交。",
    ),
    (
        "OA 申请操作指引",
        "OA",
        "路径：OA → 发起申请。选择表单类型后填写字段并提交，进入审批流；"
        "同表单支持 AI 预填（参考本人历史已批准申请，需人工核对）。"
        "「我的申请」可查看进度与撤回；审批通过后会回写表单状态。",
    ),
    (
        "合同创建与审批指引",
        "合同",
        "路径：合同 → 新增合同。支持 AI 合同识别（上传 pdf/docx/txt/jpg/png 抽取字段草稿）"
        "与 AI 风险审查（仅提示不拦截）。提交后按审批流逐级审批，通过后发放正式合同编号 HT...。",
    ),
    (
        "开票登记指引",
        "财务",
        "路径：财务 → 发票。结算单经客户确认后发起开票申请，审批通过生成发票记录；"
        "财务在发票列表点「登记」补录发票号/金额/税率/购买方/销售方/日期，"
        "支持上传发票图片或 PDF 进行 AI 识别回填，金额与结算金额不一致时系统会提示核对。",
    ),
    (
        "采购申请操作指引",
        "采购",
        "路径：采购 → 采购申请 → 新增。逐行填写物资名称/规格/单位/数量/预估单价；"
        "每行可用「价格参考」查看同品名历史采购均价/区间/最近价与 AI 点评。"
        "提交后走会签审批，通过后可转采购合同。",
    ),
    (
        "样品管理指引",
        "任务",
        "样品随任务登记：任务编辑页「样品信息」区逐行填写名称/型号/VIN/车型/日期，"
        "支持「拍照识别」上传样品标签照片自动回填（需人工核对）。"
        "任务提交审批时发放样品编号（任务号-01 起）；出入库在样品列表操作并留存流水。",
    ),
    (
        "AI 功能通用说明",
        "AI",
        "全站 AI 能力由管理员在「AI 中心 → AI 设置」统一开关与限配额；"
        "AI 产出均为草稿/建议，须人工确认后才会保存或提交；"
        "AI 未配置或功能停用时，相关入口自动隐藏或降级为手工/搜索模式。",
    ),
]


def _seed_knowledge(db: Session) -> None:
    """预置知识库操作手册（幂等：同标题存在即跳过；dev 库由 alembic 迁移插入，此处兜底测试/新装库）。"""
    from app.modules.aicenter.models import KnowledgeEntry  # noqa: PLC0415

    for title, category, content in KNOWLEDGE_PRESETS:
        if db.scalar(select(KnowledgeEntry).where(KnowledgeEntry.title == title, KnowledgeEntry.deleted == 0)):
            continue
        db.add(KnowledgeEntry(title=title, category=category, content=content))


def _seed_authorizations(db: Session) -> None:
    """演示授权（B9-C3）：给演示账号播种基础授权，避免开箱即用就被拦截。

    幂等：按 (user, auth_type, role_code) 查重；授权范围留空 = 不限。
    职责分离示范：编制（manager1）/ 复核批准（leader1、tech1、qa1）分属不同人。
    """
    db.flush()  # 单号规则可能尚未落库（autoflush=False）
    demo = (
        ("manager1", "test_item", "", "部门负责人 · 检测项目操作授权"),
        ("manager1", "report_role", "preparer", "报告编制授权"),
        ("manager1", "report_role", "signer", "报告用章授权"),
        ("leader1", "test_item", "", "分管领导 · 检测项目操作授权"),
        ("leader1", "report_role", "approver", "报告批准授权"),
        ("leader1", "report_role", "reviewer", "报告复核授权"),
        ("test1", "test_item", "", "试验岗 · 检测项目操作授权"),
        ("tech1", "test_item", "", "技术负责人 · 检测项目操作授权"),
        ("tech1", "report_role", "approver", "报告批准授权"),
        ("qa1", "test_item", "", "质量负责人 · 检测项目操作授权"),
        ("qa1", "report_role", "approver", "报告批准授权"),
    )
    now = datetime.now().replace(microsecond=0)
    for username, auth_type, role_code, remark in demo:
        u = db.scalar(select(User).where(User.username == username, User.deleted == 0))
        if not u:
            continue
        exists = db.scalar(
            select(HrAuthorization).where(
                HrAuthorization.user_id == u.id,
                HrAuthorization.auth_type == auth_type,
                HrAuthorization.role_code == role_code,
                HrAuthorization.deleted == 0,
            )
        )
        if exists:
            continue
        a = HrAuthorization(
            auth_no=next_no(db, "hr_authorization"),
            user_id=u.id,
            user_name=u.name or u.username,
            auth_type=auth_type,
            role_code=role_code,
            valid_from=now,
            status="active",
            applicant_id=u.id,
            applicant_name=u.name or "",
            approver_id=u.id,
            approver_name=u.name or "",
            activated_at=now,
            remark=remark,
            create_by=u.id,
        )
        db.add(a)
        db.flush()
        db.add(
            HrAuthorizationEvent(
                authorization_id=a.id,
                auth_no=a.auth_no,
                event_type="create",
                from_status="",
                to_status="active",
                operator_id=u.id,
                operator_name=u.name or "",
                reason="演示种子授权",
                effective_at=now,
                snapshot="{}",
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
        _seed_org_memberships(db)
        _seed_flows(db)
        _seed_oa_forms(db)
        _seed_quote_templates(db)
        _seed_knowledge(db)
        _seed_authorizations(db)
        # E1 企业微信移植：全模拟组织 / 人员 / 标签（幂等，重复跑不重复建）
        from app.seeds import wecom_org  # noqa: PLC0415 避免种子与模块加载循环

        wc_summary = wecom_org.import_org(db)
        db.commit()
        # E1 企业微信移植：39 个在用审批模板 → OA 表单 + 审批定义（幂等）
        from app.seeds import wecom_templates  # noqa: PLC0415 避免种子与模块加载循环

        wt_summary = wecom_templates.import_templates(db)
        db.commit()
        print(
            f"seed ok: menus={len(perm_to_id)} perms, dicts={len(DICTS)}, rules={len(NUMBER_RULES)}, "
            f"wecom_org={wc_summary}, wecom_templates={wt_summary}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

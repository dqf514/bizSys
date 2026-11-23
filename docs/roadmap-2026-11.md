# HMVIC bizSys 需求分批路线图（2026-11）

> 来源：`HMVIC system功能开发.csv`（蒋侃，2026-11-18 / 2026-11-19，共 32 项有效条目 + 3 项待澄清条目）。
> 本文是**需求落地的排期依据**：每批列出需求项编号、依赖前置、涉及模块与表、交付物、风险。
> 需求原文逐条保留在 CSV；导航里的占位页（`src/modules/*/pages/*`）会显示对应的需求项编号与批次。

## 批次总览

| 批次 | 主题 | CSV 项 | 依赖前置 | 状态 |
| --- | --- | --- | --- | --- |
| **B1** | 基础设施：全站布局统一 + 导航分区重构 + 新模块骨架 + 消息中心 | 30 | — | **已交付** |
| **B2** | 客户自助账号体系 + 在线任务委托 | 5 | B1 导航分区 | **已交付** |
| **B3** | 访客系统（预约/审批/通行/签离/区域/NDA/联动/审计） | 6–17 | B2 账号体系、门禁与人脸接口 | **已交付** |
| **B4** | 资产 & 样车 & 样品 & 物料统一管理 + 库存预警 + BOM | 23 | B1 骨架、需求方提供的详细逻辑 | **已交付（两轮：台账 + BOM/呆滞预警）** |
| **B5** | 任务字段扩展 + 智能排程甘特 + 项目管理 | 18–22、31 | B4 资产与物料 | **已交付** |
| **B6** | 设备台账 + 设备预警 + 设备能耗 + 数字孪生 | 67–69 | B4 资产、B5 排程 | 待需求澄清 |
| **B7** | 营收分析看板 + 产能利用率看板 | 3、4 | B5 排程数据、B6 设备数据 | 待开发 |
| **B8** | 报告模板与审批流、结算计费对接、安全巡检、知识库扩展、流程中心联动、作业申请流程、人力资源扩展 | 24–29、32 | B5 | 待开发 |
| **F5** | 全流程驱动 / 业务事件驱动 + 流程与事件开关面板（横切批次，非 CSV 条目） | — | B1–B5 | **已交付** |
| **F6** | 对外门户专业化 + 访客预约闭环 + 全站移动优先（横切批次，非 CSV 条目） | — | B2 账号体系、B3 访客域、F5 流程引擎 | **已交付** |
| **B9** | 检测机构合规基线落地 + 人员能力授权纵切（CSV 1、26） | 1、26 | 需求方两份 docx（已入库） | **已交付** |
| **B10** | HR L1–L5 + 质量体系域（CSV 26 剩余层） | 26 | B9 授权台账 | **进行中**（B10-1 已交付） |

外部依赖项：**第 1 项**「运营平台合规开发原则」与**第 2 项**「SSO / 统一权限中心（UPMS）」原为"文件未入库"的历史遗留 —— 两份 docx 已由需求方提供并入库（仓库根目录），第 1 项已在 **B9** 逐条核查并落地为可执行约束（见 [`docs/compliance-baseline.md`](compliance-baseline.md)）；第 2 项仍涉及外部身份系统对接（企微 SSO 已在 B6/F5 落地，UPMS 统一权限中心对接需单独立项，不排入当前批次）。

---

## B1 — 基础设施（已交付）

| 项 | 内容 |
| --- | --- |
| 需求项 | 30（统一消息中心） |
| 交付物 | 全站布局/宽度体系（`.bs-page` 骨架 + 布局令牌）；导航分区重构（8 业务分区 + 底部系统管理）；13 个新模块入口骨架（菜单 + 权限 + 占位页）；消息中心完整实现（列表 / 关键词检索 / 业务分类页签与计数 / 已读 / 全部已读） |
| 涉及模块 | 前端 `styles/page.css`、`layout/useNavZones.ts`、`modules/common/pages/PlannedFeature.vue`、`modules/message/pages/MessageCenter.vue`；后端 `seeds/init_data.py`、`modules/admin/router.py`（`/admin/notifies` 检索与 `/admin/notifies/counts`） |
| 迁移 | `backend/scripts/migrate_nav_zones.py`（幂等；规范结构直接由种子的 `MENU_TREE` 推导） |
| 风险 | 菜单结构变更使既有 `prefs.navOrder` 失效 —— 前端已有失效回退，无需人工处理 |

**本批次确立的"新需求接入路径"**（后续批次照此办理）：

1. 后端 `app/seeds/init_data.py` 的 `MENU_TREE` 加菜单行（`title_key`/`name`/`path`/`component_key`/`icon`/`permission`），权限码遵循 `module:resource:action`；
2. 权限点挂进 `_seed_roles` 的 `biz_perms`（或仅超管）；
3. 需要调整树形结构时跑 `uv run python scripts/migrate_nav_zones.py`（种子不回写 `parent_id`/`sort`）；
4. 前端 `src/modules/<域>/pages/<Name>.vue` 建页面，`component_key` 的前缀必须等于模块目录名；
5. 图标在 `src/icons.ts` 注册；文案进 `src/locales/{zh-CN,en-US}/`；
6. 占位阶段用 `PlannedFeature.vue`（读 `planned.json` 的 `items.<key>`），功能开工后替换为真实页面并把 `planned.json` 里该条目的 `status` 改成 `inProgress` / `done`。

---

## B2 — 客户自助账号 + 在线任务委托（CSV 5）

> **状态：已交付（2026-11-21）**

### 已交付

| 项 | 内容 |
| --- | --- |
| 账号模型 | **不新建账号表**：`partner_user` 扩展 `account_type`（supplier/customer）、`perm_scope`（entrust/staff/tender）、`manager_id/manager_name`、`staff_limit`；客户账号与员工账号完全隔离，沿用门户 token（`typ=portal_access`、`aud=portal`），双向不通用 |
| 客户自助账号 | `POST /portal/auth/register?companyType=customer` 注册（pending）→ 内部 `crm:account:review` 审核启用（绑定往来单位 + 客户经理 + 权限范围 + 人员名额）→ 驳回/停用即不可登录；列表页 `客户自助账号`（`/crm/accounts`，页签计数 all/pending/enabled/rejected/disabled） |
| 外来人员备案 | 门户 `POST /portal/staff` 自助登记（姓名/证件/职务/车牌/来访日期/来访事由/NDA）→ 内部 `crm:staff:review` 审核（备案通过后抄送业务负责人与访客管理人员，并勾选可进入区域 `visit_perm`）；内部亦可代登记；列表页 `客户方人员备案`（`/crm/partner-staffs`，含导出） |
| 在线任务委托 | 门户基于**已审批合同**提交委托（仿真 sim / 模型 model / 试验 test / 委外 outsource，带试验项目明细行）→ 内部受理台 `在线委托`（`/task/entrusts`）受理（自动取号 `WT` + 抄送业务负责人）→ 生成任务草稿并回写 `taskId/taskNo`；客户可撤回；驳回后不可再受理 |
| 业务代提交 | 客户经理在受理台"代提交委托"（`source=staff`），与客户自助下单同一张 `task_entrust` 单据 |
| 表与迁移 | `task_entrust` / `task_entrust_item`（task 域，`WT` 单号规则）、`crm_partner_staff`；`partner_user` 加 5 列 —— 迁移 `n2a2b3c4d5e6_b2_customer_selfservice.py` |
| 权限码 | `crm:account:list/review/edit`、`crm:staff:list/create/review/edit/export`、`task:entrust:list/create/review/dispatch/export`（菜单挂在 `经营与协同` 分区） |
| 前端 | `modules/task/pages/EntrustList.vue`、`modules/crm/pages/CustomerAccountList.vue`、`modules/crm/pages/PartnerStaffList.vue`、门户 `PortalOrders.vue`（在线委托）、`PortalStaff.vue`（人员登记）、`PortalRegister.vue`（账号类型选择） |
| 测试 | `tests/test_b2_selfservice.py`（11 条 HTTP 黑盒：注册待审、审核绑定客户、停用、委托全链路、驳回与撤回、待审不可登录、列表计数、门户 token 隔离、人员备案审核、名额上限、导出） |

### 原始需求与风险（存档）

- **需求要点**：补充客户自助账号体系；客户来访/支持人员自助登记备案，客户经理审核后抄送业务负责人与访客管理人员并勾选访客系统权限（与安防/门禁联动）；基于合同的客户在线任务提交（仿真、模型、试验），业务经理可代提交。
- **依赖前置**：B1 的导航分区（`经营与协同 → 客户自助 / 在线委托` 入口已就位）。
- **涉及模块**：`crm`（客户账号）、`portal`（合作方门户壳）、`task`（任务创建）。
- **风险**：客户账号与员工账号共用 `sys_user` 会污染权限模型 —— 实际改为扩展 `partner_user`（独立认证体系已具备），不新建 `crm_partner_account`。
- **遗留**：访客系统权限的"勾选"目前落在 `crm_partner_staff.visit_perm`（可进入区域），与 B3 访客域的凭证下发对接**已在 B3 落地**（`visitor_visit.zone_ids` → `visitor_credential` 授权区域）。

---

## B3 — 访客系统（CSV 6–17）

> **状态：已交付（2026-11-21）**

### 已交付

| 项 | 内容 |
| --- | --- |
| 新增域 | `visitor`（`app/modules/visitor/`，models/schemas/service/router 四件套），表前缀 `visitor_`；错误码段 **98xxx**（98001–98008） |
| 区域分级 | `visitor_zone`：编码/名称/类型（公共接待区、样车接收区、试验区、准备区、生产加工区、工具仪器间、数据机房）/安全等级 L1–L4/是否额外审批/需陪同/需 NDA/双人作业/相机管控/联动设备/人数上限；工具仪器间与样车存储区默认禁入 |
| 访客单 | `visitor_visit` + `visitor_approval`：状态机 `pending→approved→visiting→left`，旁路 `rejected/cancelled/overdue`；审批链 `host→dept→(zone)`；`VT` 单号；访客类型与预约来源字典；陪同见证、授权区域、计划时间窗、签入/签离闭环 |
| 通行凭证 | `visitor_credential`：按"人 + 时间 + 区域"下发最小权限；核验方式 qrcode/face/ic/plate/manual；`POST /visitor/credentials/verify` 供门禁/闸机/梯控调用，放行与否均写审计 |
| 合规审计 | `visitor_access_log` **只追加不可删改**：`AppendOnlyModel`（无 `deleted`/`version`/`update_*`），API 不提供任何 PUT/PATCH/DELETE；事件类型签入/签离/区域进入/区域离开/拒绝通行；`summary` 应急报表按天/按事件聚合，`days` 上限 180（保留期 ≥180 天） |
| 黑名单 | `visitor_blacklist`：姓名/证件/电话/单位/原因/生效失效期/来源（manual/system），命中即拒绝放行并生成预警 |
| 预警 | `visitor_alert`：滞留超时（`POST /visitor/alerts/scan` 扫描生成）/尾随进入/闯入禁区/越权访问/黑名单命中；处置闭环 `open→handled|ignored`；**拒绝放行时先提交事务再抛错，保证告警与审计不丢** |
| NDA | `visitor_nda`：电子签署 + `evidence_hash` 存证哈希防篡改 + 有效期 + 作废；区域 `need_nda=1` 且未签 **不予放行**（98007） |
| 样品/样车交接 | `visitor_sample_handover`：交接单号/样品编号/名称/条码/类型（样品/样车/模型）/数量/送样人/接收人/交接时间，可关联访客单反查带入物 |
| 角色隔离 | 访客与安全域权限**不挂业务角色**（`biz_user` 无任何 `visitor:*` 权限），单独设 `security_officer`（安保员）角色，演示账号 `security1 / Test@123456` |
| 权限码 | `visitor:visit:list/create/review/checkin/export`、`visitor:zone:list/edit`、`visitor:nda:list/sign`、`visitor:credential:list/verify/edit`、`visitor:blacklist:list/edit`、`visitor:audit:list/export/report`、`visitor:handover:list/create`、`visitor:alert:list/handle`（菜单挂在 `访客与安全` 分区） |
| 表与迁移 | `visitor_zone` `visitor_visit` `visitor_approval` `visitor_credential` `visitor_access_log` `visitor_nda` `visitor_blacklist` `visitor_sample_handover` `visitor_alert` —— 迁移 `n3a2b3c4d5e6_b3_visitor_module.py`（9 张表全部登记进「一键清空」清单） |
| 前端 | `modules/visitor/pages/` 8 个页面：`VisitList` `ZoneList` `NdaList` `CredentialList` `BlacklistList` `AccessLogList` `HandoverList` `AlertList`（`src/api/visitor.ts` + `src/locales/{zh-CN,en-US}/visitor.json`） |
| 测试 | `tests/test_b3_visitor.py`（16 条 HTTP 黑盒：区域 CRUD 与重名、登记→审批→签入→签离全链路、追加审批级、未签 NDA 拦截、驳回/取消、黑名单拦截签入、凭证区域范围核验、审计只读与汇总、导出、交接、预警处置与扫描、NDA 计数与作废、统计计数、业务角色 403） |

### 原始需求与风险（存档）

- **需求要点**：多渠道预约与登记（微信/小程序/网页/员工邀请/前台现场）；被访人 + 部门审批，敏感区域额外审批；访客类型（客户、监管评审、供应商、快递、临时工、外包维修）；凭证通行（二维码/人脸/IC 卡/车牌，按"人+时间+区域"下发最小权限）；签入签出闭环与滞留告警；黑名单与闯入/尾随预警；区域分级（公共接待区/样车接收区/试验区/准备区/生产加工区/工具仪器间/数据机房）；样品样车交接联动（送样人 + 样品条码 + 交接时间 + 接收人，可反查）；陪同与见证；NDA 电子签；设备/环境隔离（手机相机管控、危化品双人）；门禁/闸机/梯控/视频/LIMS/OA/消防联动；合规审计（日志不可删改、保存 ≥180 天，分级权限，一人一号，应急报表）。
- **依赖前置**：B2 客户账号与访客人员主数据；门禁/人脸/车牌厂商接口。
- **涉及模块**：`visitor`（新增域）、`safety`（巡检与门禁联动）、`crm`（客户主体）、`task`/`sample`（样品交接）。
- **交付物**：`visitor_visit`（预约/登记）、`visitor_zone`（区域与分级）、`visitor_credential`（凭证与有效期）、`visitor_access_log`（不可删改审计）、`visitor_nda`（签署与存证）；审批走现有流程引擎（`ApprovalDefinition`）。
- **风险**：合规审计要求"日志不可删改 + ≥180 天保留"与平台统一的软删机制冲突 —— 审计表需单独实现只追加（无 `deleted` 语义、禁止 UPDATE/DELETE），并把保留期写进备份策略。
- **遗留**：① 多渠道预约的**外部渠道入口**（微信/小程序）尚未对接 —— **已在 F6 落地**（门户 `POST /portal/visits` 预约入口 + 移动优先页面，微信推送链接即可完成预约）；② 门禁/视频/LIMS/消防的**厂商接口**未接入，凭证核验已提供 `POST /visitor/credentials/verify` 作为对接点；③ 访客审批走**域内审批链**（host→dept→zone）而非通用流程引擎 `ApprovalDefinition` —— **已在 F6 落地**（`biz_type=visitor_visit` 接入审批引擎，节点可在「流程设置」设计；域内审批链保留为流程停用时的人工兜底）。

---

## B4 — 资产 & 样车 & 样品 & 物料统一管理（CSV 23）

> **状态：已交付（2026-11-21 第一轮 / 2026-11-22 第二轮）** —— 新建 `asset` 域，覆盖仓储 / 采购 / 验收 / 流水 / 盘点 / 样件 / 固定资产 / 折旧 / 处置 / 工具全链路 CRUD；
> 第二轮补齐 **BOM（父子结构 + 版本 + 用量）** 与 **呆滞预警**，并落地物料台账页。

### 已交付（第一轮：台账与全链路）

| 项 | 内容 |
| --- | --- |
| 后端域 | `app/modules/asset/`（`models.py` / `schemas.py` / `service.py` / `router.py` + `finance_router.py`），18 张 `ast_*` 表，迁移 `n1a2b3c4d5e6_asset_module.py` |
| 菜单 | 库存与资产（StockAsset）→ 进出库管理（采购订单 / 验收单 / 仓库 / 库存物料 / 库存流水 / 库存盘点 / 样件管理 / 样件借出）· 资产财务（固定资产 / 处置报废 / 工具领用） |
| 前端 | `src/modules/asset/pages/` 11 个页面 + `src/api/asset.ts` + `locales/{zh-CN,en-US}/asset.json` |
| 统一框架 | 部门取 `sys_dept`、供应公司取 `crm_customer`（`partner_type ∈ supplier/both`）、权限码 `asset:*` 挂 `sys_menu`（biz_user 角色按前缀批量授权）——**未新建组织/公司/权限表** |
| 库存预警 | 物料安全库存 `safetyStock` + `lowStock` 标记 + `GET /asset/items/counts.lowStock` + 列表 `filters[low_stock]=1` |
| 状态机 | 采购订单 `draft→confirmed→closed`、验收单 `draft→accepted`、盘点 `draft→counting→finished`、处置单 `draft→approved→done`、借出 `loaned→in_stock`（均带"终态不可改删"约束） |
| 测试 | `tests/test_asset_stock.py`（14）+ `tests/test_asset_finance.py`（14），HTTP 黑盒全链路；后端全量 `pytest -q` 311 全绿 |

### 已交付（第二轮：BOM + 呆滞预警）

| 项 | 内容 |
| --- | --- |
| BOM 表 | `ast_bom`（父件 + 版本号 `bom_version` + 状态 draft/effective/obsolete + 生效日期）+ `ast_bom_line`（子件、用量、损耗率、位号 refDesignator、安装位置），迁移 `n4a2b3c4d5e6_b4_bom_stagnant.py` |
| BOM 端点 | `asset/bom_router.py` 12 个端点：列表 / 计数 / 详情 / **多级展开**（带循环检测）/ **用量对比** / 引用反查；新建 / 修改 / **激活** / **作废** / **复制版本** / 删除 / 导出 xlsx |
| BOM 规则 | 同一父件**仅一个生效版本**（激活新版本自动作废旧版本）；版本号在父件内唯一（重复 → 97004）；仅草稿可改可删（生效态改删 → 97001）；禁止自引用（→ 97001）；复制版本按 `V1.0→V1.1` 递增 |
| 用量对比 | 理论需求 = 子件用量 ×（1 + 损耗率）× 父件数量；实际领用 = 出库流水累计；差额 = 理论 − 实际，用于核对领料偏差 |
| 呆滞预警 | `ast_item.stagnant_days`（默认 90 天阈值）；按**最后一次出入库流水**计算闲置天数，分级 `normal / slow / stagnant / dead`（阈值倍数）；输出呆滞金额 |
| 预警筛选 | `filters[stagnant]=1`、`filters[stagnant_level]=xx`、`filters[warning]=1`、`filters[low_stock]=1`；`GET /asset/items/counts` 增加 `lowStock / stagnant / stagnantAmount / warning` 计数 |
| 物料台账页 | `MaterialList.vue`：预警 / 低库存 / 呆滞页签（均带计数）+ 分类与分级检索 + 呆滞分级与金额列 + 导出（与筛选一致）+ BOM 关联反查抽屉 |
| BOM 页 | `BomList.vue`：列表 / 页签（草稿·生效·作废）/ 新建编辑（子件行编辑）/ 激活作废复制 / 多级展开树 / 用量对比 / 深链 `?detail=<id>` |
| 编号与菜单 | 编号规则新增 `BM`（BOM 单号）；菜单在**生产资源 → 样品与物料**下新增「物料清单」（`menu.bom`）+ 权限码 `asset:bom:*` / `asset:material:*` |
| 一键清空 | 登记 `Bom` / `BomLine` |
| 测试 | `tests/test_b4_bom_stagnant.py`（6 个用例，覆盖版本规则 / 多级展开 / 用量对比 / 呆滞分级与筛选 / 导出与权限）；后端全量 `pytest -q` 344 全绿 |

### 剩余项

- **`task` 域样品表与新台账的关系**：现有 `task_sample` 已被任务/样品单据引用 —— 统一台账走**新表 + 双写过渡**，不要原地改列，避免影响已上线的样品流程。

### 原始需求与风险（存档）

- **需求要点**：把现有"样品管理"替换为资产 & 样车 & 样品 & 物料的统一管理；物料需增加库存预警与 BOM 管理。**详细功能逻辑与代码文件由需求方提供**。
- **依赖前置**：需求方提供详细逻辑文档；B1 的 `生产资源 → 样品与物料` 目录已就位。
- **涉及模块**：`asset`（新增域）、`task`（现有样品）、`procurement`（入库/库存关联）。
- **交付物**：`asset_item`（统一台账：类别/编码/条码/库位/状态）、`asset_bom`（BOM 父子）、`asset_stock`（库存与流水）、预警规则（低于阈值/呆滞）。
- **风险**：现有 `task` 域的样品表已被任务/样品单据引用 —— 统一台账建议**新表 + 双写过渡**，不要原地改列，避免影响已上线的样品流程。

---

## B5 — 任务字段扩展 + 智能排程 + 项目管理（CSV 18–22、31）

> **状态：已交付（2026-11-22）** —— 任务域补齐字段扩展与流转能力，新建 `production` / `project` 两个域。

### 已交付

| 项 | 内容 |
| --- | --- |
| 任务字段扩展 | `task_task` 新增 9 列：`plan_start_date` `duration_hours` `priority` `role_group` `mesh_count` `solver` `compute_resource` `compute_cores` `compute_nodes`；**仅在请求显式携带时覆盖**（`model_fields_set`），避免部分更新被默认值冲掉 |
| 角色分组 | 请求未指定 `roleGroup` 时按 `taskType` 派生（`cfd→sim` `model→model` `windtunnel/test→test` `outsource→outsource`）；负责人按字典 `task_owner_rule` 解析对应角色在职用户，命中不到回落当前登录人 |
| 工序流转 | 新表 `task_process`（一任务多工序）：状态机 `pending→running→done`（`skipped` 旁路）；**同一任务同时只允许一道工序进行中**（否则 60020）；当前工序回写任务 `processStage` |
| 七维分配 | 新表 `task_assignment`，维度字典 `task_dimension`（人/机/料/法/环/测/安/样车）；状态机 `pending→allocated→confirmed`（`rejected` 终态），置 confirmed 自动写 `confirmedAt`；**排程域读取其中 `equipment/person/vehicle`（时段独占）与 `material`（数量占用）** |
| 全过程追溯 | 新表 `task_trace`，节点：任务输入 / 报告输出 / 样车归还 / 模型车发运 / 验收 / 结算；`GET /task/tasks/{id}/operation-flow` 输出「工序节点 + 追溯节点」的统一流程图 |
| 角色分组可见性 | 授予 `task:group:<组>` 的用户**列表只返回本组任务**，详情/编辑跨组被拒（60021）；超管与未授予分组权限者不受限 |
| 智能排程域 | 新增 `production` 域（`prd_plan` + `prd_schedule`，`PL`/`SC` 单号）：自动排期按「优先级 → 计划开始日」贪心排位，设备/人员/样车**时段独占**、物料**数量占用**；**能顺延到空档即算正常排期，不标冲突**，只有排不下或物料缺量才 `conflict`；发布时二次校验冲突（99004）并回写任务计划日期；含资源占用视图与排程行导出 |
| 项目域 | 新增 `project` 域（`prj_project` + `prj_project_task`，`PJ` 单号）：项目状态机 `draft→planning→executing→accepting→closed`（仅 draft/cancelled 可删，99101）；**基于合同立项**（合同须 approved）；甘特行自动生成（任务类型→分组，起止日期优先取已发布排程），进度按权重加权回算；甘特行可手工增删改（里程碑） |
| 表与迁移 | `task_process` `task_assignment` `task_trace` `prd_plan` `prd_schedule` `prj_project` `prj_project_task` —— 迁移 `n5a2b3c4d5e6_b5_task_ext_production_project.py`（7 张表全部登记进「一键清空」清单；`alembic/env.py` 已 import 新域模型） |
| 权限码 | `task:process:edit` `task:assignment:edit` `task:trace:edit` `task:group:sim|model|test|outsource`；`production:schedule:list/create/edit/delete/auto/publish/list:export`；`project:list/create/edit/delete/list:export` |
| 错误码 | `60020 TASK_PROCESS_INVALID_STATE` `60021 TASK_ROLE_GROUP_DENIED`；`99001`–`99005`（排程）；`99101`–`99103`（项目） |
| 字典 | `task_role_group` `task_process` `task_dimension` `task_owner_rule` |
| 前端 | `modules/production/pages/ScheduleBoard.vue`（排程看板 + 甘特 + 资源占用）、`modules/project/pages/ProjectList.vue`（项目列表 + 甘特 + 生成甘特）、组件 `ScheduleGantt.vue` `ProjectGantt.vue`（ECharts custom 系列）、`modules/task/components/TaskProcessPanel.vue`（工序/七维/追溯/流程图四页签，挂进任务详情面板） |
| 测试 | `tests/test_b5_task_ext_production_project.py`（9 条 HTTP 黑盒：字段持久化与部分更新不被冲掉、负责人解析、工序状态机与单工序约束、七维 CRUD、追溯与流程图、角色分组可见性、自动排期→发布→冲突拦截→取消→资源占用、缺料冲突、项目 CRUD→生成甘特→进度回算→状态流转）；后端全量 `pytest -q` 353 全绿 |

### 原始需求与风险（存档）

- **需求要点**：任务需覆盖"任务输入 → 报告输出 / 样车归还 / 模型车发运"全过程可追溯；油泥样车/样件/展车需增加加工工序流转（油泥 / CNC / 表面处理）；CFD 专属字段（网格数、求解器、算力资源）；任务创建后有审批/操作流程图，按任务类型流转到负责人；任务分配界面覆盖人机料法环测安；执行中可查看进度；任务按人员角色分组并设权限；智能排程（按设备/人员/样车/物料约束自动排期，人工可调后再发布）；大型项目全生命周期，按任务输入与排期自动生成项目甘特图（可自定义编辑）。
- **依赖前置**：B4 的设备/物料/样车主数据（排程约束需要）。
- **涉及模块**：`task`（字段扩展与工序流转）、`production`（排程与甘特）、`project`（项目与甘特）。
- **交付物**：`task_process`（工序流转）、`task_field_ext`（CFD/加工扩展字段）、`prod_schedule`（排程与资源占用）、`project` + `project_task`（项目与甘特）。
- **风险**：排程约束求解是本批最大的算法风险 —— 建议先用规则式贪心（设备/人员时段冲突 + 前置工序）跑通，再评估是否引入求解器；甘特图可复用现有 `TaskGantt` 组件的渲染层。
- **遗留**：① 排程目前是**规则式贪心**，未引入求解器；跨项目、跨设备族的复杂约束（换型时间、模具/工装、批次合并）尚未建模，B6 设备台账接入后可再评估；② 项目甘特的**任务依赖（`depends_on`）**已落字段但未做关键路径计算；③ 项目/排程单据此前**未接入审批引擎**（仅靠状态机与权限点控制）—— 已在 **F5 全流程驱动**批次接入（项目立项、工时填报、回款复核、到货验收、资产处置、报告用章均有 `POST .../submit`），排程方案发布仍按状态机控制。

---

## B6 — 设备预警 / 能耗 / 数字孪生（CSV 67–69）

- **需求要点**：CSV 中这三条**没有详细要求**，仅标注为待开发。
- **依赖前置**：需求方补充说明；B4 设备台账 + B5 排程占用数据。
- **交付物**（待澄清后确定）：设备台账扩展、预警规则与阈值、能耗采集与统计模型、三维/拓扑孪生视图。
- **风险**：能耗与预警通常依赖设备侧数据采集（Modbus/OPC-UA 等），若无采集通道则只能做手工录入看板 —— **落地前必须先问清数据来源**。

---

## B7 — 营收分析看板 + 产能利用率看板（CSV 3、4）

- **需求要点**：营收分析看板需增加营收维度分析，并把风洞 / CFD / 加工三大业务收入拆分（`biz_block` 字典已补 `cfd`）；产能利用率看板包含风洞台次利用率、风洞中心设备利用率、加工中心设备利用率，且须与资产管理平台联动。
- **依赖前置**：B5 的排程/台次数据、B6 的设备台账与占用数据。
- **涉及模块**：`sales`（营收看板）、`production`（产能看板）、`finance`（结算与发票口径）。
- **交付物**：营收维度（业务线 / 合同 / 客户 / 期间）的聚合视图；产能利用率（台次、设备工时）的口径定义与看板。
- **风险**：**收入口径必须先定义清楚**（按合同额还是按结算额确认收入、三条业务线如何归类、跨月任务如何分摊）—— 口径未定就做看板会返工。

---

## B8 — 报告 / 结算 / 安全 / 知识库 / 流程中心 / 人力资源（CSV 24–29、32）

| 项 | 需求要点 | 落点 |
| --- | --- | --- |
| 24 | 安全巡检管理 | `safety` 域：巡检计划、记录、隐患整改闭环 |
| 25 | 报告模板与审批流 | `report` 域：报告模板（类似报价模板设计器）+ 审批定义 |
| 26 | 人力资源管理 | `hr` 域：人员档案扩展；详细要求见需求方 docx（待提供） |
| 27 | 结算对接订单自动计费 | `finance` 域：按合同/任务订单自动生成结算单 |
| 28 | 标准与方法库、体系文件、公司制度、设备操作说明、上墙看板、标志标识标牌 | `ai` 知识库扩展：文档分类与检索 |
| 29 | 参考企微现有流程完成 HMVIC 流程开发，并与业务自动关联（人员是否在岗、早/中/晚班） | 流程引擎 + 考勤数据源 |
| 32 | 作业申请流程：叉车、吊装、高处作业、动火等 | **不需要新模块** —— 用 `OaForm` 表单模板 + `ApprovalDefinition`（`biz_type='oa'`）实现，复用现有 OA 表单设计器与流程引擎；B1 已建「流程与办公 → 作业申请」入口 |

- **依赖前置**：B5（任务/排程数据是结算计费与流程联动的输入）。
- **风险**：报告模板 + 审批流与现有报告封章流程耦合较深，需先在测试库回归报告全链路；结算自动计费涉及金额口径与财务确认流程，必须有可回滚的人工干预入口。

---

## F5 — 全流程驱动 / 业务事件驱动 + 开关面板（已交付）

> **状态：已交付（2026-11-22）** —— 横切批次（非 CSV 条目），把系统从"事后记录工具"改造为**流程驱动 / 数据流转 / 任务流转的驱动器**。
> 内部代号沿用 F 系列（承接 F1 引擎合并 → F2 流程中心 → F3 业务全量流程化 → F4 OA 表单引擎）。

| 项 | 内容 |
| --- | --- |
| 流程注册表 | `app/modules/approval/registry.py`（`FlowBinding` + 16 条 `BINDINGS`）：逐类单据登记流程定义 code、可发起状态、审批中·通过·驳回·撤回四个状态口径、发起权限、通过后钩子；`submit_flow()` / `apply_result()` / `require_manual()` / `flow_enabled()` / `capabilities_out()` |
| 接入流程的单据 | **项目立项**（draft→planning）、**工时填报**（draft→approved）、**回款单**（draft→confirmed）、**到货验收**（draft→accepted）、**资产处置**（draft→approved）、**报告用章**（approved→sealing→seal_approved）；另 10 类历史单据（合同/任务/报告/报价/结算/发票/采购申请/采购合同/定标/OA）纳入同一注册表统一口径 |
| 直通与守卫 | 未配置启用的流程定义 → 按**人工审核口径直通**（`passThrough`），不产生实例；流程总开关关闭 → 禁止提交审批（**70006**）并恢复人工直通后门；流程启用时人工直达端点被拦（**70005**） |
| 事件驱动 | `app/common/events.py` 事件目录扩到 **9 个**（新增 `FlowStarted` `DocumentStatusChanged` `SchedulePlanPublished` `TaskCompleted`）；每个处理器可挂开关键 `event.trigger.<事件>.<处理器>`，`critical=true` 的失败回滚业务事务；跨域联动示例：任务开始执行自动推进项目状态（`event.trigger.TaskAssigned.project.start`） |
| 开关面板 | 后端 `app/modules/settings/automation.py` + `GET/PUT /admin/automation`（`admin:automation:list` / `admin:automation:edit`）；前端 `modules/admin/pages/AutomationSettings.vue`（菜单 `menu.automation`）逐条启停流程总开关与事件触发开关，落 `sys_config` 写入即生效 |
| 流程能力清单 | `GET /approval/flow-capabilities`（**仅登录**）→ 前端 `useFlowCapability()` 据此决定单据页显示「提交审批」还是历史人工动作（验收 / 批准 / 用章） |
| 新增端点 | `POST /project/projects/{id}/submit`、`POST /hr/timesheets/{id}/submit`、`POST /finance/payments/{id}/submit`、`POST /asset/receipts/{id}/submit`、`POST /asset/disposals/{id}/submit`、`POST /report/reports/{id}/seal-apply`（**用章申请与实际签章分离**）、`GET /finance/payments/counts` |
| 错误码 | `70005 APPROVAL_INVALID_STATE`（流程已启用不允许人工直通）· `70006 APPROVAL_FLOW_DISABLED`（流程已停用不允许提交审批） |
| 迁移 | `n6a2b3c4d5e6_flow_driven.py`（仅加列、无新表：`prj_project`/`hr_timesheet`/`ast_disposal`/`ast_receipt` 加 `flow_instance_id`，`fin_payment` 加 `status` + `flow_instance_id`，`rpt_report` 加 `seal_flow_instance_id`；存量回款置 `confirmed`） |
| 前端 | `composables/useFlowCapability.ts`；项目/工时/回款/到货/处置/报告六个列表页新增「提交审批」动作与 `approving`/`rejected` 状态页签（含计数） |
| 测试 | `tests/test_flow_driven.py`（8 条 HTTP 黑盒：开关面板清单、权限强制、流程能力清单、回款计数、流程开关关停 → 70006、人工后门 70005/恢复、缺定义直通、事件开关关停 → 跨域联动停用）；后端全量 `pytest -q` 360 全绿 |

---

## F6 — 对外门户专业化 + 访客预约闭环 + 全站移动优先（已交付）

> **状态：已交付（2026-11-22）** —— 横切批次（非 CSV 条目），来源：需求方对「对外网站太简陋、页面设计和布局不好、访客登记缺失、很多操作手机优先」的一次性反馈。
> 内部代号沿用 F 系列（承接 F1 引擎合并 → F2 流程中心 → F3 业务全量流程化 → F4 OA 表单引擎 → F5 全流程驱动）。

### F6.1 门户基座升级（Portal Pro）

| 项 | 内容 |
| --- | --- |
| 门户首页 | 新增 `PortalHome.vue`（`/portal` 不再是空壳）：品牌 hero + 服务入口宫格 + 最新公告 + 我的进度摘要 |
| 独立外壳 | `PortalLayout.vue` 重做：桌面 sticky 顶栏（品牌/主导航/语言/账号）+ 移动精简顶栏 + `PortalMobileDock.vue` 底部 Dock + 页脚（公司全称/地址/电话/邮箱/备案号，接 `GET /portal/branding`） |
| 移动端表格降级 | 新增 `components/common/ResponsiveTable.vue`：桌面 `el-table`、窄屏（<768px）自动降级为**卡片流**（首列作标题，其余列渲染「标签：值」行）；`ListTable.vue` 改为其适配层 → **约 50 个列表页一次性获得移动卡片降级** |
| 门户页面 | `PortalMy` / `PortalOrders` / `PortalStaff` 三张表改 `ResponsiveTable`；`PortalTenderList` 移动端状态筛选改**底部弹层**；`PortalTenderDetailPanel` 移动端 `label-position="top"` + 主操作**吸底** + 去掉内联 `width:220px`；`PortalRegister` 去掉 `position:fixed` 覆盖层改走门户布局 |
| 认证补强 | `POST /portal/auth/refresh`（refresh token 存 Redis，7 天）+ 前端**单飞 refresh**；401 改 SPA 内 `location.replace`（保表单不丢）；`GET/PUT /portal/account`、`POST /portal/account/password` |
| 招标接口 | `GET /portal/tenders` 加 `page/size` 分页（原先一次拉全量） |
| PWA | `frontend/index.html` 加 `theme-color`（明暗双值）、`apple-mobile-web-app-capable`、`apple-touch-icon`；新增 `public/manifest.webmanifest`（可「添加到主屏」） |
| 令牌 | `--bs-layout-content-max-width`（1200px，门户宽版）、`--bs-layout-portal-bottom-nav-height`（58px） |
| 前端测试 | 新增 `modules/portal/useDeadline.test.ts`（7 条：截止时间解析/天数/紧急阈值纯函数）；扩展 `components/flow/flowModel.test.ts`（FORM_* 审批人类型识别与校验） |

### F6.2 访客预约闭环（门户 ↔ 审批引擎 ↔ 凭证）

| 项 | 内容 |
| --- | --- |
| 门户端点 | 新增 `app/modules/portal/visit_router.py`（prefix `/portal`）：`GET /portal/hosts` · `GET /portal/zones` · `POST /portal/visits` · `GET /portal/visits` · `GET /portal/visits/{id}` · `POST /portal/visits/{id}/cancel` · `GET /portal/visits/{id}/credential` · `GET /portal/visits/{id}/credential/qr` · `GET /portal/visits/{id}/pass?code=` · `POST /portal/visits/{id}/checkin` · `POST /portal/visits/{id}/checkout` |
| 动态审批人 | 审批引擎新增 `FORM_USER` / `FORM_ROLE` / `FORM_DEPT_LEADER` 三类「按表单字段解析」的审批人，`approver_value` 存**流程变量名**（如 `hostUserId`）而非用户 id；可用变量由流程定义 `variables_schema` 声明，设计器给出下拉 |
| 外部发起人 | 引擎新增 `FlowInitiator(id=0, name="合作方·XX")`：`approval_instance.initiator_id = 0`（真实用户 id 从 1 起不冲突），审批中心「我发起的」自然不含外部单据 |
| 流程绑定 | `registry.py` 新增 `FlowBinding(biz_type="visitor_visit")`：`submitFrom=(pending,)`、`approving/approved/rejected` 口径、`passThrough=True`（流程未配置或停用时直通）、`onApproved/onRejected` → `app/modules/visitor/flow_handlers.py`（置状态 + 下发凭证 + 短信通知 + 写 `vis_approval` 镜像行） |
| 人工兜底 | 访客单已挂流程实例时，域内 `POST /visitor/visits/{id}/approve` 返回 **70005**（流程已启用不允许人工直通）；流程停用时恢复 |
| 二维码 | 新增 `app/modules/visitor/qr.py::credential_qr_svg()`（**segno**，纯 Python 零传递依赖）；端点返回 `image/svg+xml`；前端用 `portalHttp` 以 blob 取回再 `URL.createObjectURL`（`<img src>` 不带 Authorization 头） |
| 数据模型 | `vis_visit` 加 `flow_instance_id`（BigInteger, nullable, index）与状态 `approving`；迁移 `n7a2b3c4d5e6_portal_visitor_flow.py`（**手写**，因 `alembic/env.py` 未 import visitor models） |
| 错误码 | 98010 访客预约状态不允许 · 98011 无权访问 · 98012 凭证过期或无效 · 98013 报告下载码无效（前端镜像 `src/api/types.ts`） |
| 前端 | 新增 `PortalVisits.vue`（预约表单 + 我的预约）、`PortalVisitDetail.vue`（审批时间线 + 凭证二维码 + 扫码签到/签离 + 取消）；访客列表页加 `approving` 页签与「去审批」入口；「流程设置」页新增**流程变量**声明与 FORM_* 审批人下拉 |

### F6.3 门户对外经营数据

| 项 | 内容 |
| --- | --- |
| 后端 | 新增 `app/modules/portal/experience_router.py`（prefix `/portal`）：`GET /portal/progress`（委托/任务/结算/发票/回款聚合）· `GET /portal/reports` · `POST /portal/reports/{id}/download-code` · `GET /portal/reports/{id}/download?code=` · `GET /portal/billing` · `GET /portal/handovers` |
| 隔离口径 | 一律按 `partner_user.customer_id` 过滤；报告只暴露 `sealed/seal_approved/approved` 状态，不含内部意见与审批人；**下载码一次性**（Redis `portal_dl:{rid}`，校验后即焚） |
| 前端 | 新增 `PortalProgress.vue` · `PortalReports.vue` · `PortalBilling.vue` · `PortalHandovers.vue`，并在 `PortalHome.vue` 做入口宫格 |

### F6.4 全站移动优先（重点页抽样）

| 项 | 内容 |
| --- | --- |
| 表格卡片降级 | `ResponsiveTable`（见 F6.1）→ 访客 8 页、审批待办、任务列表等约 50 个列表页自动获得卡片流 |
| 审批待办 | `ApprovalActionbar.vue` 窄屏按钮改 2×2 网格 + **吸底**（`env(safe-area-inset-bottom)`）；`TodoList.vue` 补卡片底部操作槽 |
| 流程图 | `FlowGraphViewer.vue` 窄屏**默认折叠**为「点击展开」（LogicFlow 画布在小屏需横向拖拽；隐藏容器尺寸为 0，`fitView` 会失效 → 懒初始化 + 折叠时销毁） |
| 详情页 | `ContractDetail.vue` / `TaskDetailPanel.vue` 的 `el-descriptions` 窄屏改单列；任务明细表改 `ResponsiveTable` |
| 签字 | 新增 `components/common/SignaturePad.vue`（canvas Pointer-Events 手写板，触摸/鼠标/手写笔通用，输出 PNG dataURL）；`NdaList.vue` 的 NDA 签署由文本框改手写板 |
| 状态标签 | `StatusTag.vue` 补 `visiting` / `left` / `overdue` / `cancelled` 四个访客状态色 |
| 样式 | `mobile.css` 补分页窄屏折叠（只留 prev/pager/next）、`el-descriptions` 单列、`.el-pagination` 换行 |

### F6.5 验证

| 范围 | 结果 |
| --- | --- |
| 后端 | `tests/test_f6_portal_visit.py`（9 条）· `tests/test_f6_portal_experience.py`（5 条）· `tests/test_f6_portal_guard.py`（10 条）；后端全量 `pytest -q` 386 全绿 |
| 前端 | `pnpm lint` / `typecheck` / `i18n:check`（24 域键集一致，2425 个使用键全部有定义）/ `test:unit`（52 全绿）/ `build` 全绿 |

### F6.6 遗留

- 门户尚未对接**微信/小程序原生入口**（当前是可在微信内打开的 H5 + 「添加到主屏」PWA）。
- 访客短信通道依赖 `msg.sms.custom.url` 配置，未配置时**静默跳过**不阻断业务（访客可在门户页面直接看到状态）。
- 报告下载码目前为**单次有效**，未做「有效期 + 次数」策略。

---

## B9 — 检测机构合规基线落地 + 人员能力授权纵切（CSV 1、26）

> **状态：已交付（2026-11-23）** —— 来源：需求方把《第三方检测机构运营平台合规开发原则.docx》与《第三方检测机构运营平台_人力资源管理模块功能说明.docx》（V1.0，CMA/CNAS/TISAX）放到仓库根目录，要求"分析并展开核查与进化"。
> 这两份是路线图里**唯二挂着"等文档"的两条线**。本批次把文档逐条吃进来、核对现状、落地**三个最有杠杆的控制点**（审计证据链 / 电子签名密码学绑定 / 人员授权台账），其余写进 B10 排期。

### B9.1 核查结论

《合规开发原则》共 20 余条控制要求，逐条核对现状后识别出 **4 个核心缺口**（详见 [`docs/compliance-baseline.md`](compliance-baseline.md)）：

| 缺口 | 文档要求 | 原状 |
| --- | --- | --- |
| 审计追踪非字段级 | 谁/何时/哪表/**哪字段**/**旧值→新值**/原因/终端/IP | `sys_audit_log` 只有 `detail(JSON)` 汇总；`trace_id` 参数全仓 283 处调用点无人传值 |
| 审计日志可删改 | WORM / 哈希链 / 不可清空 | `AuditLog` 继承 `BaseModel` → 带 `deleted`/`version`，**可软删**；全仓零哈希链；`sys_audit_log` / `vis_access_log` / `vis_nda` **都在「一键清空」清单里** |
| 电子签名无密码学绑定 | 禁图片章、代签 | 全仓零密码学签名；`vis_nda.evidence_hash` 是**无密钥 sha256**（可离线复算），`ip=""` 硬编码为空；报告用章是 pypdf 文字水印占位 |
| 职责分离（SoD）无落地 | 检测/复核/批准/系统管理四权分立 | 无角色互斥；`report_sign` 种子是单级；`rpt_report` 无编制/复核/批准字段 |

HR 模块文档 L1–L5 共 35 个菜单，`hr` 域原状**只有 `hr_timesheet` 一张表**，`StaffList.vue` 是占位页。

### B9.2 已交付

| 项 | 内容 |
| --- | --- |
| **C1 审计证据链** | `AuditLog` 改继承只追加基类 `AppendOnlyModel`（**物理删** `deleted`/`version`/`update_time`/`update_by`），新增字段级列 `field_name` `old_value` `new_value` `reason` `user_agent` + 链列 `chain_seq`（唯一索引）`prev_hash` `row_hash` `hash_alg`；`create_time` 精度提为 `DATETIME(3)`（哈希含毫秒时间戳，秒精度必算错） |
| | 新表 `sys_audit_chain_head`（单行 `chain_key='main'`，**链头是唯一权威游标**，不用 `MAX(id)` —— 并发下必然分叉）与 `sys_audit_failure`（只追加，写失败台账） |
| | `common/audit.py::record()` 保持全部旧参数并新增 keyword-only 默认参数 → **283 处调用点零改动**；链头 `SELECT ... FOR UPDATE NOWAIT` 拿不到锁立即失败（不挂死业务）；`sys_config` 开关 `audit.strict.enabled` 控制是否回滚业务事务 |
| | 链校验 `verify_chain(db, mode='full'\|'since_anchor')` 逐行校验四件事：① `chain_seq` 连续 ② `prev_hash` 相连 ③ 重算 `row_hash` ④ 链头与末行一致；存量行 `chain_seq IS NULL` 计入 `legacyRows`，**不回填历史哈希**（不伪造历史） |
| | 锚定写 **DB 之外的文件** `backend/data/audit-anchor/anchor-YYYYMMDD.txt`（只追加，每行 `seq\|hash\|ts\|hmac`）→ 用于发现整链被重写/截断；写入时机 = 备份成功后 + 手动端点 |
| | 「一键清空」移除 `sys_audit_log` / `vis_access_log` / `vis_nda`，新增 `RETAINED_AUDIT_TABLES` 常量并在返回体 `retainedAuditTables` 里公开 |
| | 物理加固：迁移里加 `BEFORE UPDATE` / `BEFORE DELETE` 触发器 `SIGNAL SQLSTATE '45000'` 阻断改删（测试库由 `create_all` 建表无触发器，测试不依赖触发器） |
| **C2 电子签名密码学绑定** | 新增 `core/signature.py`：HMAC-SHA256 签名/验签，密钥 `sha256("bizsys:evidence-signature:" + jwt_secret)`（与 `crypto.py` 同源、域分隔前缀不同），`canonical(payload)` 按**固定字段序**生成 `name=value\n` 串，`compare_digest` 比对；字段组 `NDA_FIELDS` / `REPORT_SEAL_FIELDS` |
| | NDA：签名绑定 `biz_type + nda_no（单号，稳定可复算）+ 姓名/单位/证件号/标题 + 签署时间 + 签署人 id/姓名 + 真实 IP + 手写图 sha256`；`ip=""` 硬编码改为从请求上下文取真实 IP；存量行标 `legacy-sha256`，验签返回 `verdict="legacy-unverifiable"`（旧哈希无密钥、离线可复算，**不能当密码学证据**） |
| | 报告用章：新增 `seal_by_name` `seal_content_hash` `seal_signature` `seal_alg` + 三级角色 `preparer/reviewer/approver` 的 id/name 列；**内容哈希必须在 `apply_seal_watermark()` 之后算**（盖章会产出新 PDF，先算必然对不上）；文件缺失返回 `""` 并在验签端点返回 `contentUnavailable`（签名本身仍可验） |
| | 签章后锁定：`report/service.py::assert_report_editable()`，`status == 'sealed'` 抛 **61003**；统一挂到 `update_remark` / `update_conclusion` / AI 摘要采用 / AI 辅助采用路径 |
| **C3 人员授权台账** | 新表 `hr_authorization`（继承 `BaseModel`）+ `hr_authorization_event`（继承 `AppendOnlyModel`，只追加）；维度四列 `scope_method` / `scope_params` / `scope_device_id`+name / `scope_domain` **显式建模可索引**，`scope_json` 只是展示兜底**不做过滤依据**（避免"快照里恰好有值"这种隐性授权） |
| | 状态机 `draft→confirmed→active⇄suspended→expired/revoked`（+ `approving`/`rejected` 审批态）；**暂停 / 撤销 / 过期原因必填**；非法跃迁一律拒绝 |
| | `check_authorization()` 单条 SELECT 走复合索引，作用域在 Python 侧匹配（记录维度为空 = 该维度不限；**授权有值但请求未带该维度 → 不匹配**）；请求内 memo（`db.info`）避免重复打库；**不做跨请求缓存**（撤销必须立即生效） |
| | `assert_authorized()` 统一拦截入口 —— **超管（`role_code=super`）旁路** + `sys_config` 双开关 `auth.enforce.report` / `auth.enforce.task`（默认开）+ 越权抛 **63007** |
| | 拦截点前置：**报告编制**、**报告用章**、**检测进度录入**、**任务派工**四处；每次状态变更写**字段级**审计（`field_name='status'` / `old_value` / `new_value` / `reason`，`strict=True`） |
| | **SoD 动态探测**（不改流程定义）：`resolve_report_roles()` 从签批实例的 `approval_record` 取通过序列 → 编制/复核/批准；`node_count >= 2` 时**硬拦截**（三人不得同人 + 各自持对应角色授权），否则降级告警写审计。管理员在「流程设置」给 `report_sign` 发新版本加节点 → `flow_version` 递增 → 自动变硬拦截，**代码零改动** |
| | 流程接入：`registry.py` 新增 `FlowBinding(biz_type="hr_authorization")`，`pass_through=False` → **授权不允许绕过审批**（未配流程定义时提交直接报错） |
| | 新端点（prefix `/hr`，`hr/authorization_router.py`）：列表 / counts / 导出 / options/users / 详情 / **timeline** / **state-at**（回放任一历史时点状态）/ 新建 / 编辑 / submit / activate / suspend / resume / revoke / expire |
| **种子** | `MENU_TREE` 新增 `menu.authorization`（「行政人事 → 人员授权」，图标 `Key`，权限 `hr:authorization:list` + 按钮 create/edit/submit/approve/activate/revoke/export）；新增角色 `hr_manager`（人事管理员，挂全部 `hr:authorization:*`），`biz_user` 只加 `hr:authorization:list`（**授权管理属质量/人事职责，与检测员职责分离**）；新增演示账号 `tech1` / `qa1` / `hr1`；新增流程 `hr_authorization_approve`（科室负责人 → 技术负责人 → 质量负责人，**固定 USER 节点**而非 ROLE 节点 —— 无人拥有该角色时引擎会"解析失败自动跳过"，审批形同虚设）；编号规则新增 `AU` |
| **前端** | 新增 `modules/hr/pages/AuthorizationList.vue`（检索 + 8 状态页签含计数 + 明细表 + 详情抽屉（变更轨迹时间线 + **时点回放**）+ 新建/编辑弹窗「保存草稿 / 提交审批」双按钮）；`modules/admin/pages/AuditLogList.vue` 补字段级列 + **链校验面板**（全量/自锚点、断链定位、锚定、证据详情与重算哈希比对）；`NdaList.vue` / `ReportList.vue` 补**验签**入口与结论弹窗（存量 NDA 打灰标提示不可密码学验证） |
| **迁移** | `n8a2b3c4d5e6_audit_chain_evidence.py`（审计表改精度+增列+DROP 4 列、建链头/失败台账、`vis_nda` 5 列 + 存量标 legacy、`rpt_report` 10 列、只追加触发器）· `n9a2b3c4d5e6_hr_authorization.py`（**手写**建 `hr_authorization` + `hr_authorization_event` —— `alembic/env.py` 未 import hr 域 models，autogenerate 会删表） |
| **测试** | `tests/test_c1_audit_chain.py`（链连续 / 直接 UPDATE 检出 `row_hash_mismatch` / 删中间行 → `seq_gap` / 删尾部行 → 锚点 `truncated` / 改链头 → `head_mismatch` / 字段级落库 / UA-IP 自动补 / 无写接口 / strict 回滚）· `tests/test_c1_purge_retains_audit.py`（purge 前后审计行数不减）· `tests/test_c2_signature.py`（签名往返 / 改 payload 验签失败 / NDA 新字段落库 + verify 有效 / 存量行 `legacy-unverifiable` / 报告签章 `signatureValid & contentMatch` / 签章后改结论 → `contentMatch=false` / 签章后改 remark → 61003）· `tests/test_c3_authorization.py`（状态机全路径 + 非法跃迁 / 原因必填 / 事件表只追加 / `state_at` 回放 / 授权命中未命中过期 / 超管旁路 / 开关旁路 / SoD / 四处拦截点 / 审批联动 / 台账接口） |
| **修复** | `init_data.py` 新增 `_repair_user_nodes()` **自愈**：演示账号被删后重建 → 用户 id 变化 → 流程节点里存的旧 id 解析不到人 → 提交审批报"节点未配置可用审批人"，整条审批链卡死（测试库「一键清空」用例、生产账号重建都会触发）。按种子声明的**用户名**把**已失效**节点重指到当前用户 id；**只修失效节点**（管理员在「流程设置」改过的有效节点不动） |

### B9.3 验证

| 范围 | 结果 |
| --- | --- |
| 后端 | `uv run ruff check app tests` 通过；`uv run pytest -q` **424 全绿** |
| 前端 | `pnpm lint` / `typecheck` / `i18n:check`（24 域键集一致）/ `scan:literal:strict` / `scan:colors` / `test:unit` / `build` 全绿 |

### B9.4 遗留（转 B10）

见下节 B10。

---

## B10 — HR L1–L5 + 质量体系域（进行中）

> **状态：进行中（2026-11 起）** —— B9 落地了 HR 的**L2 技术能力与授权**（授权台账 + 拦截点），
> **B10-1 已交付 L1 基础人事**，其余层按下列排期推进。

| 批次 | 范围 | 依据 | 关键交付 | 状态 |
| --- | --- | --- | --- | --- |
| **B10-1** | HR L1 基础人事 | docx L1 | 组织架构（`sys_dept` 扩展）/ 岗位 / 员工主数据（`sys_user` 的 `employee_no`/`hire_date` 从"预留"转正式）/ 入职调岗离职返聘 / AB 角代理人 | **已交付** |
| **B10-2** | HR L2 技术能力（一人一档证书） | docx L2 | 证书台账（`hr_certificate`：证书编号 / 签发机构 / 有效期 / 附件）/ 能力矩阵（岗位 ↔ 证书 ↔ 授权的映射）/ 与 B9 授权台账的联动校验（持证才能授权）/ 续期预警 | 排期中 |
| **B10-3** | HR L3 质量体系活动 | docx L3 | 培训记录 / 人员监督（技术监督活动）/ 能力监控（持证与授权的续期预警）/ 绩效工作量（与工时汇总打通） | 排期中 |
| **B10-4** | HR L4 合规与安全 | docx L4 | 背景调查登记 / 保密等级（`sys_user` 加密级）/ 外部人员（复用 `crm_partner_staff`）/ 审计追溯界面（复用 B9 证据链） | 排期中 |
| **B10-5** | HR L5 分析与集成 | docx L5 | 合规仪表盘（授权覆盖率 / 持证率 / 培训完成率 / 在职率）/ 报表中心 / 评审证据包（一键导出人员能力包）/ LIMS-OA-IAM 集成对接点 | 排期中 |
| **B10-6** | 质量体系域（新建） | 合规原则 2.5 / 质量体系文件 | 不符合项 / CAPA（纠正与预防措施）/ 内审 / 管理评审 / 标准方法库 / 设备校准台账 / 环境监控 / 质控盲样 / 样品条码全链路 | 排期中 |
| **B10-7** | 数据权限与字段级权限 | 合规原则 3.4 | `sys_role.data_scope` 落地（当前是**死字段**，无任何查询消费）/ 字段级可见与可改控制 | 排期中 |

**B10 的前置依赖**：B9 的 `hr_authorization` 台账与 `assert_authorized()` 拦截点是 L2/L3/L4 的底座 —— 能力监控、离岗清权、评审证据包都建立在"授权可查、可回放、越权可拦"之上。
**B10-1 已把「离岗清权」从 B10-4 提前落地**：离职生效时批量撤销 B9 授权（`effect_employment()`），
B10-4 只需补**背景调查与保密等级**两侧。

**本批次不做（长期外部依赖）**：CSV（IQ/OQ/PQ 验证方案）、门禁/LIMS 真实厂商对接、备份恢复演练、UPMS 统一权限中心对接。

### B10.1 — HR L1 基础人事（已交付，2026-11-23）

> 用户定调：**"组织架构和员工主数据是所有内容的基石和起点，和当前的部门/用户/角色整合起来，一起先完成"**。
> 本批次把 `sys_dept` / `sys_user` / `sys_role` 三张既有表**整合进一张组织树**，一次做完整 L1。

**建模决策**（用户确认）

| 问题 | 决策 |
| --- | --- |
| 员工主数据与 `sys_user` 怎么建模 | **独立 `hr_employee` 表，1:1 关联 `sys_user`**（HR 域隔离，`sys_user` 仍是认证主源，`hr_employee` 是 HR 主源，联动同步） |
| 组织架构怎么落地 | **扩展 `sys_dept` + 新建 `hr_position`**（单一组织树无双轨；**部门写入口只有 `/admin/depts`**） |
| 本批次做到哪一步 | **组织架构 + 员工主数据 + 人事事务 + AB 角**（一次做完整 L1） |
| 敏感个人信息怎么存 | **AES-GCM 加密存储 + 脱敏展示**（域 `hr-employee-idno`，与配置密钥/签名密钥域分隔） |

**已交付**

| 项 | 内容 |
| --- | --- |
| **组织架构** | `sys_dept` 扩 6 列（`dept_type` / `site_code` / `address` / `manager_id` / `effective_from` / `effective_to`）；新表 `hr_position`（岗位说明书 + 关键岗位 `key_role` + A/B 角）；新表 `hr_org_change`（**只追加**的部门/岗位变更快照） |
| **员工主数据** | 新表 `hr_employee`（一人一档，`id_no` 加密落库）+ `hr_employee_control`（黑白名单）；`sys_user.employee_no` / `hire_date` 转**从 HR 同步的冗余列**（以 HR 档案为准） |
| **人事事务** | 新表 `hr_employment`（单号 `EM`）+ `hr_employment_event`（只追加轨迹）；状态机 `draft→approving→approved→effective` / `rejected` |
| **AB 角代理人** | 新表 `hr_delegate`（`scope` = 岗位/授权/任务；**不借账号**；委托人离岗自动 `expired`） |
| **审批接入** | `registry.py::BINDINGS` 第 **19** 条 `biz_type="hr_employment"` / `definition_code="hr_employment_approve"` / **`pass_through=False`**（人事事务不允许人工直通） |
| **关键设计：审批通过 ≠ 生效** | 离职需**择时生效**（离职当日清权），故副作用统一由 `POST /hr/employments/{eid}/effect` → `effect_employment()` 触发 |
| **离职清权（本批次最重要的落点）** | 禁号（`sys_user.status=disabled`，**不删除**保 ALCOA 完整）+ 撤 MFA + **撤销 B9 授权台账**（批量 `revoked` + 写 `hr_authorization_event`）+ 代理失效 + 清岗位 A/B 角；**物理权限（门禁/钥匙/工牌）无对接 → 写「待现场确认」审计，诚实标注外部依赖** |
| **敏感信息** | 证件号 AES-GCM 加密落库；出参一律掩码（前 4 + 后 4）；**明文唯一出口** `GET /hr/employees/{eid}/id-no`（权限 `hr:staff:idno`，**每次访问写审计**） |
| **迁移** | `na2b3c4d5e6_hr_l1_org_employee.py`（`sys_dept` 加列 + 建 7 张新表）· `nb2b3c4d5e6_hr_employment_account.py`（`hr_employment` 开账号 4 列）—— **全手写**（`alembic/env.py` 未 import hr 域 models，autogenerate 会删表） |
| **前端** | 新增 `hr/OrgStructureList.vue`（左树 + 右岗位清单 + 变更轨迹时间线）· `hr/PositionList.vue`（岗位 + 说明书 + 关键岗位 + A/B 角）· `hr/PersonnelAffairsList.vue`（事务列表 + 生效动作 + 代理人抽屉）· `hr/StaffList.vue`（**占位页替换为真实员工档案**） |
| **测试** | `tests/test_b10_1_hr_l1.py` —— 11 个用例（部门扩展字段 / 岗位 CRUD + 关键岗位 / 变更轨迹 / 证件号加密掩码 + 明文出口留痕 / 建档冲突 + 黑名单 / 入职流 / 调岗流 / 离职清权 / 状态守卫 / 代理生命周期 / 删除阻断） |

**验证**

| 范围 | 结果 |
| --- | --- |
| 后端 | `uv run ruff check app tests` 通过；`uv run pytest -q` 全绿 |
| 前端 | `pnpm lint` / `typecheck` / `i18n:check` / `scan:literal:strict` / `scan:colors` / `test:unit` / `build` 全绿 |

**遗留（转 B10-2 及以后）**：`hr_employee` 尚未接**一人一档证书**（L2）；`job_level`（职级）仍是 admin 域维护的死字段；
`sys_user` 与 `hr_employee` 的**双向同步只做单向**（HR → 认证），认证侧改 HR 档案会以 HR 为准；
门禁/工牌物理权限**无对接**（已写待确认审计）。

---

## 通用注意事项

- **新增表必须手写 Alembic 迁移** —— `alembic/env.py` 只 import 了 9 个模型的 metadata，autogenerate 会误删表。
- **权限码遵循 `module:resource:action`**，服务端强制校验，特权操作写入 `sys_audit_log`。
- **每个新接口路径补一条后端测试**（`backend/tests/test_*.py`），每个 bug 修复补一条回归测试。
- **前端页面必须带检索与计数** —— 服务端分页列表要有 `q` 关键词与页签计数（`all` 页签最左）。
- **文案一律走 i18n**，中英键集保持一致；颜色一律走 `--bs-*` 令牌。

## 验证命令

```bash
# 前端
cd frontend
pnpm token:build && pnpm i18n:check && pnpm scan:literal:strict && pnpm scan:colors
pnpm lint && pnpm typecheck && pnpm test:unit && pnpm build

# 后端
cd backend
uv run ruff check app tests
uv run pytest -q
uv run python -m app.seeds.init_data
uv run python scripts/migrate_nav_zones.py   # 存量库导航结构迁移（幂等）
```

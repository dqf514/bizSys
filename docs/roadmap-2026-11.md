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

外部依赖项（不排入批次）：**第 1 项**「运营平台合规开发原则」与**第 2 项**「SSO / 统一权限中心（UPMS）」均指向需求方提供的 docx，文件未入库，落地前需先拿到原文；第 2 项同时涉及外部身份系统对接，需单独立项。

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
- **遗留**：① 多渠道预约的**外部渠道入口**（微信/小程序）尚未对接，当前统一为前台/员工代登记 + 门户预登记（B2 的 `crm_partner_staff`）；② 门禁/视频/LIMS/消防的**厂商接口**未接入，凭证核验已提供 `POST /visitor/credentials/verify` 作为对接点；③ 访客审批走**域内审批链**（host→dept→zone）而非通用流程引擎 `ApprovalDefinition`，以便与区域分级策略强绑定。

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
- **遗留**：① 排程目前是**规则式贪心**，未引入求解器；跨项目、跨设备族的复杂约束（换型时间、模具/工装、批次合并）尚未建模，B6 设备台账接入后可再评估；② 项目甘特的**任务依赖（`depends_on`）**已落字段但未做关键路径计算；③ 项目/排程单据目前**未接入审批引擎**（仅靠状态机与权限点控制），与"全流程驱动"目标存在差距，列入后续流程贯通批次。

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

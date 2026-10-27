# 采购管理模块设计（一期）

> 版本：v1.0（一期）· 状态：设计 + 实施基线
> 关联文档：`docs/api-contract.md`（接口契约）、`docs/adr/`（架构决策）、`开发需求文档-MVP.md`

## 1. 背景与目标

现有系统已覆盖「客户 → 合同 → 任务 → 报告 → 财务（结算/开票/到账）」的收入侧闭环，但**支出侧（采购）**完全缺失：供应商信息散落在客户表之外的线下台账，采购申请、采购合同、物资出入库均无系统化承载，无法回答"这个任务的物料成本是多少""这家供应商供过哪些货"。

采购管理一期的目标是把支出侧的最小闭环搬上线：

```
往来单位(供应商) → 采购申请 →(审批)→ 采购合同 →(会签)→ 入库/出库 → 任务成本可追
```

设计原则：

1. **复用不重造**：审批走统一审批引擎（含会签 sign_mode），编号走编号规则中心，枚举走字典中心，权限/菜单走菜单驱动的权限点体系，事件回写走进程内事件总线（ADR-0002）。
2. **往来单位统一**：供应商不新建平行档案表，扩展现有 `crm_customer` 为「往来单位」（客户/供应商/两者皆是），保证纳税识别号、银行账户等主数据只维护一份。
3. **一期最小可用**：申请→合同→出入库三单据 + 双向互跳；招投标、询价比价、财务挂接（应付）留二期。

## 2. 需求结构化

| # | 需求 | 一期方案 |
|---|------|---------|
| 1 | 供应商档案统一管理 | `crm_customer` 扩展 `partner_type`（customer/supplier/both）+ 供应商分类/评级字段，菜单更名「往来单位」 |
| 2 | 采购申请（含任务关联） | 新单据 `pur_request` + 明细行，可挂任务（task_id）或为通用采购；两级顺序审批 |
| 3 | 采购合同会签 | 新单据 `pur_contract`，由已通过的申请生成；会签节点（sign_mode=and，多人同时持有待办、全员通过） |
| 4 | 物资出入库 | 新单据 `pur_stock_order` + 明细行，registered→confirmed 两态（登记→确认），不做审批流 |
| 5 | 菜单/权限/路由 | 「业务系统」下新增「采购管理」目录，三个列表页 + 按钮级权限点，全部走菜单驱动 |
| 6 | 详情互跳 | 申请↔合同、合同↔出入库单、往来单位↔采购单据，前端详情页深链互跳 |
| 7 | 招投标 | 二期：在申请前插入「采购方式=公开招标」时的标讯/评标子流程（见 §9） |

## 3. 领域模型

表前缀统一 `pur_`；全部继承 `BaseModel`（id / create_time / create_by / update_time / update_by / version 乐观锁 / deleted 逻辑删除）。

### 3.1 往来单位（crm_customer 扩展）

| 字段 | 类型 | 说明 |
|------|------|------|
| partner_type | String(16) | `customer`（默认）/ `supplier` / `both`，加索引 |
| supply_category | String(32) | 字典 `supply_category`（供应商主营分类，仅供应商用） |
| supplier_rating | String(8) | 字典 `customer_grade` 复用 A/B/C/D（供应商评级，仅供应商用） |

存量数据迁移：全部置 `customer`，行为不变。`GET /crm/customers/options` 增加 `partner_type` 查询参数：`supplier` 过滤 `partner_type IN (supplier, both)`，`customer` 过滤 `IN (customer, both)`，缺省不过滤（兼容现有合同/任务选择器）。

### 3.2 采购申请 pur_request

| 字段 | 类型 | 说明 |
|------|------|------|
| request_no | String(32) nullable unique | 编号 PRyyyymmddNNNN，提交审批时发放（draft 为空，同合同模式） |
| title | String(255) | 申请标题 |
| task_id | BigInteger nullable | 关联任务（null=通用采购），加索引 |
| task_no / task_name | String 冗余 | 列表免 join |
| purchase_method | String(32) | 字典 `purchase_method`：询价/单一来源/竞争性谈判/公开招标 |
| budget_amount | Numeric(14,2) nullable | 预算金额 |
| expect_date | Date nullable | 期望到货日期 |
| reason | Text nullable | 采购事由 |
| remark | Text nullable | 备注 |
| status | String(16) | `draft → approving → approved / rejected`；voided（作废） |
| flow_instance_id | BigInteger nullable | 统一审批实例 |

明细 `pur_request_item`：request_id(FK)、item_name、spec（规格型号）、unit、quantity Numeric(12,2)、estimate_price Numeric(14,2) nullable、remark。cascade delete-orphan + lazy selectin（同合同附件模式）。

状态机约束（与合同一致）：仅 draft/rejected 可编辑、删除（删除仅限 draft）；approving 禁编辑；提交审批行锁 + 发编号 + `approval.start`。

### 3.3 采购合同 pur_contract

| 字段 | 类型 | 说明 |
|------|------|------|
| contract_no | String(32) nullable unique | 编号 CGyyyymmddNNNN，提交审批时发放 |
| name | String(255) | 合同名称 |
| request_id | BigInteger nullable | 来源采购申请（可空，允许直接建合同），加索引 |
| supplier_id | BigInteger | 供应商 = crm_customer.id（partner_type ∈ supplier/both），加索引 |
| supplier_name | String(128) | 冗余 |
| amount | Numeric(14,2) | 合同金额 |
| sign_date / start_date / end_date | Date nullable | 签订/履行起止 |
| pay_cycle / delivery | String(32) | 复用字典 pay_cycle / delivery_way |
| handler_id / handler_name | 经办人 | 同销售合同 |
| remark | Text nullable | |
| status / flow_instance_id | 同申请状态机 | |

审批差异：**会签**。种子定义 `purchase_contract_approve` 第一节点 `sign_mode="and"`、approver_type=USER、approver_value="manager1.id,leader1.id"（CSV），第二节点分管领导终审（sequential 单签）。引擎已支持 CSV 多人 + and 语义：全员同时持有待办、全员通过节点才算过。审批通过后可发起出入库。

### 3.4 出入库单 pur_stock_order

| 字段 | 类型 | 说明 |
|------|------|------|
| order_no | String(32) unique | 登记即发放：RK…（入库）/ CK…（出库） |
| order_type | String(8) | `in` / `out`，加索引 |
| contract_id | BigInteger nullable | 关联采购合同（仅 approved 可选），加索引 |
| warehouse | String(32) | 字典 `warehouse` |
| handler_id / handler_name | 经办人 | |
| order_date | Date | 出入库日期 |
| remark | Text nullable | |
| status | String(16) | `registered → confirmed`（确认后只读）；无审批流 |

明细 `pur_stock_item`：order_id(FK)、item_name、spec、unit、quantity、price nullable、remark。确认（confirm）为幂等动作：行锁 + 状态校验，确认后单据与明细只读。预留 `source_type/source_id` 扩展位（二期接招投标结果/资产台账）。

**样品出入库统一进本流程（source_type=sample）**：任务样品的入/出库动作不再直接翻转 `task_sample.in_stock`，而是登记生成 StockOrder（明细 item_name=样品名、spec=型号、remark 带 VIN/样品编号，source_id=样品 id，RK/CK 编号登记即发）。确认前样品在样品管理页/任务详情显示「入库确认中/出库确认中」徽标（由查询派生 `pendingOrder`：source_type=sample + status=registered 的最新单，不落字段）；采购侧 confirm 同事务回写 `in_stock` 并补写 `task_sample_flow` 流水（样品已删/已在目标状态则整体回滚）；确认前可经 `POST /task/samples/{sid}/stock-cancel` 取消登记（逻辑删单，样品状态不变）。防重：同一样品仅允许一张未确认单（60001）；有待确认单时 `PUT /task/samples/{sid}` 与任务整体编辑均禁止直改 in_stock、禁止删除样品。出入库列表 `filters[source_type]=purchase|sample` 按来源筛选（purchase 含历史空来源），样品单输出补挂 sampleNo/sampleName/vin/taskId/taskNo/taskName 支持互跳；导出含来源/来源单据列。历史样品数据不动（旧 in_stock 原样保留）。

## 4. 与平台能力的整合点

| 能力 | 接入方式 |
|------|---------|
| 统一审批引擎 | `POST …/submit`：行锁 → 状态校验 → 发编号 → `approval_svc.start(biz_type, definition_code, title, initiator, form_snapshot, variables)`；service 订阅 `ApprovalCompleted/Rejected/Withdrawn` 按 biz_type 过滤回写状态（completed→approved、rejected→rejected、withdrawn→draft）。biz_type：`purchase_request` / `purchase_contract` |
| 会签 | `ApprovalNode.sign_mode="and"` + `approver_type="USER"` + `approver_value="id1,id2"`（引擎现成）；种子 `_seed_flow` 节点条目扩展支持 dict 形态 `{seq, name, users:[...], sign_mode:"and"}` |
| 编号规则 | `NUMBER_RULES` 新增：`purchase_request`=PR、`purchase_contract`=CG、`stock_in`=RK、`stock_out`=CK（均 yyyymmdd+4 位、按日重置，与现有单据一致） |
| 字典 | `DICTS` 新增：`purchase_method`（询价 inquiry/单一来源 single_source/竞争性谈判 negotiation/公开招标 public_bid）、`supply_category`（设备 equipment/耗材 consumable/服务 service/其他 other）、`warehouse`（一号仓库 wh1/二号仓库 wh2） |
| 权限 | `procurement:request:list/create/edit/submit/delete/list:export`、`procurement:contract:*`（同构）、`procurement:stock:list/create/confirm/delete/list:export`，挂菜单权限点，biz_user 角色全量重挂 |
| 菜单 | MENU_TREE「业务系统」下新增 `menu.procurement` 目录（图标 ShoppingCart）：采购申请 PurchaseRequests /procurement/requests、采购合同 PurchaseContracts /procurement/contracts、出入库 StockOrders /procurement/stock；`_seed_menus` 幂等补齐 |
| 审计 | 全部写动作走 `audit()`：module=procurement，action=purchase_request_create/submit/… |
| 错误码 | response.py 新增 95xxx 段：PROCUREMENT_INVALID_STATE 95001、PROCUREMENT_SUPPLIER_INVALID 95002、PROCUREMENT_REQUEST_NOT_APPROVED 95003 |

## 5. 事件驱动闭环

```
申请 submit ──▶ approval.start(purchase_request) ──▶ 会签/顺序审批
     ◀── ApprovalCompleted/Rejected/Withdrawn ── 回写 pur_request.status
申请 approved ──▶ 「生成采购合同」端点：复制明细汇总 + 选定供应商 → pur_contract(draft)
合同 submit ──▶ approval.start(purchase_contract) ──▶ 会签节点(and) ─▶ 终审
     ◀── 事件回写 pur_contract.status
合同 approved ──▶ 出入库登记（registered）──▶ confirm（confirmed，只读）
```

事件总线为进程内同步（与业务写入同事务，ADR-0002），一期不引入 Outbox。审批待办通知复用现有 `ApprovalTodoCreated` 订阅链（站内 + 企微占位），采购模块零新增。

## 6. API 一览（前缀 /api/v1/procurement）

| 端点 | 权限 | 说明 |
|------|------|------|
| GET /requests · /requests/counts · /requests/{id} | procurement:request:list | 列表（q/status/filters/range/sort 白名单）· 页签计数（all 最左）· 详情含审批 timeline |
| POST /requests · PUT · DELETE /{id} | create/edit/delete | 删除仅 draft |
| POST /requests/{id}/submit | submit | 行锁 + 发 PR 编号 + 启动审批 |
| POST /requests/{id}/void | edit | 作废（approving 需先撤回） |
| POST /requests/{id}/generate-contract | procurement:contract:create | 已批准申请 → 生成采购合同草稿（幂等：一申请一合同） |
| POST /requests/export | list:export | xlsx |
| GET /contracts · counts · {id}；POST/PUT/DELETE；POST /{id}/submit · /void；POST /export | procurement:contract:* | 同构；会签定义 purchase_contract_approve |
| GET /stock-orders · counts · {id}；POST/PUT/DELETE；POST /{id}/confirm；POST /export | procurement:stock:* | confirm 后只读；删除仅 registered；filters[source_type] 按来源筛选；样品单 confirm 回写 task_sample |

CRM 变更：`GET /crm/customers` 过滤白名单 +`partner_type`；`GET /crm/customers/options?partner_type=supplier|customer`；`CustomerIn`/`_out` +3 字段；导出模板 +`partnerType` 列。

## 7. 前端

- `src/api/procurement.ts` + `src/modules/procurement/pages/{PurchaseRequestList,PurchaseContractList,StockOrderList}.vue`，严格沿用批次D/G 列表规范：ListPage + SearchBar(q) + StatusTabs（all 最左 + counts）+ ListTable（白名单排序）+ ActionBar + ExportButton + BackButton + 抽屉内置 X + footer 次左主右。
- 往来单位页（crm/CustomerList）SearchBar 增加「单位类型」select（filters[partner_type]），表单增加类型/供应分类/评级；菜单文案 zh「往来单位」/ en「Partners」（menu.customer 键不变，仅改文案）。
- 详情互跳：申请详情 → 生成/查看合同；合同详情 → 来源申请、出入库单列表链接；出入库详情 → 合同。
- i18n：新增 `locales/{zh-CN,en-US}/procurement.json`，`i18n.ts` 注册第 14 个 domain；menu.json 增加 menu.procurement* 键。

## 8. 数据迁移与种子

1. Alembic 新迁移（head: b1c2d3e4f5a6 → 新 rev）：`crm_customer` 加 3 列（partner_type 默认 'customer'、索引）；新建 `pur_request` / `pur_request_item` / `pur_contract` / `pur_stock_order` / `pur_stock_item` 五表。
2. 种子 `init_data.py`：DICTS +3、NUMBER_RULES +4、`_seed_flows` +2 定义（purchase_request_approve 两级顺序；purchase_contract_approve 会签+终审）、biz_perms +采购权限点、MENU_TREE +采购目录。全部幂等，重复执行无副作用。
3. `backend/scripts/migrate_nav_procurement.py`：沿用批次E 幂等模式归一排序后调 `init_data.main()`。
4. 测试库走 `Base.metadata.create_all`（conftest 导入 app.main 即注册全部模型），无需单独迁移。

## 9. 二期实录（招投标 + 合作方门户，已实施）

> 本节原为二期规划；二期已按下列简化决策落地，接口契约详见 docs/api-contract.md「二期」与「合作方门户 /portal」两节。

**招投标（内部 /procurement/tenders）**

- 模型：`pur_tender`（TenderProject，tender_no 发布时发 ZB）+ `pur_tender_registration`（报名/资质附件/审核）
  + `pur_tender_bid`（投标报价/投标文件，一项目一合作方一份，重复提交即改标）+ `pur_tender_eval`（评标：评分+评语+推荐，一评标人一投标一条）。
- 状态机简化为 `draft → published → evaluating → awarding → awarded`（+ `terminated`）：
  报名中/投标中不单列状态，窗口由 `reg_deadline`/`bid_deadline` 字段控制，门户侧强制截止（96002）；
  `start-evaluation` 是内部动作，不要求到点，进入评标即关闭门户报名与投标。
- 评标为简洁版：评分+评语+推荐中标，按投标聚合均分；不做开标大厅/CA 签章/专家库。
- 定标走审批引擎：`tender_award_approve`（种子单级 leader1），提交即 awarding 并锁 award_bid_id；
  事件订阅 ApprovalCompleted → awarded 并落 winner_bid_id/winner_name/winner_amount（门户公示口径），
  Rejected/Withdrawn → 回 evaluating 清 award_bid_id，可重新定标。
- 定标生成采购合同：供应商=中标门户账号绑定的往来单位（未绑定报 95002 提示先绑定）、金额=中标价、
  关联原采购申请；`pur_tender.contract_id` 幂等（一项目一合同）。未采用一期规划的 `pur_contract.bid_project_id`
  反向挂接，互跳以 tender.contractId 为准。
- 权限码 `procurement:tender:*`（list/create/edit/delete/publish/terminate/review/evaluate/award/list:export）。

**合作方门户（/portal，独立认证）**

- 账号体系独立：`partner_user` 表（username/password_hash/company_name/contact/phone/email/
  status pending→enabled|rejected|disabled/customer_id 绑定往来单位/review_*），注册即待审核，
  内部在 /procurement/partners 审核（通过时可绑定供应商往来单位）。
- 认证隔离：门户 JWT `typ=portal_access` + `aud=portal`（12h，无刷新）。内部 `decode_token` 不指定
  audience，PyJWT 对带 aud 的门户 token 抛 InvalidAudience → 401；门户 `decode_portal_token` 强制
  audience="portal"，内部 token 无 aud → 401。双向互拒，任一泄露不可串用。
  登录锁定与内部同策略（5 次/15 分钟，Redis），登录日志落 sys_login_log（username 带 `portal:` 前缀）。
- 端点白名单：仅公告口径字段（pur_tender 公开列）+ 本人报名/投标；门户不可见 draft/terminated 项目，
  详情不含任何他人投标或评标信息；附件下载校验本人归属，存储防目录穿越。
- 前端独立入口 /portal（独立 axios 实例、token key `bs.portal_token`、路由守卫 /portal 前缀早分支），
  不进内部菜单/标签页体系。

**未实施（顺延）**

- 财务挂接（采购合同 → 应付结算）、库存台账 `pur_stock_balance`、Outbox 事件升级、
  开标大厅/CA/专家库、供应商评级自动计算、采购合同附件组件。

## 10. 一期不做清单（明确边界）

- 应付/财务挂接、任务详情页内嵌采购列表（一期仅单向 task_id 关联 + 互跳）
- 招投标全流程、供应商评级自动计算、库存余额校验
- 采购合同附件上传（一期走备注/线下；合同附件组件二期复用 ctr 模式）

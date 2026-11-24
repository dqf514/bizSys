# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概览

bizSys 是一个 pnpm workspace 单体仓库：Python 后端（FastAPI + SQLAlchemy 2 同步 + MySQL + Redis）+ Vue 3 前端。业务覆盖 CRM/合同/任务/审批/OA/财务/HR/采购/招投标/销售/AI 中心等域。

```
backend/    FastAPI + SQLAlchemy 2（同步）
frontend/   Vue 3 + TS 单包应用
deploy/     Docker Compose + Dockerfile + nginx
docs/       ADR-0001~0004 + api-contract.md + roadmap-2026-11.md + compliance-baseline.md + 各域设计文档
pre/        前期会议素材（截图/字幕/纪要）
CHANGELOG.md  变更日志（Keep a Changelog + 语义化版本，系统内「变更日志」页渲染此文件）
```

代码里常引用 ADR 编号：`ADR-0001` Python/FastAPI + 同步 SQLAlchemy（ADR-0002）自研审批引擎与事件总线、`ADR-0003` 前端单包（不做 monorepo）、`ADR-0004` 工作流引擎合并。**改动前先读对应 ADR**；`docs/api-contract.md` 必须与后端接口变更保持同步。

## 常用命令

根目录 `package.json` 全部代理到 `frontend`：

```bash
pnpm install          # 安装依赖
pnpm dev              # Vite :5173，/api 代理到 :8000
pnpm build            # token:build → i18n:check → scan:literal:strict → scan:colors → vue-tsc → vite build
pnpm lint             # eslint --max-warnings 0
pnpm typecheck        # vue-tsc --noEmit
pnpm test             # vitest run
pnpm i18n:check       # zh-CN / en-US 键集必须一致
pnpm scan:literal     # = frontend 的 scan:literal:strict，扫描硬编码中文字面量并失败退出
pnpm token:build      # 由 src/styles/tokens/*.tokens.json 生成 tokens.css
```

（根目录没有 `scan:colors` 代理，它只在 `pnpm build` 内部执行；`frontend/` 下另有非 strict 版 `scan:literal`。）

单测（vitest 配置内嵌在 `vite.config.ts`，environment=jsdom）：

```bash
cd frontend
pnpm test:unit src/i18n.test.ts            # 单个文件
pnpm test:unit src/i18n.test.ts -t "关键字"  # 单个用例
```

后端（`uv`，Python 3.13），全部在 `backend/` 目录执行：

```bash
uv sync
uv run alembic upgrade head
uv run python -m app.seeds.init_data
uv run uvicorn app.main:app --port 8000
uv run ruff check app tests
uv run pytest -q
uv run pytest tests/test_approval_engine.py -k start   # 单个用例
```

后端测试需要本地 MySQL（默认 `127.0.0.1:3307/bizsys`）与 Redis；`tests/conftest.py` 把库名替换成 `bizsys_test` 并 `create_all` 建表，**不跑迁移**，该库跨次运行残留，测试数据要带 `uuid4().hex[:8]` 后缀。

CI（`.github/workflows/ci.yml`）：backend job = MySQL 8.4 + Redis 7 → ruff → alembic → seed → pytest；frontend job = pnpm lint/typecheck/i18n:check/scan:literal/test/build。

## 后端架构

### 分层与模块

`app/core/`（跨域基建，不含业务知识）：`config`（pydantic-settings，读 `.env`）、`db`（同步 Engine/Session）、`security`（bcrypt + JWT）、`crypto`（AES-GCM 加密 sys_config 密钥）、`redis`、`deps`（当前用户/权限点）、`exceptions`（`BizException` + 异常处理器）、`response`（响应信封 + 错误码注册表）、`route`（`EnvelopeRoute`）、`schemas`（`CamelModel` 基类）。

`app/common/`（跨模块构件）：`models.py`（`BaseModel`：id + 审计四列 + `version` 乐观锁 + `deleted` 逻辑删除）、`pagination.py`、`filters.py`（白名单驱动的列表检索）、`audit.py`、`events.py`（进程内同步事件总线）。

`app/modules/<domain>/` 共 21 个域：`admin` `aicenter` `approval` `asset` `auth` `contract` `crm` `finance` `hr` `integration` `maintenance` `oa` `portal` `procurement` `production` `project` `report` `sales` `settings` `task` `visitor`。每域遵循四件套：

- `models.py` — SQLAlchemy 2.0 `Mapped[]` 声明式，继承 `BaseModel`，表名按域前缀（`sys_*` `crm_*` `task_*` `rpt_*` …）
- `schemas.py` — Pydantic v2，入参 `XxxIn(CamelModel)`（camelCase 别名，`populate_by_name=True`），出参 `XxxOut(BaseModel)`；输出 dict 手工构造成 camelCase
- `service.py` — 业务规则/状态机/副作用，**接收同步 `Session` 作为首参，不自己 commit**
- `router.py` — `APIRouter(prefix="/<域>", tags=[...], route_class=EnvelopeRoute)`，负责 `Depends` 注入、序列化、审计写入与 `db.commit()`

例外：`crm` / `integration` 没有 `service.py`；`auth/service.py`、`portal/service.py` 会自行 commit。

`asset` 域有**三个 router 同前缀**：`asset/router.py`（进出库管理：仓库/库位/物料/采购订单/验收单/流水/盘点/样件/样件借出）、`asset/finance_router.py`（资产财务：固定资产/折旧/处置/工具/工具领用）、`asset/bom_router.py`（BOM 物料清单：`ast_bom`/`ast_bom_line`，父子结构+版本+多级展开+用量对比），都在 `main.py` 以 `prefix="/api/v1"` 挂载。它**不新建组织/公司/权限表**：部门取 `sys_dept`，供应公司取 `crm_customer`（`partner_type ∈ supplier/both` 且启用），单号走 `app/services/numbering.py`（`PO/YS/PD/LJ/LY/CZ/BM`），取号走 `service.next_asset_no`（计数器落后于存量数据时自动跳过已占用号）。物料台账（`MaterialList.vue`）与物料清单（`BomList.vue`）菜单挂在**生产资源 → 样品与物料**下。

B2 客户自助体系沿用同一"同前缀分文件"惯例：`crm/selfservice_router.py`（前缀 `/crm`：客户自助账号 `crm:account:*` + 客户方人员备案 `crm:staff:*`，业务规则在 `crm/staff_service.py`）与 `task/entrust_router.py`（前缀 `/task`：在线任务委托 `task:entrust:*`，业务规则在 `task/entrust.py`）。客户账号**不并入 `sys_user`**：`partner_user` 扩展 `account_type`（`supplier`/`customer`）、`perm_scope`、`manager_id/manager_name`、`staff_limit`，沿用门户 token 体系（`typ=portal_access`、`aud=portal`），与内部 token 双向隔离。

`app/services/` 是**跨域**服务（不属于任何模块）：`numbering.py`（可配编号，前缀+日期位+流水，DB 行锁）、`excel.py`（导出）、`ai.py` / `masking.py` / `prompts.py`（AI 网关与提示词注册表）。

### 响应信封

`app/core/route.py::EnvelopeRoute` 在 `main.py` 中**必须于 `include_router` 之前**挂到 `app.router.route_class`，它把普通 JSON 返回自动包成：

```json
{"code": 0, "message": "ok", "data": {}, "traceId": "..."}
```

错误码按域分段定义在 `app/core/response.py`（`0` 成功、`1xxxx` 通用、`2xxxx` 认证、`3xxxx` 管理、`4xxxx` CRM、`5xxxx` 合同、`6xxxx` 任务/报告、`7xxxx` 审批、`62xxx` OA、`63xxx` HR、`64xxx` 销售、`65xxx` AI、`8xxxx` 财务、`9xxxx` 集成、`95xxx` 采购、`96xxx` 招投标/门户、`97xxx` 资产与库存、`98xxx` 访客与安全、`99xxx` 生产排程/项目），前端镜像在 `src/api/types.ts`。新增业务错误码必须同时在两侧登记。审批段另有 `70005`（流程已启用，不允许人工直通）与 `70006`（流程已停用，不允许提交审批）。

### 鉴权与权限

`app/core/deps.py`：

```python
current: User = Depends(require_perm("report:seal"))   # 权限点工厂，超管 role_code "super" 绕过
current: User = Depends(require_any_perm("a", "b"))    # 任一满足
current: User = Depends(get_current_user)              # 仅登录
```

- 权限码格式 `module:resource:action`（如 `report:seal`、`admin:user:list:export`、`crm:customer:import`）。
- 权限码由 `sys_menu.permission` 定义、种子在 `app/seeds/init_data.py::MENU_TREE`；**新端点的权限码必须在那里登记**，否则无法被角色授权。
- `user.perm_codes` 是**实时从数据库**推导（用户 → 启用角色 → 角色菜单 → 菜单权限），JWT 里的 `perms` claim 仅供展示，不要据此判断。
- JWT 用 `typ` claim 区分令牌族：`access` / `refresh` / `step_up`（敏感操作二次验证）/ `mfa_pending` / `portal_access`（带 `aud=portal`，与内部令牌互不通用）。门户另有独立依赖 `app/modules/portal/deps.py`。
- **登录会话口径（记住登录状态）**：access token 固定 15 分钟（前端 20001 时静默续期）；refresh token 分两档 —— `remember=true`（登录页勾选）**30 天**、存 `localStorage`；`remember=false` **12 小时**、存 `sessionStorage`（关浏览器即失效）。口径写进 refresh token 的 `rem` claim 并**在轮换时继承**。改密会吊销该用户其余会话（Redis 索引 `refresh:user:{uid}`）。
- 审计：`app/common/audit.py::record(...)` 写 `sys_audit_log`，尽力而为、失败不阻断业务；登录/增删改/导出都要记。

### 列表检索

后端统一用 `app/common/filters.py::apply_list_filters(stmt, model, query_params, db, page, search_cols=[...], filter_cols={...}, range_cols={...}, sort_cols={...})`，协议：

```
?page=1&size=20&q=关键词&status=xx&sort=updated_at:desc
&filters[customer_id]=1,2
&range[end_date]=2026-01-01|2026-12-31
```

返回统一为 `{"items": [], "total": n, "page": 1, "size": 20}`（`page_result()`）。白名单外的列自动忽略；`status=all` 视为不过滤。

### 审批引擎

`app/modules/approval/` 是自研可配置流程引擎（`engine.py` + `graph.py` + `condition.py`），而非外部工作流：

- 节点类型 `approval` / `condition`（按 `instance.variables` 路由）/ `cc`（不阻塞）
- 签署模式 `or`（任一通过其余作废）/ `and` / `sequential`（依次逐个）
- 审批人类型 `USER` / `ROLE` / `DEPT_LEADER` / `PARENT_DEPT_LEADER` / `SUPERVISOR_CHAIN`（按发起人组织解析）/ **`FORM_USER` / `FORM_ROLE` / `FORM_DEPT_LEADER`（按表单字段解析，F6 新增）**。后三类的 `approver_value` 存**流程变量名**（如 `hostUserId`）而非用户 id，变量清单由流程定义的 `variables_schema` 声明。
- **外部发起人**（门户单据）：`engine.FlowInitiator(id=0, name="合作方·XX")`，`approval_instance.initiator_id = 0`（真实用户 id 从 1 起不冲突）；组织类节点在外部单据上会 `auto_pass` 跳过。
- `start` / `approve` / `reject`（意见必填）/ `withdraw`（仅发起人且无人处理）/ `add_sign`（加签）/ `transfer`（转办）
- 每次状态变化写 `approval_record` 时间线

业务单据与审批引擎通过 `app/common/events.py` 事件总线解耦（同一事务内同步派发）：`ApprovalCompleted` `ApprovalRejected` `ApprovalWithdrawn` `ApprovalTodoCreated` `TaskAssigned`。订阅方通过 **import 模块即订阅**（见 `main.py` 中 `notifier`、`oa.router`、`procurement.router`、`sales.router` 的 noqa 导入）。跨模块只走 service / 事件，禁止 router 互相 import。

### 流程注册表与事件开关（F5，全流程驱动）

- `app/modules/approval/registry.py` — **流程注册表**（`FlowBinding` 冻结 dataclass + **19** 条 `BINDINGS`）：把每类单据登记为 `bizType` / 流程定义 code / 可发起状态 / 审批中·通过·驳回·撤回四个状态口径 / 发起权限 / 通过后钩子。核心 API：`submit_flow()`（发起审批）、`apply_result()`（回写状态）、`require_manual()`（人工直通守卫，流程启用时抛 70005）、`flow_enabled()`（读流程总开关）、`switch_key()`、`bindings_out()`、`capabilities_out()`。
- **未配置启用的流程定义 → 按人工审核口径直通**（`passThrough` + `passThroughStatus`），不产生审批实例；**流程总开关关闭 → 禁止提交审批（70006），同时恢复人工直通后门**。
- `app/modules/approval/wiring.py::install()` — 显式装配订阅（幂等），在 `main.py` 调用；不再依赖各域 service 模块级 `subscribe()` 的隐式导入。
- `app/modules/settings/automation.py` — 「流程与事件开关」面板数据：流程总开关 `flow.<bizType>.enabled` 与事件触发开关 `event.trigger.<事件>.<处理器>` 都落 `sys_config`，写入即生效。端点 `GET/PUT /admin/automation`（`admin:automation:list` / `admin:automation:edit`）。
- `GET /approval/flow-capabilities`（**仅登录**）→ 前端 `useFlowCapability()` 据此决定单据页显示「提交审批」还是历史人工动作（验收 / 批准 / 用章）。
- 事件目录 `EVENT_CATALOG`（9 个事件）；每个处理器可挂开关键，`critical=true` 的失败会回滚业务事务。
- 新增流程驱动端点：`POST /project/projects/{id}/submit`、`POST /hr/timesheets/{id}/submit`、`POST /hr/employments/{id}/submit`、`POST /finance/payments/{id}/submit`、`POST /asset/receipts/{id}/submit`、`POST /asset/disposals/{id}/submit`、`POST /report/reports/{id}/seal-apply`（用章申请与实际签章分离）。
- 前端页面 `src/modules/admin/pages/AutomationSettings.vue`（菜单 `menu.automation`，权限 `admin:automation:list` / `admin:automation:edit`）。

### 任务扩展 / 工序流转 / 排程 / 项目（B5）

- `app/modules/task/extension.py` — 任务扩展的**纯逻辑层**（不依赖 router）：角色分组派生 `role_group_of`、按任务类型解析默认负责人 `resolve_owner`（字典 `task_owner_rule`）、分组可见性 `visible_role_groups` / `assert_task_visible`、工序与分配的读写与 `process_out` / `assignment_out` / `trace_out`、全过程追溯与操作流程图 `operation_flow`。
- `app/modules/task/process_router.py` — 工序流转 / 七维分配 / 全过程追溯 / 操作流程图 / 负责人推荐的路由（prefix `/task`）。**同一任务同时只允许一道工序进行中**（否则 60020）。
- `app/modules/production/` — 智能排程（`prd_plan` + `prd_schedule`，`PL`/`SC` 单号）：规则式贪心排期，设备/人员/样车**时段独占**、物料**数量占用**。**能顺延到空档就算正常排期（`scheduled`），只有排不下或物料缺量才 `conflict`**；发布时二次校验冲突（99004）并回写任务计划日期。
- `app/modules/project/` — 项目与项目任务（甘特行）（`prj_project` + `prj_project_task`，`PJ` 单号）：项目状态机 `draft→planning→executing→accepting→closed`（仅 draft/cancelled 可删，99101）；甘特行可从任务自动生成（起止日期优先取已发布排程），进度按权重加权回算。
- 三者**已通过流程注册表接入审批引擎**（项目立项、工时填报、回款复核、到货验收、资产处置均有 `POST .../submit`；见上文「流程注册表与事件开关」）。

### HR L1 组织与人事（B10-1）

> 对应《人力资源管理模块功能说明》**L1 基础人事**。组织架构与员工主数据是其余所有域的地基 ——
> 部门树决定审批链解析（`DEPT_LEADER` / `SUPERVISOR_CHAIN` 走 `sys_dept.parent_id`），
> 员工在职状态决定 B9 授权台账是否应当继续生效。

**单一写入口**：`sys_dept` 是**全站唯一的部门表**（B10-1 起扩 6 列：`dept_type` / `site_code` / `address` / `manager_id` / `effective_from` / `effective_to`），
**写入口只有 `POST/PUT /admin/depts`**（`admin:dept:edit`）；HR 域只提供**岗位**与**变更轨迹**，**不要新建部门表或第二个写入口**。
写 `manager_id` 时必须同步任职表 `sys_user_dept.is_leader`（`admin/org.py::apply_dept_manager`）—— 审批引擎的 `DEPT_LEADER` 读的是任职表。

**新表**（`app/modules/hr/models.py`，均已登记进 `maintenance/service.py::_PURGE_TABLES`）

| 表 | 基类 | 说明 |
| --- | --- | --- |
| `hr_position` | `BaseModel` | 岗位说明书 + `key_role`（技术/质量负责人、授权签字人等关键岗位）+ A/B 角（`primary_user_id` / `backup_user_id`） |
| `hr_employee` | `BaseModel` | 员工一人一档（`employee_no` 唯一；`user_id` 1:1 → `sys_user`，可空 = 未开账号） |
| `hr_employee_control` | `BaseModel` | 黑白名单（`control_type` = blacklist / whitelist） |
| `hr_employment` | `BaseModel` | 人事事务单据（单号前缀 `EM`）：入职 / 调岗 / 离职 / 返聘 |
| `hr_employment_event` | `AppendOnlyModel` | 人事事务变更轨迹（**只追加**） |
| `hr_delegate` | `BaseModel` | 代理人（AB 角，**不借账号**；委托人离岗自动 `expired`） |
| `hr_org_change` | `AppendOnlyModel` | 组织变更快照（**只追加**） |

**敏感个人信息**：`hr_employee.id_no` 以 AES-GCM 密文（`enc:` 前缀，域 `hr-employee-idno`，与配置密钥 / 签名密钥**域分隔**）落库；
出参一律掩码（`hr/employee.py::mask_id_no`，前 4 + `*`×(len-8) + 后 4）；
**明文唯一出口** `GET /hr/employees/{eid}/id-no`（权限 `hr:staff:idno`），**每次访问写 `sys_audit_log`**（action `hr_employee_idno_view`）。
证件号唯一性只能**解密后逐条比对**（密文不可 SQL 比对）。

**审批接入**：`registry.py::BINDINGS` 第 **19** 条 —— `biz_type="hr_employment"` / `definition_code="hr_employment_approve"` / **`pass_through=False`**（人事事务不允许人工直通）。

**审批通过 ≠ 生效**：状态机 `draft→approving→approved→effective` / `rejected`；副作用**统一**由
`POST /hr/employments/{id}/effect` → `hr/employment.py::effect_employment()` 触发：

| 事件 | 副作用 |
| --- | --- |
| onboard 入职 | 建 `sys_user`（**自动生成**的初始密码明文**只在生效响应里出现一次**；HR 表单填的密码不回显）→ 按岗位 `position_type` 绑默认角色（`staff` → `biz_user`）→ 建主部门任职（`is_primary=1`）→ 回填 `hr_employee.user_id` → 同步 `sys_user.employee_no` / `hire_date` → `employ_status=probation` |
| transfer 调岗 | 更新 `hr_employee.dept_id/position_id` + `sys_user.dept_id/dept_name` + 主部门任职同步 |
| resign 离职 | **禁号**（`sys_user.status='disabled'`，**不删除**保 ALCOA 完整）+ **撤 MFA** + **撤销 B9 授权台账**（批量 `revoked` + 写 `hr_authorization_event`）+ **代理失效** + **清岗位 A/B 角** → `employ_status='resigned'`；**物理权限（门禁/钥匙/工牌）无对接 → 写「待现场确认」审计** |
| rehire 返聘 | 恢复原账号（`status='enabled'`，一人一号历史连续）+ `employ_status='regular'`；**不恢复授权**（能力须重新确认） |

前端四页：`src/modules/hr/pages/OrgStructureList.vue`（组织架构）/ `PositionList.vue`（岗位）/ `StaffList.vue`（员工档案）/ `PersonnelAffairsList.vue`（人事事务 + 代理人抽屉）。
人事事务页页脚**三按钮**：取消 / 保存草稿 / 提交审批（`v-permission="'hr:employment:submit'"`）+ 行内「生效」（`hr:employment:effect`）。

### 企业微信审批移植（E1）

**源文档** `企业微信审批与组织数据技术文档.html`（仓库根，**含真实人员数据 → 不入库，已 gitignore**）。入库的只有脱敏后的 `backend/app/seeds/data/*.json`。

**数据落位（不新建组织表）**：

| 企微概念 | 落位 | 键 |
| --- | --- | --- |
| 11 部门 | `sys_dept` | `code = WC01…WC11`（**写入口仍只有 `POST/PUT /admin/depts`**，本批次只读种子） |
| 23 标签 | `sys_role` | `code = wc_tag_<slug>` —— **标签 → 角色的唯一通道，只做审批人来源，不绑菜单权限** |
| 40 人 | `sys_user` + `sys_user_dept` + `hr_employee` | `username = mock001…mock040`、`name = 模拟员工NN`、密码 `Mock@123456` |
| 39 模板（表单） | `oa_form` | `key = wc_<slug>`、`status=published`、`schema_json={"fields":[…]}`、`scope_json` |
| 39 模板（流程） | `approval_definition` + `approval_node` | `code = wc_<slug>_approve`、`biz_type = "oa"` |

**导入器** `app/seeds/wecom_templates.py::import_templates(db)`（由 `init_data.main()` 幂等调用）；报告脚本 `backend/scripts/wecom_import_report.py`。产物 `app/seeds/data/wecom_flow_packages.json`（39 个流程包）。

**控件映射**：企微 22 类 → `text/textarea/number/money/date/daterange/select/radio/checkbox/file/user/text_block/resource/table/formula/phone/location/attendance/hr_ref`。Contact 控件 `type=multi` → `user` + `multiple=true`；`mode=department` → `resource` + `resource=dept`。

**新增/变更的引擎能力**：

- 条件规则组 `{logic, rules[]}`（可嵌套）+ `between` 区间 + `in`/`empty`/`not_empty`（`approval/condition.py`、`oa/schemas.py::CONDITION_OPS`、前端 `ConditionEditor.vue`）。
- 节点类型新增 `executor`（办理节点，单人处理）。
- `approval_definition.options`（Text JSON，10 个流程通用选项）—— **未配置时保持既有行为**；`commentRequired` 让**通过**也必须填意见（`70003`）；`commentSignRequired` 要求**签名**（只作用于审批节点，办理节点走「办理意见必填」），签名随 `commentSignature` 提交并写入 `approval_record.payload.signature`。
- `approval_node.field_permissions`（Text JSON，`editable`/`viewonly`/`hidden`）—— `oa/service.py::instance_detail()` 按**当前待办节点**掩码：`hidden` 从 schema+data 剔除，`viewonly` 下发 `readOnly: true`。
- `oa_form.scope_json`（Text JSON，`depts`/`roles`/`users`）—— `GET /oa/catalog` 按当前用户过滤，空 = 全员可见。
- 公式支持 `SUM(表key.列key)` / `HOURS(字段key)`（后端 `oa/service.py::_extract_aggregates`；前端 `frontend/src/modules/oa/formLogic.ts` 的 `evalFormula`/`sumOfColumn`/`hoursOf` —— **两端语义必须一致**）。

**流程包（JSON 化）** schema `bizsys.flowpackage/v1`，实现 `app/modules/approval/packages.py`；4 个端点（`GET /approval/packages/export-all`、`GET /approval/definitions/{code}/package`、`POST /approval/packages/import`、`GET /oa/admin/forms/{id}/package`），权限 `admin:flow:export` / `admin:flow:import`；**导入幂等**（按 `code` / `form.key` upsert）。前端页 `src/modules/admin/pages/FlowPackageList.vue`（菜单 `menu.flowPackages`）。

**企微 op 编码推定**（文档未给语义，按 21 条条件文案交叉推定）：op1=eq / op2=gt / op3=lt / op4=gte / op5=lte / op6=between。**op2/op4 的 gt/gte 归属仅在恰好等于阈值时有差异**；2 处 op6 阈值缺失按条件标题重建（`reconstructed=true`）；1 处 op2 阈值不可知落 `gt 0`（`needs_review=true`）—— 详见 `docs/api-contract.md` E1 章节与导入报告。

**新增迁移（手写）**：`nc2b3c4d5e6_wecom_flow_upgrade.py`（`options` + `field_permissions`）、`nd2b3c4d5e6_oa_form_scope.py`（`scope_json`）—— `alembic/env.py` 未 import oa 域 models，**必须手写**。

### AI 能力

三层结构：

1. `app/services/ai.py::gateway_chat(db, feature=..., messages=..., user=...)` — **唯一出网入口**。统一处理功能开关（`ai.feature.<name>`，默认开）、配额（`ai.quota.user_daily_calls` / `user_daily_tokens` / `global_daily_tokens`，0=不限）、脱敏（`ai.masking.level`）、用量日志 `ai_usage_log`（success/error/fallback 三态、token、成本估算，**用独立 session 写库，业务回滚也保留日志**）、tenacity 重试。绕过它直接 httpx 调用等于绕过开关/配额/脱敏/审计。
2. `app/services/prompts.py` — 提示词注册表，key=feature 名（`report_assist` 拆成 `.conclusion` / `.proofread` / `.completeness`），带 `version`，**代码拥有、只读**，前端只展示预览。
3. `app/services/masking.py` — 脱敏分级 `off | standard | strict`，只作用于出网 prompt 文本，不改库内数据；`hr_prefill` `oa_prefill` `flow_anomaly` `daily_digest` `assistant` `knowledge` 强制至少 standard。

`app/modules/aicenter/` 是 AI 中心（用量/统计/功能开关/配额/脱敏级别/模型单价/提示词预览/知识库/自然语言问数/每日摘要/全局助手）。自然语言问数只允许命中白名单意图（`nl_query.py` 的 `DOMAINS`），由服务端映射到手写聚合 SQL，**禁止自由 SQL**。

各业务域的 AI 辅助在模块内 `ai_*.py`（`approval/ai_assist.py`、`approval/flow_suggest.py`、`oa/ai_prefill.py`、`oa/ai_anomaly.py`、`hr/ai_prefill.py`、`task/ai_sample_ocr.py`、`finance/ai_invoice_ocr.py`、`procurement/ai_price_ref.py`、`procurement/ai_tender.py`），统一形态：服务端组装并截断上下文 → 解析 JSON 并白名单归一 → 返回**草稿**。**AI 结果一律不自动落库，必须人工确认**。

### 变更日志（Keep a Changelog）

- **单一数据源 = 仓库根目录 `CHANGELOG.md`**（代码拥有、随版本走；镜像内由 `deploy/backend.Dockerfile` 的 `COPY CHANGELOG.md` 提供）。后端**只解析不改写**：`app/modules/admin/changelog.py::parse_changelog`（按 mtime 缓存，改文件即时生效）。
- 端点 `GET /admin/changelog`（**仅需登录**）：返回 `currentVersion` / `latestVersion` / `latestDate` / `releases[{version, date, sections[{type, items[{text, children}]}]}]`。分类 `added`/`changed`/`deprecated`/`removed`/`fixed`/`security`，未登记的分类原样透传（前端回退显示原名）。
- 前端页面 `src/modules/admin/pages/ChangelogList.vue`（菜单 `menu.changelog` → `/admin/changelog`，权限 `admin:changelog:list`，挂在「系统管理 → 系统与审计」）；分类徽标走 i18n `admin.changelog.type.*`。
- **版本号四处必须一致**：`CHANGELOG.md` 顶部版本 == `Settings.app_version` == `frontend/package.json` == `backend/pyproject.toml`（**含 `backend/uv.lock` 的 `bizsys-backend` 版本**，否则 `uv sync --frozen` 失败），版本号严格递减 —— 由 `tests/test_changelog.py` 在 CI 断言。
- **每次功能性变动都要在 `CHANGELOG.md` 顶部追加条目**（与代码同一次提交），分类按 Keep a Changelog 六类选。

### 客户端 IP（反向代理链）

- 应用跑在**容器 nginx 之后**（nginx 前面还有一层对外网关 `portal.hmvic.cn`），`request.client.host` 只是 **TCP 对端地址**（nginx / 网关容器的内网 IP）。审计日志、登录日志、NDA 签名绑定要的是**真实客户端 IP** —— 一律走 `app/core/client_ip.py::client_ip(request)`，**不要直接写 `request.client.host`**（全仓 13 处已替换）。
- 取值逻辑：**跳数模式**（默认）从 `X-Forwarded-For` 右侧往左数 `TRUSTED_PROXY_HOPS` 跳（默认 `2` = 网关 + 容器 nginx；链比跳数短时取最左一条，局域网直连场景结论不变）；配了 `TRUSTED_PROXY_CIDRS` 则改按**网段**判定（从右往左跳过受信任代理网段，优先于跳数）；回落链 = `X-Real-IP` → TCP 对端。`TRUST_PROXY_HEADERS=false` 或 `TRUSTED_PROXY_HOPS=0` = **不采信任何代理头**。
- nginx 侧**已配好** `X-Real-IP` / `X-Forwarded-For`（追加语义 `$proxy_add_x_forwarded_for`）—— **不用改 nginx**；但**网关侧必须用追加语义**（`$proxy_add_x_forwarded_for`，不要 `$http_x_forwarded_for` 原样透传），否则链首可被客户端伪造。
- 三个环境变量由 `deploy/docker-compose.yml` 透传给后端容器（`deploy/.env` 可覆盖），改完 `docker compose up -d backend` 生效；口径详见 `deploy/DEPLOY.md` 与 `docs/api-contract.md`。

### IP 属地（离线 ip2region）

- 审计日志 / 登录日志在 IP 旁边展示**属地**（省 / 市，字号更小）：`backend/app/core/ipgeo.py::resolve_region(ip)` → 属地文案（回环→「本机」，内网/保留地址→「内网」，公网如「安徽省 宣城市」，查不到→空串）。
- **数据源是离线库**：`backend/app/core/data/ip2region_v4.xdb`（v4 格式，~10.6MB，随仓库入库）+ vendored 纯 Python 绑定 `backend/app/core/ip2region/`（上游 `lionsoul2014/ip2region` 的 `binding/python`，Apache-2.0/MIT 双许可，同目录 `LICENSE.md`）。**不引入 pip 依赖、不访问外网**。
- **属地在读取时计算，不落库** —— `sys_audit_log` 是只追加的（BEFORE UPDATE/DELETE 触发器），落库属地要回填历史行 → 不可行；读取时算（内存向量索引 + 二分查找，µs 级 + `lru_cache`）顺带让**历史记录立即就有属地**，也不用给审计表加列 / 加迁移。新增展示属地的接口一律在出参里拼 `ipRegion`，**不要往审计表加属地列**。
- 出参口径：`GET /admin/audit-logs`（列表 / 证据详情 / 导出都含 `ipRegion`）、`GET /admin/login-logs`（`sys_login_log` 此前**没有任何查询端点**，本次新增，沿用 `admin:audit:list` 权限，不另设权限码）。

### 已知坑

- `alembic/env.py` 只 import 了 admin/approval/asset/auth/contract/crm/finance/production/project/report/settings/task/visitor 的 models；`oa`/`hr`/`procurement`/`sales`/`aicenter`/`portal` 的表不在 metadata 里，**autogenerate 会试图删表**。这些表的变更手写迁移。
- 迁移链单线无分支，当前 head = `nd2b3c4d5e6_oa_form_scope.py`。新迁移用可读递增 id（如 `ne2b3c4d5e6_xxx.py`），`down_revision` 指向当前 head。
- `SessionLocal(autoflush=False)`：同一事务里新插入的行需要显式 `db.flush()` 才能被后续 SELECT 看到。
- `db.py::_ensure_utf8mb4` 会强制补 `charset=utf8mb4`（历史上 pymysql 默认 latin1 导致中文乱码）。
- 事务边界在 router 的 `db.commit()`，service 不 commit（`auth`/`portal` 例外）。
- **新增业务表必须同时登记进「一键清空」清单**（`app/modules/maintenance/service.py::_PURGE_TABLES`）：该工具会清空编号序列 `sys_number_seq`，漏登记的表会残留旧单号，下次取号从 1 重来直接撞唯一键（`Duplicate entry 'LJ202611210001'`）。
- **单号计数器可能被重置**（管理员在编号规则页重置序列、或清库后计数归零），取号不能假设号段连续；资产域走 `asset/service.py::next_asset_no` 逐号试探跳过已占用号。
- **访客域的合规审计表 `visitor_access_log` 是只追加的**：它继承 `visitor/models.py::AppendOnlyModel`（**没有** `deleted`/`version`/`update_*` 列），所以 `apply_list_filters` 里那句 `hasattr(model, "deleted")` 的守卫是必需的，且 API **不得**为该路径提供任何 PUT/PATCH/DELETE。合规要求"不可删改 + 保留 ≥180 天"。
- **访客域的拒绝放行也必须留痕**：`svc.check_in` 命中黑名单/超窗/越权时会抛 `BizException`，但它此前已 `db.add()` 了 `VisitorAlert` 与 `VisitorAccessLog`。router 里必须写成 `except BizException: db.commit(); raise` —— 否则事务回滚把告警和审计一起丢掉（合规事故）。
- **`BaseModel` 已有 `version` 乐观锁列**，业务上的"版本号"不能复用它：BOM 用 `bom_version`（对外输出为 `version`，乐观锁另存 `lockVersion`）。
- **BOM 子件行用 ORM 级联删除**：`Bom.lines` 是 `cascade="all, delete-orphan"`，整表替换必须走 `bom.lines.clear()`；用 `query(BomLine).filter(...).delete()` 批量删会绕过 ORM，flush 时报 "expected to delete 1 row(s); 0 were matched"。
- **预警类筛选是"分页后过滤"**：`filters[low_stock]` / `filters[stagnant]` / `filters[stagnant_level]` / `filters[warning]` 依赖库存与流水统计，无法下推到 SQL。列表与导出**必须共用同一个后置过滤函数**（`asset/router.py::_apply_item_alert_filters`），否则从「呆滞」页签导出时会把全部物料导出。
- **门户 token 与内部 token 双向隔离**：门户 JWT 带 `aud=portal` + `typ=portal_access`，内部 `decode_token` 不校验 audience → 门户 token 打内部接口直接 401；门户 `decode_portal_token` 强制 audience=portal → 内部 token 打门户接口 401。**新增内部接口时不要拿门户 token 去试**，也别为了"方便"去掉任一侧的校验。门户 refresh token 存 Redis `portal_refresh:{jti}`（7 天），登出要吊销。
- **二维码用 `segno` 服务端生成**：`app/modules/visitor/qr.py::credential_qr_svg()`（纯 Python、零传递依赖、已在 `backend/pyproject.toml`）。前端**不要用 `<img src>` 直连**（不会带 `Authorization` 头），要用 `portalHttp` 以 `responseType:'blob'` 取回再 `URL.createObjectURL`。
- **访客单接审批引擎后的迁移是手写的**：`n7a2b3c4d5e6_portal_visitor_flow.py` 给 `vis_visit` 加 `flow_instance_id` 与 `approving` 状态 —— `alembic/env.py` 未 import visitor models，autogenerate 会误删表（见上一条）。
- **`FORM_*` 审批人类型存的是"变量名"**：`approval/registry.py` 之外的 `FlowNode.approverValue` 在 `approverType ∈ {FORM_USER, FORM_ROLE, FORM_DEPT_LEADER}` 时存**流程变量名**（如 `hostUserId`），不是用户/角色 ID；可用变量由流程定义 `variables_schema` 声明。别把它当 id 传给引擎。
- **审计表是只追加的，不可改不可删**（B9）：`sys_audit_log` / `sys_audit_failure` / `hr_authorization_event` 继承 `app/common/models.py::AppendOnlyModel`（**没有** `deleted`/`version`/`update_*` 列），`vis_access_log` / `vis_nda` 同理。迁移里给 `sys_audit_log` 加了 `BEFORE UPDATE`/`BEFORE DELETE` 触发器 `SIGNAL SQLSTATE '45000'`。**审计类表禁止登记进「一键清空」清单**（`maintenance/service.py::RETAINED_AUDIT_TABLES` 是保留清单）；而 `hr_authorization` / `hr_authorization_event` **必须**登记进 `_PURGE_TABLES`（否则编号序列清零撞唯一键）。
- **`sys_audit_log.create_time` 必须是 `DATETIME(3)`**（B9）：`row_hash` 含毫秒时间戳，秒精度会让整条链重算**必然**报 `row_hash_mismatch`。迁移、模型、`tests/conftest.py::_ensure_columns` **三处必须同时改**。
- **审计链头是唯一权威游标**（B9）：`sys_audit_chain_head`（`chain_key='main'`）的 `last_seq`/`last_hash` 决定下一行位置，写入用 `SELECT … FOR UPDATE NOWAIT`。**不要用 `MAX(id)`** —— 并发下会产出两行同 `prev_hash` 的分叉。存量行 `chain_seq IS NULL`，**不回填历史哈希**（不伪造历史），校验时计入 `legacyRows`。
- **存量 NDA / 报告签章不可密码学验证**（B9）：存量 `vis_nda` 是无密钥 sha256（离线可复算），验签返回 `verdict="legacy-unverifiable"`；存量 `rpt_report` 无 `seal_signature`，`verify_seal` 返回 `signatureValid=false`。前端要打灰标说明"不可作为密码学证据"。
- **报告内容哈希必须在 `apply_seal_watermark()` 之后算**（B9）：盖章会产出新 PDF，先算必然对不上。`seal_time` 列是 `DATETIME(0)`，签名载荷按**秒口径**计算。
- **授权校验不做跨请求缓存**（B9）：`hr/authorization.py::check_authorization()` 只允许请求内 memo（`db.info`）—— 撤销必须立即生效。过滤永远走显式列（`scope_method`/`scope_params`/`scope_device_id`/`scope_domain`），**`scope_json` 只是展示快照，不做过滤依据**。
- **`hr_authorization` 的流程绑定 `pass_through=False`**（B9）：未配置流程定义时提交审批直接报错 —— 授权不允许绕过审批，这是刻意的。
- **`sys_dept` 是全站唯一的部门表**（B10-1）：扩了 6 列（`dept_type`/`site_code`/`address`/`manager_id`/`effective_from`/`effective_to`），**写入口只有 `POST/PUT /admin/depts`** —— HR 域只提供**岗位**（`hr_position`）与**变更轨迹**（`hr_org_change`），**不要新建部门表或第二个写入口**。`dept.manager_id` 是权威写入方，必须与 `sys_user_dept.is_leader` 双向同步（`admin/org.py::apply_dept_manager` / `sync_dept_manager_from_members`）—— 审批引擎的 `DEPT_LEADER` 解析读的是任职表。
- **`hr_employee.id_no` 是加密字段**（B10-1）：落库必须是 `enc:` 密文（域 `hr-employee-idno`），出参**一律掩码**；**明文唯一出口**是 `GET /hr/employees/{eid}/id-no`（权限 `hr:staff:idno`），**每次访问必须写审计**。证件号唯一性只能解密后逐条比对，别写 SQL 比对密文。
- **审批通过 ≠ 生效**（B10-1）：`hr_employment` 状态机 `draft→approving→approved→effective`；副作用**统一**由 `POST /hr/employments/{id}/effect` → `hr/employment.py::effect_employment()` 触发。**不要手工改 `sys_user.status` 来"离职"** —— 那会跳过撤 MFA、撤 B9 授权、代理失效、清岗位 A/B 角四件事，留下"账号已停但授权仍在"的合规缺口；也**不要直接改 `hr_employee.employ_status`**（在职状态是清权的触发源）。
- **不要拿 `request.client.host` 当客户端 IP**（B10-2）：那是 TCP 对端（nginx / 网关容器 IP），审计里会显示成内网地址。用 `app/core/client_ip.py::client_ip(request)`（见上文「客户端 IP」）—— 新增 router / 记 IP 的地方一律走它。
- **IP 属地不要往审计表加列**：`sys_audit_log` 是只追加的（触发器禁止 UPDATE），属地一律在**出参里现算**（`app/core/ipgeo.py::resolve_region`，离线 xdb）—— 见上文「IP 属地」。
- **外部门户入口（客户自助 / 在线委托）在内网导航是隐藏的**：`init_data.py::HIDDEN_MENUS = {"PartnerAccounts", "PortalHome", "PortalOrders"}` 强制 `visible=0`（菜单行仍在，权限点仍由它承载）。门户是与内网隔离的第二套外壳（`partner_user` / `typ=portal_access`），内网人员点进去只会跳到门户登录页 —— 改导航结构（`scripts/migrate_nav_zones.py`）时**别把这两个入口放回可见**。
- **`hr_employment` 的 `pass_through=False`**（B10-1）：人事事务不允许人工直通，未配流程定义时提交直接报错 —— 与 `hr_authorization` 同理，是刻意的。
- **`hr_employment` / `hr_delegate` 的 `scope` 校验很严**：`scope="position"` 必须同时给 `positionId`（否则 63018），`scope="auth"` 必须给 `authId`。
- **B10-1 新表都在 `hr` 域，而 `alembic/env.py` 没 import hr models** —— 新增 hr 表的迁移**必须手写**（`na2b3c4d5e6_hr_l1_org_employee.py` / `nb2b3c4d5e6_hr_employment_account.py`），autogenerate 会删表。
- **变更日志的单一数据源是仓库根 `CHANGELOG.md`**：不要另建表、也不要前端本地副本 —— 后端 `admin/changelog.py` 按 mtime 缓存解析结果，改文件即时生效；**镜像里靠 `deploy/backend.Dockerfile` 的 `COPY CHANGELOG.md` 提供文件，漏改会让容器内读到空变更日志**（页面显示空态，不报错）。
- **`options`（流程通用选项）缺省 = 保持既有行为**（E1）：`engine._options_of()` 查不到定义或列就返回 `{}`，于是「意见必填 / 需签名 / 允许加签 / 通过后可撤销」全部**不生效**。企微模板的 options 由导入器**显式写全 10 个键**（缺失即 False），而 bizSys 存量定义没有 options —— **别把 `bool(opts.get(k))` 当成「未配置=关闭」**：加签的判定是 `opts.get("allowAddSign") is False`。
- **`commentSignRequired` 只作用于审批节点**（E1）：办理节点（`executor`）走「办理意见必填」口径，前端 `ApprovalActionbar` 同样按 `nodeType !== 'executor'` 决定是否弹签名板 —— **前后端两边都要排除 executor**，否则办理节点永远签不了。
- **`daterange` 不能作为流程变量**（E1）：`EXPOSABLE_TYPES` 不含它。企微「时长」按小时比较，导入器为此合成 `HOURS(<fieldkey>)` 公式字段暴露给引擎，**原始 daterange 保持不暴露**。
- **公式求值前后端必须同语义**（E1）：后端 `oa/service.py::_eval_formula` / `_sum_of_column` / `_hours_of`，前端 `frontend/src/modules/oa/formLogic.ts` 的 `evalFormula` / `sumOfColumn` / `hoursOf`。**改了任一侧就要同步另一侧**，否则表单预览与服务端重算的金额对不上。`_formula_refs` 要把 `SUM(...)` / `HOURS(...)` 整段剥掉，否则聚合参数会被当成控件引用。
- **企微模拟数据不得升级成真实数据**（E1）：源 HTML `企业微信审批与组织数据技术文档.html` 含真实人员数据，**不入库**（已 gitignore）；入库的只有脱敏后的 `backend/app/seeds/data/*.json`。模拟人员一律 `mockNNN` / `模拟员工NN`，`hr_employee.id_no` / `mobile` / `email` 与 `sys_user.mobile/email/wecom_userid` **留空**。**企微 vid（人员与部门 ID）解析阶段即丢弃、不落盘** —— `backend/scripts/parse_wecom_doc.py` 不再输出 `wecom_id`，改写种子 JSON 时别把它加回去。
- **刷新会轮换 refresh token，前端必须把新的存回**（0.9.0）：后端 `auth/service.py::refresh()` 吊销旧 jti 并签发新 jti；前端 `api/http.ts::refreshAccessToken()` 若只存 access token，**下一轮续期就会拿已吊销的旧 token → 401 → 被踢回登录页**（曾因此让「登录状态只能维持 15~30 分钟」）。
- **`remember`（记住登录状态）口径必须随轮换继承**：refresh token 的 `rem` claim 决定有效期（30 天 / 12 小时）；`refresh()` 重签时按 `payload["rem"]` 取值，**别按默认值重签**，否则「不记住」会被悄悄延长成 30 天。前端存储档位（localStorage / sessionStorage）也要跟着 `rem` 走。

## 合规基线（B9）

> 详细逐条对照见 [`docs/compliance-baseline.md`](docs/compliance-baseline.md)（原则 → 现状 → 机制 → 验收方法）。
> 需求方原始 docx 已入库：B9 落地的三个控制点为 **C1 审计证据链**、**C2 电子签名密码学绑定 + 签章后锁定**、**C3 人员授权台账 + 拦截点前置**。

- **C1 审计证据链** —— `app/common/audit.py::record()` 保持旧参数不变，新增 keyword-only 默认参数（`field_name`/`old_value`/`new_value`/`reason`/`user_agent`/`strict`），**全仓调用点零改动**。默认尽力而为（失败记 `sys_audit_failure`）；`strict=True` 或 `sys_config` 开关 `audit.strict.enabled` 时抛 30005 并由调用方 `db.commit()` 回滚。校验端点 `GET /admin/audit-logs/chain/verify`，锚点写在 **DB 之外** 的 `backend/data/audit-anchor/anchor-YYYYMMDD.txt`（只追加）→ 整链被重写/截断时锚点对不上。
- **C2 电子签名** —— `app/core/signature.py`（HMAC-SHA256，密钥 `sha256("bizsys:evidence-signature:" + jwt_secret)`，域分隔前缀与 `core/crypto.py` 不同）。NDA 用 `nda_no`（不是自增 id）参与签名；报告内容哈希含最终 PDF 字节。签章后 `report/service.py::assert_report_editable()` 抛 61003 锁定记录。
- **C3 人员授权** —— `app/modules/hr/authorization.py` + `hr_authorization` / `hr_authorization_event`。状态机 `draft→confirmed→active⇄suspended→expired/revoked`（+`approving`/`rejected`），暂停/撤销/过期**原因必填**。**四处拦截点前置**：报告编制、报告用章、检测进度录入、任务派工；超管旁路 + `auth.enforce.report`/`auth.enforce.task` 双开关。SoD 靠 `report/service.py::resolve_report_roles()` **动态探测**审批节点数（≥2 硬拦截 63008），管理员发流程新版本即生效，**代码零改动**。
- 审计、签名、授权三处的错误码（30003–30005 / 61003–61004 / 63005–63009 / 98014）**必须**在 `app/core/response.py` 与 `frontend/src/api/types.ts` **双侧登记**。
- **审计日志"开了不等于合格"**：当前只有手动校验入口，**定期审阅机制未建**（排 B10-6）。
- **B10-1 落地了"离职当日清权"的系统侧**：禁号 + 撤 MFA + 撤 B9 授权 + 代理失效 + 清 A/B 角，全部在 `hr/employment.py::effect_employment()` 里；**物理权限（门禁/钥匙/工牌）无对接**，已写「待现场确认」审计（诚实标注外部依赖，别假装已闭环）。

## 前端架构

### 目录

```
src/
├── api/          http.ts（axios 实例）+ portalHttp.ts（门户独立实例）+ types.ts（共享 DTO）+ 各域客户端
├── modules/<域>/pages/*.vue        路由页面（componentKey 映射到这里）
├── modules/<域>/components/*.vue    模块私有组件
├── components/{common,list,form,approval,assistant,flow}/
├── layout/        AppShell + SideNav + TopBar + ContextPanel + MobileDock + TabWorkspace …
├── composables/   useListPage useDict useIsMobile useDock(在 layout) useAiCapabilities …
├── stores/        auth theme tabs branding context（pinia setup 风格）
├── router/        index.ts（静态+动态路由）+ guards.ts
├── styles/        tokens/*.tokens.json → tokens.css + element-vars.css（生成物）· page.css（页面骨架）
├── locales/{zh-CN,en-US}/*.json
```

### 路由是后端驱动的

菜单树存在数据库（`sys_menu`），登录后 `auth.fetchMe()` 拿到 `MenuNode[]`，`src/router/index.ts::menuToRoutes` 转成路由，`componentKey`（形如 `task/TaskList`）经 `import.meta.glob('@/modules/*/pages/**/*.vue')` 解析到页面文件，再 `router.addRoute('Shell', r)` 挂载。菜单变更不需要改前端路由代码。侧栏分区结构见下文「导航分区」。

动态路由 `meta` 字段：`tabKey` `titleKey`（i18n 键，菜单标题由后端给 `titleKey`）`title`（回退）`icon` `keepAlive` `componentName`（对应 `defineOptions({ name })`）`permission` `menuId`。静态深链写在 `extraRoutes`（如 `/contract/contracts/:id`）。

`src/router/guards.ts` 负责：未登录跳 `/login`；首次进入时拉 `fetchMe` 并注册动态路由后**重定向到同一路径**；匹配到 NotFound 但路径在 `allMenuPaths` 中说明无权 → 403；`onError` 捕获 chunk 加载失败并一次性 reload 自愈；`afterEach` 打开/切换标签页。

### API 层

`src/api/http.ts` 只有一个 axios 实例（`baseURL: '/api/v1'`）：

- 请求拦截器带 `Authorization: Bearer <bs.access_token>`
- 响应拦截器拆信封：`code === 0` 通过；`code === 20001` 走**单飞 refresh**（`POST /api/v1/auth/refresh`）后重放原请求一次；其他非零码弹 `ElMessage.error(message)` 并 reject
- `request<T>()` 返回已拆封的 `data`；`download()` 处理 blob 与 `content-disposition` 文件名；`toQuery()` 把 `filters`/`range` 对象展开成 `filters[k]` / `range[k]`
- 门户用 `src/api/portalHttp.ts`（`baseURL: '/api/v1/portal'`，独立 token `bs.portal_token`，**无刷新**）
- 二步验证通过 `X-Step-Up-Token` 头传递

每个域的客户端文件形如 `src/api/contract.ts`：一个端点一个导出函数，路径相对 `/api/v1`，共享 DTO 全部放 `src/api/types.ts`。

### 设计令牌

源文件 `src/styles/tokens/*.tokens.json`：`base`（语义色/强调色/图表色/排版/间距/圆角/阴影/**动效**/密度/布局）、`default-light`、`default-dark`、`brand-smvic`。

`pnpm token:build` 生成 `src/styles/tokens.css` 与 `src/styles/element-vars.css`（**AUTO-GENERATED，禁止手改**，ESLint 已忽略）。命名：嵌套路径 → kebab-case → 前缀 `--bs-`，如 `color.brand.primaryHover` → `--bs-color-brand-primary-hover`。

主题切换：`src/stores/theme.ts` 在 `<html>` 上写 `data-theme`（light/dark/brand-smvic）、`data-density`（comfortable/compact）、`data-accent`（6 种），并持久化到 `localStorage`（`bs.theme` / `bs.density` / `bs.accent`）；`index.html` 内联脚本在首屏前还原以防闪烁。

canvas/SVG 里 `var()` 无效，用 `src/utils/chartTheme.ts::resolveToken(name, fallback)`（`getComputedStyle` 读取）、`chartPalette()`、`statusColor()`。

### 样式与动效

`src/styles/` 加载顺序：`tokens.css` → `element-vars.css` → `reset.css` → `page.css` → `motion.css` → `mobile.css`（**`mobile.css` 必须最后**，它要在窄屏覆盖令牌）。

`motion.css` 提供 `bs-fade-up` / `bs-fade-in` / `bs-stagger` / `page-anim` / `pop-enter-active` / `pop-leave-active` 等类，并在文件末尾用 `prefers-reduced-motion: reduce` 全局关闭非必要动画（**新动画必须走令牌 + 该 kill switch，不能只靠动效传达状态**）。`mobile.css` 是 <768px 的全局覆盖（近全屏弹层、44×44 触控热区、字号下限）。

**动效时长/缓动只允许引用令牌**：`--bs-motion-fast` `--bs-motion-base` `--bs-motion-slow` `--bs-motion-enter` `--bs-motion-exit` `--bs-motion-curve`；**退场必须快于入场**（`--bs-motion-exit < --bs-motion-enter`）。组件里不得硬编码 ms 或 cubic-bezier。

### 布局与宽度规范

全站只有一套页面骨架与宽度体系，入口是 `src/styles/page.css` + `base.tokens.json` 的 `layout` 块。**新页面一律用 `.bs-page` 家族，不要自造 padding / max-width。**

| 类 | 用途 |
| --- | --- |
| `.bs-page` | 页面根容器：16px 内边距（`--bs-layout-content-padding`）、`--bs-color-bg-app` 底色、12px 区块间距 |
| `.bs-page--fill` | 填满滚动视口（列表页模型，表格内部滚动） |
| `.bs-page--scroll` | 页面自身滚动（详情页模型） |
| `.bs-page--narrow` | **页面根的修饰类**（与 `.bs-page` 同时使用）：单栏表单/文档页把内容列限宽 960px 居中 |
| `.bs-page--flush` | 去掉内边距（容器已由 `ListPage` 提供） |
| `.bs-page-card` / `--flush` | 页面内的白卡内容块 |
| `.bs-page-header` / `.bs-page-title` / `.bs-page-actions` | 页面头部（用 `components/common/PageHeader.vue`，不要重复定义标题样式） |

宽度令牌（`pnpm token:build` 生成）：`--bs-layout-content-padding`（16px，窄屏回落 12px）、`--bs-layout-content-narrow-max-width`（960px）、`--bs-layout-form-max-width`（640px）、`--bs-layout-field-max-width`（420px）、`--bs-layout-section-gap`（12px）、抽屉 5 档 `--bs-layout-drawer-{xs,sm,md,lg,xl}`、弹窗 5 档 `--bs-layout-dialog-{xs,sm,md,lg,xl}`。**抽屉/弹窗宽度只能引用这 10 个令牌**，禁止裸 px / 百分比。

**三条不变量（改错就崩）**：

1. `.bs-page` 基类不得带 `min-height: 100%` —— 列表页的 `height:100%` 父链是 `el-table` 内部滚动的承重链，链断表格会塌成 0 高；需要"填满"请显式加 `.bs-page--fill`。
2. 不改变页面的滚动模型（全站并存三种：表格内滚 / 页面自滚 / `tab-content` 滚），换了会连带改掉 `TabWorkspace` 的滚动记忆与 `TaskEdit` 的 sticky 头。
3. 详情页根容器是 `--bs-color-bg-app`（灰底），内部内容块用 `.bs-page-card`（白卡）；不要把根容器刷成 surface 底色 —— 切页时背景会跳变。

**不得令牌化的"承重"像素**：`AiUsage` 的图表容器高度（ECharts 初始化时读容器高度且无 `ResizeObserver`，改成变量高度会塌陷）、`QuotationPrint` 的整块打印样式（物理尺寸语义）、`TaskEdit` 的 `scroll-margin-top: 72px`（sticky 头锚点）、`TaskEdit` 的 220px 固定侧栏、`TaskList` 的 `size="70%"` 抽屉、门户自有体系。

### 导航分区

侧边导航 = **工作台 + 8 个业务分区 + 底部钉住的系统管理**：

```
工作台                      业务中心（客户/合同/任务/报告/项目/财务）
生产资源（设备/排程/样品与物料/采购/产能）    库存与资产（进出库管理/资产财务）
销售中心（报价/模板/营收）                    经营与协同（客户自助/在线委托/客户方人员备案/客户自助账号/知识库）
行政人事（工时填报/工时统计/人员档案）        流程与办公（新申请/我的申请/作业申请/流程待办/消息中心）
访客与安全（访客/区域/凭证/审计/交接/预警/巡检）  系统管理（底部固定）
```

- 分区切分由 `src/layout/useNavZones.ts` 完成：顶层 `dir` 是"分区"（可排序），`System` 是固定分区（`isSystemZone` 匹配 `name === 'System' || titleKey === 'menu.system'`）。
- 分区顺序存在用户 prefs `navOrder`（顶层菜单 id 列表）；分区集合变化后旧偏好失效，`validOrder` 已内置回退。
- **分区手风琴**：展开态只渲染「工作台 + 分区头 + 当前展开的一个分区」，分区头可点击折叠（带 caret、条目计数徽标、`aria-expanded`）；再次点击同一分区 → 全部收起。展开状态记在 `localStorage['bs.navZoneOpen']`（分区 id，`'none'` 表示全部收起），**记住上次展开的分区，不随路由自动切换**；仅在记忆的分区已失效（权限调整/菜单改版）时重新定位到当前路由所在分区。
- **折叠态 = 图标轨 + 浮层**：64px 折叠态只显示「工作台 + 各分区图标」，悬停/聚焦分区图标弹出 `ElPopover` 浮层（`placement="right-start"`，`popper-class="nav-zone-flyout"`），面板内二级目录作分组标题、叶子菜单作条目，面板自身滚动。**必须用 `ElPopover` 而非自绘 absolute 浮层**（`.app-shell`/`.side-nav` 是 `overflow: hidden`，自绘浮层会被裁掉）。
- 分区相关纯函数都在 `useNavZones.ts`（可单测）：`zoneHasPath` / `findZoneByPath`（当前路由落在哪个分区，按路径前缀匹配详情页）/ `countZoneItems`（分区条目数）/ `parseOpenZoneId`（记忆值求交集）。
- **菜单结构在后端**：`app/seeds/init_data.py::MENU_TREE`。种子按 `name` 匹配已有行并同步 `title_key/path/component_key/icon/permission/menu_type`，**不回写 `parent_id`/`sort`** —— 结构调整必须跑 `uv run python scripts/migrate_nav_zones.py`（幂等，规范结构直接从 `MENU_TREE` 推导）。
- `perm_to_id[perm] = m.id`：**一个权限码只能挂一个菜单**，撞车会让后者顶掉前者，超管与角色都拿不到被顶掉的菜单（种子会打印 `WARN duplicate permission`）。
- `HIDDEN_MENUS` 里的菜单强制 `visible=0`（入口并入他页，但权限点仍由它承载）。
- 登记新菜单的完整步骤见 `docs/roadmap-2026-11.md` 的「新需求接入路径」。

### 对外门户（/portal）

门户是**与内部系统完全隔离的第二套外壳**，面向供应商 / 客户等外部合作方。

- **认证隔离**：门户账号存 `partner_user`（不并入 `sys_user`），令牌 `typ=portal_access` + `aud=portal`；内部 `decode_token` 不校验 audience，带 aud 的门户 token → 401；门户 `decode_portal_token` 强制 audience=portal，内部 token → 401。**双向不可用**，新增接口别把两边混在一个 axios 上。
- **独立布局**：`src/modules/portal/pages/PortalLayout.vue`（桌面 sticky 顶栏 + 移动精简顶栏 + `PortalMobileDock.vue` 底部 Dock + 页脚），**不复用内部 `AppShell`**；门户路由是 `/portal` 的兄弟树，走 `guards.ts` 的 `/portal` 早分支。
- **权限范围**：`partner_user.perm_scope` 逗号分隔（`tender` / `entrust` / `staff` / `visit`），门户页面按 `hasScope()` 裁剪导航项与 Dock。
- **门户页面**（`src/modules/portal/pages/`）：`PortalHome`（首页）`PortalTenderList` `PortalTenderDetailPanel` `PortalMy` `PortalOrders` `PortalStaff` `PortalRegister` `PortalVisits` `PortalVisitDetail` `PortalProgress` `PortalReports` `PortalBilling` `PortalHandovers`。
- **i18n 命名空间**：`portal.json` 的根是嵌套的 `"portal"`（历史遗留），所以运行时键是 **`portal.portal.*`**（如 `t('portal.portal.home.title')`），不是 `portal.home.*`。其余域是「域名即根」（`visitor.json` → `visitor.visit.*`，`common.json` → `common.action.*`）。
- **门户数据隔离**：报告 / 对账 / 交接 / 进度一律按 `partner_user.customer_id` 过滤；报告下载走**一次性下载码**（Redis `portal_dl:{rid}`），对外不暴露内部审批意见与审批人。
- **访客预约闭环**：门户 `POST /portal/visits` → `vis_visit(status=pending)` → 审批引擎（`biz_type=visitor_visit`）→ 通过后自动下发凭证 + 短信 → 门户看二维码 → 扫码签到/签离。审批链在「流程设置」里设计，节点审批人类型 `FORM_USER` / `FORM_ROLE` / `FORM_DEPT_LEADER` 的 `approverValue` 存**流程变量名**（如 `hostUserId`），不是用户 id。
- **门户登录**：合作方登录并入主登录页 `/login?tab=partner`；旧路由 `/portal/login` → 重定向，`/portal/tenders/:id` → `/portal/tenders?id=N`。
- **PWA**：`frontend/index.html` + `frontend/public/manifest.webmanifest` + `apple-touch-icon.png`，可「添加到主屏」。

### 共享组件与组合式函数

- `components/list/`：`ListPage`（页面骨架 slots: actions/searchBar/statusTabs/toolbar/table）、`SearchBar`（声明式 `SearchField[]`：`key` `labelKey` `type` `options` `width`）、`StatusTabs`（**每个 tab 必须带 count，含 all，且 all 在最左**）、`ListTable`（`ListColumn[]` + 分页 + 服务端排序；**内部是 `ResponsiveTable` 的适配层**，窄屏自动降级为卡片）、`ActionBar`（行操作，图标/颜色全局统一，`perm` 控显隐，`confirm` 二次确认，超出内联数量收进「更多」）、`ExportButton`；`types.ts` 导出 `ListColumn` / `SortChange`
- `components/common/`：`BackButton`（页面级返回，**放右上角**）、`PageHeader`（**唯一的页面标题组件**，props `title` + slot `actions`）、`StatusTag`、`CountUp`、**`ResponsiveTable`**（桌面表格 / 窄屏卡片流，列表页统一走它；**分页条由它统一渲染**：`.table-pagination` = 左「共 N 条」+ 右 `el-pagination`，`showPagination` 默认 `true`，内嵌表格传 `:show-pagination="false"` 关掉）、**`SignaturePad`**（canvas 手写签名板，触屏可用）
- `components/form/`：`RemoteSelect` `ContractSelect` `CustomerSelect` `SmartInput`（本地历史）`UploadFiles`
- `components/flow/`：`FlowChainDesigner` `FlowChainNode` `FlowChainConnector` `FlowGraphViewer` + `flowModel.ts`（`process_graph` 双写兼容 LogicFlow）
- `components/assistant/AiAssistant.vue`（全局悬浮助手）
- `layout/`：`AppShell`（grid: topbar / [sidenav | main | context] / statusbar）、`SideNav` `SideNavItem` `TopBar` `NotifyBell` `ShortcutBar` `CommandPalette`（Ctrl/Cmd+K）`ContextPanel` `TabWorkspace`（KeepAlive + 滚动记忆）`MobileNavDrawer` `MobileDock` `DockSettingsDialog` `NavSortDialog`
- `composables/`：`useListPage`（列表页状态机：query/load/search/reset/setStatus/onSortChange/exportList，挂载与 KeepAlive `onActivated` 自动刷新）、`useDict`、`useIsMobile`（`matchMedia('(max-width: 767px)')`）、`useAiCapabilities`、`useHotkeys`、`useShortcuts`、`useDocumentTitle`、`usePopoverA11y`
- `layout/useDock.ts`（底部 Dock 快捷项，持久化到用户 prefs `dockShortcuts`，按权限过滤，默认 todo/tasks/contracts/OA-apply）、`layout/useNavZones.ts`（业务分区 + 固定的「系统管理」分区）

## 强制规范（CI 会拦）

1. **不得硬编码界面文案** —— 一律 `t('domain.key')`，并在 `src/locales/zh-CN` 与 `en-US` **同时**加键。`scan:literal:strict` 在 build 中拦截硬编码中文字面量。
2. **不得硬编码颜色** —— 一律 `var(--bs-*)`；改 `src/styles/tokens/*.tokens.json` 后跑 `pnpm token:build`。`scan:colors` 在 build 中拦截裸 hex（白名单：`modules/auth/Login.vue`、`modules/sales/pages/QuotationPrint.vue`、`modules/sales/components/QuotationPreview.vue`、`utils/chartTheme.ts`）。
3. 新增 Element Plus 组件要同时改 `src/plugins/element-plus.ts`（组件数组 + 样式 import）；新图标名要登记到 `src/icons.ts`（后端菜单的 `icon` 字符串按名解析）。
4. 新页面放 `src/modules/<域>/pages/`，并确保 `defineOptions({ name: '...' })` 与路由 `componentName` 一致（KeepAlive 依赖）。
5. **每次功能性变动都要写变更日志** —— 在仓库根 `CHANGELOG.md` 顶部追加版本条目（Keep a Changelog 六类：`Added`/`Changed`/`Deprecated`/`Removed`/`Fixed`/`Security` + 语义化版本号 + 日期），并把版本号同步到 `Settings.app_version`、`frontend/package.json`、`backend/pyproject.toml`（+ `backend/uv.lock`）。`tests/test_changelog.py` 在 CI 校验一致性。
6. **可选 Boolean prop 必须显式给默认值** —— Vue 的 `Boolean` 类型 props **未传值时默认是 `false`**（不是 `undefined`）。写 `v-if="props.x !== false"`（意为「未传即允许」）时必须用 `withDefaults` 把 `x` 默认成 `true`，否则条件恒为 false、组件永远处于关闭状态（列表页分页条曾经因此全站不渲染）。`frontend/src/components/booleanPropDefaults.test.ts` 在 CI 拦截。

## UI 一致性规则

- **检索**：所有服务端分页列表页必须有 `SearchBar` 且带关键词字段 `q`；后端缺 `q` 支持时按 `filters` 白名单模式补上。小型全量列表至少给本地关键词过滤。树表（菜单/部门）豁免。
- **分页与总条数**：列表页的分页条由 `ResponsiveTable` 统一渲染（`.table-pagination`：左「共 N 条」`common.table.total` + 右 `el-pagination`），**默认开启**；`ListTable` 必须把 `:total` / `:page` / `:size` 透传下去，并接 `@update:page` / `@update:size`。纯前端全量列表（无服务端分页）显式传 `:show-pagination="false"`，别留一个点不动的翻页控件。
- **表格占满内容区**：`el-table` 只拉伸**没有固定 `width`** 的列（EP 内部 `flexColumns = columns.filter(c => !isNumber(c.width))`）；一旦所有列都写死 `width`，表格宽度 = 列宽之和，右侧会留出大片空白，与其他板块观感不一致。列表页至少保留一列弹性列（写 `min-width` 而不是 `width`）；`ListTable.vue` 已内置兜底（自动把最后一列转成弹性列），但原生 `<el-table>` 必须自己保证。
- **状态页签**：每个 tab 显示计数（含 `all`），`all` 永远最左；缺计数接口时按 `task counts` 的模式补 `…/counts`。
- **关闭/返回/页脚**：抽屉与弹窗只用内置右上角 `X`，不要额外的自定义关闭按钮；页面级返回用 `src/components/common/BackButton.vue` 放右上角。弹窗页脚：次要操作在左、主要操作在右。
- **导航**：系统管理区固定在侧边导航**底部**（图标 + 文字，仅在存在可见的管理菜单时显示，展开态点击弹出向上的 popover、折叠态向右弹出）。折叠/展开按钮同在该底部工具条，**绝不在左上角**。折叠态只显示图标（原生 `title` 提示），系统管理入口折叠态仅图标但 popover 仍可用。导航分区排序在 `NavSortDialog`，入口在 TopBar 头像菜单（同时承载外观/语言）。展开态分区**手风琴**（一次只展开一个分区，分区头可点击折叠 + 计数徽标；展开状态记 `localStorage['bs.navZoneOpen']`）；折叠态为**图标轨 + 分区浮层**（悬停分区图标弹出该分区菜单）。
- **移动端外壳**（<768px，`useIsMobile`）：侧边导航收进汉堡抽屉（`MobileNavDrawer`，同样的分区/菜单数据与权限过滤，分区头同样可手风琴折叠，与桌面共用 `bs.navZoneOpen`）；右侧上下文面板变浮动按钮 + 右抽屉；状态栏隐藏。底部常驻 `MobileDock`：放大的中间 Workbench 按钮 + 4 个可自定义快捷项（长按 Dock 或头像菜单「Dock Shortcuts」打开 `DockSettingsDialog`；存用户 prefs `dockShortcuts`，按权限过滤，默认 todo/tasks/contracts/OA-apply）。全局覆盖样式在 `src/styles/mobile.css`。
- **动效**：见上文「样式与动效」。
- **移动优先**（窄屏判定统一用 `useIsMobile()`，断点 **767px**）：
  - **表格 → 卡片**：列表一律走 `components/common/ResponsiveTable.vue`（`ListTable.vue` 是它的适配层）。桌面 `el-table`、窄屏自动降级为卡片流（首列作卡片标题，其余列渲染「标签：值」行）。单元格内容统一走 `#cell="{ row, col }"` 具名作用域插槽 —— 桌面表格与移动卡片因此永远同源。表格里没有对应位置的「操作」列，用 `#cardFooter` 补到卡片底部。**新列表页不要直接写裸 `<el-table>`**。
  - **主操作吸底**：审批意见/同意/驳回、报名/投标提交、预约提交等高频动作在窄屏用 `position: sticky; bottom: 0` + `env(safe-area-inset-bottom)`（参考 `ApprovalActionbar.vue`）。
  - **表单**：窄屏 `label-position="top"`，输入框最小触控高度 44px；手机号 `inputmode="tel"`、邮箱 `inputmode="email"`、验证码/密码 `enterkeyhint`。
  - **筛选**：超过 4 个筛选项时窄屏改**底部弹层**（`el-drawer direction="btt"` + `append-to-body`），不要横向长条。
  - **画布/流程图**：LogicFlow 画布窄屏不可用（需横向拖拽且隐藏容器 `fitView` 会失效）—— 用「点击展开」折叠，展开时才懒初始化、折叠时销毁。
  - **签字**：触屏签名用 `components/common/SignaturePad.vue`（canvas Pointer Events），不要用 textarea 代替。
  - **安全区**：全站固定元素（底部 Dock、吸底操作条）必须加 `env(safe-area-inset-bottom)`。
- **草稿 / 提交审批（凡走审批流程的单据表单一律如此）**：只要单据进入审批引擎（见 `app/modules/approval/registry.py::BINDINGS` 的 19 类），填报弹窗/详情页的页脚必须是**两个按钮**：左「`common.action.saveDraft`（保存草稿）」→ 只落库不发起流程；右「`common.action.submitApproval`（提交审批）」primary → 落库后**立即**调 `POST …/submit` 发起审批。参考实现：`ContractEdit` / `TaskEdit`（`saveDraft` + `saveAndSubmit`）、`QuotationEdit` / `TimesheetFill` / `PaymentCreateDialog` / `ReceiptList` / `DisposalList` / `ProjectList` / `PurchaseRequestList` / `PurchaseContractList`（`save(submit = false)` 两分支）。
  - **例外**：后端**没有草稿态**的单据（结算单 `settlement`、开票申请 `invoice`、报告用章 `report_seal`、访客登记 `visitor`）只有**一个** primary 按钮，文案必须是「提交审批」，**不得**写成含糊的「提交」或「保存」；结算单这类要在表单上方加 `el-alert` 说明"提交后立即发起审批"（`finance.settlement.submitTip`）。
  - 「提交审批」按钮按权限点隐藏（`v-permission="'<域>:<资源>:submit'"`），`v-permission` 支持**数组**表示"任一满足"（`['hr:timesheet:submit','hr:timesheet:create']`）。
  - **新增单据类型时**：先在 `registry.py::BINDINGS` 登记 `submit_from`（必须含 `draft`），再照上面加两个按钮；流程总开关关掉时只显示「保存草稿」（用 `useFlowCapability().flowEnabled(bizType)` 判断）。

## 代码风格

前端：Prettier（`semi: false`、`singleQuote`、`printWidth: 100`、`trailingComma: all`、LF）+ ESLint flat config（`typescript-eslint`、`eslint-plugin-vue`）。组件 PascalCase 且带 `defineOptions({ name: '...' })`；变量 camelCase；组合式函数 `useXxx`；CSS 类 kebab-case。

后端：Ruff，`line-length = 120`、`target-version = "py313"`、`select = ["E","F","I","UP","B"]`、`ignore = ["B008"]`（FastAPI Depends 惯用法）、`known-first-party = ["app"]`。优先 `Annotated`/`Depends`，不要在调用处给默认值。

## 测试

- 后端 `backend/tests/test_*.py`（pytest）。`conftest.py` 建库 `bizsys_test` 并**复用幂等种子**；绝不能指向开发库。fixture：`client` / `admin_headers` / `manager_headers` / `leader_headers` / `db`。测试通过 HTTP 黑盒方式打 `client`；登录需要图形验证码，helper `captcha_fields()` 直接从 Redis 读答案。每个 bug 修复与每条新 API 路径都要补测试。
- 前端 Vitest 文件与源码同目录，命名 `*.test.ts`。目前只有纯函数单测（未装组件挂载库）：`src/i18n.test.ts`、`src/composables/oaFormDesignDraft.test.ts`、`src/composables/smartInputHistory.test.ts`、`src/components/flow/flowModel.test.ts`、`src/layout/useDock.test.ts`、`src/layout/useNavZones.test.ts`、`src/modules/oa/components/fieldOps.test.ts`。

## 提交与 PR

Conventional Commits，中文 subject：`feat(oa): OA 前端 + 统一流程设计`、`fix(router): 发版后首次打开空白页自愈`、`docs:`、`chore:`。常用 scope：`admin` `oa` `flow` `contract` `finance` `frontend` `scripts` `layout`。正文用短 bullet，末尾写验证结果（如「测试 100 全绿」）。

PR 需说明改动、新增的 Alembic 迁移或种子数据、跑过的命令，UI 改动附截图。

## 安全与配置

`backend/.env.example` → `backend/.env`（不入库）；生产前必须更换 `JWT_SECRET` 与数据库凭据。密钥在 `sys_config` 中以 AES-GCM 加密存储（`enc:` 前缀），`app/core/crypto.py` 负责加解密。上传文件落在 `backend/uploads/`（gitignored），扩展名白名单由 `settings.upload_allowed_ext` 控制，上限 `upload_max_mb`（默认 50MB）。权限码 `module:resource:action`，**必须服务端强制**，特权操作写 `sys_audit_log`。

## 部署

`deploy/docker-compose.yml` 全栈（前端 18080 / 后端 18000 / MySQL 13307 / Redis 16379），端口与密钥在 `deploy/.env`（不入库）。容器内 nginx 同源转发 `/api/` 到后端，网关反代到 18080；注意 `proxy_read_timeout 300s` 与 `client_max_body_size 50m` 需在网关侧对齐，否则上传/导出被截断。种子账号：`admin / Admin@123456`、`manager1 / Test@123456`、`leader1 / Test@123456` —— 上线后立即改密。

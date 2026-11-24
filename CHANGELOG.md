# 变更日志

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范，版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

分类含义：`Added` 新增 · `Changed` 变更 · `Deprecated` 废弃 · `Removed` 移除 · `Fixed` 修复 · `Security` 安全。

**每次功能性变动都要在本文件顶部追加一条版本条目**（与代码同一次提交），分类按上表选择；系统内的「系统管理 → 变更日志」页面（`/admin/changelog`）直接渲染本文件。

---

## [0.10.0] - 2026-11-24

### Added

- **审计日志 / 登录日志的 IP 属地**：IP 下方以更小的字号展示属地（省 / 市，如「安徽省 宣城市」），内网 / 回环分别标注「内网」/「本机」。数据源为**离线 ip2region v4 库**（`backend/app/core/data/ip2region_v4.xdb`，随仓库入库）+ vendored 纯 Python 绑定（`backend/app/core/ip2region/`，Apache-2.0 / MIT 双许可）—— **不引入 pip 依赖、不访问外网**。属地在**读取时**计算：审计表是只追加的（不可 UPDATE），落库属地需要回填历史行，因此不出列、不加迁移，顺带让历史记录立即就有属地。
- **新增登录日志查询端点** `GET /admin/login-logs`（沿用 `admin:audit:list` 权限）：此前 `sys_login_log` 只写不查，没有任何读取入口。审计日志页新增「审计日志 / 登录日志」视图切换，登录日志支持按用户名检索、按成功 / 失败过滤。
- 新增测试 `backend/tests/test_audit_ip_region.py`（属地分类、公网解析、审计 / 登录日志出参、门户入口不在内网导航）。

### Changed

- **内网导航移除「客户自助 / 在线委托」两个外部门户入口**（`PortalHome` / `PortalOrders` 改为隐藏菜单）：门户是与内网隔离的第二套外壳（独立认证 `partner_user` / `typ=portal_access`），内网人员点进去只会跳到门户登录页，体验很差。菜单行保留（权限点仍由其承载），门户用户仍可直接访问 `/portal`。

---

## [0.9.0] - 2026-11-24

### Added

- **登录页新增「记住登录状态」勾选**：勾选 = **30 天内免登录**（refresh token 30 天 + 令牌存 localStorage，跨浏览器重启保留）；不勾选 = **仅本次浏览器会话**（refresh token 12 小时 + 令牌存 sessionStorage，关闭浏览器即退出）。会话口径写进 refresh token 的 `rem` claim，**刷新轮换时必须继承**，否则「不记住」会被悄悄延长成 30 天。
- **改密后吊销该用户其余登录会话**：会话最长 30 天，不吊销等于旧密码在别处仍可用；带 `refresh_token` 调用则保留当前设备会话（改密后不强制自己下线）。Redis 侧新增「用户全部会话」索引 `refresh:user:{uid}`，支持按用户批量吊销。
- 新增环境变量 `REFRESH_TOKEN_EXPIRE_DAYS`（默认 30）/ `REFRESH_TOKEN_EXPIRE_HOURS`（默认 12），`deploy/docker-compose.yml` 已透传。

### Fixed

- **修复登录状态实际只能维持 15~30 分钟、随后被踢回登录页**：后端刷新会**轮换** refresh token（吊销旧的），但前端只存了新的 access token、**没存新的 refresh token** —— 下一轮续期拿的是已吊销的旧 token，直接 401。现在前端会把轮换后的 refresh token 存回（并保持原有的「记住 / 会话」存储口径）。
- 修复登出时用的是 store 里可能已过期的 refresh token（旧会话残留）——改为实时从存储读取。

---

## [0.8.0] - 2026-11-24

### Added

- **企业微信在用的 39 个审批模板完整复刻**到本系统（源文档 `企业微信审批与组织数据技术文档.html`，**含真实人员数据 → 源文件不入库**，入库的只有脱敏后的 `backend/app/seeds/data/*.json`）。随种子自动落地：跑一次 `uv run python -m app.seeds.init_data` 即有 **39 张 OA 表单 + 39 条审批定义**（347 字段 / 350 节点 / 122 条件节点 / 106 分支 / 1487 条节点字段权限 / 64 个暴露变量字段），**0 结构性问题**。
- **流程引擎能力升级**（承接企微在用模板，原系统接不住的部分）：
  - 条件判断支持**规则组**（`{logic: "and"|"or", rules: […]}`，可嵌套）与**区间** `between`，并补齐 `in` / `empty` / `not_empty` 操作符（`approval/condition.py`、`oa/schemas.py::CONDITION_OPS`、前端 `ConditionEditor.vue`）；
  - 新增**办理节点** `executor`（单人处理，可配「办理意见必填」「办理人可修改」）；
  - 新增**流程通用选项** `approval_definition.options`（10 个开关：审批意见必填 / 意见需签名 / 允许加签 / 通过后可撤销 / 审批人可改流程 / 可改抄送 / 办理人可修改 / 允许代提交 / 明细表权限控制）—— **未配置时全部保持既有行为**；
  - 新增**节点字段权限** `approval_node.field_permissions`（`editable` / `viewonly` / `hidden`）：按当前待办节点掩码，`hidden` 字段从 schema 与数据中剔除、`viewonly` 下发只读标记；
  - 新增**审批意见手写签名**：「审批意见需签名」落地，待办按需展示签名板，签名随意见提交并写入审批时间线留痕（**只作用于审批节点**，办理节点走「办理意见必填」口径）。
- **表单控件升级**：新增 6 类控件 —— **明细表**（可增删行的子表）、**公式**（支持 `SUM(表.列)` 求和与 `HOURS(字段)` 时长，提交时服务端重算）、**手机号**、**位置**、**假勤原子**（出勤 / 请假 / 补卡）、**人事原子**（入职 / 转正 / 调岗 / 离职）；「成员」控件支持**多选**。
- **表单可见范围** `oa_form.scope_json`（部门 / 角色 / 人员），OA 目录按当前用户裁剪 —— 企微「可见范围」落地。
- **审批流程 JSON 化**（用户诉求「所有审批流程可以 json 化，为后期批量导入导出创造便利」）：定义流程包 schema `bizsys.flowpackage/v1`，一套 JSON 同时承载「OA 表单 + 审批定义」，新增 4 个端点 —— 导出全部 / 导出单个 / 导入（幂等，`?dry_run=true` 可试导入）/ OA 表单导出；新增系统管理页「**审批模板包**」（`/admin/flowpackages`）。产物 `backend/app/seeds/data/wecom_flow_packages.json`（39 个流程包）既是迁移留档，也是现成的批量导入样例。
- **模拟组织与人员种子**（全模拟，规避隐私风险）：11 个部门 → `sys_dept`（`WC01…WC11`）、23 个企微标签 → `sys_role`（`wc_tag_*`，**只做审批人来源，不绑定菜单权限**）、40 名员工 → `sys_user` + 任职 + 标签关系（用户名 `mockNNN`、姓名 `模拟员工NN`）、30 个岗位 → `hr_position`。**证件号 / 手机 / 邮箱 / 企微 vid 一律留空**。
- 新增权限码 `admin:flow:export` / `admin:flow:import` 与菜单 `menu.flowPackages`；新增手写迁移 `nc2b3c4d5e6_wecom_flow_upgrade.py`、`nd2b3c4d5e6_oa_form_scope.py`。
- 新增测试：`tests/test_wecom_org_seed.py`、`tests/test_wecom_templates_import.py`（15）、`tests/test_flow_packages.py`（9）、`tests/test_approval_executor_options.py`（12）、前端 `src/modules/oa/formLogic.test.ts`（23）。

### Changed

- 前端表单运行时支持**多选成员**、**公式聚合求值**（与后端同语义）、**节点只读掩码**；表单设计器新增「允许多选」开关与公式语法提示（`SUM(表.列)` / `HOURS(字段)`）。
- 审批操作条按流程通用选项决定「通过」是否必须填意见、是否必须签名、是否展示「加签」按钮；待办出参新增 `commentRequired` / `commentSignRequired` / `executorCommentRequired` / `allowAddSign` 四个标记。
- 条件分支的 op 编码推定口径固化：op1=eq / op2=gt / op3=lt / op4=gte / op5=lte / op6=between（文档未给 op 语义，按条件文案交叉推定；阈值恰好相等时可能有差，已列入导入报告的「待人工复核」项）。

### Fixed

- 修复 OA 表单校验把 `SUM(表.列)` 的**聚合参数误判为「引用的控件不存在」**（`_extract_aggregates` 返回值解包时丢掉了 kind，导致所有带明细表求和的公式字段都校验失败）。
- 修复企微「时长」类条件无法落到流程变量的问题：`daterange` 不可暴露，现合成 `HOURS(<字段>)` 公式字段供引擎比较。

### Security

- 移植材料全程脱敏：源技术文档 `企业微信审批与组织数据技术文档.html`（含真实人员数据）**不入库**（已在 `.gitignore`），入库的只有脱敏后的 `backend/app/seeds/data/*.json`；真实姓名一律替换为 `模拟员工NN`、账号替换为 `mockNNN`，**手机号 / 邮箱 / 证件号 / 企微 vid 全部丢弃不落盘**（本次追加清除残留的部门企微 ID）。

---

## [0.7.3] - 2026-11-24

### Fixed

- 列表页的**分页条与总条数从来没渲染过**（审计日志、在线任务委托、往来单位、合同等所有服务端分页列表都看不到翻页控件和「共 N 条」）：根因是 Vue 对 `Boolean` 类型 props 在**未传值时默认取 `false`**，`ResponsiveTable` 的 `showPagination` 未传值即 `false`，于是 `v-if="props.showPagination !== false"` 恒不成立。改为用 `withDefaults` 显式默认 `true`，分页条恢复正常。
- 审批操作条 `ApprovalActionbar` 的 `canAct` 同类隐患：未传值时默认 `false` 会整块隐藏「同意 / 驳回」按钮，改为显式默认 `true`（调用方显式传值的行为不变）。
- 分页条在窄屏改用紧凑翻页（上一页 / 页码 / 下一页）：Element Plus 的翻页条在 375px 宽度下会折成三行、把卡片列表区挤没。

### Added

- 新增 Boolean prop 默认值守卫（`frontend/src/components/booleanPropDefaults.test.ts`）：可选 Boolean prop 用「未传即允许」写法（`x !== false`）时必须在 `withDefaults` 里显式给默认值；同时锁定列表分页条默认渲染、`ListTable` 显式转发 `showPagination`。

---

## [0.7.2] - 2026-11-24

### Fixed

- 补齐三个菜单的中英文标题词条（在线任务委托 / 客户自助账号 / 客户方人员备案）：此前词条缺失，侧边导航、顶栏标题、命令面板与底部 Dock 直接回显原始键名（如 `menu.entrustList`）。

### Added

- 新增菜单标题 i18n 守卫（`backend/tests/test_menu_i18n.py`）：后端种子 `MENU_TREE` 里的每个 `menu.*` 标题键，必须在 `zh-CN` / `en-US` 的 `menu.json` 都有词条，且中英键集一致。

---

## [0.7.1] - 2026-11-24

### Fixed

- 审计日志 / 登录日志 / NDA 签名绑定的客户端 IP 改为**真实访问者 IP**：此前记录的是 TCP 对端地址（容器 nginx、网关容器的内网 IP），现由 `app/core/client_ip.py::client_ip()` 从 `X-Forwarded-For` 按受信任代理跳数还原；全仓 13 处 `request.client.host` 已替换。
- `FastAPI(version=...)` 改为取 `Settings.app_version`（此前硬编码 `0.1.0`，健康检查与 OpenAPI 报的是旧版本号）。

### Changed

- 新增反向代理链配置：`TRUSTED_PROXY_HOPS`（默认 `2` = 上层网关 + 容器 nginx）/ `TRUST_PROXY_HEADERS` / `TRUSTED_PROXY_CIDRS`（可选，按网段判定代理），由 `deploy/docker-compose.yml` 透传给后端容器；口径见 `deploy/DEPLOY.md`。

---

## [0.7.0] - 2026-11-23

### Added

- 系统管理新增「变更日志」页面（`/admin/changelog`，菜单 `menu.changelog`）：按 Keep a Changelog 规范按版本倒序展示全部功能性变动，分类徽标 + 时间线视图。
- 后端新增 `GET /api/v1/admin/changelog`（仅需登录）：解析仓库根目录 `CHANGELOG.md`，返回当前版本号、最新版本、发布日期与分类条目。
- 变更日志纳入 CI 校验：条目可解析、版本号严格递减、当前版本与 `frontend/package.json` / `backend/pyproject.toml` / `Settings.app_version` 三处一致；新增「变更日志门禁」CI 作业 —— 改动 `backend/app` / `frontend/src` / `backend/alembic` 却没更新本文件的提交直接失败。

### Changed

- 应用版本号提升至 `0.7.0`（`frontend/package.json`、`backend/pyproject.toml`、`app.core.config.Settings.app_version`）。
- 交付流程增加一步：功能性变动必须同步更新本文件（见 `docs/roadmap-2026-11.md` 的「新需求接入路径」）。

---

## [0.6.0] - 2026-11-23

### Added

- B10-1 HR L1 基础人事：组织架构（`sys_dept` 扩展 + `hr_position` 岗位说明书与关键岗位/A·B 角）、员工主数据（`hr_employee` 一人一档）、人事事务单（入职 / 调岗 / 离职 / 返聘）、代理人（`hr_delegate`）、组织与人事变更轨迹（只追加）。
- 人事事务接入审批引擎（`hr_employment_approve` 流程，`pass_through=False`），并提供独立的「生效」动作：审批通过 ≠ 生效，副作用（建号 / 任职同步 / 离职清权）统一由生效动作触发。
- B9-C3 人员授权台账（`hr_authorization`）与四处拦截点前置：报告编制、报告用章、检测进度录入、任务派工。
- 前端新增四页：组织架构、岗位与说明书、人员档案、人事事务。

### Security

- 员工证件号 AES-GCM 加密落库（`enc:` 密文），列表与详情出参一律掩码；明文仅 `GET /hr/employees/{id}/id-no` 一个出口，每次访问写入审计日志。
- 离职生效时当日回收系统权限：禁用账号、撤销 MFA、撤销人员授权、失效代理与岗位 A/B 角；物理门禁无对接的部分如实标注为待现场确认。

---

## [0.5.0] - 2026-11-22

### Added

- B5 任务扩展：工序流转（同一任务同时只允许一道工序进行中）、七维分配、全过程追溯与操作流程图。
- B5 智能排程与项目：规则式贪心排期（设备 / 人员 / 样车时段独占、物料数量占用）、项目全生命周期与甘特行。
- F5 流程注册表与事件开关：19 类单据的流程绑定、流程总开关与事件触发开关面板、六类单据的「提交审批」端点。
- F5/F6 审批人类型扩展：`FORM_USER` / `FORM_ROLE` / `FORM_DEPT_LEADER`（按表单字段解析审批人）。
- F6 对外门户专业化：门户首页、移动 Dock、筛选底部弹层、访客预约闭环（门户提交 → 审批 → 下发凭证 → 扫码签到签离）、经营数据视图。

### Changed

- 全站移动优先：列表表格窄屏自动降级为卡片流、主操作吸底、筛选改底部弹层、手写签名板、流程图窄屏折叠。
- 全站走审批流程的单据统一为「保存草稿 / 提交审批」双按钮。

---

## [0.4.0] - 2026-11-21

### Added

- B1 基础设施：全站布局与宽度体系（`.bs-page` 骨架 + 布局令牌）、导航分区重构（8 个业务分区 + 底部系统管理）、需求模块骨架、统一消息中心。
- B2 客户自助体系：客户自助账号（注册 → 审核 → 启用）、客户方人员备案、基于已审批合同的在线任务委托（门户下单 + 内部受理台）。
- B3 访客与安全：访客登记审批、区域分级、凭证通行、签离、只追加的合规审计。
- B4 资产与库存：仓库 / 库位 / 物料 / 采购订单 / 到货验收 / 库存流水 / 盘点 / 样件台账，资产财务（固定资产 / 折旧 / 处置 / 工具领用），BOM 物料清单与呆滞预警。

### Changed

- 侧边导航改为分区手风琴 + 折叠态图标轨浮层，展开状态本地记忆。
- 列表页统一检索、状态页签计数、表格弹性列与操作列图标化。

---

## [0.3.0] - 2026-11-13

### Added

- AI 中心：统一网关（功能开关 / 配额 / 脱敏 / 用量日志 / 重试）、用量与成本看板、模型单价、提示词注册表、知识库、自然语言问数（白名单意图，禁止自由 SQL）、每日摘要、全局助手。
- 全站 AI 辅助：合同识别、报告全文辅助、工时与 OA 智能预填、流程路由建议与异常催办、采购价格参考、招投标评标辅助、拍照进度 OCR —— 一律返回草稿，人工确认后才落库。
- 销售 AI 报价：报价模板可视化设计、AI 三级回退、审批发送、打印转合同。
- 人事工时填报与三维度统计。

### Changed

- Element Plus 按需引入 + 图标注册表 + 图表主题令牌，前端包体瘦身。
- 全站动效规范（令牌化时长与缓动 + 减少动效偏好开关）与可访问性专项（键盘可达、触控尺寸档）。

---

## [0.2.0] - 2026-10-27

### Added

- 采购管理一期：往来单位统一、采购申请、采购合同会签、样品出入库全流程。
- 采购管理二期：招投标全流程与独立认证的合作方门户。
- 合作方账号体系与门户内外打通，合作方登录并入主登录页。
- 登录图形随机码、用户级 MFA（短信 / 邮件）、消息通道设置（企微 / 邮件 / 短信）。

### Changed

- 移动端自适应：汉堡导航、可定制底部 Dock、响应式弹层表单；登录页全屏品牌化重设计。

---

## [0.1.0] - 2026-10-09

### Added

- M0 基座：FastAPI + SQLAlchemy 2（同步）+ MySQL + Redis，响应信封、权限点、审计与统一列表检索协议。
- 自研可配置审批引擎（节点 / 签署模式 / 审批人类型 / 加签转办）与事件总线。
- CRM 往来单位、合同管理、任务管理三大业务域全量模块。
- Vue 3 + TypeScript 全量前端（页签工作区、双主题、双语）。
- CI 工作流与全栈 Docker 部署（前端 / 后端 / MySQL / Redis / nginx）。

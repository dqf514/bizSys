# 架构体检报告（2026-10）

> 范围：后端架构/安全/扩展性、前端架构/可维护性/性能、数据模型/部署运维/测试体系三路只读体检。
> 定位：本系统是后续整套企业信息系统的基石，本报告作为分阶段整改路线图。
> 验证基线：后端 pytest 123 全绿、ruff 通过；前端 typecheck/i18n/test/build 通过，**lint 有 9 个既有报错（CI 必红）**。

## P0 根基风险（尽快处理）

### 安全与正确性
1. **弱 JWT 密钥可启动**：`app/core/config.py` 有开发默认值，`deploy/docker-compose.yml` 生产仍回退 `change-me-in-prod`；HS256 密钥过短有 PyJWT 警告。要求：prod 拒绝默认/弱密钥与弱 DB 凭据、企微加密密钥与 JWT 拆分、生产不建固定密码演示账号。（中）
2. **MySQL root / 无认证 Redis 默认暴露 0.0.0.0**：compose 默认发布端口且应用用 root 连库。要求：默认不发布或绑 127.0.0.1、最小权限业务账号、Redis ACL。（中）
3. **审批实例详情/时间线 IDOR**：`approval/router.py` 实例读取仅要求登录，任意用户可枚举读取合同金额/OA 表单等。要求：抽象 OA `_can_view` 为统一 `require_instance_visible`，无关用户 404，补越权测试。（中）
4. **data_scope 只有声明未生效**：角色存 all/dept/self 但列表/详情/导出/下拉/OA 资源检索均无行级过滤。要求：统一 DataScopePolicy（含归属模型、字段级脱敏、越权测试矩阵）。（大）
5. **审批失败开放**：缺审批人自动通过、未绑定流程定义时任务/结算/OA 直接生效。要求：`approval_required` 配置化、必须审批类型 fail-closed、显式"无需审批"与"定义缺失"分离。（中）
6. **审批并发未闭环**：首次发起可双开、会签完成判断与撤回未在 instance 层串行化、任务提交未锁业务行。要求：统一"业务行→instance→task"锁序，补并发测试。（中）
7. **软删除 deleted/version 允许 NULL**：`sys_user_dept` 迁移回填未写默认值导致 NULL 行被 `deleted==0` 查询漏掉且可能撞唯一键。要求：修复迁移回填 + 全表 `NOT NULL DEFAULT 0` + 数据质量检查。（中）
8. **Alembic 漏注册 OA 模型**：`alembic/env.py` 未导入 oa.models（36/38 表），测试又走 `create_all`，三条 schema 路径可漂移。要求：全模型统一注册入口、CI 增加空库迁移 diff / 历史库升级 / autogenerate 无差异检查。（中）
9. **备份不是灾备**：默认关闭、compose 无 backups 卷、内置导出无一致性快照、不含 uploads、无恢复流程与演练。要求：持久卷+异机复制、mysqldump 一致快照、manifest+校验+原子 rename、DB+文件同批次、恢复演练与告警。（大，持久卷等先行小改）
10. **前端 CI 必红 + 真实状态所有权问题**：FormDesigner 7 处、FlowChainDesigner 2 处 `vue/no-mutating-props`（直接 splice props）。要求：改为生成 next 数组再 emit，补 v-model 集成测试，不用 eslint-disable 消错。（中）
11. **甘特图 tooltip 存储型 XSS**：`TaskGantt.vue` 拼 HTML 未转义 taskName 等。要求：纯文本 tooltip 或统一 escape，恢复 `vue/no-v-html` 规则。（小）

## P1 强烈建议

### 后端
- 业务/事务大量集中在 router（CRM 无 service，contract/finance/task/admin router 500–1000 行）：下沉 application service、统一事务所有权。（大）
- 乐观锁是非原子读后比较且 version 可省略：改 SQLAlchemy `version_id_col` 或原子 UPDATE，核心编辑必传 version。（中）
- `admin:user:edit` 可挂超管角色提权；super 角色 code/status 可被改：拆 assign-role 权限、只能授予自身权限子集、保护内置 super。（中）
- 密码策略不统一；改密/重置不吊销 refresh 会话：统一策略 + 用户级会话族撤销 + 首登强制改密。（中）
- 登录缺 IP 维度限流（账号锁定可被 DoS）；refresh 旋转非原子：限流+Lua 原子消费+旧令牌重用撤销会话族。（中）
- 企微 qr-url 接受任意 redirect_uri：服务器端 allowlist，state 绑定回调并原子消费。（中）
- 新业务接审批需改 4–6 处（发起+三事件订阅+启动导入+展示映射）：建 `BusinessFlowAdapter` 注册表，启动校验。（中）
- 流程定义 process_graph 与 node/seq 双真相；无 running 实例时历史定义可被原地改写：单一规范模型，凡被实例引用即不可变只出新版。（中）
- 上传仅验扩展名；XLSX 导入无行数/解压限制；SVG 公开提供：流式限量+魔数校验+导入配额+SVG 净化/nosniff。（中）
- **XLSX 导出公式注入**：业务字符串未转义 `= + - @` 前缀，统一导出中心转义。（小）
- 企微通知/PDF 转换在审批事务内同步执行：transactional outbox + worker + 重试死信。（大）
- N+1 与大内存：审批/OA 列表逐条查待办、统计 Python 聚合、导出 size=100000 全量内存：分组查询、SQL 聚合、异步导出。（中）
- 审计覆盖不全（菜单/字典/角色删除/任务子记录），traceId 未入日志：ContextVar 传播 + 统一审计装饰器。（中）
- OA 服务端不校验字典成员/资源真实性，原始额外字段整体落库：按 schema 规范化 payload、字典/资源服务端校验、名称服务端重生成。（中）

### 前端
- 多处把第一页 100/200 条当全量（审批人选择、合同详情关联、甘特/月历）：远程搜索分页选择器、关联分页、超限提示。（中）
- 前端回归保护薄弱（仅 9 用例，无 formLogic/路由/HTTP/组件测试，无 Playwright 配置）：按风险分层补测 + 主链路 E2E。（大）
- 移动端只有桌面壳：breakpoint composable、移动壳、响应式弹窗表单，优先 OA 申请/待办/任务录入。（大）
- 入口包 1.43MB（Element Plus+全量图标全量引入）：按需引入+显式图标注册表+包体预算。（中）
- `useListPage` 无"最后请求生效"机制，旧响应可覆盖新筛选：请求序号/AbortController 提升到通用层。（中）
- 详情页 KeepAlive 键与页签键不一致，同页签看不同 ID 累积缓存实例：统一身份或 KeepAlive max + 生命周期处理。（中）
- 跨域深 import 5 处、路由名第二段可能碰撞：模块 public API + lint boundaries + 路由名带域前缀。（中）

### 数据/部署/测试
- 主链缺数据库外键（38 表仅 12 FK 列）：先孤儿数据盘点+修 purge，再分批命名 FK（RESTRICT），多态关联保留应用校验。（大）
- 财务不变量可绕过：`invoiceable_amount>amount`、累计到账可超额：行锁内边界校验+CHECK，或显式建模溢缴/退款。（中）
- purge 清单漏 `fin_settlement_confirm`、文件删除与 DB 提交非原子、重种子后 USER 节点需手工重指：集中清理清单+逐表断言+隔离区删除+审批人重绑定产品化。（大）
- OA/流程定义 `(key,version,deleted)` 唯一键不支持反复删除重建：删除令牌或生成列实现仅活动行唯一。（中）
- 健康检查不查 Redis、容器无 healthcheck：/live 与 /ready 拆分 + 依赖超时 + compose healthcheck。（小）
- 启动自动迁移+全量种子会重置角色菜单绑定；个别 downgrade 不可用：迁移独立发布步骤+增量种子+明确回滚策略。（中）
- 测试共享 session 状态且依赖 `zz` 文件顺序：独立 schema/用例隔离、补并发/迁移/恢复测试与覆盖率门槛。（大）
- 存量库表列字符集未统一审计修复：information_schema 审计+迁移统一 utf8mb4+CI 断言。（中）

## P2 中期演进
- 流程变量/图结构发布期契约校验（类型、必填、可达性、环路、表达式），缺必需变量 fail-closed。
- 审批/列表复合索引按 EXPLAIN 补齐，深分页改 keyset；清理冗余单列索引。
- 统计口径统一为只读指标查询服务，避免各页面漂移；不必急于上 BI。
- 核心公共 API 补 response_model 与契约测试，后续可生成客户端。
- Redis/DB 显式超时与熔断；结构化 JSON 日志、traceId 全链串联、metrics/告警、Docker 日志轮转。
- CI 增加真实镜像构建+Compose 冒烟+Playwright 主链路；更新或退役 `backend/scripts/e2e_full.py`（含恒真断言）。
- 时间策略：先写明"全系统东八区"ADR、修正 Numeric/Date 类型注解与 ID 类型不一致；多区域需求再做 UTC 改造。
- 前端：ListTable 泛型化、Create/Update DTO 拆分后启用 no-explicit-any；图表/快捷入口语义色板+主题切换重绘+色值扫描质量门；i18n 用 import.meta.glob 自动组装；抽 useFormDialog 骨架；超大 SFC 先补测试再拆分；筛选状态入 route query；组件画廊。

## P3 可选
- 清理过时注释（token 缓存/Redis INCR 等旧描述）。
- 备份调度在 Redis 故障时多 worker 重复执行：生产独立单实例任务或 fail-closed。
- `.dockerignore` 增加 backend/backups；README 测试数量与主链描述更新。

## 做得好的地方（整改时保留）
- 统一审批引擎方向正确：条件表达式禁 eval，会签/依次签/转办/加签/版本化齐备；OA `_can_view` 是对象授权样板。
- 67 个权限码均有种子映射，角色停用即时生效；编号服务行锁+唯一键+savepoint 有真实并发测试。
- 统一响应/异常/TraceId、筛选排序白名单、无拼接 SQL；上传 UUID 存储名、备份下载防穿越。
- 前端列表基础设施（useListPage/ListTable/StatusTag 等）复用良好；HTTP 刷新单飞；ECharts 按需+甘特异步；发版旧 chunk 自愈。
- 迁移单头连续、CI 含空库迁移+种子；测试库强制 bizsys_test 隔离；清空前密码+确认词+备份。

## 推荐整改顺序
1. P0 安全底线：密钥/端口/演示种子、审批 IDOR、甘特 XSS、前端 lint 修复让 CI 转绿。
2. P0 数据与迁移根基：deleted 非空、Alembic 全模型注册+迁移 diff CI、备份持久化与恢复演练。
3. P0 审批正确性：可见性统一、fail-closed、锁序闭环；随后 data_scope 专项。
4. P1 分层与扩展：BusinessFlowAdapter、service 下沉、outbox、导出转义、OA 服务端校验。
5. P1/P2 前端：请求竞态、截断数据、按需引入、移动端、测试体系。

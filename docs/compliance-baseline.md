# 检测机构运营平台 —— 合规开发基线

> **来源**：《第三方检测机构运营平台合规开发原则.docx》（面向 CMA / CNAS / TISAX 认可与认证的落地框架，需求方提供并入库于仓库根目录）。
> **配套**：《第三方检测机构运营平台_人力资源管理模块功能说明.docx》（V1.0）—— 人力资源 L1–L5，见 [`roadmap-2026-11.md`](roadmap-2026-11.md) 的 B9 / B10 章节。
> **本文定位**：把 docx 里的每一条控制要求，落成仓库里**可执行、可验收**的约束。逐条给出【文档要求 → 仓库现状 → 落地机制 → 验收方法】。
> **成文**：2026-11-23（B9 批次首次成文）。本文是**活文档** —— 每次改动控制点都要回来更新「仓库现状」与「落地状态」两列。

---

## 0. 怎么用这份文档

1. **评审时**：拿第五章《高频不符合项自查清单》逐条打勾 —— 那是 CNAS/CMA 内审最常见的开单点。
2. **开发时**：动审计、签名、授权、权限相关的代码前，先看本文对应条目 —— 这些位置**不允许"先跑通再说"**。
3. **交接时**：新人接手只看本文 + `CLAUDE.md`，就能知道哪些地方是"合规红线"（不可删改、不可绕过）。

**一句话结论**：运营平台不是"业务系统集合"，而是一个**合规证据生产系统** —— 每一次点击都应自动产出可审计、可归因、不可抵赖的记录。B9 批次把三个最关键的底座做实了（审计证据链 / 电子签名 / 人员授权），其余排入 B10。

---

## 一、总体开发原则（docx 2.1–2.7）

### 2.1 数据完整性优先：ALCOA+ 是底层铁律

| ALCOA+ 项 | 文档要求 | 仓库现状 / 落地机制 | 验收方法 |
| --- | --- | --- | --- |
| **可归因** Attributable | 一人一号，操作绑定身份，禁共用账号 | `sys_user` 独立账号 + 图形验证码 + MFA（`mfa_pending` 令牌族）；所有业务写入经 `Depends(get_current_user)` 取当前用户；审计行落 `user_id` + `user_agent` + `ip` | 任意一条 `sys_audit_log` 的 `userId` 能追到唯一账号；无 `userId` 的系统级写入仅限 `init_data` 种子 |
| **清晰** Legible | 结构化录入，禁自由文本歧义 | 领域入参统一 Pydantic `CamelModel` + 字段级校验；审计的 `field_name` / `old_value` / `new_value` 是**结构化列**而非自由文本 | 审计详情页的「变更前 → 变更后」是独立列，不是一段 JSON |
| **同步** Contemporaneous | 服务端时间戳，禁事后补录 | `create_time` 由数据库 `server_default=func.now()` 生成（客户端不传）；`core/reqctx.py` 每请求缓存一次服务端时间（`server_now`），审计与业务写入共用同一时钟 | 客户端改本地时间不影响落库时间；审计行的 `createTime` 与业务行一致 |
| **原始** Original | 手动录入要挂原始依据 | 报告上传保留原件 + 签章 PDF；访客 NDA 保留手写签名 PNG 并入签名哈希；设备/谱图直采**未实现**（B10-6） | 报告详情页能下载原件；NDA 验签通过说明签名图未被替换 |
| **准确** Accurate | 公式/修约/单位由系统算 | 金额、折旧、工时由后端计算；AI 输出**一律草稿、不自动落库**（人工确认） | 前端无金额硬算；`ai_*` 端点返回值不带 `commit` |
| **完整/一致/持久/可得** | 异常数据不删、时间线统一、长期可读、可检索导出 | 逻辑删除 + 审计只追加（异常数据不物理删）；单号统一走 `services/numbering.py`；审计与访客审计导出 xlsx | 一键清空**不删**审计三表（返回体 `retainedAuditTables` 公开保留清单） |

> **扫描件 ≠ 原始电子记录；Excel 台账 ≠ 合规系统** —— 这是 docx 的关键判断。B9 的落点就是把"证据"从文件搬到系统里（哈希链 + 密码学签名 + 只追加日志）。

### 2.2 审计追踪不是"日志"，而是证据链 ✅ 已落地

> docx 原文：字段级记录（谁、何时、哪张表、哪个字段、旧值 → 新值、原因、终端/IP）；审计日志不可关闭、不可删除、不可修改，普通账号无权触碰；支持"时间轴回放"；**质量负责人需定期审阅审计追踪 —— 开了不等于合格**。

| 落地机制 | 实现 | 位置 |
| --- | --- | --- |
| **字段级记录** | `sys_audit_log` 新增 `field_name` / `old_value` / `new_value` / `reason` / `user_agent` 五列；`record()` 新增 keyword-only 默认参数 → **全仓 283 处调用点零改动** | `app/common/audit.py` |
| **不可删改** | `AuditLog` 改继承只追加基类 `AppendOnlyModel`（**物理删除** `deleted` / `version` / `update_time` / `update_by`）；迁移里加 `BEFORE UPDATE` / `BEFORE DELETE` 触发器 `SIGNAL SQLSTATE '45000'` | `app/common/models.py`、`app/modules/admin/models.py`、迁移 `n8a2b3c4d5e6_audit_chain_evidence.py` |
| **不可清空** | 「一键清空」清单移除 `sys_audit_log` / `vis_access_log` / `vis_nda`，新增常量 `RETAINED_AUDIT_TABLES` 并在返回体公开 | `app/modules/maintenance/service.py` |
| **哈希链** | 每行落 `chain_seq`（唯一索引）/ `prev_hash` / `row_hash` / `hash_alg`；`row_hash = HMAC-SHA256(prev_hash ‖ canonical(row))`；**链头 `sys_audit_chain_head` 是唯一权威游标**（`SELECT … FOR UPDATE NOWAIT`），**不用 `MAX(id)`** —— 并发下 `MAX(id)` 必然产生同 `prev_hash` 分叉 | `app/common/audit.py` |
| **链校验** | `verify_chain(mode='full'\|'since_anchor')` 逐行校验四件事：① `chain_seq` 连续 ② `prev_hash` 与上行相连 ③ 重算 `row_hash` 比对 ④ 链头与末行一致 | `app/common/audit.py::verify_chain` |
| **篡改/截断发现** | 锚点写 **DB 之外的文件** `backend/data/audit-anchor/anchor-YYYYMMDD.txt`（只追加，每行 `seq\|hash\|ts\|hmac`）→ 整链被重写/截断时锚点对不上 | `app/common/audit.py::write_anchor` / `list_anchors` |
| **时间轴回放** | 授权台账 `GET /hr/authorizations/{id}/state-at?at=` 回放**任一历史时点**的授权状态 | `app/modules/hr/authorization.py::state_at` |
| **审阅入口** | 前端「审计日志」页的**证据链校验面板**（全量 / 自锚点、断链定位、锚定、逐条重算哈希比对） | `frontend/src/modules/admin/pages/AuditLogList.vue` |

**⚠ 尚未闭环**：docx 明确写"开了不等于合格，质量负责人需**定期审阅**"。当前只有**手动校验入口**，没有"月度自动审阅 + 审阅记录留痕"。→ 排 B10-7（治理批次）。

**⚠ 关键精度铁律**：`create_time` 必须是 `DATETIME(3)` —— 哈希含毫秒时间戳，秒精度会**必然**算错导致全链报 `row_hash_mismatch`。迁移、模型、`tests/conftest.py::_ensure_columns` **三处必须同时改**。

### 2.3 职责分离（SoD）与最小权限 ✅ 部分落地

> docx 原文：检测、复核、批准、系统管理四权分立；RBAC + 数据权限 + 字段权限三层隔离；临时顶岗走"授权代理"流程不借账号；离职、调岗当日回收权限，季度复核。

| 落地机制 | 实现 | 状态 |
| --- | --- | --- |
| **报告三级 SoD（动态探测）** | `report/service.py::resolve_report_roles()` 从签批实例的 `approval_record` 取通过序列 → 编制/复核/批准；`node_count >= 2` 时**硬拦截**（三人不得同人 + 各自持对应角色授权），否则**降级告警**写审计。管理员在「流程设置」给 `report_sign` 发新版本加节点 → `flow_version` 递增 → **代码零改动即变硬拦截** | ✅ |
| **RBAC** | 权限码 `module:resource:action`，服务端 `require_perm()` 强制；`user.perm_codes` **实时从数据库推导**（用户→启用角色→角色菜单→菜单权限），JWT 里的 `perms` 仅供展示 | ✅ |
| **授权代理（不借账号）** | `hr_authorization` 台账把"谁能做什么"从 RBAC 拆到**业务维度**（方法/参数/设备/角色）；临时顶岗 = 给代理发一条限定范围的授权 | ✅ |
| **离职当日回收权限** | 离职单生效（`effect_employment()`）→ 禁号 + 撤 MFA + **批量 `revoke` B9 授权**（写 `hr_authorization_event`）+ 代理失效 + 清岗位 A/B 角；**物理权限（门禁/钥匙/工牌）无对接** → 写「待现场确认」审计 | ✅ **B10-1 已落地（系统侧）**；物理侧 ⚠️ |
| **数据权限（`data_scope`）** | `sys_role.data_scope` 字段存在但**无任何查询消费** —— 是死字段 | ❌ B10-7 |
| **字段级权限** | 不存在（原始数据不可改、报告模板受限等要求未落地） | ❌ B10-7 |
| **季度复核** | 无 | ⏳ B10-7 |

### 2.4 电子签名是密码学绑定，不是贴图章 ✅ 已落地

> docx 原文：签名需绑定账号、证书或多因子认证；签名后记录锁定；**禁止代签、批量自动签、图片印章**；签名动作要留痕，包含意图确认、绑定数据哈希。

| 落地机制 | 实现 | 位置 |
| --- | --- | --- |
| **密码学绑定** | `core/signature.py`：HMAC-SHA256 签名/验签，密钥 `sha256("bizsys:evidence-signature:" + jwt_secret)`（与 `core/crypto.py` 同源、**域分隔前缀不同**）；`canonical(payload)` 按**固定字段序**生成 `name=value\n` 串（字段重排 → 签名不同）；`hmac.compare_digest` 比对 | `app/core/signature.py` |
| **NDA 签名内容** | `biz_type + nda_no（单号，稳定可复算）+ 姓名/单位/证件号/标题 + 签署时间 + 签署人 id/姓名 + 真实 IP + 手写图 sha256`。**用单号而不是自增 id** —— id 在 insert 前未知会造成循环依赖 | `app/modules/visitor/service.py::sign_nda` |
| **真实 IP 落库** | 原 `ip=""` 硬编码 → 从 `core/reqctx.py` 的请求上下文取真实 IP（端口器端点 `request.client.host`） | `app/core/reqctx.py` |
| **签章后锁定** | `report/service.py::assert_report_editable()`，`status == 'sealed'` 抛 **61003**；统一挂到 `update_remark` / `update_conclusion` / AI 摘要采用 / AI 辅助采用路径 | `app/modules/report/service.py` |
| **绑定数据哈希** | 报告内容哈希 = `sha256(最终PDF字节sha256 \| report_no \| task_item_id \| sha256(conclusion))`；**必须在 `apply_seal_watermark()` 之后算** —— 盖章会产出新 PDF，先算必然对不上 | `app/modules/report/service.py` |
| **意图确认 + 留痕** | 签名动作写字段级审计（`field_name='status'` / `old_value` / `new_value` / `reason`，`strict=True`） | `app/common/audit.py` |
| **存量兼容** | 旧 NDA 是**无密钥 sha256**（可离线复算）→ 标 `legacy-sha256`，验签返回 `verdict="legacy-unverifiable"`，前端打灰标"不可作为密码学证据" | `app/modules/visitor/router.py` |
| **证书 / 多因子** | 系统用的是 HMAC + JWT 体系，**非 PKI 数字证书**；MFA 已具备（`mfa_enabled` + `mfa_pending` 令牌） | ⚠️ 说明 |

### 2.5 单一可信数据源（Single Source of Truth） ⚠️ 部分

| 对象 | 现状 |
| --- | --- |
| 部门 | ✅ 全站取 `sys_dept`（asset 域明确不建自己的部门表；**B10-1 起扩列且写入口唯一**） |
| 供应公司 | ✅ 取 `crm_customer`（`partner_type ∈ supplier/both`） |
| 人员 | ⚠️ **B10-1 已建 `hr_employee` 一人一档**（HR 主源）+ `sys_user`（认证主源），**联动同步、单向**（HR → 认证）；「主身份源来自 HR」仍待统一身份层改造 → B10-5 |
| 样品 / 设备 / 标准方法 / 客户 / 报告 | ❌ 各自为政；跨系统同步无幂等与冲突处理策略 |

### 2.6 安全左移 + 隐私默认 ⚠️ 部分

- ✅ 数据分级已有雏形：`visitor_zone.security_level`（L1–L4）、`sys_config` 密钥 AES-GCM 加密存储、AI 出网脱敏分级 `ai.masking.level`（`off/standard/strict`）。
- ✅ **B10-1：员工证件号 AES-GCM 加密落库 + 出参掩码 + 明文唯一出口留痕**（`GET /hr/employees/{id}/id-no` 每次写审计，域 `hr-employee-idno` 与配置/签名密钥分离）。
- ❌ 原型数据分级（公开/内部/客户机密/原型高密）、原型区人员打标、水印外发 → B10-4。
- ⚠️ 零信任：内部系统用「登录 + 角色权限点」，**未按令牌最小范围授权**。

### 2.7 可验证、可回溯、可恢复 ⚠️ 部分

- ✅ 可回溯：审计证据链 + 授权时点回放。
- ⚠️ 备份：已有 `mysqldump` / 内置导出 + gzip + 保留策略，**未加密、未异地存放、未做恢复演练**。备份成功后自动写审计锚点（锚点校验以 DB 外文件为准）。
- ❌ CSV（IQ/OQ/PQ）：URS → FS/DS → 测试脚本 → 权限/审计/备份恢复测试的完整验证链未建立 → B10-6。

---

## 二、分体系对齐要点（docx 3.1–3.3）

### 3.1 CMA / CNAS（检测业务可信）

| 维度 | 文档要求 | 仓库现状 | 判定 |
| --- | --- | --- | --- |
| 样品溯源 | 条码/二维码，收样→流转→检测→留样→处置全节点留痕 | `task_sample` 样品台账 + `visitor_sample_handover` 交接单；**条码全链路未实现** | ⚠️ B10-6 |
| 设备管理 | 校准有效期、期间核查、状态标识自动拦截 | 无设备台账（CSV 设备域待澄清） | ❌ B6 / B10-6 |
| **人员能力** | 资质、培训、授权范围绑定账号，**超范围不能派任务** | ✅ **B9 落地**：授权台账 + 派工/录入/编制/签章四处拦截 | ✅ |
| 标准方法 | 方法库版本受控，旧版自动失效，变更留痕 | 无方法库 | ❌ B10-6 |
| 环境监控 | 温湿度/洁净度超限报警，关联当批数据有效性 | 无 | ❌ B10-6 |
| 质控 | 平行样、空白、加标、盲样自动插入与判定 | 无 | ❌ B10-6 |
| 报告 | 三级审核、版本控制、作废召回、追溯二维码 | ⚠️ 三级审核靠**动态探测 + 角色授权**落地（流程本身仍是单级，靠「流程设置」加节点）；版本控制/作废召回/二维码未做 | ⚠️ B9 部分 |
| 时间逻辑 | 采样、收样、上机、审核时间线不能矛盾（防补录） | ✅ 服务端统一时钟 + 审计链；**各节点时间线矛盾校验未做** | ⚠️ |

### 3.2 TISAX（信息资产与原型保护）

| 维度 | 现状 | 判定 |
| --- | --- | --- |
| ISO 27001 通用底座 | 访问控制（RBAC）✅ / 加密（`sys_config` AES-GCM）✅ / 日志（只追加 + 哈希链）✅ / 备份 ⚠️ 无加密无演练 / 供应商安全 ⚠️ / 事件管理 ⚠️（访客告警非安全事件） | ⚠️ |
| 原型保护 | 物理红/黄/绿区 ✅（`visitor_zone` 分区 + 安全等级）；数字图纸加密 ❌、外发水印 ❌、销毁留证 ❌ | ⚠️ B10-4 |
| 数据保护 | 主体权利 / DPIA ❌ | ❌ |
| 区域访客 | ✅ 红区访客专项审批 + NDA + 全程陪同 + 禁带设备管控（`visitor_zone` + `visitor_visit`） | ✅ |
| 供应链穿透 | 分包商安全台账 ❌ | ❌ B10-4 |
| 成熟度证据 | 有运行记录（审计链、访客审计、授权轨迹）+ 周期性复审 ⏳ | ⚠️ |

### 3.3 等保 2.0 三级（国内配套）

| 要求 | 现状 |
| --- | --- |
| 多因素认证 | ✅ `mfa_enabled` + `mfa_pending` 令牌族 + `step_up` 二次验证 |
| 登录锁定 | ✅ 15 分钟窗口内失败 5 次锁定（Redis `login_fail:{username}`） |
| 会话超时 | ✅ access token 有 TTL；`refresh` 令牌族独立 |
| 全量加密日志 | ⚠️ 审计行本身明文存储（哈希链保证不可篡改，但不防"读取"） |
| HTTPS 传输 | ✅ 网关侧（nginx 同源转发 `/api/`），部署需在网关对齐 `client_max_body_size` / `proxy_read_timeout` |
| 堡垒机运维 | ❌ 依赖部署侧 |

---

## 三、平台架构与开发注意事项（docx 4.1–4.7）

### 4.1 统一身份与权限中心

| 文档要求 | 现状 |
| --- | --- |
| OIDC + JWT + RBAC/ABAC | ✅ JWT（`typ` 令牌族隔离 `access`/`refresh`/`step_up`/`mfa_pending`/`portal_access`）+ RBAC；**ABAC 未做** |
| 兼容 LDAP/AD | ❌ 未做（企微 SSO 已有） |
| **主身份源来自 HR** | ❌ 未做 → B10-5 |
| 临时身份带有效期 | ✅ 门户 `partner_user` 有 `staff_limit` / 有效期；访客单有时窗 |
| 权限变更走审批流并写审计 | ⚠️ 权限点本身是超管直改（`admin:role:edit`），**未接审批流**；授权台账已接审批流 |

### 4.2 服务边界与数据分区

- ✅ 运营平台承担中台：主数据（`sys_dept` / `crm_customer` / `sys_user`）、流程引擎（`approval`）、审计中心（`sys_audit_log`）、编号服务（`services/numbering.py`）。
- ✅ 子系统不直接连库：统一走 `/api/v1` + 权限点。
- ❌ 高密数据（原型、谱图）独立存储 + 独立密钥：未做。

### 4.3 时间与服务端信任 ✅ 已落地

| 要求 | 落地 |
| --- | --- |
| 统一 NTP 时间源 | ⚠️ 依赖部署侧（容器时间同步）；应用内统一取 DB/进程时间 |
| **禁止客户端时间** | ✅ `create_time` 由 DB `server_default=func.now()`；客户端不传时间字段 |
| 关键操作服务端落时间戳并**生成哈希链** | ✅ 审计写入即入链（`core/reqctx.py` 缓存每请求服务端时间 `server_now`） |

### 4.4 审计与日志设计

| 要求 | 现状 |
| --- | --- |
| 区分业务审计 / 安全审计 / 访问审计 | ⚠️ **业务审计**已字段级化；**安全审计**（登录成功/失败/MFA 挑战）落在 `sys_login_log` + `sys_audit_log`；**访问审计**（谁看了/导出了文件）→ 导出已记审计，查看未区分 |
| 只追加存储 + WORM/哈希链 | ✅ 见 2.2 |
| 导出"评审包"（PDF + 原文 + 审计轨迹） | ❌ 未做 → B10-5 |

### 4.5 电子记录生命周期 ✅ 基本落地

> docx 状态流转：草稿 → 提交 → 审核 → 批准 → 锁定 → 归档 → 到期销毁；锁定后修改必须"撤回/作废重做"，不允许原地静默改；删除采用逻辑软删并保留快照。

| 要求 | 落地 |
| --- | --- |
| 锁定后修改必须作废重做 | ✅ 报告签章后 `assert_report_editable()` 抛 **61003** |
| 逻辑软删并保留快照 | ✅ `BaseModel.deleted`；审计表例外（只追加） |
| 草稿→提交→审核→批准 | ✅ 流程引擎（`registry.py` 18 条 `BINDINGS`） |
| 归档 / 到期销毁 | ❌ 未实现 |

### 4.6 接口与集成合规 ⚠️ 部分

| 对接 | 现状 |
| --- | --- |
| LIMS ↔ 仪器 | ❌ 无仪器直采通道（外部依赖） |
| LIMS ↔ 访客 | ⚠️ 送样人身份与访客记录关联：部分（`visitor_sample_handover` 有送样人字段，**未与 `sys_user` 强关联**） |
| LIMS ↔ OA | ❌ 偏差/不符合项/CAPA 未实现（`oa` 域只有表单与作业申请） |
| 对外客户门户数据脱敏 | ✅ 门户只暴露 `sealed/seal_approved/approved` 报告，不含内部意见与审批人；AI 出网脱敏分级 |

### 4.7 计算机化系统验证（CSV） ❌ 未启动

按 URS → FS/DS → 测试脚本 → 权限测试 + 审计测试 + 备份恢复测试推进，每次升级重跑回归并留验证报告；质量部参与验收。

> **当前可当作 CSV 证据的运行记录**：后端 `pytest -q` 全量回归（424 例）+ 前端 `lint/typecheck/i18n:check/scan:literal/scan:colors/test:unit/build`；审计链的**锚定文件**与**链校验记录**本身即是"配置变更受控"的证据。→ 完整 CSV 文档包排 B10-6。

---

## 四、与《人力资源管理模块功能说明》的衔接

HR docx 的 L1–L5 共 35 个菜单不可能一次做完。B9 做 **L2 技术能力与授权**（"授权是 HR 的灵魂功能"），
**B10-1 已交付 L1 基础人事**，其余排 B10-2 及以后：

| docx L 层 | 内容 | 状态 |
| --- | --- | --- |
| **L1 基础人事** | 组织架构 / 岗位 / 员工主数据 / 入职调岗离职 / AB 角代理 | ✅ **B10-1 已交付**（含**离职当日清权**） |
| **L2 技术能力与授权** | 一人一档 / 证书 / 能力矩阵 / **授权管理** / 角色权限映射 | ✅ **B9 已落地授权管理（3.4）**；证书与能力矩阵 ⏳ B10-2 |
| L3 质量体系活动 | 培训 / 人员监督 / 能力监控 / 绩效工作量 | ⏳ B10-3 |
| L4 合规与安全 | 背景调查 / 保密等级 / 外部人员 / **离岗清权** / 审计追溯 | ⚠️ **离岗清权已由 B10-1 落地（系统侧）**；背景调查 / 保密等级 / 外部人员 ⏳ B10-4（审计追溯已由 B9 提供底座） |
| L5 分析与集成 | 合规仪表盘 / 报表中心 / 评审证据包 / LIMS-OA-IAM 集成 | ⏳ B10-5 |

**docx 第八章「开发注意事项」逐条落地情况**：

| docx 要求 | 落地 |
| --- | --- |
| 授权是状态机：草稿 → 确认 → 授权 → 生效 → 暂停 → 过期 → 撤销，每次变更加审计 | ✅ `hr_authorization` 状态机 + `hr_authorization_event` 只追加事件表 + 字段级审计 |
| 时间快照：报告、原始记录要能反查"操作时刻的授权状态" | ✅ `GET /hr/authorizations/{id}/state-at` |
| 拦截点前置：LIMS 派工、数据录入、报告签发前必须调用 HR 授权服务校验 | ✅ 四处拦截点：**报告编制 / 报告用章 / 检测进度录入 / 任务派工** |
| 数据隔离：HR 基础信息、技术能力、薪酬考勤分域 | ⚠️ **HR 基础信息已独立成 `hr_employee` 域**（B10-1）；薪酬考勤仍 ❌ → B10-7 |
| TISAX 增强：原型区人员单独打标，背调 + 保密 + 门禁 + 离岗清权全链路闭环 | ⚠️ **离岗清权系统侧已落地**（B10-1）；原型打标 / 背调 / 保密 / 门禁 ❌ → B10-4 |
| 审计不可关闭：权限变更、监督结论、授权签字人范围修改，必须进入只追加日志 | ✅ 审计链只追加 + 不可清空 |

---

## 五、高频不符合项自查清单（docx 第五章，11 条）

> docx 原文列举的内审高频开单点。**打勾 = 本仓库有对应机制且已验证**。

| # | 不符合项 | 仓库机制 | 状态 |
| --- | --- | --- | --- |
| 1 | 审计日志"开了没人看"，且可后台清空 | 审计三表移出「一键清空」（返回体 `retainedAuditTables` 公开保留清单）；链校验面板 + 锚点文件 + 审计留痕可追责 | ⚠️ **机制已落地，"定期审阅"未制度化** → B10-7 |
| 2 | 检测员自录自审，管理员兼业务操作 | SoD 动态探测（≥2 节点硬拦截，三人不得同人）+ 授权台账按角色（编制/复核/批准）授权 + `hr_manager` 角色与 `biz_user` 职责分离 | ✅ |
| 3 | 电子签名是图片章，签名后数据仍可改 | HMAC-SHA256 密码学绑定（NDA + 报告签章）+ 验签端点 + 签章后锁定（61003） | ✅（存量 NDA 标"不可密码学验证"） |
| 4 | 系统时间不同步，谱图时间早于采样时间 | 服务端统一时钟（`create_time` DB 生成 + `reqctx.server_now`）+ `DATETIME(3)` 精度 | ⚠️ 统一 NTP 依赖部署侧；节点间时间线矛盾校验未做 |
| 5 | 仪器数据人工抄录，无原始文件绑定 | 报告原件保留 + 签章 PDF 哈希绑定 + NDA 手写签名入哈希 | ⚠️ 仪器直采未做（B10-6 / 外部依赖） |
| 6 | 离职人员账号仍在运行、可导出数据 | `sys_user.status` 禁用即失去全部权限（`perm_codes` 实时推导）；授权撤销立即生效（**不做跨请求缓存**） | ✅ **离岗清权已自动化**（B10-1 `effect_employment()`：禁号 + 撤 MFA + 撤授权 + 代理失效 + 清 AB 角）；⚠️ **物理权限（门禁/工牌）无对接** → 现场确认待办 |
| 7 | 访客进入样品区无陪同、无留痕 | `visitor_visit` 陪同见证 + `visitor_access_log` 只追加（签入/签离/区域进出/拒绝通行全留痕）+ 敏感区域需陪同 + NDA 前置 | ✅ |
| 8 | 原型样件照片以明文存放在共享盘 | 上传文件落 `backend/uploads/`（gitignored）+ 扩展名白名单 + 大小上限 | ⚠️ 原型数据分级与加密未做 → B10-4 |
| 9 | 老系统 LDAP 账号与新 SSO 权限不同步 | 企微 SSO 单一入口；`user.perm_codes` 实时从数据库推导，**不依赖 JWT 快照** | ✅（LDAP 未对接） |
| 10 | 备份存在，但从未做过恢复演练 | 备份（含清空前自动备份）+ 保留策略 + 备份后自动写审计锚点 | ❌ **无恢复演练、无异地、无加密** → B10-7 |
| 11 | 检测员未授权却能录入数据 | **四处拦截点**：报告编制 / 报告用章 / 检测进度录入 / 任务派工；越权抛 **63007** | ✅ |

---

## 六、落地状态汇总

| 控制点 | 状态 | 关键工件 |
| --- | --- | --- |
| ALCOA+ 可归因 / 清晰 / 同步 | ✅ | `sys_user` + 结构化审计列 + 服务端时钟 |
| ALCOA+ 原始 / 准确 | ⚠️ 部分 | 仪器直采未做；金额与 AI 草稿机制已达标 |
| **审计证据链（字段级 + 哈希链 + 不可清空 + 校验 + 锚定）** | ✅ | `common/audit.py`、`sys_audit_chain_head`、前端链校验面板 |
| **电子签名密码学绑定 + 签章后锁定** | ✅ | `core/signature.py`、NDA 验签、报告验签 |
| **人员授权台账 + 状态机 + 时点回放 + 拦截点前置 + SoD** | ✅ | `hr_authorization`、`hr/authorization.py`、四处拦截点 |
| 职责分离 | ⚠️ 部分 | SoD 动态探测 ✅；数据权限 / 字段权限 / 季度复核 ❌ |
| 单一可信数据源 | ⚠️ 部分 | 部门 / 供应公司 ✅；**人员（`hr_employee` 一人一档，HR 主源）✅**；样品 / 设备 / 方法 ❌ |
| **组织架构 + 员工主数据 + 人事事务（B10-1 L1）** | ✅ | `sys_dept` 扩列 + `hr_position` + `hr_employee` + `hr_employment` + `hr_org_change` |
| **离职当日清权（系统侧）** | ✅ | `hr/employment.py::effect_employment()`：禁号 + 撤 MFA + 撤 B9 授权 + 代理失效 + 清 AB 角；**物理侧 ⚠️**（门禁/工牌无对接 → 待现场确认审计） |
| **敏感个人信息（证件号）加密 + 脱敏 + 明文出口留痕** | ✅ | `hr_employee.id_no` AES-GCM（域 `hr-employee-idno`）+ `GET /hr/employees/{id}/id-no` 写审计 |
| 数据分级与隐私默认 | ⚠️ 部分 | 访客分区等级 / 配置加密 / AI 脱敏 / 证件号加密 ✅；原型分级 ❌ |
| 可验证可回溯可恢复 | ⚠️ 部分 | 证据链 ✅；备份加密与恢复演练 ❌；CSV ❌ |
| CSV（IQ/OQ/PQ） | ❌ | 排 B10-6 |
| 数据权限三层（RBAC+数据+字段） | ⚠️ 部分 | RBAC ✅；数据/字段 ❌ |
| 统一身份 IAM / 主身份源来自 HR | ⚠️ 部分 | 企微 SSO + JWT 多令牌族 ✅；HR 主身份源 / OIDC / LDAP ❌ |

---

## 七、开发者红线（改动这些位置前必读）

1. **不要给审计表加 `deleted` / `version` / `update_*`** —— 只追加基类 `AppendOnlyModel` 没有这些列，是设计意图不是遗漏。审计表的 UPDATE/DELETE 会被数据库触发器 `SIGNAL` 掉。
2. **不要把审计三表加回「一键清空」清单** —— `sys_audit_log` / `vis_access_log` / `vis_nda` 是合规证据，清理需要走正式的数据销毁流程，不是工具按钮。
3. **不要用 `MAX(id)` 当链游标** —— 链头 `sys_audit_chain_head` 是唯一权威游标，并发下 `MAX(id)` 会产生同 `prev_hash` 分叉。
4. **不要把 `create_time` 精度改回秒** —— 哈希含毫秒时间戳，秒精度会让整条链校验报 `row_hash_mismatch`。迁移 / 模型 / `tests/conftest.py` 三处必须同时改。
5. **不要给 NDA / 报告签章的签名换算法而不升 `sign_version` / `key_version`** —— 存量行会变成"无法验证"且看不出原因。
6. **不要在 `check_authorization()` 里加跨请求缓存** —— 撤销必须立即生效。请求内 memo（`db.info`）是允许的。
7. **不要用 `scope_json` 做授权过滤依据** —— 它只是展示快照。过滤永远走显式列（`scope_method` / `scope_params` / `scope_device_id` / `scope_domain`），避免"快照里恰好有值"这种隐性授权。
8. **不要绕过 `assert_authorized()` 直接改业务数据** —— 拦截点前置是 docx 的硬要求（"未授权不能录入数据"）。
9. **授权类单据不允许人工直通** —— `registry.py` 里 `hr_authorization` 的 `pass_through=False`，未配流程定义时提交会直接报错，这是刻意的。
10. **新增业务表必须登记进「一键清空」清单** —— 但审计类表**例外，禁止登记**。
11. **不要手工改 `sys_user.status` 来"离职"** —— 离职副作用**必须走 `hr/employment.py::effect_employment()`**（`POST /hr/employments/{id}/effect`）。
    手工改状态会**跳过撤 MFA、撤 B9 授权、代理失效、清岗位 A/B 角**四件事，留下"账号已停但授权仍在"的合规缺口。
    同理，**审批通过 ≠ 生效**：`approved` 只是审批态，副作用在 `effect` 才执行。
12. **不要绕过 `effect_employment()` 直接改 `hr_employee.employ_status`** —— 在职状态是清权的**触发源**，
    改了它而没走生效流程，等于把离职做成了"改个字段"，审计链上查不到清权记录。
13. **不要在 `sys_dept` 之外新建部门表或第二个部门写入口** —— 写入口唯一是 `POST/PUT /admin/depts`；
    HR 域只提供**岗位**（`hr_position`）与**变更轨迹**（`hr_org_change`）。
14. **不要把 `hr_employee.id_no` 明文写进日志 / 出参 / 导出** —— 落库必须是 `enc:` 密文，
    出参一律掩码；明文只有 `GET /hr/employees/{id}/id-no` 一条出口，且**每次访问必须写审计**。

---

## 相关文档

- [`roadmap-2026-11.md`](roadmap-2026-11.md) —— B9 / B10 排期与批次总览
- [`api-contract.md`](api-contract.md) —— B9 新端点、错误码、`sys_audit_log` 字段级列与哈希链、`hr_authorization` 状态机与流程绑定；**B10-1 端点表 / `hr_employment` 状态机与生效副作用**
- [`../CLAUDE.md`](../CLAUDE.md) —— 开发者速查（已知坑 / 合规基线小节）

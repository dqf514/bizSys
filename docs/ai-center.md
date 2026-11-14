# AI 中心（统一网关 / 用量监控 / 配额）

> 版本：2026-11 落地。后端 `app/services/ai.py` + `app/modules/aicenter/`；前端 `src/modules/admin/pages/AiUsage.vue`、`AiSettings.vue`。

## 1. 架构

```
业务模块 ──> gateway_chat(db, feature=...) ──> ai_usage_log（独立会话提交）
                  │                                  ▲
                  ├─ 功能开关 ai.feature.{f}           │（业务回滚不丢日志）
                  ├─ 配额检查（当日 success 聚合）      │
                  └─ OpenAI 兼容 POST {base_url}/chat/completions（429/5xx/网络重试 3 次）
```

- 所有 AI 调用统一经 `gateway_chat()`，逐条落 `ai_usage_log`：用户、feature、模型、prompt/completion tokens、
  耗时、状态（success/error/fallback）、错误/回退原因、关联业务（bizType/bizId）、prompt_version。
- 日志用**独立 SessionLocal 提交**（`_write_log`）：业务事务回滚后用量记录仍保留，统计口径不被业务成败影响。
- 配置全部存 sys_config：
  - 连接（系统设置 → AI 设置卡片）：`ai.enabled` / `ai.base_url` / `ai.api_key`（AES-GCM 加密）/
    `ai.model` / `ai.vision_model`（空 = 复用 model，图片类功能使用）/ `ai.timeout`
  - 功能开关（AI 中心 → AI 设置）：`ai.feature.{quote|contract_ocr|task_photo|report_summary|approval_assist|contract_risk|report_assist|nl_query|hr_prefill|oa_prefill|flow_route|flow_anomaly|tender_assist|sample_ocr|invoice_ocr|price_ref|assistant|daily_digest|knowledge}`，缺省启用
  - 配额：`ai.quota.user_daily_calls` / `ai.quota.user_daily_tokens` / `ai.quota.global_daily_tokens`，0 = 不限
- 环回/内网端点（127.0.0.1/localhost/::1）自动绕过系统代理（httpx trust_env 在 Windows 会读注册表代理）。

## 2. 异常语义

| 异常 | 错误码 | 去向 |
|---|---|---|
| 未配置/调用失败 `AiUnavailable` | （业务自行回退或转 65004） | 报价走三级回退；合同/拍照/摘要转 65004 或 65001 |
| 功能停用 `AiFeatureDisabled` | 65002 | 报价静默回退模板（记 fallback 日志）；其余功能直接报错 |
| 配额超限 `AiQuotaExceeded` | 65003 | 直接回前端，不静默回退 |
| 文本提取为空/AI 输出非法 | 65004 | 业务侧转业务错误 |

前端入口统一经 `GET /ai/capabilities`（`useAiCapabilities` composable，模块级缓存）判断显隐：
未配置提示「联系管理员配置」，功能停用提示「已被管理员停用」。

## 3. 已接入功能（全部「AI 建议 → 人工确认 → 才保存」）

| feature | 入口 | 交互 |
|---|---|---|
| `quote` | 报价单编辑页「AI 生成」 | 需求文本 → 报价草稿回填（不落库）；失败三级回退（模板/历史复制） |
| `contract_ocr` | 合同新建/编辑页「AI 识别填充」 | pdf/docx/txt 文本提取、jpg/png 走视觉模型；客户名模糊匹配候选由人工选择；「回填到表单」才写入表单 |
| `task_photo` | 任务详情「进度记录」tab「拍照记进度」 | 现场照片 → 视觉分析出 百分比+描述草稿 → 人工编辑 → 「确认登记」写 task_progress_log（图片作附件，按日志行鉴权查看） |
| `report_summary` | 报告详情抽屉「AI 生成摘要」 | 报告文本 + 任务信息 → 摘要草稿 → 人工编辑 → 「采用并保存」写 report.remark（仅 uploaded/rejected） |
| `approval_assist` | 审批中心详情抽屉「AI 审批助手」 | 单据快照（值截断）+提交说明+合同类单据按权限附客户历史统计（合同数/均价/偏离/近90天相近单/累计到账）→ 要点/风险（high/mid/low）/意见草稿 → 「引用到审批意见」填意见框，人工修改后随审批动作提交；不落库。限实例相关人（发起/审批/抄送）或 approval:view |
| `contract_risk` | 合同新建/编辑页「AI 风险审查」 | 已填字段白名单 + 可选合同原文（新传 pdf/docx/txt、图片走视觉，或引用已上传附件）→ 风险清单（级别+条款+问题+建议）+ 缺失条款 + 总评 → 仅展示，可复制或人工「加入备注」；不落库 |
| `report_assist` | 报告详情抽屉「AI 全文辅助」（签章前入口） | 三类：结论与不确定度草稿（人工编辑后「采用并保存」写 report.conclusion，仅 uploaded/rejected）；格式与错别字校对（issues 清单，采纳/忽略仅 UI 态）；完整性检查（编号一致性/签章信息/日期/条目缺漏规则 + AI 缺失项合并为检查清单）。校对与检查不落库 |
| `nl_query` | 工作台「AI 问数」卡片 | 自然语言 → AI 仅产白名单意图（七域：任务量/合同额/应收未收/结算/工时/采购申请/报价，禁止自由 SQL）→ 后端按域校验列表权限（无权限 20002）+ 手写聚合模板执行 → 答案卡（文本+明细行+口径说明+时间范围）+ 跳转对应列表；「我」由后端解析为当前用户；追问回传上轮时间范围；用量记 feature=nl_query |
| `hr_prefill` | 工时填报页每行「AI 预填」 | 任务最近 5 条进度日志 + 本人该任务最近 5 条工时 + 当日已报合计 → 当日工时数（服务端 0.5 步进 clamp [0.5,24]）与工作内容草稿（≤500 字）→ 只回填当前行，人工修改保存才落库 |
| `oa_prefill` | OA 发起弹窗「AI 预填」 | 本人同表单最近 3 条历史申请 → 字段草稿合并进表单 + 标注「由历史申请预填」；资源/人员/文件/布局控件不预填，选项值服务端校验（∈/⊆ options），非法值丢弃；无历史直接回空不调 AI |
| `flow_route` | 流程定义编辑弹窗「AI 建议审批链」 | 业务类型 + 金额/分类 + 启用用户/角色清单 + 同类定义节点摘要 → 建议节点链 + 设计理由；USER/ROLE 审批人服务端逐一核验存在且启用（非法节点丢弃、全丢 65004），人工「采纳」才替换编辑中的节点 |
| `flow_anomaly` | OA 流程处理行操作「AI 异常分析」 | 滞留节点/待办人/时长 + 服务端确定性信号（审批人停用锁定、超同表单历史中位处理时长、组织节点解析不到人）+ 最近时间线 → 原因分析 + 处理建议（催办/转办/退回；转办人选只信服务端按姓名匹配回的 userId）；「发送催办通知」走独立非 AI 端点写 sys_notify + 审计 oa_urge |
| `tender_assist` | 招标详情投标区「AI 评标辅助」（评标中/定标中/已定标） | 公告要求提取（≤10 条）+ 各投标文件文本（≤10 份、每份截 4000，提取失败全项待确认）→ 逐项 符合/偏离/待人工确认（verdict 白名单归一、bidId 白名单过滤、缺失补齐 manual）；同弹窗附报价比对表（确定性计算、非 AI、可导出 xlsx）；仅辅助，评分定标仍人工 |
| `sample_ocr` | 任务编辑页样品区「拍照识别」 | 样品标签照片 → 多模态提取 名称/型号/VIN/车型/日期 草稿 → 回填首个空行或追加新行；不落库，人工核对后随任务保存 |
| `invoice_ocr` | 发票登记弹窗「发票识别」 | 发票图片/PDF → 发票号/金额/税率/购买方/销售方/日期草稿回填；金额服务端对照结算金额复核（不一致弹内告警提示人工核对）；登记落库仍走原 PUT |
| `price_ref` | 采购申请明细行「价格参考」 | 同品名历史聚合（申请预估价 + 已确认入库成交价）：次数/均价/区间/最近价 + 当前价偏离度（纯计算，不受开关影响）；AI 点评仅功能开启时附加，失败/停用为空不阻断 |
| `assistant` | 右下角常驻「AI 助手」面板（桌面+移动，移动端避开 Dock） | 意图白名单路由：query=复用 nl_query（再次权限校验）/ navigate=仅允许服务端权限菜单树 ∩ 前端候选 ∩ 静态深链交集内的 path（幻觉路径降级 guide）/ guide=知识库检索作答；每条回复标注类型（查数/导航/指引），导航给确认按钮再跳转；只读，不产生任何业务写入；AI 未配置降级为菜单关键词/知识库搜索 |
| `daily_digest` | 工作台「AI 每日摘要」卡片 | 聚合当前用户待审批 + 进行中临期/逾期任务 → 一段话摘要 + ≤3 条重点；AI 不可用回退模板摘要（degraded）；「推送给自己」企微就绪且已绑定推企微，否则落站内通知（sys_notify + 审计留痕） |
| `knowledge` | 管理端「AI 中心 → 知识库」CRUD + 独立「知识库问答」页（/ai/knowledge，登录可用） | 关键词检索（标点分词 + 长词 2-gram，标题权重 ×3）top3 → AI 仅基于条目作答并标注来源（usedIds 取交集，空则兜底全部命中）；AI 未配置/停用/失败降级为命中条目原文展示；预置 7 条操作手册（迁移 l1a2b3c4d5e6 + seeds 幂等兜底） |

### 问数白名单域（`app/modules/aicenter/nl_query.py`）

| domain | 权限码 | 口径 |
|---|---|---|
| `task_volume` | task:list | 按创建时间；subject=self → 负责人=当前用户 |
| `contract_amount` | contract:list | 按创建时间；金额合计；subject=self → 经办人 |
| `receivable` | finance:settlement:list + finance:payment:list | 已开票/已到账结算金额 − 已登记到账 |
| `settlement` | finance:settlement:list | 按创建时间分状态计数/金额 |
| `work_hours` | hr:timesheet:list | 仅本人填报（草稿+已提交），按工作日期 |
| `procurement` | procurement:request:list | 按创建时间；预算合计；subject=self → 创建人 |
| `quotation` | sales:quote:list | 按创建时间；报价合计；subject=self → 创建人 |

## 4. 用量监控

页面 `/admin/ai/usage`（admin:ai:usage）：统计卡（累计调用/成功率/累计 tokens/活跃用户/平均耗时）+
近 N 天趋势折线 + 按功能/模型柱状 + 按用户 Top10 + 明细分页（q/feature/status/时间段检索，admin:ai:usage:export 导出 xlsx）。
全部为 SQL 聚合，不拉全量。

## 5. 新功能接入步骤

1. 在 `app/services/ai.py` 的 `FEATURES` 登记新 feature key。
2. 业务 service 调 `gateway_chat(db, feature=..., messages=..., user=..., biz_type=..., biz_id=...)`；
   `AiUnavailable` 决定回退或报错，不要在业务会话里自行写日志。
3. 前端 `ai.json` 加 `feature.{key}` 文案（中英双语）；入口按钮经 `useAiCapabilities().featureOn(key)` 判断。
4. AI 结果一律走「草稿 → 人工确认 → 落库」，不自动写业务表。

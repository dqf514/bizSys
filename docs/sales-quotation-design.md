# 销售系统 · AI 报价设计文档

> 状态：设计评审稿（未开发） · 2026-11-13
> 范围：销售系统顶级区首个功能「报价单」——模板 CRUD + WYSIWYG、AI 辅助生成（OpenAI 兼容）、审批与发送、PDF/打印、导航整合。
> 约定：沿用 AGENTS.md 全部规范（四件套模块、编号规则、审批引擎、权限码、i18n/tokens、SearchBar/StatusTabs/counts、导出模式）。

## 1. 背景与目标

销售线索→报价→合同是业务主线缺口：当前合同只能从既有客户直接立项，报价环节在线下（Word/Excel），
口径不一、无法留痕、无法统计转化率。本功能把报价单纳入系统：

1. **模板化**：报价单格式由模板驱动（公司抬头/条款/字段布局 WYSIWYG 配置），多模板并存（检测校准/技术服务/框架）。
2. **AI 辅助生成**：填写"客户需求描述"后一键生成报价明细与说明文案；无 AI 配置时自动回退"模板默认 + 历史报价复用"。
3. **流程闭环**：草稿 → 提交审批（复用自研审批引擎）→ 通过 → 发送客户（留痕）→ 客户反馈（接受/拒绝）→ 可一键转合同。
4. **输出**：打印友好页面（浏览器另存 PDF）+ 后续可选服务端 PDF。

非目标（本期）：在线支付、客户门户协同报价、多币种汇率自动换算、CRM 线索管理（线索暂以"意向客户=往来单位"承载）。

## 2. 数据模型（backend/app/modules/sales/models.py）

全部继承 BaseModel（审计四列 + 乐观锁 + 逻辑删）。

### sales_quote_template（报价模板）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| key | String(64) | 模板标识 |
| name | String(128) | 模板名（如 检测校准报价单） |
| status | String(16) | draft/published/disabled（发布后改版走 tpl_version+1 新草稿，同 oa_form） |
| tpl_version | Integer | 模板版本 |
| layout_json | Text | WYSIWYG 布局：`{headerHtml, footerHtml, clausesHtml, showFields:[...], itemColumns:[{key,label,width}]}` |
| default_terms | Text | 默认条款（付款方式/有效期/交付周期，AI 回退与新建预填用） |
| sort | Integer | 目录排序 |

### sales_quotation（报价单）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| quote_no | String(32) unique nullable | 报价编号 BJ…（提交审批时发放，草稿不占号） |
| title | String(255) | 报价标题 |
| customer_id / customer_name | BigInteger / String(128) | 关联 crm_customer（冗余名） |
| contact_name / contact_phone | String(64/32) | 客户联系人 |
| template_id / tpl_version | BigInteger / Integer | 模板快照引用（版式随模板快照渲染） |
| requirement | Text | 客户需求描述（AI 生成输入） |
| intro_html / terms_html | Text | 报价说明/条款（AI 或模板生成后可编辑） |
| total_amount | Numeric(14,2) | 合计（=明细汇总，服务端重算） |
| tax_rate | Numeric(5,2) | 税率 %（默认 6，明细可覆盖？本期整单一个税率） |
| currency | String(8) | 默认 CNY（字典预留） |
| valid_until | Date | 报价有效期 |
| status | String(16) | draft → approving → approved / rejected → sent → accepted / declined / expired；终态 voided |
| ai_meta | Text | AI 生成元信息 JSON（model/promptVersion/fallback 原因），空=非 AI 生成 |
| sent_at / sent_channel / sent_to | DateTime / String(16) / String(128) | 发送留痕（email/wecom/print） |
| feedback_note | String(500) | 客户反馈备注（接受/拒绝时填写） |
| flow_instance_id | BigInteger | 审批实例 |
| contract_id | BigInteger nullable | 转合同生成的 ctr_contract.id（幂等） |

### sales_quotation_item（报价明细行）

| 字段 | 说明 |
| --- | --- |
| quotation_id | FK sales_quotation.id（cascade 删） |
| seq | 行序 |
| name / spec / unit | 项目名称 / 规格说明 / 单位 |
| qty | Numeric(12,2) |
| unit_price | Numeric(14,2) |
| amount | Numeric(14,2)（=qty×unit_price，服务端重算） |
| remark | String(255) |

要点：合计与行金额**服务端重算**，不信任前端提交值；模板 layout_json 快照进报价单（新建时复制，
模板后续改版不影响已发报价，同 oa_instance schema 快照语义）——快照列 `layout_snapshot` Text。

## 3. AI 生成与回退策略

### 3.1 配置（sys_config，系统设置页新增"AI 集成"卡片，admin:setting:edit）

| 键 | 说明 |
| --- | --- |
| ai.enabled | 0/1 总开关 |
| ai.base_url | OpenAI 兼容端点（如 https://api.deepseek.com/v1、企业网关） |
| ai.api_key | 加密存储（复用 cryptography，界面只写不回显） |
| ai.model | 模型名（如 deepseek-chat） |
| ai.timeout | 秒，默认 30 |

依赖已就绪：httpx（调用）+ tenacity（重试）均在 pyproject。调用封装 `app/services/ai.py`：
`chat(messages, *, timeout) -> str`，仅 POST `{base_url}/chat/completions`（OpenAI 兼容最小子集），
指数退避重试 2 次，超时/4xx/5xx 一律抛 `AiUnavailable`。

### 3.2 生成入口与 Prompt

`POST /sales/quotations/ai-generate`（sales:quote:create）：

```
入参：{quotationId}（草稿）或 {customerId, requirement, templateId}（未保存的即时生成）
输出：{items:[{name,spec,unit,qty,unitPrice,remark}], introHtml, termsHtml, source:"ai"|"fallback", fallbackReason?}
```

System prompt 内置（代码常量，带版本号）：输出**严格 JSON**（response_format json_object 若支持，
否则解析容错）；金额不明时给 0 并在 remark 标注"待询价"；引用该客户近 3 单历史报价行作为 few-shot 上下文
（脱敏后）。生成结果**仅回填草稿**，不落库前必须人工确认——AI 不直接产生正式数据。

### 3.3 回退策略（无配置/调用失败，自动降级，结果显式标注 source）

1. `ai.enabled=0` 或未配置 → **模板回退**：introHtml/termsHtml 取模板 default_terms，明细行为空 + 前端提示"AI 未配置，请手工填写或从历史报价复制"；
2. 配置了但调用失败/超时/解析失败 → **历史回退**：取该客户最近一单报价的明细复制为草稿行（备注标"复制自 BJ…"），terms 用模板默认；
3. 两种回退都记 `ai_meta.fallback_reason`，审计日志留痕（action=sales_quote_ai_fallback）。
4. 前端在生成按钮旁标注来源徽标（AI 生成 / 模板回退 / 历史回退），避免"看起来是 AI 写的其实是复制"。

## 4. 审批与发送流程

### 4.1 审批（复用自研引擎，零新机制）

- biz_type=`sales_quotation`；种子流程 `quote_approve`：部门负责人(DEPT_LEADER) → 分管领导(PARENT_DEPT_LEADER)（同 OA 请假组织解析口径）；
- 提交校验：明细 ≥1 行、total>0、valid_until ≥ 今天、模板已发布；提交即发 quote_no（编号规则 biz_type=`quotation`，前缀 BJ，daily）；
- 事件回写：订阅 ApprovalFinished → status=approved/rejected（同 contract/task 模式）；
- 驳回 → 可改后重新提交（同合同）。

### 4.2 发送与反馈

- 仅 approved 可发送：`POST /sales/quotations/{id}/send`（channel=email/wecom/print）：
  - email：走集成占位适配器（9xxxx 域），本期实现 SMTP 可选配置，未配置 → 40001 风格提示"未配置邮件通道"但允许 channel=print 标记"已线下送达"；
  - 发送留痕 sent_at/sent_channel/sent_to，状态 → sent；
- 客户反馈：`POST /sales/quotations/{id}/feedback`（accept/decline + note）→ accepted/declined；
- 有效期过期：APScheduler 每日任务把 sent 且 valid_until<今天 的置 expired；
- **转合同**：accepted（或 approved，由权限控制）→ `POST /sales/quotations/{id}/to-contract`：
  预填合同（名称/客户/金额/备注带报价号），跳转合同编辑页人工确认后保存；幂等（contract_id 已存在则直接返回）。

## 5. PDF / 打印

- **本期（推荐）**：打印视图路由 `/sales/quotations/{id}/print`（独立干净页，按 layout_snapshot 渲染
  公司抬头/客户信息/明细表/条款/签章区），专用 print CSS（@page A4、隐藏操作区、页眉页脚），
  浏览器"打印→另存为 PDF"即产出正式 PDF；打印页提供「标记已发送(print)」按钮。
- **后续可选**：服务端 weasyprint 渲染同一 HTML 模板出 PDF 附件（用于邮件通道附件）；引入前评估
  部署依赖（cairo/pango），故不进本期。
- 明细表列由模板 `itemColumns` 驱动（可隐藏 规格/备注 列），金额格式千分位 + 大写合计（前端工具函数）。

## 6. 前端（frontend/src/modules/sales/）

| 页面 | componentKey | 说明 |
| --- | --- | --- |
| QuoteTemplateList | sales/QuoteTemplateList | 模板列表/新建/版本/发布/停用（sales:template:*） |
| QuoteTemplateDesigner | sales/QuoteTemplateDesigner | WYSIWYG：抬头/页脚/条款富文本（el 现成 editor？用轻量 contenteditable 组件）+ 明细列勾选 + 实时预览 |
| QuotationList | sales/QuotationList | 列表：SearchBar(q=单号/标题/客户) + StatusTabs(counts) + 导出；行操作 编辑/提交/发送/反馈/转合同/打印 |
| QuotationEdit | sales/QuotationEdit | 编辑页：客户远程检索、需求描述 +「AI 生成」按钮（loading/来源徽标）、明细行可编辑表格、合计实时、条款富文本 |
| QuotationPrint | sales/QuotationPrint | 打印视图（静态路由深链，无壳） |

规范点：移动端 390px 适配（编辑页单列、明细行卡片化）；全部 t() + tokens；列表页 q/counts/导出三件套。

## 7. 菜单 / 权限 / 导航迁移

- 顶级区**销售系统（SalesSystem，icon "Sell"）**：位于人事行政之后、系统管理之前；
  子级：报价单（Quotations `/sales/quotations`，sales:quote:list）→ 报价模板（QuoteTemplates `/sales/templates`，sales:template:list）。
- 权限码：`sales:quote:list/create/edit/submit/send/feedback/to-contract/list:export`、`sales:template:list/create/edit/publish`；
  biz_user 种子给 quote 全部（不含 template publish），模板写权限按需。
- 导航迁移：沿用批次E 方式——TARGET_TREE/TITLE_KEYS/CANON_PATHS 加 SalesSystem 区，批次脚本 `migrate_nav_sales.py` 委托批次E main。
- 错误码段：**64xxx**（64xxx 销售：64001 报价状态不允许 / 64002 模板未发布 / 64003 AI 不可用且无可回退历史 / 64004 已转合同）。
- purge 清单：sales_quotation_item → sales_quotation → sales_quote_template（先于 crm_customer）。

## 8. 测试与验收

- pytest：模板 CRUD/版本发布唯一、报价校验（空明细/负金额/服务端重算篡改）、状态机（提交/驳回重提/发送/反馈/过期任务）、
  防重发号、转合同幂等、AI 回退三分支（mock httpx：正常 JSON / 超时 / 未配置）、越权 403、导出列。
- E2E（playwright）：建模板→发布→AI 生成（无配置走模板回退）→人工调明细→提交→两级审批→发送(print)→接受→转合同跳转；移动端；EN 无漏翻。
- 前缀 sl_ 测试数据，清理脚本沿用 clean_test_prefix_data 模式补 sales 三表。

## 9. 实施分期建议

1. **P1 骨架**：模板 CRUD（先纯表单配置，不做拖拽）+ 报价 CRUD/状态机/审批/打印视图/转合同 + 菜单迁移 + 回退策略（模板/历史）。
2. **P2 AI 接入**：sys_config AI 卡片 + ai.py + ai-generate 端点 + 前端生成按钮与来源徽标。
3. **P3 通道**：SMTP 邮件发送 + 服务端 PDF（weasyprint 评估）+ 企微通知集成。

P1 即可形成完整线下闭环（打印即 PDF），P2/P3 增量解耦，互不阻塞。

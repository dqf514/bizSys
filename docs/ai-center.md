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
  - 功能开关（AI 中心 → AI 设置）：`ai.feature.{quote|contract_ocr|task_photo|report_summary}`，缺省启用
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

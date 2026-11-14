import { download, request, toQuery } from './http'
import type {
  AiCapabilities,
  AiCenterSettings,
  AiUsageRow,
  AiUsageStats,
  ApprovalAssistResult,
  ContractParseResult,
  ContractRiskResult,
  ListQuery,
  NlQueryAnswer,
  NlQueryContext,
  PageResult,
  ReportAssistKind,
  ReportAssistResult,
  ReportSummaryDraft,
  TaskProgressAiDraft,
  TaskProgressLogItem,
} from './types'

// ---------------- AI 中心（用量监控 / 设置 / 能力探测） ----------------

export function getAiCapabilities() {
  return request<AiCapabilities>({ url: '/ai/capabilities', method: 'get' })
}

export function listAiUsage(params: ListQuery) {
  return request<PageResult<AiUsageRow>>({
    url: '/admin/ai/usage',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function exportAiUsage(params: ListQuery) {
  return download(
    {
      url: '/admin/ai/usage/export',
      method: 'get',
      params: toQuery(params as Record<string, unknown>),
    },
    'ai_usage.xlsx',
  )
}

export function getAiStats(days = 30) {
  return request<AiUsageStats>({ url: '/admin/ai/stats', method: 'get', params: { days } })
}

export function getAiCenterSettings() {
  return request<AiCenterSettings>({ url: '/admin/ai/settings', method: 'get' })
}

export function updateAiCenterSettings(data: Partial<Pick<AiCenterSettings, 'features' | 'quota'>>) {
  return request<AiCenterSettings>({ url: '/admin/ai/settings', method: 'put', data })
}

// ---------------- AI 辅助（建议 → 人工确认 → 才保存） ----------------

export function aiParseContract(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<ContractParseResult>({ url: '/contract/contracts/ai-parse', method: 'post', data: form })
}

export function listTaskProgress(taskId: number) {
  return request<TaskProgressLogItem[]>({ url: `/task/tasks/${taskId}/progress`, method: 'get' })
}

export function aiAnalyzeTaskPhoto(taskId: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<TaskProgressAiDraft>({
    url: `/task/tasks/${taskId}/progress/ai-image`,
    method: 'post',
    data: form,
  })
}

export function addTaskProgress(
  taskId: number,
  data: { percent: number; note: string; imagePath?: string; source: 'ai' | 'manual' },
) {
  return request<TaskProgressLogItem>({ url: `/task/tasks/${taskId}/progress`, method: 'post', data })
}

export function aiReportSummary(reportId: number) {
  return request<ReportSummaryDraft>({
    url: `/report/reports/${reportId}/ai-summary`,
    method: 'post',
    data: {},
  })
}

export function aiApprovalAssist(instanceId: number) {
  return request<ApprovalAssistResult>({
    url: `/approval/instances/${instanceId}/ai-assist`,
    method: 'post',
    data: {},
  })
}

export function aiContractRiskReview(
  fields: Record<string, unknown>,
  file?: File,
  attachmentId?: number,
) {
  const form = new FormData()
  form.append('payload', JSON.stringify(fields))
  if (file) form.append('file', file)
  if (attachmentId) form.append('attachment_id', String(attachmentId))
  return request<ContractRiskResult>({ url: '/contract/contracts/ai-risk-review', method: 'post', data: form })
}

export function updateReportRemark(reportId: number, remark: string) {
  return request<{ id: number; remark: string }>({
    url: `/report/reports/${reportId}/remark`,
    method: 'put',
    data: { remark },
  })
}

export function aiReportAssist(reportId: number, kind: ReportAssistKind) {
  return request<ReportAssistResult>({
    url: `/report/reports/${reportId}/ai-assist`,
    method: 'post',
    data: { kind },
  })
}

export function updateReportConclusion(reportId: number, conclusion: string) {
  return request<{ id: number; conclusion: string }>({
    url: `/report/reports/${reportId}/conclusion`,
    method: 'put',
    data: { conclusion },
  })
}

export function aiNlQuery(question: string, context?: NlQueryContext) {
  return request<NlQueryAnswer>({
    url: '/ai/nl-query',
    method: 'post',
    data: { question, context },
  })
}

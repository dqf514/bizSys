import { download, request, toQuery } from './http'
import type {
  AiCapabilities,
  AiCenterSettings,
  AiUsageRow,
  AiUsageStats,
  ContractParseResult,
  ListQuery,
  PageResult,
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

export function updateReportRemark(reportId: number, remark: string) {
  return request<{ id: number; remark: string }>({
    url: `/report/reports/${reportId}/remark`,
    method: 'put',
    data: { remark },
  })
}

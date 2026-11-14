import { download, request, toQuery } from './http'
import type {
  AiCapabilities,
  AiCenterSettings,
  AiUsageRow,
  AiUsageStats,
  ApprovalAssistResult,
  AssistantReply,
  ContractParseResult,
  ContractRiskResult,
  DailyDigestResult,
  InvoiceOcrResult,
  KnowledgeAskResult,
  KnowledgeEntry,
  ListQuery,
  NlQueryAnswer,
  NlQueryContext,
  PageResult,
  PriceReferenceResult,
  ReportAssistKind,
  ReportAssistResult,
  ReportSummaryDraft,
  SampleOcrResult,
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

// ---------------- AI-4：OCR / 价格参考 / 助手 / 摘要 / 知识库 ----------------

export function aiSampleOcr(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<SampleOcrResult>({ url: '/task/samples/ai-ocr', method: 'post', data: form })
}

export function aiInvoiceOcr(invoiceId: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<InvoiceOcrResult>({
    url: `/finance/invoices/${invoiceId}/ai-ocr`,
    method: 'post',
    data: form,
  })
}

export function getPriceReference(itemName: string, price?: number | null) {
  return request<PriceReferenceResult>({
    url: '/procurement/price-reference',
    method: 'get',
    params: { itemName, price: price ?? undefined },
  })
}

export function aiAssistantChat(message: string, menus: { title: string; path: string }[] = []) {
  return request<AssistantReply>({ url: '/ai/assistant', method: 'post', data: { message, menus } })
}

export function getDailyDigest() {
  return request<DailyDigestResult>({ url: '/ai/daily-digest', method: 'get' })
}

export function pushDailyDigest(summary: string, highlights: string[]) {
  return request<{ channel: string }>({
    url: '/ai/daily-digest/push',
    method: 'post',
    data: { summary, highlights },
  })
}

export function askKnowledge(question: string) {
  return request<KnowledgeAskResult>({ url: '/ai/knowledge/ask', method: 'post', data: { question } })
}

export function searchKnowledge(q: string) {
  return request<{ entries: KnowledgeEntry[] }>({
    url: '/ai/knowledge/search',
    method: 'get',
    params: { q },
  })
}

export function listKnowledgeEntries(params: ListQuery & { category?: string }) {
  return request<PageResult<KnowledgeEntry>>({
    url: '/admin/ai/knowledge',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function createKnowledgeEntry(data: { title: string; category: string; content: string }) {
  return request<{ id: number }>({ url: '/admin/ai/knowledge', method: 'post', data })
}

export function updateKnowledgeEntry(id: number, data: { title: string; category: string; content: string }) {
  return request<{ id: number }>({ url: `/admin/ai/knowledge/${id}`, method: 'put', data })
}

export function deleteKnowledgeEntry(id: number) {
  return request<void>({ url: `/admin/ai/knowledge/${id}`, method: 'delete' })
}

export function uploadKnowledgeAttachment(id: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<{ id: number; attachmentName: string }>({
    url: `/admin/ai/knowledge/${id}/attachment`,
    method: 'post',
    data: form,
  })
}

export function downloadKnowledgeAttachment(id: number, fileName = 'attachment') {
  return download({ url: `/admin/ai/knowledge/${id}/attachment`, method: 'get' }, fileName)
}

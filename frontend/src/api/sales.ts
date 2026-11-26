import { request, download, toQuery } from './http'
import type {
  AiGenerateResult,
  ListQuery,
  PageResult,
  Quotation,
  QuotationPayload,
  QuoteTemplate,
  QuoteTemplateLayout,
} from './types'

// ---------------- 报价模板 ----------------

export function listQuoteTemplates() {
  return request<QuoteTemplate[]>({ url: '/sales/templates', method: 'get' })
}

export function quoteTemplateOptions() {
  return request<QuoteTemplate[]>({ url: '/sales/templates/options', method: 'get' })
}

export function getQuoteTemplate(id: number) {
  return request<QuoteTemplate>({ url: `/sales/templates/${id}`, method: 'get' })
}

export interface QuoteTemplatePayload {
  key: string
  name: string
  sort?: number
  layout: Partial<QuoteTemplateLayout>
}

export function createQuoteTemplate(data: QuoteTemplatePayload) {
  return request<QuoteTemplate>({ url: '/sales/templates', method: 'post', data })
}

export function updateQuoteTemplate(id: number, data: QuoteTemplatePayload) {
  return request<QuoteTemplate>({ url: `/sales/templates/${id}`, method: 'put', data })
}

export function publishQuoteTemplate(id: number) {
  return request<QuoteTemplate>({ url: `/sales/templates/${id}/publish`, method: 'post' })
}

export function disableQuoteTemplate(id: number) {
  return request<QuoteTemplate>({ url: `/sales/templates/${id}/disable`, method: 'post' })
}

export function newVersionQuoteTemplate(id: number) {
  return request<QuoteTemplate>({ url: `/sales/templates/${id}/new-version`, method: 'post' })
}

export function deleteQuoteTemplate(id: number) {
  return request<void>({ url: `/sales/templates/${id}`, method: 'delete' })
}

// ---------------- 报价单 ----------------

export function listQuotations(params: ListQuery) {
  return request<PageResult<Quotation>>({
    url: '/sales/quotations',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function quotationCounts() {
  return request<Record<string, number>>({ url: '/sales/quotations/counts', method: 'get' })
}

export function getQuotation(id: number) {
  return request<Quotation>({ url: `/sales/quotations/${id}`, method: 'get' })
}

export function createQuotation(data: QuotationPayload) {
  return request<Quotation>({ url: '/sales/quotations', method: 'post', data })
}

export function updateQuotation(id: number, data: QuotationPayload) {
  return request<Quotation>({ url: `/sales/quotations/${id}`, method: 'put', data })
}

export function deleteQuotation(id: number) {
  return request<void>({ url: `/sales/quotations/${id}`, method: 'delete' })
}

export function submitQuotation(id: number) {
  return request<Quotation>({ url: `/sales/quotations/${id}/submit`, method: 'post', data: {} })
}

export function sendQuotation(id: number, channel: 'email' | 'print' | 'download', recipient = '') {
  return request<Quotation>({ url: `/sales/quotations/${id}/send`, method: 'post', data: { channel, recipient } })
}

export function feedbackQuotation(id: number, action: 'accept' | 'decline', note = '') {
  return request<Quotation>({ url: `/sales/quotations/${id}/feedback`, method: 'post', data: { action, note } })
}

export function quotationToContract(id: number) {
  return request<{ contractId: number; duplicated: boolean }>({
    url: `/sales/quotations/${id}/to-contract`,
    method: 'post',
  })
}

export function aiGenerateQuotation(data: {
  quotationId?: number
  customerId?: number
  templateId?: number
  requirement: string
}) {
  return request<AiGenerateResult>({ url: '/sales/quotations/ai-generate', method: 'post', data })
}

export function exportQuotations(params: ListQuery) {
  return download(
    {
      url: '/sales/quotations/export',
      method: 'get',
      params: toQuery(params as Record<string, unknown>),
    },
    'quotations.xlsx',
  )
}

// ---------------- 营收分析看板（B7） ----------------

/** 看板查询参数（查询参数走 camelCase 别名由后端 Query 别名映射） */
export interface RevenueQuery {
  /** 起始日期 YYYY-MM-DD（含） */
  from?: string
  /** 截止日期 YYYY-MM-DD（含） */
  to?: string
  /** 业务线 biz_block */
  biz_block?: string
  /** 客户 crm_customer.id */
  customer_id?: number
}

export interface RevenueRange {
  from: string
  to: string
}

/** 看板汇总：三口径 + 派生指标 */
export interface RevenueSummary {
  /** 合同总额（已签合同金额合计） */
  contractAmount: number
  /** 结算总额（已生效结算单金额合计） */
  settledAmount: number
  /** 回款总额（已确认到账金额合计） */
  receivedAmount: number
  /** 已签未结算 = contractAmount - settledAmount */
  unsettledAmount: number
  /** 已结算未回款 = settledAmount - receivedAmount */
  unreceivedAmount: number
  contractCount: number
  customerCount: number
  avgContractAmount: number
  /** 回款率 % = receivedAmount / settledAmount */
  receivableRate: number
  /** 结算率 % = settledAmount / contractAmount */
  collectionRate: number
}

/** 业务线维度 */
export interface RevenueBizBlock {
  bizBlock: string
  bizBlockText: string
  bizBlockTextEn?: string
  contractAmount: number
  settledAmount: number
  receivedAmount: number
  contractCount: number
  customerCount: number
  collectionRate: number
  receivableRate: number
}

/** 客户维度 */
export interface RevenueCustomer {
  customerId: number
  customerName: string
  contractAmount: number
  settledAmount: number
  receivedAmount: number
  unsettledAmount: number
  unreceivedAmount: number
  contractCount: number
  /** 业务线文本（字典标签） */
  bizBlocks: string[]
  /** 业务线原始编码 */
  bizBlockCodes?: string[]
  collectionRate: number
  receivableRate: number
}

/** 月度维度 */
export interface RevenueMonth {
  month: string
  contractAmount: number
  settledAmount: number
  receivedAmount: number
  contractCount: number
  collectionRate: number
  receivableRate: number
}

/** 合同明细维度 */
export interface RevenueContract {
  contractId: number
  contractNo: string
  contractName: string
  customerId: number
  customerName: string
  bizBlock: string
  bizBlockText: string
  bizBlockTextEn?: string
  amount: number
  contractAmount: number
  settledAmount: number
  receivedAmount: number
  signDate: string
  collectionRate: number
  receivableRate: number
}

/** 口径说明 */
export interface RevenueCaliber {
  contractAmount: string
  settledAmount: string
  receivedAmount: string
}

/** 营收分析看板 */
export interface RevenueBoard {
  range: RevenueRange
  summary: RevenueSummary
  byBizBlock: RevenueBizBlock[]
  byCustomer: RevenueCustomer[]
  byMonth: RevenueMonth[]
  byContract: RevenueContract[]
  caliber: RevenueCaliber
  /** 口径说明英文版 */
  caliberEn?: RevenueCaliber
}

export function getRevenueBoard(params: RevenueQuery) {
  return request<RevenueBoard>({
    url: '/sales/revenue/board',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function getRevenueCaliber() {
  return request<{ caliber: RevenueCaliber; caliberEn: RevenueCaliber }>({
    url: '/sales/revenue/caliber',
    method: 'get',
  })
}

export function exportRevenue(params: RevenueQuery) {
  return download(
    {
      url: '/sales/revenue/export',
      method: 'get',
      params: toQuery(params as Record<string, unknown>),
    },
    'revenue.xlsx',
  )
}

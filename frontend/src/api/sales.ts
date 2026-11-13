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

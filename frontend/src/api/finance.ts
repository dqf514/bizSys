import { request, download, toQuery } from './http'
import type {
  InvoiceListItem,
  ListQuery,
  PageResult,
  Payment,
  Settlement,
  SettlementDetail,
  SettlementTaskOption,
} from './types'

export interface CreateSettlementPayload {
  taskId: number
  amount: number
  invoiceableAmount?: number
  remark?: string
}

export interface UpdateInvoicePayload {
  invoiceNo: string
  amount: number
  invoiceDate?: string
}

export interface CreatePaymentPayload {
  settlementId: number
  payType: string
  payerName: string
  payerAccount?: string
  amount: number
  bank?: string
  paidAt: string
  remark?: string
}

export function listSettlements(params: ListQuery) {
  return request<PageResult<Settlement>>({
    url: '/finance/settlements',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function settlementCounts() {
  return request<Record<string, number>>({ url: '/finance/settlements/counts', method: 'get' })
}

export function settlementTaskOptions(q?: string) {
  return request<SettlementTaskOption[]>({
    url: '/finance/settlements/task-options',
    method: 'get',
    params: q ? { q } : {},
  })
}

export function createSettlement(data: CreateSettlementPayload) {
  return request<Settlement>({ url: '/finance/settlements', method: 'post', data })
}

export function getSettlement(id: number) {
  return request<SettlementDetail>({ url: `/finance/settlements/${id}`, method: 'get' })
}

export function applyInvoice(id: number) {
  return request<void>({ url: `/finance/settlements/${id}/apply-invoice`, method: 'post' })
}

export function sendSettlementConfirm(id: number, data: { receiverId: number; note?: string }) {
  return request<Settlement>({ url: `/finance/settlements/${id}/send-confirm`, method: 'post', data })
}

export function confirmSettlement(id: number, data: { action: 'confirm' | 'object'; note?: string }) {
  return request<Settlement>({ url: `/finance/settlements/${id}/confirm`, method: 'post', data })
}

export function submitSettlement(id: number) {
  return request<void>({ url: `/finance/settlements/${id}/submit`, method: 'post' })
}

export function updateInvoice(id: number, data: UpdateInvoicePayload) {
  return request<SettlementDetail>({ url: `/finance/invoices/${id}`, method: 'put', data })
}

export function listInvoices(params: ListQuery) {
  return request<PageResult<InvoiceListItem>>({
    url: '/finance/invoices',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function invoiceCounts() {
  return request<Record<string, number>>({ url: '/finance/invoices/counts', method: 'get' })
}

export function exportInvoices(params: ListQuery) {
  return download(
    {
      url: '/finance/invoices/export',
      method: 'get',
      params: toQuery(params as Record<string, unknown>),
    },
    'invoices.xlsx',
  )
}

export function listPayments(params: ListQuery) {
  return request<PageResult<Payment>>({
    url: '/finance/payments',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function createPayment(data: CreatePaymentPayload) {
  return request<Payment>({ url: '/finance/payments', method: 'post', data })
}

export function exportSettlements(params: ListQuery) {
  return download(
    {
      url: '/finance/settlements/export',
      method: 'get',
      params: toQuery(params as Record<string, unknown>),
    },
    'settlements.xlsx',
  )
}

export function exportPayments(params: ListQuery) {
  return download(
    {
      url: '/finance/payments/export',
      method: 'get',
      params: toQuery(params as Record<string, unknown>),
    },
    'payments.xlsx',
  )
}

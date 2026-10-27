import { request, download, toQuery } from './http'
import type {
  ListQuery,
  PageResult,
  PartnerAccount,
  PurchaseContract,
  PurchaseContractDetail,
  PurchaseRequest,
  PurchaseRequestDetail,
  StockOrder,
  TenderEval,
  TenderProject,
  TenderProjectDetail,
  TenderRegistration,
} from './types'

// ---- 采购申请 ----

export function listPurchaseRequests(params: ListQuery) {
  return request<PageResult<PurchaseRequest>>({
    url: '/procurement/requests',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function purchaseRequestCounts() {
  return request<Record<string, number>>({ url: '/procurement/requests/counts', method: 'get' })
}

export function getPurchaseRequest(id: number) {
  return request<PurchaseRequestDetail>({ url: `/procurement/requests/${id}`, method: 'get' })
}

export function createPurchaseRequest(data: Partial<PurchaseRequest>) {
  return request<PurchaseRequest>({ url: '/procurement/requests', method: 'post', data })
}

export function updatePurchaseRequest(id: number, data: Partial<PurchaseRequest>) {
  return request<PurchaseRequest>({ url: `/procurement/requests/${id}`, method: 'put', data })
}

export function deletePurchaseRequest(id: number) {
  return request<void>({ url: `/procurement/requests/${id}`, method: 'delete' })
}

export function submitPurchaseRequest(id: number, comment = '') {
  return request<PurchaseRequest>({ url: `/procurement/requests/${id}/submit`, method: 'post', data: { comment } })
}

export function voidPurchaseRequest(id: number) {
  return request<PurchaseRequest>({ url: `/procurement/requests/${id}/void`, method: 'post' })
}

export function generateContract(
  requestId: number,
  data: { supplierId: number; name?: string; amount?: number | null; payCycle?: string; delivery?: string; remark?: string },
) {
  return request<PurchaseContract>({
    url: `/procurement/requests/${requestId}/generate-contract`,
    method: 'post',
    data,
  })
}

export function exportPurchaseRequests(params: ListQuery) {
  return download(
    { url: '/procurement/requests/export', method: 'post', data: toQuery(params as Record<string, unknown>) },
    'purchase-requests.xlsx',
  )
}

// ---- 采购合同 ----

export function listPurchaseContracts(params: ListQuery) {
  return request<PageResult<PurchaseContract>>({
    url: '/procurement/contracts',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function purchaseContractCounts() {
  return request<Record<string, number>>({ url: '/procurement/contracts/counts', method: 'get' })
}

export function getPurchaseContract(id: number) {
  return request<PurchaseContractDetail>({ url: `/procurement/contracts/${id}`, method: 'get' })
}

export function createPurchaseContract(data: Partial<PurchaseContract>) {
  return request<PurchaseContract>({ url: '/procurement/contracts', method: 'post', data })
}

export function updatePurchaseContract(id: number, data: Partial<PurchaseContract>) {
  return request<PurchaseContract>({ url: `/procurement/contracts/${id}`, method: 'put', data })
}

export function deletePurchaseContract(id: number) {
  return request<void>({ url: `/procurement/contracts/${id}`, method: 'delete' })
}

export function submitPurchaseContract(id: number, comment = '') {
  return request<PurchaseContract>({ url: `/procurement/contracts/${id}/submit`, method: 'post', data: { comment } })
}

export function voidPurchaseContract(id: number) {
  return request<PurchaseContract>({ url: `/procurement/contracts/${id}/void`, method: 'post' })
}

export function exportPurchaseContracts(params: ListQuery) {
  return download(
    { url: '/procurement/contracts/export', method: 'post', data: toQuery(params as Record<string, unknown>) },
    'purchase-contracts.xlsx',
  )
}

// ---- 出入库 ----

export function listStockOrders(params: ListQuery) {
  return request<PageResult<StockOrder>>({
    url: '/procurement/stock-orders',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function stockOrderCounts() {
  return request<Record<string, number>>({ url: '/procurement/stock-orders/counts', method: 'get' })
}

export function getStockOrder(id: number) {
  return request<StockOrder>({ url: `/procurement/stock-orders/${id}`, method: 'get' })
}

export function createStockOrder(data: Partial<StockOrder>) {
  return request<StockOrder>({ url: '/procurement/stock-orders', method: 'post', data })
}

export function updateStockOrder(id: number, data: Partial<StockOrder>) {
  return request<StockOrder>({ url: `/procurement/stock-orders/${id}`, method: 'put', data })
}

export function confirmStockOrder(id: number) {
  return request<StockOrder>({ url: `/procurement/stock-orders/${id}/confirm`, method: 'post' })
}

export function deleteStockOrder(id: number) {
  return request<void>({ url: `/procurement/stock-orders/${id}`, method: 'delete' })
}

export function exportStockOrders(params: ListQuery) {
  return download(
    { url: '/procurement/stock-orders/export', method: 'post', data: toQuery(params as Record<string, unknown>) },
    'stock-orders.xlsx',
  )
}

// ---- 招投标（二期） ----

export interface TenderPayload {
  name?: string
  requestId?: number | null
  tenderMethod?: string
  budgetAmount?: number | null
  regDeadline?: string | null
  bidDeadline?: string | null
  openTime?: string | null
  announcement?: string
  version?: number | null
}

export function listTenders(params: ListQuery) {
  return request<PageResult<TenderProject>>({
    url: '/procurement/tenders',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function tenderCounts() {
  return request<Record<string, number>>({ url: '/procurement/tenders/counts', method: 'get' })
}

export function getTender(id: number) {
  return request<TenderProjectDetail>({ url: `/procurement/tenders/${id}`, method: 'get' })
}

export function createTender(data: TenderPayload) {
  return request<TenderProject>({ url: '/procurement/tenders', method: 'post', data })
}

export function updateTender(id: number, data: TenderPayload) {
  return request<TenderProject>({ url: `/procurement/tenders/${id}`, method: 'put', data })
}

export function deleteTender(id: number) {
  return request<void>({ url: `/procurement/tenders/${id}`, method: 'delete' })
}

export function publishTender(id: number) {
  return request<TenderProject>({ url: `/procurement/tenders/${id}/publish`, method: 'post' })
}

export function terminateTender(id: number) {
  return request<TenderProject>({ url: `/procurement/tenders/${id}/terminate`, method: 'post' })
}

export function startEvaluation(id: number) {
  return request<TenderProject>({ url: `/procurement/tenders/${id}/start-evaluation`, method: 'post' })
}

export function reviewRegistration(tenderId: number, regId: number, data: { approve: boolean; comment?: string }) {
  return request<TenderRegistration>({
    url: `/procurement/tenders/${tenderId}/registrations/${regId}/review`,
    method: 'post',
    data,
  })
}

export function upsertTenderEval(tenderId: number, data: { bidId: number; score: number; comment?: string; recommend?: boolean }) {
  return request<TenderEval>({ url: `/procurement/tenders/${tenderId}/evals`, method: 'post', data })
}

export function awardTender(tenderId: number, bidId: number) {
  return request<TenderProject>({ url: `/procurement/tenders/${tenderId}/award`, method: 'post', data: { bidId } })
}

export function generateTenderContract(tenderId: number) {
  return request<PurchaseContract>({ url: `/procurement/tenders/${tenderId}/generate-contract`, method: 'post' })
}

export function exportTenders(params: ListQuery) {
  return download(
    { url: '/procurement/tenders/export', method: 'post', data: toQuery(params as Record<string, unknown>) },
    'tenders.xlsx',
  )
}

export function downloadRegistrationAttachment(regId: number) {
  return download({ url: `/procurement/tenders/registrations/${regId}/attachment`, method: 'get' }, 'qualification')
}

export function downloadBidProposal(bidId: number) {
  return download({ url: `/procurement/tenders/bids/${bidId}/proposal`, method: 'get' }, 'proposal')
}

// ---- 合作方账号（二期） ----

export function listPartnerAccounts(params: ListQuery) {
  return request<PageResult<PartnerAccount>>({
    url: '/procurement/partners',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function partnerAccountCounts() {
  return request<Record<string, number>>({ url: '/procurement/partners/counts', method: 'get' })
}

export function reviewPartnerAccount(id: number, data: { approve: boolean; comment?: string; customerId?: number | null }) {
  return request<PartnerAccount>({ url: `/procurement/partners/${id}/review`, method: 'post', data })
}

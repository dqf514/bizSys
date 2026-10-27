import { request, download, toQuery } from './http'
import type {
  ListQuery,
  PageResult,
  PurchaseContract,
  PurchaseContractDetail,
  PurchaseRequest,
  PurchaseRequestDetail,
  StockOrder,
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

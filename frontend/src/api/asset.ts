import { request, download, toQuery } from './http'
import type {
  AssetBom,
  AssetBomExplode,
  AssetBomInput,
  AssetBomUsage,
  AssetDepreciation,
  AssetDisposal,
  AssetFixedAsset,
  AssetItem,
  AssetItemBomRefs,
  AssetItemOption,
  AssetLedger,
  AssetLocation,
  AssetLocationOption,
  AssetPrototype,
  AssetPrototypeLoan,
  AssetPrototypeOption,
  AssetPurchaseOrder,
  AssetReceipt,
  AssetStockCount,
  AssetTool,
  AssetToolLoan,
  AssetToolOption,
  AssetWarehouse,
  AssetWarehouseStats,
  ListQuery,
  PageResult,
} from './types'

/* ---------- 仓库与库位 ---------- */

export function listWarehouses(params: ListQuery) {
  return request<PageResult<AssetWarehouse>>({
    url: '/asset/warehouses',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function warehouseCounts() {
  return request<Record<string, number>>({ url: '/asset/warehouses/counts', method: 'get' })
}

export function warehouseStats() {
  return request<AssetWarehouseStats>({ url: '/asset/warehouses/stats', method: 'get' })
}

export function getWarehouse(id: number) {
  return request<AssetWarehouse & { locations: AssetLocation[] }>({
    url: `/asset/warehouses/${id}`,
    method: 'get',
  })
}

export function createWarehouse(data: Partial<AssetWarehouse>) {
  return request<AssetWarehouse>({ url: '/asset/warehouses', method: 'post', data })
}

export function updateWarehouse(id: number, data: Partial<AssetWarehouse>) {
  return request<AssetWarehouse>({ url: `/asset/warehouses/${id}`, method: 'put', data })
}

export function deleteWarehouse(id: number) {
  return request<void>({ url: `/asset/warehouses/${id}`, method: 'delete' })
}

export function exportWarehouses(params: ListQuery) {
  return download(
    { url: '/asset/warehouses/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'warehouses.xlsx',
  )
}

export function listLocations(params: ListQuery) {
  return request<PageResult<AssetLocation>>({
    url: '/asset/locations',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function listAllLocations() {
  return request<AssetLocationOption[]>({ url: '/asset/locations/all', method: 'get' })
}

export function createLocation(data: Partial<AssetLocation>) {
  return request<AssetLocation>({ url: '/asset/locations', method: 'post', data })
}

export function updateLocation(id: number, data: Partial<AssetLocation>) {
  return request<AssetLocation>({ url: `/asset/locations/${id}`, method: 'put', data })
}

export function deleteLocation(id: number) {
  return request<void>({ url: `/asset/locations/${id}`, method: 'delete' })
}

/* ---------- 存货档案 ---------- */

export function listItems(params: ListQuery) {
  return request<PageResult<AssetItem>>({
    url: '/asset/items',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function itemCounts() {
  return request<Record<string, number>>({ url: '/asset/items/counts', method: 'get' })
}

export function listAllItems() {
  return request<AssetItemOption[]>({ url: '/asset/items/all', method: 'get' })
}

export function getItem(id: number) {
  return request<AssetItem>({ url: `/asset/items/${id}`, method: 'get' })
}

export function createItem(data: Partial<AssetItem>) {
  return request<AssetItem>({ url: '/asset/items', method: 'post', data })
}

export function updateItem(id: number, data: Partial<AssetItem>) {
  return request<AssetItem>({ url: `/asset/items/${id}`, method: 'put', data })
}

export function deleteItem(id: number) {
  return request<void>({ url: `/asset/items/${id}`, method: 'delete' })
}

export function exportItems(params: ListQuery) {
  return download(
    { url: '/asset/items/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'inventory-items.xlsx',
  )
}

/* ---------- 物料清单（BOM） ---------- */

export function listBoms(params: ListQuery) {
  return request<PageResult<AssetBom>>({
    url: '/asset/boms',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function bomCounts() {
  return request<Record<string, number>>({ url: '/asset/boms/counts', method: 'get' })
}

export function getBom(id: number) {
  return request<AssetBom>({ url: `/asset/boms/${id}`, method: 'get' })
}

/** 多级展开：子件本身是总成时按其生效 BOM 继续下钻 */
export function explodeBom(id: number, maxDepth = 5) {
  return request<AssetBomExplode>({
    url: `/asset/boms/${id}/explode`,
    method: 'get',
    params: { max_depth: maxDepth },
  })
}

/** 用量对比：理论需求 vs 实际领用 */
export function bomUsage(id: number, qty = 1) {
  return request<AssetBomUsage>({
    url: `/asset/boms/${id}/usage`,
    method: 'get',
    params: { qty },
  })
}

/** 存货的 BOM 关联反查（作为父件 / 作为子件） */
export function itemBomRefs(id: number) {
  return request<AssetItemBomRefs>({ url: `/asset/items/${id}/bom-refs`, method: 'get' })
}

export function createBom(data: AssetBomInput) {
  return request<AssetBom>({ url: '/asset/boms', method: 'post', data })
}

export function updateBom(id: number, data: AssetBomInput) {
  return request<AssetBom>({ url: `/asset/boms/${id}`, method: 'put', data })
}

/** 生效：同一父件的其它生效版本自动作废 */
export function activateBom(id: number) {
  return request<AssetBom>({ url: `/asset/boms/${id}/activate`, method: 'post' })
}

/** 作废：停用当前生效版本 */
export function obsoleteBom(id: number) {
  return request<AssetBom>({ url: `/asset/boms/${id}/obsolete`, method: 'post' })
}

/** 复制为新版本草稿（版本号 +0.1） */
export function copyBom(id: number) {
  return request<AssetBom>({ url: `/asset/boms/${id}/copy`, method: 'post' })
}

export function deleteBom(id: number) {
  return request<void>({ url: `/asset/boms/${id}`, method: 'delete' })
}

export function exportBoms(params: ListQuery) {
  return download(
    { url: '/asset/boms/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'asset-boms.xlsx',
  )
}

/* ---------- 采购订单 ---------- */

export function listPurchaseOrders(params: ListQuery) {
  return request<PageResult<AssetPurchaseOrder>>({
    url: '/asset/purchase-orders',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function purchaseOrderCounts() {
  return request<Record<string, number>>({ url: '/asset/purchase-orders/counts', method: 'get' })
}

export function getPurchaseOrder(id: number) {
  return request<AssetPurchaseOrder>({ url: `/asset/purchase-orders/${id}`, method: 'get' })
}

export function createPurchaseOrder(data: Partial<AssetPurchaseOrder>) {
  return request<AssetPurchaseOrder>({ url: '/asset/purchase-orders', method: 'post', data })
}

export function updatePurchaseOrder(id: number, data: Partial<AssetPurchaseOrder>) {
  return request<AssetPurchaseOrder>({ url: `/asset/purchase-orders/${id}`, method: 'put', data })
}

export function deletePurchaseOrder(id: number) {
  return request<void>({ url: `/asset/purchase-orders/${id}`, method: 'delete' })
}

export function confirmPurchaseOrder(id: number) {
  return request<AssetPurchaseOrder>({ url: `/asset/purchase-orders/${id}/confirm`, method: 'post' })
}

export function closePurchaseOrder(id: number) {
  return request<AssetPurchaseOrder>({ url: `/asset/purchase-orders/${id}/close`, method: 'post' })
}

export function exportPurchaseOrders(params: ListQuery) {
  return download(
    {
      url: '/asset/purchase-orders/export',
      method: 'post',
      params: toQuery(params as Record<string, unknown>),
    },
    'asset-purchase-orders.xlsx',
  )
}

/* ---------- 到货验收 ---------- */

export function listReceipts(params: ListQuery) {
  return request<PageResult<AssetReceipt>>({
    url: '/asset/receipts',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function receiptCounts() {
  return request<Record<string, number>>({ url: '/asset/receipts/counts', method: 'get' })
}

export function getReceipt(id: number) {
  return request<AssetReceipt>({ url: `/asset/receipts/${id}`, method: 'get' })
}

export function createReceipt(data: Partial<AssetReceipt>) {
  return request<AssetReceipt>({ url: '/asset/receipts', method: 'post', data })
}

export function updateReceipt(id: number, data: Partial<AssetReceipt>) {
  return request<AssetReceipt>({ url: `/asset/receipts/${id}`, method: 'put', data })
}

export function deleteReceipt(id: number) {
  return request<void>({ url: `/asset/receipts/${id}`, method: 'delete' })
}

export function acceptReceipt(id: number) {
  return request<AssetReceipt>({ url: `/asset/receipts/${id}/accept`, method: 'post' })
}

export function exportReceipts(params: ListQuery) {
  return download(
    { url: '/asset/receipts/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'asset-receipts.xlsx',
  )
}

/* ---------- 库存台账 ---------- */

export function listLedger(params: ListQuery) {
  return request<PageResult<AssetLedger>>({
    url: '/asset/ledger',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function ledgerCounts() {
  return request<Record<string, number>>({ url: '/asset/ledger/counts', method: 'get' })
}

export function getLedgerRow(id: number) {
  return request<AssetLedger>({ url: `/asset/ledger/${id}`, method: 'get' })
}

export function createLedger(data: Partial<AssetLedger>) {
  return request<AssetLedger>({ url: '/asset/ledger', method: 'post', data })
}

export function updateLedger(id: number, data: Partial<AssetLedger>) {
  return request<AssetLedger>({ url: `/asset/ledger/${id}`, method: 'put', data })
}

export function deleteLedger(id: number) {
  return request<void>({ url: `/asset/ledger/${id}`, method: 'delete' })
}

export function exportLedger(params: ListQuery) {
  return download(
    { url: '/asset/ledger/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'asset-ledger.xlsx',
  )
}

/* ---------- 库存盘点 ---------- */

export function listStockCounts(params: ListQuery) {
  return request<PageResult<AssetStockCount>>({
    url: '/asset/counts',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function stockCountCounts() {
  return request<Record<string, number>>({ url: '/asset/counts/counts', method: 'get' })
}

export function getStockCount(id: number) {
  return request<AssetStockCount>({ url: `/asset/counts/${id}`, method: 'get' })
}

export function createStockCount(data: Partial<AssetStockCount>) {
  return request<AssetStockCount>({ url: '/asset/counts', method: 'post', data })
}

export function updateStockCount(id: number, data: Partial<AssetStockCount>) {
  return request<AssetStockCount>({ url: `/asset/counts/${id}`, method: 'put', data })
}

export function deleteStockCount(id: number) {
  return request<void>({ url: `/asset/counts/${id}`, method: 'delete' })
}

export function startStockCount(id: number) {
  return request<AssetStockCount>({ url: `/asset/counts/${id}/start`, method: 'post' })
}

export function finishStockCount(id: number) {
  return request<AssetStockCount>({ url: `/asset/counts/${id}/finish`, method: 'post' })
}

export function exportStockCounts(params: ListQuery) {
  return download(
    { url: '/asset/counts/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'asset-counts.xlsx',
  )
}

/* ---------- 样车样件台账 ---------- */

export function listPrototypes(params: ListQuery) {
  return request<PageResult<AssetPrototype>>({
    url: '/asset/prototypes',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function prototypeCounts() {
  return request<Record<string, number>>({ url: '/asset/prototypes/counts', method: 'get' })
}

export function listAllPrototypes() {
  return request<AssetPrototypeOption[]>({ url: '/asset/prototypes/all', method: 'get' })
}

export function getPrototype(id: number) {
  return request<AssetPrototype & { loans: AssetPrototypeLoan[] }>({
    url: `/asset/prototypes/${id}`,
    method: 'get',
  })
}

export function createPrototype(data: Partial<AssetPrototype>) {
  return request<AssetPrototype>({ url: '/asset/prototypes', method: 'post', data })
}

export function updatePrototype(id: number, data: Partial<AssetPrototype>) {
  return request<AssetPrototype>({ url: `/asset/prototypes/${id}`, method: 'put', data })
}

export function deletePrototype(id: number) {
  return request<void>({ url: `/asset/prototypes/${id}`, method: 'delete' })
}

export function exportPrototypes(params: ListQuery) {
  return download(
    { url: '/asset/prototypes/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'asset-prototypes.xlsx',
  )
}

/* ---------- 样件出借归还 ---------- */

export function listPrototypeLoans(params: ListQuery) {
  return request<PageResult<AssetPrototypeLoan>>({
    url: '/asset/prototype-loans',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function prototypeLoanCounts() {
  return request<Record<string, number>>({ url: '/asset/prototype-loans/counts', method: 'get' })
}

export function getPrototypeLoan(id: number) {
  return request<AssetPrototypeLoan>({ url: `/asset/prototype-loans/${id}`, method: 'get' })
}

export function createPrototypeLoan(data: Partial<AssetPrototypeLoan>) {
  return request<AssetPrototypeLoan>({ url: '/asset/prototype-loans', method: 'post', data })
}

export function updatePrototypeLoan(id: number, data: Partial<AssetPrototypeLoan>) {
  return request<AssetPrototypeLoan>({ url: `/asset/prototype-loans/${id}`, method: 'put', data })
}

export function deletePrototypeLoan(id: number) {
  return request<void>({ url: `/asset/prototype-loans/${id}`, method: 'delete' })
}

export function returnPrototypeLoan(id: number, data?: { returnDate?: string; remark?: string }) {
  return request<AssetPrototypeLoan>({ url: `/asset/prototype-loans/${id}/return`, method: 'post', data })
}

export function exportPrototypeLoans(params: ListQuery) {
  return download(
    {
      url: '/asset/prototype-loans/export',
      method: 'post',
      params: toQuery(params as Record<string, unknown>),
    },
    'asset-prototype-loans.xlsx',
  )
}

/* ---------- 固定资产与折旧 ---------- */

export function listAssets(params: ListQuery) {
  return request<PageResult<AssetFixedAsset>>({
    url: '/asset/assets',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function assetCounts() {
  return request<Record<string, number>>({ url: '/asset/assets/counts', method: 'get' })
}

export function getFixedAsset(id: number) {
  return request<AssetFixedAsset & { depreciations: AssetDepreciation[] }>({
    url: `/asset/assets/${id}`,
    method: 'get',
  })
}

export function createFixedAsset(data: Partial<AssetFixedAsset>) {
  return request<AssetFixedAsset>({ url: '/asset/assets', method: 'post', data })
}

export function updateFixedAsset(id: number, data: Partial<AssetFixedAsset>) {
  return request<AssetFixedAsset>({ url: `/asset/assets/${id}`, method: 'put', data })
}

export function deleteFixedAsset(id: number) {
  return request<void>({ url: `/asset/assets/${id}`, method: 'delete' })
}

export function depreciateAsset(id: number, data: { period: string; method: string; remark?: string }) {
  return request<AssetDepreciation>({ url: `/asset/assets/${id}/depreciate`, method: 'post', data })
}

export function listDepreciations(params: ListQuery) {
  return request<PageResult<AssetDepreciation>>({
    url: '/asset/depreciations',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function createDepreciation(data: Partial<AssetDepreciation>) {
  return request<AssetDepreciation>({ url: '/asset/depreciations', method: 'post', data })
}

export function updateDepreciation(id: number, data: Partial<AssetDepreciation>) {
  return request<AssetDepreciation>({ url: `/asset/depreciations/${id}`, method: 'put', data })
}

export function deleteDepreciation(id: number) {
  return request<void>({ url: `/asset/depreciations/${id}`, method: 'delete' })
}

export function exportAssets(params: ListQuery) {
  return download(
    { url: '/asset/assets/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'fixed-assets.xlsx',
  )
}

/* ---------- 处置与报废 ---------- */

export function listDisposals(params: ListQuery) {
  return request<PageResult<AssetDisposal>>({
    url: '/asset/disposals',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function disposalCounts() {
  return request<Record<string, number>>({ url: '/asset/disposals/counts', method: 'get' })
}

export function getDisposal(id: number) {
  return request<AssetDisposal>({ url: `/asset/disposals/${id}`, method: 'get' })
}

export function createDisposal(data: Partial<AssetDisposal>) {
  return request<AssetDisposal>({ url: '/asset/disposals', method: 'post', data })
}

export function updateDisposal(id: number, data: Partial<AssetDisposal>) {
  return request<AssetDisposal>({ url: `/asset/disposals/${id}`, method: 'put', data })
}

export function deleteDisposal(id: number) {
  return request<void>({ url: `/asset/disposals/${id}`, method: 'delete' })
}

export function approveDisposal(id: number) {
  return request<AssetDisposal>({ url: `/asset/disposals/${id}/approve`, method: 'post' })
}

export function completeDisposal(id: number) {
  return request<AssetDisposal>({ url: `/asset/disposals/${id}/complete`, method: 'post' })
}

export function exportDisposals(params: ListQuery) {
  return download(
    { url: '/asset/disposals/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'asset-disposals.xlsx',
  )
}

/* ---------- 工具与领用 ---------- */

export function listTools(params: ListQuery) {
  return request<PageResult<AssetTool>>({
    url: '/asset/tools',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function toolCounts() {
  return request<Record<string, number>>({ url: '/asset/tools/counts', method: 'get' })
}

export function listAllTools() {
  return request<AssetToolOption[]>({ url: '/asset/tools/all', method: 'get' })
}

export function getTool(id: number) {
  return request<AssetTool & { loans: AssetToolLoan[] }>({ url: `/asset/tools/${id}`, method: 'get' })
}

export function createTool(data: Partial<AssetTool>) {
  return request<AssetTool>({ url: '/asset/tools', method: 'post', data })
}

export function updateTool(id: number, data: Partial<AssetTool>) {
  return request<AssetTool>({ url: `/asset/tools/${id}`, method: 'put', data })
}

export function deleteTool(id: number) {
  return request<void>({ url: `/asset/tools/${id}`, method: 'delete' })
}

export function exportTools(params: ListQuery) {
  return download(
    { url: '/asset/tools/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'asset-tools.xlsx',
  )
}

export function listToolLoans(params: ListQuery) {
  return request<PageResult<AssetToolLoan>>({
    url: '/asset/tool-loans',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function toolLoanCounts() {
  return request<Record<string, number>>({ url: '/asset/tool-loans/counts', method: 'get' })
}

export function getToolLoan(id: number) {
  return request<AssetToolLoan>({ url: `/asset/tool-loans/${id}`, method: 'get' })
}

export function createToolLoan(data: Partial<AssetToolLoan>) {
  return request<AssetToolLoan>({ url: '/asset/tool-loans', method: 'post', data })
}

export function updateToolLoan(id: number, data: Partial<AssetToolLoan>) {
  return request<AssetToolLoan>({ url: `/asset/tool-loans/${id}`, method: 'put', data })
}

export function deleteToolLoan(id: number) {
  return request<void>({ url: `/asset/tool-loans/${id}`, method: 'delete' })
}

export function returnToolLoan(id: number, data?: { returnDate?: string; remark?: string }) {
  return request<AssetToolLoan>({ url: `/asset/tool-loans/${id}/return`, method: 'post', data })
}

export function exportToolLoans(params: ListQuery) {
  return download(
    { url: '/asset/tool-loans/export', method: 'post', params: toQuery(params as Record<string, unknown>) },
    'asset-tool-loans.xlsx',
  )
}

/** 访客与安全域（B3）接口客户端：区域 / 访客单 / 凭证 / 审计日志 / NDA / 黑名单 / 交接 / 预警。 */
import { download, request, toQuery } from './http'
import type {
  ListQuery,
  NdaVerifyResult,
  PageResult,
  VisitorAccessLog,
  VisitorAccessLogSummary,
  VisitorAlert,
  VisitorBlacklist,
  VisitorCredential,
  VisitorHandover,
  VisitorNda,
  VisitorStats,
  VisitorVisit,
  VisitorVisitInput,
  VisitorZone,
  VisitorZoneInput,
} from './types'

/* ---------------- 区域 ---------------- */

export function listVisitorZones(params: ListQuery) {
  return request<PageResult<VisitorZone>>({
    url: '/visitor/zones',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function visitorZoneCounts() {
  return request<Record<string, number>>({ url: '/visitor/zones/counts', method: 'get' })
}

export function createVisitorZone(data: VisitorZoneInput) {
  return request<VisitorZone>({ url: '/visitor/zones', method: 'post', data })
}

export function updateVisitorZone(id: number, data: VisitorZoneInput) {
  return request<VisitorZone>({ url: `/visitor/zones/${id}`, method: 'put', data })
}

export function toggleVisitorZone(id: number, status: 'enabled' | 'disabled') {
  return request<VisitorZone>({
    url: `/visitor/zones/${id}/toggle`,
    method: 'post',
    params: { status },
  })
}

/* ---------------- 访客登记 ---------------- */

export function listVisitorVisits(params: ListQuery) {
  return request<PageResult<VisitorVisit>>({
    url: '/visitor/visits',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function visitorVisitCounts() {
  return request<Record<string, number>>({ url: '/visitor/visits/counts', method: 'get' })
}

export function visitorStats() {
  return request<VisitorStats>({ url: '/visitor/visits/stats', method: 'get' })
}

export function getVisitorVisit(id: number) {
  return request<VisitorVisit>({ url: `/visitor/visits/${id}`, method: 'get' })
}

export function createVisitorVisit(data: VisitorVisitInput) {
  return request<VisitorVisit>({ url: '/visitor/visits', method: 'post', data })
}

export function approveVisitorVisit(
  id: number,
  data: { level?: string; action: 'approve' | 'reject'; comment?: string },
) {
  return request<VisitorVisit>({ url: `/visitor/visits/${id}/approve`, method: 'post', data })
}

export function checkInVisitorVisit(
  id: number,
  data: { method?: string; device_id?: string; credential_no?: string },
) {
  return request<VisitorVisit>({ url: `/visitor/visits/${id}/checkin`, method: 'post', data })
}

export function checkOutVisitorVisit(id: number, data: { method?: string; device_id?: string }) {
  return request<VisitorVisit>({ url: `/visitor/visits/${id}/checkout`, method: 'post', data })
}

export function cancelVisitorVisit(id: number) {
  return request<VisitorVisit>({ url: `/visitor/visits/${id}/cancel`, method: 'post' })
}

export function exportVisitorVisits(params: ListQuery) {
  return download(
    {
      url: '/visitor/visits/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'visitor-visits.xlsx',
  )
}

/* ---------------- 通行凭证 ---------------- */

export function listVisitorCredentials(params: ListQuery) {
  return request<PageResult<VisitorCredential>>({
    url: '/visitor/credentials',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function verifyVisitorCredential(data: {
  credential_no: string
  zone_id?: number | null
  method?: string
  device_id?: string
  direction?: string
}) {
  return request<{ pass: boolean; reason: string; credentialNo: string; visitId: number | null }>({
    url: '/visitor/credentials/verify',
    method: 'post',
    data,
  })
}

export function revokeVisitorCredential(id: number) {
  return request<{ id: number; status: string }>({
    url: `/visitor/credentials/${id}/revoke`,
    method: 'post',
  })
}

/* ---------------- 合规审计（只读） ---------------- */

export function listVisitorAccessLogs(params: ListQuery) {
  return request<PageResult<VisitorAccessLog>>({
    url: '/visitor/access-logs',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function visitorAccessLogSummary(days = 7) {
  return request<VisitorAccessLogSummary>({
    url: '/visitor/access-logs/summary',
    method: 'get',
    params: { days },
  })
}

export function exportVisitorAccessLogs(params: ListQuery) {
  return download(
    {
      url: '/visitor/access-logs/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'visitor-access-logs.xlsx',
  )
}

/* ---------------- 预警 ---------------- */

export function listVisitorAlerts(params: ListQuery) {
  return request<PageResult<VisitorAlert>>({
    url: '/visitor/alerts',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function visitorAlertCounts() {
  return request<Record<string, number>>({ url: '/visitor/alerts/counts', method: 'get' })
}

export function scanVisitorOverdue() {
  return request<{ scanned: number }>({ url: '/visitor/alerts/scan', method: 'post' })
}

export function handleVisitorAlert(id: number, data: { status: 'handled' | 'ignored'; handle_remark?: string }) {
  return request<{ id: number; status: string }>({
    url: `/visitor/alerts/${id}/handle`,
    method: 'post',
    data,
  })
}

/* ---------------- NDA ---------------- */

export function listVisitorNdas(params: ListQuery) {
  return request<PageResult<VisitorNda>>({
    url: '/visitor/nda',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function visitorNdaCounts() {
  return request<Record<string, number>>({ url: '/visitor/nda/counts', method: 'get' })
}

export function signVisitorNda(data: {
  title?: string
  template?: string
  visitor_name: string
  visitor_company?: string
  signer_title?: string
  id_no?: string
  signature_data?: string
  visit_id?: number | null
  valid_from?: string | null
  valid_to?: string | null
  remark?: string
}) {
  return request<VisitorNda>({ url: '/visitor/nda', method: 'post', data })
}

export function revokeVisitorNda(id: number) {
  return request<VisitorNda>({ url: `/visitor/nda/${id}/revoke`, method: 'post' })
}

/* ---------------- 黑名单 ---------------- */

export function listVisitorBlacklist(params: ListQuery) {
  return request<PageResult<VisitorBlacklist>>({
    url: '/visitor/blacklist',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function visitorBlacklistCounts() {
  return request<Record<string, number>>({ url: '/visitor/blacklist/counts', method: 'get' })
}

export function createVisitorBlacklist(data: Partial<VisitorBlacklist>) {
  return request<VisitorBlacklist>({ url: '/visitor/blacklist', method: 'post', data })
}

export function updateVisitorBlacklist(id: number, data: Partial<VisitorBlacklist>) {
  return request<VisitorBlacklist>({ url: `/visitor/blacklist/${id}`, method: 'put', data })
}

export function toggleVisitorBlacklist(id: number, status: 'enabled' | 'disabled') {
  return request<VisitorBlacklist>({
    url: `/visitor/blacklist/${id}/toggle`,
    method: 'post',
    params: { status },
  })
}

/* ---------------- 样品 / 样车交接 ---------------- */

export function listVisitorHandovers(params: ListQuery) {
  return request<PageResult<VisitorHandover>>({
    url: '/visitor/handovers',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function createVisitorHandover(data: {
  visit_id?: number | null
  sample_no: string
  sample_name?: string
  barcode?: string
  sample_type?: string
  qty?: number
  handover_user_name?: string
  receive_user_name?: string
  remark?: string
}) {
  return request<VisitorHandover>({ url: '/visitor/handovers', method: 'post', data })
}

/* ---------------- NDA 验签（B9 合规 2.4） ---------------- */

/** 验签结论：valid 有效 / invalid 签名与内容不一致 / legacy-unverifiable 存量行（无密钥绑定） */
export function verifyVisitorNda(id: number) {
  return request<NdaVerifyResult>({ url: `/visitor/nda/${id}/verify`, method: 'get' })
}

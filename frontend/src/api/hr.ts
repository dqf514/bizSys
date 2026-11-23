import { download, request, toQuery } from './http'
import type {
  HrAuthorization,
  HrAuthorizationDetail,
  HrAuthorizationStateAt,
  HrAuthorizationTimeline,
  HrContractOption,
  HrDayData,
  HrStatsOption,
  HrStatsResult,
  HrTaskOption,
  HrTimesheetItem,
  HrWeekSummary,
  ListQuery,
  PageResult,
} from './types'

/* ---------- 工时填报（用户侧） ---------- */

export interface TimesheetPayload {
  taskId: number
  workDate: string
  hours: number
  content: string
  remark?: string
  submit?: boolean
}

export function searchTimesheetContracts(q = '') {
  return request<HrContractOption[]>({
    url: '/hr/timesheets/options/contracts',
    method: 'get',
    params: { q },
  })
}

export function searchTimesheetTasks(contractId: number, q = '') {
  return request<HrTaskOption[]>({
    url: '/hr/timesheets/options/tasks',
    method: 'get',
    params: { contractId, q },
  })
}

export function getTimesheetDay(date: string) {
  return request<HrDayData>({ url: '/hr/timesheets/day', method: 'get', params: { date } })
}

export function getTimesheetWeek(date: string) {
  return request<HrWeekSummary>({ url: '/hr/timesheets/week', method: 'get', params: { date } })
}

export function createTimesheet(data: TimesheetPayload) {
  return request<HrTimesheetItem>({ url: '/hr/timesheets', method: 'post', data })
}

/* ---------- AI 工时预填（草稿，不落库） ---------- */

export interface TimesheetPrefillResult {
  hours: number
  content: string
  basis: { progressCount: number; recentCount: number; dayUsedHours: number }
}

export function aiPrefillTimesheet(taskId: number, workDate: string) {
  return request<TimesheetPrefillResult>({
    url: '/hr/timesheets/ai-prefill',
    method: 'post',
    data: { taskId, workDate },
  })
}

export function updateTimesheet(id: number, data: TimesheetPayload) {
  return request<HrTimesheetItem>({ url: `/hr/timesheets/${id}`, method: 'put', data })
}

export function deleteTimesheet(id: number) {
  return request<void>({ url: `/hr/timesheets/${id}`, method: 'delete' })
}

export function submitTimesheet(id: number) {
  return request<HrTimesheetItem>({ url: `/hr/timesheets/${id}/submit`, method: 'post' })
}

export function withdrawTimesheet(id: number) {
  return request<HrTimesheetItem>({ url: `/hr/timesheets/${id}/withdraw`, method: 'post' })
}

/* ---------- 我的工时列表 ---------- */

export function listMyTimesheets(params: ListQuery) {
  return request<PageResult<HrTimesheetItem>>({
    url: '/hr/timesheets/my',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function myTimesheetCounts() {
  return request<Record<string, number>>({ url: '/hr/timesheets/my/counts', method: 'get' })
}

export function exportMyTimesheets(params: ListQuery) {
  return download(
    { url: '/hr/timesheets/my/export', method: 'get', params: toQuery(params as Record<string, unknown>) },
    'hr_my_timesheets.xlsx',
  )
}

/* ---------- 工时统计（管理视角） ---------- */

export interface TimesheetStatsQuery {
  dimension: 'task' | 'contract' | 'user'
  dateStart?: string
  dateEnd?: string
  deptId?: number
  userId?: number
  taskId?: number
}

export function getTimesheetStats(params: TimesheetStatsQuery) {
  return request<HrStatsResult>({ url: '/hr/timesheets/stats', method: 'get', params: toQuery({ ...params }) })
}

export function getTimesheetStatsDetail(
  params: { userId: number; dateStart?: string; dateEnd?: string; taskId?: number; page?: number; size?: number },
) {
  return request<PageResult<HrTimesheetItem>>({
    url: '/hr/timesheets/stats/detail',
    method: 'get',
    params: toQuery({ ...params }),
  })
}

export function searchTimesheetStatsOptions(kind: 'dept' | 'user' | 'task', q = '') {
  return request<HrStatsOption[]>({ url: '/hr/timesheets/stats/options', method: 'get', params: { kind, q } })
}

export function exportTimesheetStats(params: TimesheetStatsQuery) {
  return download(
    { url: '/hr/timesheets/stats/export', method: 'get', params: toQuery({ ...params }) },
    `hr_timesheet_stats_${params.dimension}.xlsx`,
  )
}

/* ---------- 人员授权台账（B9-C3） ---------- */

export interface AuthorizationPayload {
  userId: number
  authType: string
  roleCode?: string
  scopeMethod?: string
  scopeParams?: string
  scopeDeviceId?: number | null
  scopeDeviceName?: string
  scopeDomain?: string
  validFrom?: string | null
  validTo?: string | null
  remark?: string
}

export interface AuthorizationActionPayload {
  reason?: string
}

export function listAuthorizations(params: ListQuery) {
  return request<PageResult<HrAuthorization>>({
    url: '/hr/authorizations',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function authorizationCounts() {
  return request<Record<string, number>>({ url: '/hr/authorizations/counts', method: 'get' })
}

export function exportAuthorizations(params: ListQuery) {
  return download(
    { url: '/hr/authorizations/export', method: 'get', params: toQuery(params as Record<string, unknown>) },
    'hr_authorizations.xlsx',
  )
}

/** 被授权人远程检索项 */
export interface AuthorizationUserOption {
  value: number
  label: string
  sub?: string
  deptName?: string
}

export function searchAuthorizationUsers(q = '') {
  return request<AuthorizationUserOption[]>({
    url: '/hr/authorizations/options/users',
    method: 'get',
    params: { q },
  })
}

export function getAuthorization(id: number) {
  return request<HrAuthorizationDetail>({ url: `/hr/authorizations/${id}`, method: 'get' })
}

export function getAuthorizationTimeline(id: number) {
  return request<HrAuthorizationTimeline>({ url: `/hr/authorizations/${id}/timeline`, method: 'get' })
}

export function getAuthorizationStateAt(id: number, at: string) {
  return request<HrAuthorizationStateAt>({
    url: `/hr/authorizations/${id}/state-at`,
    method: 'get',
    params: { at },
  })
}

export function createAuthorization(data: AuthorizationPayload) {
  return request<HrAuthorization>({ url: '/hr/authorizations', method: 'post', data })
}

export function updateAuthorization(id: number, data: AuthorizationPayload) {
  return request<HrAuthorization>({ url: `/hr/authorizations/${id}`, method: 'put', data })
}

export function submitAuthorization(id: number, comment?: string) {
  return request<HrAuthorization>({
    url: `/hr/authorizations/${id}/submit`,
    method: 'post',
    data: { comment },
  })
}

export function activateAuthorization(id: number, reason?: string) {
  return request<HrAuthorization>({
    url: `/hr/authorizations/${id}/activate`,
    method: 'post',
    data: { reason },
  })
}

export function suspendAuthorization(id: number, reason: string) {
  return request<HrAuthorization>({
    url: `/hr/authorizations/${id}/suspend`,
    method: 'post',
    data: { reason },
  })
}

export function resumeAuthorization(id: number, reason?: string) {
  return request<HrAuthorization>({
    url: `/hr/authorizations/${id}/resume`,
    method: 'post',
    data: { reason },
  })
}

export function revokeAuthorization(id: number, reason: string) {
  return request<HrAuthorization>({
    url: `/hr/authorizations/${id}/revoke`,
    method: 'post',
    data: { reason },
  })
}

export function expireAuthorization(id: number, reason: string) {
  return request<HrAuthorization>({
    url: `/hr/authorizations/${id}/expire`,
    method: 'post',
    data: { reason },
  })
}

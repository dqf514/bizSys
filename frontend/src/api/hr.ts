import { download, request, toQuery } from './http'
import type {
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

import { download, request, toQuery } from './http'
import type {
  HrAuthorization,
  HrAuthorizationDetail,
  HrAuthorizationStateAt,
  HrAuthorizationTimeline,
  HrContractOption,
  HrDayData,
  HrDelegate,
  HrEmployee,
  HrEmployeeControl,
  HrEmployeeDetail,
  HrEmployeeOption,
  HrEmployeeTimelineItem,
  HrEmployment,
  HrEmploymentDetail,
  HrEmploymentEvent,
  HrOrgChange,
  HrOrgOptions,
  HrPosition,
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

/* ---------- 组织架构：岗位 / 变更轨迹 / 选项（B10-1） ---------- */

export interface PositionPayload {
  code: string
  name: string
  deptId?: number | null
  siteId?: number | null
  positionType: string
  duty?: string
  requirement?: string
  reportToId?: number | null
  keyRole?: string
  primaryUserId?: number | null
  backupUserId?: number | null
  status?: string
  remark?: string
}

export function listPositions(params: ListQuery) {
  return request<PageResult<HrPosition>>({
    url: '/hr/org/positions',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function positionCounts() {
  return request<Record<string, number>>({ url: '/hr/org/positions/counts', method: 'get' })
}

export function exportPositions(params: ListQuery) {
  return download(
    { url: '/hr/org/positions/export', method: 'get', params: toQuery(params as Record<string, unknown>) },
    'hr_positions.xlsx',
  )
}

export function createPosition(data: PositionPayload) {
  return request<HrPosition>({ url: '/hr/org/positions', method: 'post', data })
}

export function updatePosition(id: number, data: PositionPayload) {
  return request<HrPosition>({ url: `/hr/org/positions/${id}`, method: 'put', data })
}

export function deletePosition(id: number) {
  return request<void>({ url: `/hr/org/positions/${id}`, method: 'delete' })
}

export function listOrgChanges(params: ListQuery) {
  return request<PageResult<HrOrgChange>>({
    url: '/hr/org/changes',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function getOrgOptions() {
  return request<HrOrgOptions>({ url: '/hr/org/options', method: 'get' })
}

/* ---------- 员工主数据（B10-1） ---------- */

export interface EmployeePayload {
  employeeNo: string
  name: string
  userId?: number | null
  idNo?: string
  idType?: string
  gender?: string
  birthDate?: string | null
  education?: string
  major?: string
  mobile?: string
  email?: string
  employType: string
  employStatus: string
  deptId?: number | null
  positionId?: number | null
  hireDate?: string | null
  leaveDate?: string | null
  contractNo?: string
  contractStart?: string | null
  contractEnd?: string | null
  emergencyContact?: string
  emergencyMobile?: string
  status?: string
  remark?: string
}

export function listEmployees(params: ListQuery) {
  return request<PageResult<HrEmployee>>({
    url: '/hr/employees',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function employeeCounts() {
  return request<Record<string, number>>({ url: '/hr/employees/counts', method: 'get' })
}

export function employeeOptions() {
  return request<{ all: HrEmployeeOption[]; active: HrEmployeeOption[] }>({
    url: '/hr/employees/options',
    method: 'get',
  })
}

export function exportEmployees(params: ListQuery) {
  return download(
    { url: '/hr/employees/export', method: 'get', params: toQuery(params as Record<string, unknown>) },
    'hr_employees.xlsx',
  )
}

export function getEmployee(id: number) {
  return request<HrEmployeeDetail>({ url: `/hr/employees/${id}`, method: 'get' })
}

/** 证件号明文 —— **唯一出口**，后端每次访问写审计日志 */
export function getEmployeeIdNo(id: number) {
  return request<{ idNo: string; masked: string }>({ url: `/hr/employees/${id}/id-no`, method: 'get' })
}

export function employeeTimeline(id: number) {
  return request<{ items: HrEmployeeTimelineItem[] }>({ url: `/hr/employees/${id}/timeline`, method: 'get' })
}

export function createEmployee(data: EmployeePayload) {
  return request<HrEmployee>({ url: '/hr/employees', method: 'post', data })
}

export function updateEmployee(id: number, data: EmployeePayload) {
  return request<HrEmployee>({ url: `/hr/employees/${id}`, method: 'put', data })
}

export function deleteEmployee(id: number) {
  return request<void>({ url: `/hr/employees/${id}`, method: 'delete' })
}

export interface EmployeeControlPayload {
  controlType: string
  reason: string
  effectiveFrom?: string | null
  effectiveTo?: string | null
  status?: string
  remark?: string
}

export function createEmployeeControl(id: number, data: EmployeeControlPayload) {
  return request<HrEmployeeControl>({ url: `/hr/employees/${id}/control`, method: 'post', data })
}

/* ---------- 人事事务 / 代理人（B10-1） ---------- */

export interface EmploymentPayload {
  employeeId: number
  eventType: string
  newDeptId?: number | null
  newPositionId?: number | null
  effectiveDate?: string | null
  reason?: string
  remark?: string
  createAccount?: boolean
  username?: string
  password?: string
  roleIds?: number[]
}

export function listEmployments(params: ListQuery) {
  return request<PageResult<HrEmployment>>({
    url: '/hr/employments',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function employmentCounts() {
  return request<Record<string, number>>({ url: '/hr/employments/counts', method: 'get' })
}

export function getEmployment(id: number) {
  return request<HrEmploymentDetail>({ url: `/hr/employments/${id}`, method: 'get' })
}

export function employmentTimeline(id: number) {
  return request<{ items: HrEmploymentEvent[] }>({ url: `/hr/employments/${id}/timeline`, method: 'get' })
}

export function createEmployment(data: EmploymentPayload) {
  return request<HrEmployment>({ url: '/hr/employments', method: 'post', data })
}

export function updateEmployment(id: number, data: EmploymentPayload) {
  return request<HrEmployment>({ url: `/hr/employments/${id}`, method: 'put', data })
}

export function submitEmployment(id: number, comment?: string) {
  return request<HrEmployment>({
    url: `/hr/employments/${id}/submit`,
    method: 'post',
    data: { comment },
  })
}

export function withdrawEmployment(id: number, comment?: string) {
  return request<HrEmployment>({
    url: `/hr/employments/${id}/withdraw`,
    method: 'post',
    data: { comment },
  })
}

/** 生效：执行副作用（开号 / 调岗 / 离职清权 / 返聘） */
export function effectEmployment(id: number) {
  return request<HrEmploymentDetail>({ url: `/hr/employments/${id}/effect`, method: 'post' })
}

export interface DelegatePayload {
  principalId: number
  agentId: number
  scope: string
  positionId?: number | null
  authId?: number | null
  reason?: string
  effectiveFrom?: string | null
  effectiveTo?: string | null
  autoTakeover?: number
  remark?: string
}

export function listDelegates(params: ListQuery) {
  return request<PageResult<HrDelegate>>({
    url: '/hr/delegates',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function createDelegate(data: DelegatePayload) {
  return request<HrDelegate>({ url: '/hr/delegates', method: 'post', data })
}

export function updateDelegate(id: number, data: DelegatePayload) {
  return request<HrDelegate>({ url: `/hr/delegates/${id}`, method: 'put', data })
}

export function deleteDelegate(id: number) {
  return request<void>({ url: `/hr/delegates/${id}`, method: 'delete' })
}

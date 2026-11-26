import { download, request, toQuery } from './http'
import type {
  ListQuery,
  OaCatalogGroup,
  OaField,
  OaFlowDefOption,
  OaForm,
  OaFormScope,
  OaInstanceDetail,
  OaInstanceItem,
  OaResourceItem,
  OaResourceMeta,
  OaResourceType,
  OaStats,
  PageResult,
} from './types'

/* ---------- 用户侧 ---------- */

export function listOaCatalog() {
  return request<OaCatalogGroup[]>({ url: '/oa/catalog', method: 'get' })
}

/* ---------- 资源控件检索 ---------- */

export function listOaResourceMeta() {
  return request<OaResourceMeta[]>({ url: '/oa/resources/meta', method: 'get' })
}

export function searchOaResources(rtype: OaResourceType, params: { q?: string; page?: number; size?: number }) {
  return request<PageResult<OaResourceItem>>({
    url: `/oa/resources/${rtype}`,
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function applyOa(formId: number, data: Record<string, unknown>) {
  return request<OaInstanceItem>({ url: '/oa/instances', method: 'post', data: { formId, data } })
}

export function listMyOaInstances(params: ListQuery) {
  return request<PageResult<OaInstanceItem>>({
    url: '/oa/instances/my',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function myOaInstanceCounts() {
  return request<Record<string, number>>({ url: '/oa/instances/my/counts', method: 'get' })
}

export function exportMyOaInstances(params: { status?: string; q?: string }) {
  return download(
    { url: '/oa/instances/my/export', method: 'get', params: toQuery(params as Record<string, unknown>) },
    'oa_my_instances.xlsx',
  )
}

export function listOaRelated(tab: 'todo' | 'done' | 'cc', params: ListQuery) {
  return request<PageResult<Record<string, unknown>>>({
    url: '/oa/related',
    method: 'get',
    params: toQuery({ ...params, tab } as Record<string, unknown>),
  })
}

export function oaRelatedCounts() {
  return request<Record<string, number>>({ url: '/oa/related/counts', method: 'get' })
}

export function getOaInstance(id: number) {
  return request<OaInstanceDetail>({ url: `/oa/instances/${id}`, method: 'get' })
}

export function withdrawOaInstance(id: number) {
  return request<{ instanceId: number; status: string }>({
    url: `/oa/instances/${id}/withdraw`,
    method: 'post',
  })
}

export function getOaStats() {
  return request<OaStats>({ url: '/oa/stats', method: 'get' })
}

/* ---------- 管理侧：表单设计 ---------- */

export interface OaFormPayload {
  key: string
  name: string
  category: string
  icon: string
  sort: number
  description: string
  fields: Partial<OaField>[]
  flowDefinitionId: number | null
  /** E1：模板可见范围（空 = 全员可见） */
  scope?: OaFormScope | null
}

export function listOaForms() {
  return request<OaForm[]>({ url: '/oa/admin/forms', method: 'get' })
}

export function createOaForm(data: OaFormPayload) {
  return request<OaForm>({ url: '/oa/admin/forms', method: 'post', data })
}

export function updateOaForm(id: number, data: OaFormPayload) {
  return request<OaForm>({ url: `/oa/admin/forms/${id}`, method: 'put', data })
}

export function newOaFormVersion(id: number) {
  return request<OaForm>({ url: `/oa/admin/forms/${id}/new-version`, method: 'post' })
}

export function publishOaForm(id: number) {
  return request<OaForm>({ url: `/oa/admin/forms/${id}/publish`, method: 'post' })
}

export function disableOaForm(id: number) {
  return request<OaForm>({ url: `/oa/admin/forms/${id}/disable`, method: 'post' })
}

export function deleteOaForm(id: number) {
  return request<void>({ url: `/oa/admin/forms/${id}`, method: 'delete' })
}

export function bindLatestFlow(id: number) {
  return request<OaForm>({ url: `/oa/admin/forms/${id}/bind-latest-flow`, method: 'post' })
}

export function listOaFlowDefs() {
  return request<OaFlowDefOption[]>({ url: '/oa/admin/flow-defs', method: 'get' })
}

/* ---------- 管理侧：统计 / 干预 ---------- */

export function getOaAdminStats() {
  return request<OaStats>({ url: '/oa/admin/stats', method: 'get' })
}

export function listOaAdminInstances(params: ListQuery & { keyword?: string; stuckDays?: number }) {
  return request<PageResult<OaInstanceItem>>({
    url: '/oa/admin/instances',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function oaAdminInstanceCounts() {
  return request<Record<string, number>>({ url: '/oa/admin/instances/counts', method: 'get' })
}

export function terminateOaInstance(id: number, comment: string) {
  return request<{ instanceId: number; status: string }>({
    url: `/oa/admin/instances/${id}/terminate`,
    method: 'post',
    data: { comment },
  })
}

export function reassignOaInstance(id: number, taskId: number, toUserId: number, comment: string) {
  return request<{ instanceId: number; status: string }>({
    url: `/oa/admin/instances/${id}/reassign`,
    method: 'post',
    data: { taskId, toUserId, comment },
  })
}

export function restartOaInstance(id: number, seq: number, comment: string) {
  return request<{ instanceId: number; status: string; currentSeq: number }>({
    url: `/oa/admin/instances/${id}/restart`,
    method: 'post',
    data: { seq, comment },
  })
}

/* ---------- AI 表单预填（草稿，不落库） ---------- */

export interface OaPrefillResult {
  data: Record<string, unknown>
  filledKeys: string[]
  historyCount: number
}

export function aiPrefillOaForm(formId: number) {
  return request<OaPrefillResult>({ url: '/oa/ai-prefill', method: 'post', data: { formId } })
}

/* ---------- 管理侧：AI 异常分析 / 催办 ---------- */

export interface OaAnomalyResult {
  stuck: {
    nodeName: string
    pending: { assigneeId: number; assigneeName: string; hours: number }[]
  }
  signals: string[]
  analysis: string
  suggestions: { type: string; text: string; userId?: number; userName?: string }[]
}

export function aiOaAnomaly(id: number) {
  return request<OaAnomalyResult>({ url: `/oa/admin/instances/${id}/ai-anomaly`, method: 'post' })
}

export function urgeOaInstance(id: number, comment = '') {
  return request<{ instanceId: number; urged: number }>({
    url: `/oa/admin/instances/${id}/urge`,
    method: 'post',
    data: { comment },
  })
}

/* ---------- B8 作业申请流程（叉车 / 吊装 / 高处 / 动火） ---------- */

/** 作业申请单据状态（与 OA 单据状态口径一致） */
export type WorkApplyStatus = 'running' | 'approved' | 'rejected' | 'withdrawn' | 'terminated'

/** 作业申请列表项（data 为从 form_data 抽取的关键字段摘要） */
export interface WorkApply {
  id: number
  displayNo: string
  formKey: string
  formName: string
  applicantId: number
  applicantName: string
  status: WorkApplyStatus | string
  statusText: string
  flowInstanceId: number
  createTime: string
  finishedAt: string
  data: {
    work_location?: string
    work_dept?: string
    work_content?: string
    risk_level?: string
    work_time?: string
  }
}

/** 作业申请模板（4 类作业许可） */
export interface WorkApplyCatalogItem {
  id: number
  key: string
  name: string
  description: string
  icon: string
  fields: OaField[]
}

/** 作业申请审批时间线节点 */
export interface WorkApplyTimelineNode {
  action: string
  operatorName: string
  nodeName: string
  seq?: number
  comment: string
  payload?: Record<string, unknown> | null
  at: string
}

/** 作业申请详情（单据 + 表单结构 + 表单数据 + 时间线） */
export interface WorkApplyDetail extends WorkApply {
  schema: { fields?: OaField[] }
  formData: Record<string, unknown>
  timeline: WorkApplyTimelineNode[]
}

/** 作业申请状态页签计数 */
export interface WorkApplyCounts {
  all: number
  running: number
  approved: number
  rejected: number
  withdrawn: number
  terminated: number
}

export function listWorkApplies(params: ListQuery) {
  return request<PageResult<WorkApply>>({
    url: '/oa/work-applies',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function workApplyCounts() {
  return request<WorkApplyCounts>({ url: '/oa/work-applies/counts', method: 'get' })
}

export function getWorkApply(id: number) {
  return request<WorkApplyDetail>({ url: `/oa/work-applies/${id}`, method: 'get' })
}

export function workApplyCatalog() {
  return request<WorkApplyCatalogItem[]>({ url: '/oa/work-apply-catalog', method: 'get' })
}

export function createWorkApply(formKey: string, data: Record<string, unknown>) {
  return request<{
    id: number
    displayNo: string
    formKey: string
    formName: string
    status: string
    flowInstanceId: number
  }>({ url: '/oa/work-applies', method: 'post', data: { formKey, data } })
}

export function cancelWorkApply(id: number) {
  return request<{ id: number; displayNo: string; status: string }>({
    url: `/oa/work-applies/${id}/cancel`,
    method: 'post',
  })
}

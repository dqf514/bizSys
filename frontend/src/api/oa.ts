import { request, toQuery } from './http'
import type {
  ListQuery,
  OaCatalogGroup,
  OaField,
  OaFlowDefOption,
  OaForm,
  OaInstanceDetail,
  OaInstanceItem,
  OaStats,
  PageResult,
} from './types'

/* ---------- 用户侧 ---------- */

export function listOaCatalog() {
  return request<OaCatalogGroup[]>({ url: '/oa/catalog', method: 'get' })
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

export function listOaRelated(tab: 'todo' | 'done' | 'cc', params: ListQuery) {
  return request<PageResult<Record<string, unknown>>>({
    url: '/oa/related',
    method: 'get',
    params: toQuery({ ...params, tab } as Record<string, unknown>),
  })
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

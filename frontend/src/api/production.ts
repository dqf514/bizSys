import { request, download, toQuery } from './http'
import type {
  ListQuery,
  PageResult,
  ProdPlan,
  ProdSchedule,
  ResourceOccupancy,
} from './types'

/* ---------- 排程方案 ---------- */

export function listPlans(params: ListQuery) {
  return request<PageResult<ProdPlan>>({
    url: '/production/plans',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function planCounts() {
  return request<Record<string, number>>({ url: '/production/plans/counts', method: 'get' })
}

export function getPlan(id: number) {
  return request<ProdPlan>({ url: `/production/plans/${id}`, method: 'get' })
}

export function createPlan(data: Partial<ProdPlan>) {
  return request<ProdPlan>({ url: '/production/plans', method: 'post', data })
}

export function deletePlan(id: number) {
  return request<void>({ url: `/production/plans/${id}`, method: 'delete' })
}

/** 自动排期（规则式贪心）：按设备 / 人员 / 样车时段冲突 + 物料可用量生成方案 */
export function autoSchedule(data: {
  name?: string
  baseDate?: string
  taskIds?: number[]
  projectId?: number | null
  dateFrom?: string
  dateTo?: string
  remark?: string
}) {
  return request<ProdPlan>({ url: '/production/plans/auto', method: 'post', data })
}

export function publishPlan(id: number) {
  return request<ProdPlan>({ url: `/production/plans/${id}/publish`, method: 'post' })
}

export function cancelPlan(id: number) {
  return request<ProdPlan>({ url: `/production/plans/${id}/cancel`, method: 'post' })
}

/* ---------- 排程行 ---------- */

export function listSchedules(params: ListQuery) {
  return request<PageResult<ProdSchedule>>({
    url: '/production/schedules',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function scheduleCounts(params: ListQuery) {
  return request<Record<string, number>>({
    url: '/production/schedules/counts',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function scheduleGantt(params: ListQuery) {
  return request<{ items: ProdSchedule[]; total: number }>({
    url: '/production/schedules/gantt',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function getSchedule(id: number) {
  return request<ProdSchedule>({ url: `/production/schedules/${id}`, method: 'get' })
}

export function updateSchedule(id: number, data: Partial<ProdSchedule>) {
  return request<ProdSchedule>({ url: `/production/schedules/${id}`, method: 'put', data })
}

export function confirmSchedule(id: number) {
  return request<ProdSchedule>({ url: `/production/schedules/${id}/confirm`, method: 'post' })
}

export function deleteSchedule(id: number) {
  return request<void>({ url: `/production/schedules/${id}`, method: 'delete' })
}

/** 资源占用视图（设备 / 人员 / 样车 / 物料的已占用时段） */
export function resourceOccupancy(params: ListQuery) {
  return request<{ items: ResourceOccupancy[]; total: number }>({
    url: '/production/resources/occupancy',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function exportSchedules(params: ListQuery) {
  return download(
    {
      url: '/production/schedules/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'production_schedules.xlsx',
  )
}

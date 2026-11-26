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

/* ---------- 产能利用率看板（B7） ---------- */

/** 统计期间 */
export interface CapacityRange {
  from: string
  to: string
}

/** 看板汇总指标 */
export interface CapacitySummary {
  /** 设备总数（台账口径） */
  equipmentTotal: number
  /** 期间有排程的设备数 */
  scheduledEquipment: number
  /** 整体平均利用率 % */
  avgUtilization: number
  /** 排程占用总工时 */
  totalScheduleHours: number
  /** 冲突排程行数 */
  conflictCount: number
  /** 期间零排程设备数 */
  idleEquipment: number
  /** 利用率 > 100% 的设备数 */
  overloadEquipment: number
  /** 统计天数 */
  periodCount: number
}

/** 分类维度（风洞 / CFD / 加工 / 试验 / 其他） */
export interface CapacityCategory {
  category: string
  categoryText: string
  equipmentCount: number
  scheduleHours: number
  availableHours: number
  utilization: number
  /** 排程行数（风洞业务即「台次」） */
  scheduleCount: number
}

/** 车间维度 */
export interface CapacityWorkshop {
  workshop: string
  equipmentCount: number
  scheduleHours: number
  availableHours: number
  utilization: number
}

/** 设备明细 */
export interface CapacityEquipment {
  equipmentId: number | null
  equipmentNo: string
  equipmentName: string
  category: string
  categoryText: string
  workshop: string
  status: string
  statusText: string
  scheduleHours: number
  availableHours: number
  utilization: number
  scheduleCount: number
  conflictCount: number
  taskCount: number
  runHours: number
  lastScheduleEnd: string
  overloaded: boolean
}

/** 趋势分桶（按日或按自然周） */
export interface CapacityTrend {
  bucket: string
  scheduleHours: number
  availableHours: number
  utilization: number
  scheduleCount: number
  conflictCount: number
}

/** 冲突排程 */
export interface CapacityConflict {
  scheduleNo: string
  equipmentId: number | null
  equipmentNo: string
  equipmentName: string
  taskNo: string
  taskName: string
  planStart: string
  planEnd: string
  reason: string
}

/** 产能利用率看板总览 */
export interface CapacityBoard {
  range: CapacityRange
  summary: CapacitySummary
  byCategory: CapacityCategory[]
  byWorkshop: CapacityWorkshop[]
  equipment: CapacityEquipment[]
  trend: CapacityTrend[]
  conflicts: CapacityConflict[]
}

/** 设备下钻的排程行摘要 */
export interface CapacityScheduleRow {
  id: number
  scheduleNo: string
  planNo: string
  taskId: number | null
  taskNo: string
  taskName: string
  resourceCode: string
  resourceName: string
  planStart: string
  planEnd: string
  durationHours: number
  status: string
  statusText: string
  conflictReason: string
}

/** 单设备下钻详情 */
export interface CapacityEquipmentDetail {
  equipment: CapacityEquipment
  schedules: CapacityScheduleRow[]
  metrics: CapacityTrend[]
}

export interface CapacityQuery {
  from?: string
  to?: string
  workshop?: string
  category?: string
}

/** 产能利用率看板：汇总 + 分类 / 车间 / 趋势 / 设备明细 / 冲突清单 */
export function getCapacityBoard(params: CapacityQuery) {
  return request<CapacityBoard>({
    url: '/production/capacity/board',
    method: 'get',
    params,
  })
}

/** 单设备近 30 天排程明细（下钻） */
export function getCapacityEquipment(id: number, params?: { from?: string; to?: string }) {
  return request<CapacityEquipmentDetail>({
    url: `/production/capacity/equipment/${id}`,
    method: 'get',
    params,
  })
}

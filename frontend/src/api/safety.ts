/** Safety inspection domain (B8 / CSV 24): plans / inspections / hazards / board. */
import { request, toQuery } from './http'
import type { ListQuery, PageResult } from './types'

/* ---------------- DTO ---------------- */

export interface SafetyPlan {
  id: number
  planNo: string
  name: string
  planType: string
  planTypeText: string
  targetArea: string
  checkItems: string[]
  cycleDays: number
  nextDate: string
  ownerId: number | null
  ownerName: string
  deptId: number | null
  deptName: string
  status: string
  statusText: string
  remark: string
  createTime: string
  updateTime: string
}

export interface SafetyInspectionItem {
  item: string
  result: string
  note: string
}

export interface SafetyInspection {
  id: number
  recordNo: string
  planId: number | null
  planName: string
  area: string
  inspectDate: string
  inspectorId: number | null
  inspectorName: string
  result: string
  resultText: string
  abnormalCount: number
  items: SafetyInspectionItem[]
  status: string
  statusText: string
  summary: string
  remark: string
  createTime: string
  updateTime: string
  hazards?: SafetyHazard[]
}

export interface SafetyHazard {
  id: number
  hazardNo: string
  inspectionId: number | null
  recordNo: string
  source: string
  sourceText: string
  description: string
  level: string
  levelText: string
  status: string
  statusText: string
  responsibleId: number | null
  responsibleName: string
  deadline: string
  foundAt: string
  measure: string
  rectifiedAt: string
  rectifiedByName: string
  verifyResult: string
  verifyByName: string
  verifiedAt: string
  overdue: boolean
  remark: string
  createTime: string
  updateTime: string
}

export interface SafetyBoardCount {
  level?: string
  status?: string
  area?: string
  count: number
}

export interface SafetyBoardOverdue {
  id: number
  hazardNo: string
  description: string
  level: string
  deadline: string
  responsibleName: string
  daysOverdue: number
}

export interface SafetyBoard {
  planTotal: number
  planActive: number
  monthInspections: number
  openHazards: number
  overdueHazards: number
  byLevel: SafetyBoardCount[]
  byStatus: SafetyBoardCount[]
  byArea: SafetyBoardCount[]
  overdueTop: SafetyBoardOverdue[]
  completion: { planCount: number; doneCount: number; rate: number }
  monthlyTrend: { month: string; count: number }[]
}

export interface SafetyPlanInput {
  planNo?: string
  name: string
  planType?: string
  targetArea?: string
  checkItems?: string[]
  cycleDays?: number
  nextDate?: string | null
  ownerId?: number | null
  ownerName?: string
  deptId?: number | null
  deptName?: string
  status?: string
  remark?: string
}

export interface SafetyInspectionInput {
  recordNo?: string
  planId?: number | null
  planName?: string
  area?: string
  inspectDate?: string | null
  inspectorId?: number | null
  inspectorName?: string
  result?: string
  abnormalCount?: number
  /** 逐项结果（后端入参字段 items_json 的 camelCase 别名） */
  itemsJson?: SafetyInspectionItem[]
  status?: string
  summary?: string
  remark?: string
}

export interface SafetyHazardInput {
  hazardNo?: string
  inspectionId?: number | null
  recordNo?: string
  source?: string
  description: string
  level?: string
  status?: string
  responsibleId?: number | null
  responsibleName?: string
  deadline?: string | null
  foundAt?: string | null
  measure?: string
  remark?: string
}

/* ---------------- plans ---------------- */

export function listSafetyPlans(params: ListQuery) {
  return request<PageResult<SafetyPlan>>({
    url: '/safety/plans',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function safetyPlanCounts() {
  return request<Record<string, number>>({ url: '/safety/plans/counts', method: 'get' })
}

export function getSafetyPlan(id: number) {
  return request<SafetyPlan>({ url: `/safety/plans/${id}`, method: 'get' })
}

export function createSafetyPlan(data: SafetyPlanInput) {
  return request<SafetyPlan>({ url: '/safety/plans', method: 'post', data })
}

export function updateSafetyPlan(id: number, data: SafetyPlanInput) {
  return request<SafetyPlan>({ url: `/safety/plans/${id}`, method: 'put', data })
}

export function deleteSafetyPlan(id: number) {
  return request<{ id: number }>({ url: `/safety/plans/${id}`, method: 'delete' })
}

/* ---------------- inspections ---------------- */

export function listSafetyInspections(params: ListQuery) {
  return request<PageResult<SafetyInspection>>({
    url: '/safety/inspections',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function safetyInspectionCounts() {
  return request<Record<string, number>>({ url: '/safety/inspections/counts', method: 'get' })
}

export function getSafetyInspection(id: number) {
  return request<SafetyInspection>({ url: `/safety/inspections/${id}`, method: 'get' })
}

export function createSafetyInspection(data: SafetyInspectionInput) {
  return request<SafetyInspection>({ url: '/safety/inspections', method: 'post', data })
}

export function updateSafetyInspection(id: number, data: SafetyInspectionInput) {
  return request<SafetyInspection>({ url: `/safety/inspections/${id}`, method: 'put', data })
}

export function deleteSafetyInspection(id: number) {
  return request<{ id: number }>({ url: `/safety/inspections/${id}`, method: 'delete' })
}

export function submitSafetyInspection(id: number) {
  return request<{ record: SafetyInspection; hazards: number[] }>({
    url: `/safety/inspections/${id}/submit`,
    method: 'post',
  })
}

export function closeSafetyInspection(id: number) {
  return request<SafetyInspection>({ url: `/safety/inspections/${id}/close`, method: 'post' })
}

/* ---------------- hazards ---------------- */

export function listSafetyHazards(params: ListQuery) {
  return request<PageResult<SafetyHazard>>({
    url: '/safety/hazards',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function safetyHazardCounts() {
  return request<Record<string, number>>({ url: '/safety/hazards/counts', method: 'get' })
}

export function getSafetyHazard(id: number) {
  return request<SafetyHazard>({ url: `/safety/hazards/${id}`, method: 'get' })
}

export function createSafetyHazard(data: SafetyHazardInput) {
  return request<SafetyHazard>({ url: '/safety/hazards', method: 'post', data })
}

export function updateSafetyHazard(id: number, data: SafetyHazardInput) {
  return request<SafetyHazard>({ url: `/safety/hazards/${id}`, method: 'put', data })
}

export function rectifySafetyHazard(id: number, data: { measure: string }) {
  return request<SafetyHazard>({ url: `/safety/hazards/${id}/rectify`, method: 'post', data })
}

export function verifySafetyHazard(id: number, data: { verifyResult?: string; pass: boolean }) {
  return request<SafetyHazard>({ url: `/safety/hazards/${id}/verify`, method: 'post', data })
}

/* ---------------- board ---------------- */

export function getSafetyBoard() {
  return request<SafetyBoard>({ url: '/safety/board', method: 'get' })
}

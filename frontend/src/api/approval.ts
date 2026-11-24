import { download, request, toQuery } from './http'
import type {
  ApprovalCcItem,
  ApprovalInstanceDetail,
  ApprovalTask,
  ApprovalTimeline,
  FlowNode,
  FlowPreviewResult,
  ListQuery,
  PageResult,
  UserProfile,
} from './types'

export type ApprovalTab = 'todo' | 'done' | 'initiated'

export function listApprovalTasks(tab: ApprovalTab, params: ListQuery) {
  return request<PageResult<ApprovalTask>>({
    url: '/approval/tasks',
    method: 'get',
    params: toQuery({ ...params, tab } as Record<string, unknown>),
  })
}

export function approvalTaskCounts() {
  return request<Record<string, number>>({ url: '/approval/tasks/counts', method: 'get' })
}

export function exportApprovalTasks(tab: ApprovalTab, q?: string) {
  return download(
    { url: '/approval/tasks/export', method: 'get', params: { tab, q: q || undefined } },
    `approval_${tab}.xlsx`,
  )
}

export function getTimeline(bizType: string, bizId: number) {
  return request<ApprovalTimeline>({
    url: `/approval/instances/${bizType}/${bizId}/timeline`,
    method: 'get',
  })
}

export function getInstance(instanceId: number) {
  return request<ApprovalInstanceDetail>({
    url: `/approval/instances/${instanceId}`,
    method: 'get',
  })
}

export function approveTask(taskId: number, comment: string, commentSignature = '') {
  return request<void>({
    url: `/approval/tasks/${taskId}/approve`,
    method: 'post',
    data: { comment, commentSignature },
  })
}

export function rejectTask(taskId: number, comment: string, commentSignature = '') {
  return request<void>({
    url: `/approval/tasks/${taskId}/reject`,
    method: 'post',
    data: { comment, commentSignature },
  })
}

export function transferTask(taskId: number, toUserId: number, comment: string) {
  return request<void>({
    url: `/approval/tasks/${taskId}/transfer`,
    method: 'post',
    data: { toUserId, comment },
  })
}

export function addSignTask(taskId: number, approverId: number, comment: string) {
  return request<void>({
    url: `/approval/tasks/${taskId}/add-sign`,
    method: 'post',
    data: { approverId, comment },
  })
}

export function withdrawInstance(instanceId: number) {
  return request<void>({
    url: `/approval/instances/${instanceId}/withdraw`,
    method: 'post',
  })
}

export function getInstanceTimeline(instanceId: number) {
  return request<ApprovalTimeline>({
    url: `/approval/instances/${instanceId}/timeline`,
    method: 'get',
  })
}

export function listCcItems(params: ListQuery & { unread?: number }) {
  return request<PageResult<ApprovalCcItem>>({
    url: '/approval/cc',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function markCcRead(ccId: number) {
  return request<{ id: number }>({ url: `/approval/cc/${ccId}/read`, method: 'post' })
}

export function previewFlow(
  definitionCode: string,
  variables: Record<string, unknown>,
  nodes?: Partial<FlowNode>[],
) {
  return request<FlowPreviewResult>({
    url: '/approval/preview',
    method: 'post',
    data: { definitionCode, variables, nodes },
  })
}

/* ---------- AI 审批链建议（不落库，人工采纳才生效） ---------- */

export interface FlowSuggestNode {
  nodeName: string
  approverType: string
  approverValue: string
  approverName: string
  signMode: string
}

export interface FlowSuggestResult {
  nodes: FlowSuggestNode[]
  rationale: string
}

export function aiSuggestFlow(data: {
  bizType: string
  name?: string
  amount?: number | null
  category?: string
}) {
  return request<FlowSuggestResult>({ url: '/approval/definitions/ai-suggest', method: 'post', data })
}

/** lightweight user options for transfer / add-sign (fallback to admin users list) */
export type { UserProfile }

/* ---------- 流程能力清单（F5） ---------- */

/** 一类单据的流程能力：决定前端展示「提交审批」还是「人工直通」 */
export interface FlowCapability {
  bizType: string
  label: string
  managed: boolean
  /** 流程总开关：关闭时单据不进入审批中，直接落到通过态 */
  enabled: boolean
  definitionReady: boolean
  /** 允许触发提交的前置状态 */
  submitFrom: string[]
  statuses: {
    approving: string
    approved: string
    rejected: string
    withdrawn: string
  }
  submitPerm: string
}

export function getFlowCapabilities() {
  return request<{ items: FlowCapability[] }>({
    url: '/approval/flow-capabilities',
    method: 'get',
  })
}
